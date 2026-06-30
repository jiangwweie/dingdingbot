#!/usr/bin/env python3
"""Build Strategy Asset State from local Signal Observation evidence.

This command compresses existing local Signal Observation evidence into one current
Strategy Asset State row per group. It consumes lower-level opportunity,
no-action, and replay evidence, but it does not create live authority, mutate
strategy parameters, start runtime, call FinalGate, call the Operation Layer,
write to an exchange, or place orders.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    source_forbidden_effects,
)

DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.md"
)

ALLOWED_DECISIONS = {
    "go_live",
    "do_not_go_live",
    "keep_observing",
    "revise",
    "park",
    "kill",
    "promote",
    "block_for_safety",
}

ALLOWED_PROMOTION_SCOPES = {
    "intake_only",
    "trial_admission",
    "armed_observation",
    "tiny_live_ready_review",
    "l4_eligibility_review",
}


def build_strategygroup_strategy_asset_state(
    *,
    tier_policy: dict[str, Any],
    opportunity_review_work_loop_artifact: dict[str, Any] | None = None,
    signal_coverage_artifact: dict[str, Any] | None = None,
    post_revision_replay_artifact: dict[str, Any] | None = None,
    capture_gap_audit_artifact: dict[str, Any] | None = None,
    research_intake_review_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    opportunity_review_work_loop_artifact = _required_source_artifact(
        "opportunity_review_work_loop",
        opportunity_review_work_loop_artifact,
    )
    signal_coverage_artifact = _required_source_artifact(
        "signal_coverage",
        signal_coverage_artifact,
    )
    post_revision_replay_artifact = _optional_source_artifact(post_revision_replay_artifact)
    capture_gap_audit_artifact = _optional_source_artifact(capture_gap_audit_artifact)
    research_intake_review_artifact = _optional_source_artifact(research_intake_review_artifact)

    no_action_by_group = _high_priority_no_action_by_group(signal_coverage_artifact)
    no_action_attribution_queue = _no_action_attribution_queue(signal_coverage_artifact)
    role_review_rows = _role_review_rows(
        signal_coverage_artifact=signal_coverage_artifact,
        research_intake_review_artifact=research_intake_review_artifact,
    )
    quality_rows = _dict_rows(
        _as_dict(
            opportunity_review_work_loop_artifact.get("strategy_asset_recommendations")
        ).get("rows")
    )
    current_tier_by_group = _current_tier_by_group(tier_policy)
    asset_source_rows: list[dict[str, Any]] = []
    used_groups: set[str] = set()

    for row in quality_rows:
        group = str(row.get("strategy_group_id") or "unknown")
        asset_source_rows.append(
            _asset_row_from_quality(
                row=row,
                no_action_row=no_action_by_group.get(group),
                default_tier=current_tier_by_group.get(group, "unknown"),
            )
        )
        used_groups.add(group)

    for group, no_action_row in sorted(no_action_by_group.items()):
        if group in used_groups:
            continue
        asset_source_rows.append(
            _asset_row_from_no_action(
                group=group,
                row=no_action_row,
                tier=current_tier_by_group.get(group, "unknown"),
            )
        )

    capture_gap_rows = _capture_gap_asset_rows(
        capture_gap_audit_artifact,
        current_tier_by_group=current_tier_by_group,
    )
    if capture_gap_rows:
        by_group = {
            str(row.get("strategy_group_id") or "unknown"): row
            for row in asset_source_rows
        }
        for row in capture_gap_rows:
            by_group[str(row.get("strategy_group_id") or "unknown")] = row
        asset_source_rows = list(by_group.values())

    research_intake_rows = _research_intake_asset_rows(
        research_intake_review_artifact,
        current_tier_by_group=current_tier_by_group,
    )
    if research_intake_rows:
        by_group = {
            str(row.get("strategy_group_id") or "unknown"): row
            for row in asset_source_rows
        }
        for row in research_intake_rows:
            by_group[str(row.get("strategy_group_id") or "unknown")] = row
        asset_source_rows = list(by_group.values())

    completed_post_revision_groups = _completed_post_revision_groups(
        post_revision_replay_artifact
    )
    asset_source_rows = [
        _apply_post_revision_completion(row, completed_post_revision_groups)
        for row in asset_source_rows
    ]
    asset_source_rows = sorted(
        [_normalize_asset_row(row) for row in asset_source_rows],
        key=lambda row: str(row.get("strategy_group_id") or ""),
    )
    forbidden_effects = _forbidden_effects(
        ("opportunity_review_work_loop_artifact", opportunity_review_work_loop_artifact),
        ("signal_coverage_artifact", signal_coverage_artifact),
        ("post_revision_replay_artifact", post_revision_replay_artifact),
        ("capture_gap_audit_artifact", capture_gap_audit_artifact),
        ("research_intake_review_artifact", research_intake_review_artifact),
    )
    forbidden_effects.extend(_unscoped_promote_effects(asset_source_rows))
    forbidden_effects = sorted(set(forbidden_effects))
    current_decision_counts = Counter(
        str(row.get("asset_decision") or "unknown") for row in asset_source_rows
    )
    status = (
        "blocked_forbidden_effect"
        if forbidden_effects
        else "strategy_asset_state_ready"
        if asset_source_rows
        else "strategy_asset_state_empty"
    )
    default_next_step = _default_next_step(asset_source_rows, forbidden_effects)
    strategy_asset_state = _strategy_asset_state(
        asset_source_rows=asset_source_rows,
        current_decision_counts=current_decision_counts,
        no_action_attribution_queue=no_action_attribution_queue,
        capture_gap_rows=capture_gap_rows,
        research_intake_rows=research_intake_rows,
        role_review_rows=role_review_rows,
        default_next_step=default_next_step,
    )
    return {
        "schema": "brc.strategygroup_strategy_asset_state.v1",
        "scope": "strategygroup_strategy_asset_state",
        "status": status,
        "source_status": {
            "opportunity_review_work_loop": opportunity_review_work_loop_artifact.get("status"),
            "signal_coverage": signal_coverage_artifact.get("status"),
            "capture_gap_audit": capture_gap_audit_artifact.get("status"),
            "research_intake_review": research_intake_review_artifact.get("status"),
        },
        "interaction": non_executing_interaction("L0_local_strategy_asset_state"),
        "counts": {
            "strategy_group_count": len(asset_source_rows),
            "current_row_count": len(asset_source_rows),
            "high_priority_no_action_group_count": len(no_action_by_group),
            "high_priority_no_action_attribution_count": len(
                no_action_attribution_queue
            ),
            "role_review_row_count": len(role_review_rows),
            "capture_gap_audit_group_count": len(capture_gap_rows),
            "research_intake_group_count": len(research_intake_rows),
            "forbidden_effect_count": len(forbidden_effects),
            "l4_scope_change_recommended_count": 0,
        },
        "current_decision_counts": dict(sorted(current_decision_counts.items())),
        "required_asset_row_fields": [
            "strategy_group_id",
            "state_family",
            "stage",
            "current_tier",
            "current_decision",
            "promotion_scope",
            "promotion_target",
            "opportunity_type",
            "authority_boundary",
            "required_next_evidence",
            "next_checkpoint",
            "reason",
            "source_row_kind",
        ],
        "strategy_asset_state": strategy_asset_state,
        "observation_layer": _observation_layer_summary(signal_coverage_artifact),
        "role_review_rows": role_review_rows,
        "no_action_attribution_queue": no_action_attribution_queue,
        "capture_gap_audit": _capture_gap_audit_summary(capture_gap_audit_artifact),
        "research_intake_review": _research_intake_summary(
            research_intake_review_artifact
        ),
        "safety_invariants": {
            "local_strategy_asset_state_only": True,
            "input_is_not_execution_authority": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def _required_source_artifact(
    source_name: str,
    artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if artifact is None:
        raise ValueError(f"{source_name}_artifact is required")
    return artifact


def _optional_source_artifact(artifact: dict[str, Any] | None) -> dict[str, Any]:
    return artifact or {}


def render_owner_progress_markdown(artifact: dict[str, Any]) -> str:
    counts = _as_dict(artifact.get("counts"))
    lines = [
        "# Strategy Asset State",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Current rows: `{counts.get('current_row_count', 0)}`",
        f"- High-priority no-action groups: `{counts.get('high_priority_no_action_group_count', 0)}`",
        f"- No-action attribution rows: `{counts.get('high_priority_no_action_attribution_count', 0)}`",
        f"- Role review rows: `{counts.get('role_review_row_count', 0)}`",
        f"- Research intake groups: `{counts.get('research_intake_group_count', 0)}`",
        "- Single main product: `true`",
        "- L4 scope change: `false`",
        "",
        "## Current Decisions",
        "",
        _asset_state_table(
            _dict_rows(_as_dict(artifact.get("strategy_asset_state")).get("asset_rows"))
        ),
        "",
        "## Observation Layer",
        "",
        _observation_layer_table(_as_dict(artifact.get("observation_layer"))),
        "",
        "## Role Review",
        "",
        _role_review_table(_dict_rows(artifact.get("role_review_rows"))),
        "",
        "## No-Action Attribution",
        "",
        _no_action_attribution_table(
            _dict_rows(artifact.get("no_action_attribution_queue"))
        ),
        "",
        "## Next",
        "",
        f"- `{_as_dict(artifact.get('strategy_asset_state')).get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _asset_row_from_quality(
    *,
    row: dict[str, Any],
    no_action_row: dict[str, Any] | None,
    default_tier: str,
) -> dict[str, Any]:
    quality_decision = str(row.get("strategy_asset_recommendation") or "")
    decision = _decision_from_quality(quality_decision)
    evidence = _as_dict(row.get("evidence"))
    no_action_reason = _no_action_reason(no_action_row)
    replay_part = "replay_samples:{} revise_samples:{}".format(
        _int(evidence.get("replay_sample_count")),
        _int(evidence.get("revise_sample_count")),
    )
    base_reason = str(row.get("reason") or quality_decision or "decision_loop_evidence")
    reason = _join_reason_parts(
        [
            base_reason,
            _quality_decision_source_reason(quality_decision, decision),
            no_action_reason,
            replay_part,
        ]
    )
    next_checkpoint = str(row.get("next_stage") or "continue_local_review")
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("current_tier") or default_tier or "unknown"),
        "opportunity_type": (
            "no_action"
            if no_action_row and _int(evidence.get("would_enter_sample_count")) <= 0
            else "would_enter"
        ),
        "asset_decision": decision,
        "promotion_scope": _promotion_scope_for_quality_decision(decision, quality_decision),
        "promotion_target": _promotion_target_for_quality_decision(decision, quality_decision),
        "reason": reason,
        "required_next_evidence": _required_next_evidence(
            decision=decision,
            quality_row=row,
            no_action_row=no_action_row,
        ),
        "authority_boundary": _authority_boundary(row),
        "next_checkpoint": next_checkpoint,
    }


def _asset_row_from_no_action(
    *,
    group: str,
    row: dict[str, Any],
    tier: str,
) -> dict[str, Any]:
    decision = _decision_from_no_action(row)
    no_action_reason = _no_action_reason(row)
    return {
        "strategy_group_id": group,
        "tier": tier,
        "opportunity_type": "no_action",
        "asset_decision": decision,
        "promotion_scope": "not_applicable",
        "promotion_target": "not_applicable",
        "reason": _join_reason_parts(
            [
                no_action_reason or "high_priority_no_action_requires_review",
                _no_action_source_reason(row, decision),
            ]
        ),
        "required_next_evidence": _required_next_evidence_from_no_action(row),
        "authority_boundary": "local_decision_support_only; no_official_live_order_authority; no_finalgate_no_operation_layer_no_exchange_write",
        "next_checkpoint": _next_checkpoint_from_no_action(row),
    }


def _decision_from_quality(quality_decision: str) -> str:
    if quality_decision in {
        "revise_before_l2",
        "keep_l2_shadow_and_revise_fact_classifier_inputs",
    }:
        return "revise"
    if quality_decision.startswith("keep_observing"):
        return "keep_observing"
    if quality_decision == "prepare_l2_intake_review_without_promotion":
        return "promote"
    if quality_decision == "park_until_new_edge":
        return "park"
    if quality_decision == "needs_replay_before_asset_recommendation":
        return "keep_observing"
    return "unknown"


def _quality_decision_source_reason(quality_decision: str, decision: str) -> str:
    if decision != "unknown":
        return ""
    if not quality_decision:
        return "source_strategy_asset_recommendation:missing_strategy_asset_recommendation"
    return f"source_strategy_asset_recommendation:unsupported:{quality_decision}"


def _decision_from_no_action(row: dict[str, Any]) -> str:
    action = str(row.get("policy_recommended_action") or "")
    readiness = str(row.get("policy_l2_readiness") or "")
    reasons = " ".join(str(item) for item in row.get("reason_codes") or [])
    if "park" in action or "park" in readiness:
        return "park"
    if any(token in action + " " + readiness + " " + reasons for token in ("rewrite", "redesign", "classifier", "facts")):
        return "revise"
    if not action and not readiness and not reasons:
        return "unknown"
    return "keep_observing"


def _no_action_source_reason(row: dict[str, Any], decision: str) -> str:
    if decision != "unknown":
        return ""
    if (
        not row.get("policy_recommended_action")
        and not row.get("policy_l2_readiness")
        and not row.get("reason_codes")
    ):
        return "source_no_action_policy:missing_policy_recommended_action_readiness_and_reason_codes"
    return "source_no_action_policy:unsupported_no_action_judgment"


def _promotion_scope_for_quality_decision(
    decision: str,
    quality_decision: str,
) -> str:
    if decision != "promote":
        return "not_applicable"
    if quality_decision == "prepare_l2_intake_review_without_promotion":
        return "armed_observation"
    return "trial_admission"


def _promotion_target_for_quality_decision(
    decision: str,
    quality_decision: str,
) -> str:
    if decision != "promote":
        return "not_applicable"
    if quality_decision == "prepare_l2_intake_review_without_promotion":
        return "shadow_or_armed_observation_review"
    return "strategygroup_trial_admission_review"


def _required_next_evidence(
    *,
    decision: str,
    quality_row: dict[str, Any],
    no_action_row: dict[str, Any] | None,
) -> str:
    revision = _as_dict(quality_row.get("revision_completion"))
    execution = _as_dict(quality_row.get("revision_execution"))
    evidence = _as_dict(quality_row.get("evidence"))
    if decision == "revise":
        if revision.get("status") not in {"no_revision_required", "local_revision_completion_ready"}:
            blockers = revision.get("completion_blockers") or []
            return "complete_revision_specs:{}".format(",".join(str(item) for item in blockers) or "pending")
        if execution.get("status") not in {"no_revision_execution_required", "local_revision_execution_complete"}:
            blockers = execution.get("execution_blockers") or []
            return "execute_local_revision_tasks:{}".format(",".join(str(item) for item in blockers) or "pending")
        return str(quality_row.get("next_stage") or "post_revision_replay_review")
    if decision == "promote":
        return "tier_review_and_owner_lane_boundary_before_any_policy_change"
    if decision == "park":
        return "material_new_edge_evidence"
    if no_action_row:
        return _required_next_evidence_from_no_action(no_action_row)
    if _int(evidence.get("fact_source_pending_item_count")):
        return "attach_required_fact_sources"
    if _int(evidence.get("replay_sample_count")) <= 0:
        return "add_non_executing_replay_coverage"
    return str(quality_row.get("next_stage") or "continue_observation")


def _required_next_evidence_from_no_action(row: dict[str, Any]) -> str:
    readiness = str(row.get("policy_l2_readiness") or "")
    action = str(row.get("policy_recommended_action") or "")
    if "classifier" in readiness or "classifier" in action:
        return "classifier_disable_or_entry_state_review"
    if "fact" in readiness or "fact" in action:
        return "required_fact_source_mapping"
    if "rewrite" in readiness or "rewrite" in action:
        return "side_specific_classifier_rewrite_review"
    if "l2_shadow" in readiness or "l2_shadow" in action:
        return "l2_shadow_quality_observation"
    return "next_high_priority_replay_or_market_observation"


def _next_checkpoint_from_no_action(row: dict[str, Any]) -> str:
    action = str(row.get("policy_recommended_action") or "")
    if action:
        return action
    return _required_next_evidence_from_no_action(row)


def _authority_boundary(row: dict[str, Any]) -> str:
    if (
        row.get("candidate_or_finalgate_authority") is False
        and row.get("not_l4_scope_change") is True
    ):
        return "local_decision_support_only; no_official_live_order_authority; no_l4_scope_change; no_finalgate_no_operation_layer_no_exchange_write"
    return "local_decision_support_only; no_official_live_order_authority; no_finalgate_no_operation_layer_no_exchange_write"


def _normalize_asset_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_decision = str(row.get("asset_decision") or "unknown")
    normalized = {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("tier") or "unknown"),
        "opportunity_type": str(row.get("opportunity_type") or "no_action"),
        "asset_decision": raw_decision,
        "promotion_scope": str(row.get("promotion_scope") or "not_applicable"),
        "promotion_target": str(row.get("promotion_target") or "not_applicable"),
        "reason": str(row.get("reason") or "decision_required"),
        "required_next_evidence": str(row.get("required_next_evidence") or "none"),
        "authority_boundary": str(row.get("authority_boundary") or ""),
        "next_checkpoint": str(row.get("next_checkpoint") or "continue_local_review"),
    }
    if normalized["asset_decision"] not in ALLOWED_DECISIONS:
        normalized["asset_decision"] = "unknown"
        normalized["promotion_scope"] = "not_applicable"
        normalized["promotion_target"] = "not_applicable"
        normalized["reason"] = _join_reason_parts(
            [
                str(normalized.get("reason") or ""),
                f"invalid_or_missing_decision:{raw_decision}",
            ]
        )
    return normalized


def _strategy_asset_state(
    *,
    asset_source_rows: list[dict[str, Any]],
    current_decision_counts: Counter[str],
    no_action_attribution_queue: list[dict[str, Any]],
    capture_gap_rows: list[dict[str, Any]],
    research_intake_rows: list[dict[str, Any]],
    role_review_rows: list[dict[str, Any]],
    default_next_step: str,
) -> dict[str, Any]:
    return {
        "state_family": "Strategy Asset State",
        "status": "ready" if asset_source_rows else "empty",
        "primary_judgment_source": True,
        "source_role": "strategy_decision_compatibility_provenance",
        "tradeability_decision_source": False,
        "asset_count": len(asset_source_rows),
        "current_decision_counts": dict(sorted(current_decision_counts.items())),
        "single_main_product": True,
        "one_current_row_per_strategy_group": _one_row_per_group(asset_source_rows),
        "raw_replay_samples_duplicated": False,
        "no_action_attribution_is_field_input_only": True,
        "capture_gap_audit_is_decision_support_only": bool(capture_gap_rows),
        "research_intake_review_is_decision_support_only": bool(research_intake_rows),
        "role_review_is_decision_support_only": bool(role_review_rows),
        "no_action_attribution_queue_recorded": bool(no_action_attribution_queue),
        "real_order_scope_change_recommended": False,
        "l4_promotion_recommended": False,
        "default_next_step": default_next_step,
        "asset_rows": [_strategy_asset_state_row(row) for row in asset_source_rows],
        "provenance_sections": [
            "capture_gap_audit",
            "research_intake_review",
        ],
    }


def _strategy_asset_state_row(row: dict[str, Any]) -> dict[str, Any]:
    decision = str(row.get("asset_decision") or "unknown")
    stage = _strategy_asset_stage_from_decision(row)
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "state_family": "Strategy Asset State",
        "stage": stage,
        "current_tier": str(row.get("tier") or "unknown"),
        "current_decision": decision,
        "promotion_scope": str(row.get("promotion_scope") or "not_applicable"),
        "promotion_target": str(row.get("promotion_target") or "not_applicable"),
        "opportunity_type": str(row.get("opportunity_type") or "unknown"),
        "authority_boundary": str(row.get("authority_boundary") or ""),
        "required_next_evidence": str(row.get("required_next_evidence") or ""),
        "next_checkpoint": str(row.get("next_checkpoint") or ""),
        "reason": str(row.get("reason") or ""),
        "source_row_kind": "strategy_asset_state_row",
    }


def _strategy_asset_stage_from_decision(row: dict[str, Any]) -> str:
    decision = str(row.get("asset_decision") or "")
    promotion_scope = str(row.get("promotion_scope") or "")
    if decision == "promote" and promotion_scope in {"trial_admission", "intake_only"}:
        return "trial_asset_candidate"
    if decision == "promote" and promotion_scope in {"armed_observation", "tiny_live_ready_review"}:
        return "armed_observation_review"
    if decision == "revise":
        return "revision_required"
    if decision == "park":
        return "parked"
    if decision == "kill":
        return "killed"
    if decision == "block_for_safety":
        return "blocked_for_safety"
    if decision == "go_live":
        return "go_live_review"
    if decision == "do_not_go_live":
        return "do_not_go_live"
    return "armed_observation_or_keep_observing"


def _completed_post_revision_groups(artifact: dict[str, Any]) -> dict[str, int]:
    if artifact.get("status") != "passed":
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in _dict_rows(artifact.get("review_rows")):
        group = str(row.get("strategy_group_id") or "")
        if not group:
            continue
        grouped.setdefault(group, []).append(row)
    return {
        group: len(rows)
        for group, rows in grouped.items()
        if rows and all(row.get("passed") is True for row in rows)
    }


def _apply_post_revision_completion(
    row: dict[str, Any],
    completed_groups: dict[str, int],
) -> dict[str, Any]:
    group = str(row.get("strategy_group_id") or "")
    if str(row.get("asset_decision") or "") != "revise" or group not in completed_groups:
        return row
    if "capture_gap_audit:" in str(row.get("reason") or ""):
        return row
    completed = dict(row)
    case_count = completed_groups[group]
    completed["asset_decision"] = "keep_observing"
    completed["reason"] = _join_reason_parts(
        [
            str(row.get("reason") or ""),
            f"post_revision_replay_passed:{case_count}_cases",
        ]
    )
    completed["required_next_evidence"] = "tier_review_after_post_revision_quality"
    completed["next_checkpoint"] = (
        "run_post_revision_stage_review_before_any_l2_or_l4_scope_change"
    )
    return completed


def _capture_gap_asset_rows(
    artifact: dict[str, Any],
    *,
    current_tier_by_group: dict[str, str],
) -> list[dict[str, Any]]:
    if artifact.get("schema") != "brc.strategy_capture_gap_audit.v3":
        return []
    if artifact.get("status") != "strategy_capture_gap_audit_ready":
        return []

    closure_rows = _capture_gap_closure_rows(artifact)
    closure_by_group = {
        str(row.get("strategy_group_id") or "unknown"): row
        for row in closure_rows
    }
    rows: list[dict[str, Any]] = []
    for recommendation in _dict_rows(artifact.get("observation_recommendations")):
        group = str(recommendation.get("strategy_group_id") or "unknown")
        closure = closure_by_group.get(group, {})
        mapped_decision = _decision_from_capture_gap(recommendation)
        rows.append(
            {
                "strategy_group_id": group,
                "tier": current_tier_by_group.get(group, "unknown"),
                "opportunity_type": (
                    "would_enter"
                    if _int(closure.get("would_enter_count")) > 0
                    else "no_action"
                ),
                "asset_decision": mapped_decision,
                "promotion_scope": _promotion_scope_from_capture_gap(
                    recommendation
                ),
                "promotion_target": _promotion_target_from_capture_gap(
                    recommendation
                ),
                "reason": _capture_gap_reason(recommendation, closure),
                "required_next_evidence": _capture_gap_required_next_evidence(
                    recommendation
                ),
                "authority_boundary": (
                    "local_decision_support_only; source=capture_gap_audit; "
                    f"promotion_scope={_promotion_scope_from_capture_gap(recommendation)}; "
                    "no_official_live_order_authority; no_tier_policy_change; "
                    "no_finalgate_no_operation_layer_no_exchange_write"
                ),
                "next_checkpoint": str(
                    recommendation.get("next_checkpoint") or "continue_local_review"
                ),
            }
        )
    return rows


def _capture_gap_closure_rows(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    closure = _as_dict(artifact.get("priority_line_closure"))
    rows: list[dict[str, Any]] = []
    for key in (
        "phase2_priority_strategy_lines",
        "phase3_registry_identity_review",
        "phase4_visibility_review",
    ):
        rows.extend(_dict_rows(closure.get(key)))
    return rows


def _decision_from_capture_gap(row: dict[str, Any]) -> str:
    recommendation = str(row.get("observation_recommendation") or "")
    if recommendation == "promote_review":
        return "promote"
    if recommendation in {"revise", "identity_review"}:
        return "revise"
    if recommendation == "park":
        return "park"
    if recommendation in {"coverage_visibility_review", "keep_observing"}:
        return "keep_observing"
    return "unknown"


def _promotion_scope_from_capture_gap(row: dict[str, Any]) -> str:
    recommendation = str(row.get("observation_recommendation") or "")
    if recommendation == "promote_review":
        return "trial_admission"
    return "not_applicable"


def _promotion_target_from_capture_gap(row: dict[str, Any]) -> str:
    recommendation = str(row.get("observation_recommendation") or "")
    if recommendation == "promote_review":
        return "promotion_evidence_review_only"
    return "not_applicable"


def _capture_gap_reason(
    recommendation: dict[str, Any],
    closure: dict[str, Any],
) -> str:
    metrics = "would_enter:{} high_priority_no_action:{} would_enter_forward_positive:{} missed_no_action_forward_positive:{}".format(
        _int(closure.get("would_enter_count")),
        _int(closure.get("high_priority_no_action_count")),
        _int(closure.get("would_enter_forward_positive_count")),
        _int(closure.get("missed_no_action_forward_positive_count")),
    )
    return _join_reason_parts(
        [
            "capture_gap_audit:{}".format(
                recommendation.get("reason") or "strategy_capture_gap_review"
            ),
            metrics,
            "source_recommendation:{}".format(
                recommendation.get("observation_recommendation")
                or "missing_observation_recommendation"
            ),
        ]
    )


def _capture_gap_required_next_evidence(row: dict[str, Any]) -> str:
    recommendation = str(row.get("observation_recommendation") or "")
    checkpoint = str(row.get("next_checkpoint") or "continue_local_review")
    if recommendation == "identity_review":
        return f"registry_identity_classification:{checkpoint}"
    if recommendation == "coverage_visibility_review":
        return f"no_action_visibility_and_routing_summary:{checkpoint}"
    if recommendation == "promote_review":
        return f"promotion_evidence_review_only:{checkpoint}"
    if recommendation == "revise":
        return f"classifier_fact_source_revision_review:{checkpoint}"
    if recommendation == "park":
        return "material_new_edge_evidence_before_reactivation"
    return checkpoint


def _capture_gap_audit_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("schema") != "brc.strategy_capture_gap_audit.v3":
        return {
            "status": "not_loaded",
            "integrated": False,
            "owner_policy_confirmation_required_now": False,
            "live_permission_change_recommended_now": False,
        }
    visibility = _as_dict(artifact.get("owner_visibility_state"))
    observation = _as_dict(artifact.get("system_observation_summary"))
    return {
        "status": artifact.get("status"),
        "integrated": artifact.get("status") == "strategy_capture_gap_audit_ready",
        "schema": artifact.get("schema"),
        "would_enter_count": observation.get("would_enter_count", 0),
        "high_priority_no_action_count": observation.get(
            "high_priority_no_action_count",
            0,
        ),
        "owner_visibility_state": visibility,
        "owner_policy_confirmation_required_now": False,
        "live_permission_change_recommended_now": False,
        "authority_boundary": (
            "capture_gap_audit_is_review_input_only; no_tier_policy_change; "
            "no_live_profile_change; no_official_live_order_authority"
        ),
    }


def _research_intake_asset_rows(
    artifact: dict[str, Any],
    *,
    current_tier_by_group: dict[str, str],
) -> list[dict[str, Any]]:
    if artifact.get("schema") != "brc.strategygroup_research_intake_review.v1":
        return []
    if artifact.get("status") != "research_intake_review_ready":
        return []
    rows = []
    for row in _dict_rows(artifact.get("strategy_decision_provenance_rows")):
        group = str(row.get("strategy_group_id") or "unknown")
        decision = str(row.get("current_decision") or "unknown")
        promotion_scope = str(row.get("promotion_scope") or "not_applicable")
        promotion_target = str(row.get("promotion_target") or "not_applicable")
        rows.append(
            {
                "strategy_group_id": group,
                "tier": current_tier_by_group.get(group, str(row.get("tier") or "unknown")),
                "opportunity_type": str(row.get("opportunity_type") or "research_intake"),
                "asset_decision": decision,
                "promotion_scope": promotion_scope,
                "promotion_target": promotion_target,
                "reason": _join_reason_parts(
                    [
                        "research_intake_review:{}".format(
                            row.get("reason") or "main_control_intake_review"
                        ),
                        f"promotion_scope:{promotion_scope}",
                        "source=final_main_control_adapter",
                    ]
                ),
                "required_next_evidence": str(
                    row.get("required_next_evidence")
                    or "main_control_research_intake_review"
                ),
                "authority_boundary": (
                    "local_decision_support_only; source=research_intake_review; "
                    f"promotion_scope={promotion_scope}; promotion_target={promotion_target}; "
                    "non_executing_trial_readiness=false; runtime_safety_gate_required; "
                    "no_official_live_order_authority; no_tier_policy_change; "
                    "no_live_profile_change; no_finalgate_no_operation_layer_no_exchange_write"
                ),
                "next_checkpoint": str(
                    row.get("next_checkpoint")
                    or "continue_research_intake_review"
                ),
            }
        )
    return rows


def _research_intake_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    if artifact.get("schema") != "brc.strategygroup_research_intake_review.v1":
        return {
            "status": "not_loaded",
            "integrated": False,
            "owner_policy_confirmation_required_now": False,
            "live_permission_change_recommended_now": False,
        }
    summary = _as_dict(artifact.get("summary"))
    return {
        "status": artifact.get("status"),
        "integrated": artifact.get("status") == "research_intake_review_ready",
        "schema": artifact.get("schema"),
        "candidate_count": summary.get("candidate_count", 0),
        "paper_observation_admission_candidate_count": summary.get(
            "paper_observation_admission_candidate_count",
            0,
        ),
        "role_only_intake_candidate_count": summary.get(
            "role_only_intake_candidate_count",
            0,
        ),
        "scoped_promote_count": sum(
            1
            for row in _dict_rows(artifact.get("strategy_decision_provenance_rows"))
            if row.get("current_decision") == "promote"
            and row.get("promotion_scope") in ALLOWED_PROMOTION_SCOPES
        ),
        "owner_policy_confirmation_required_now": False,
        "live_permission_change_recommended_now": False,
        "authority_boundary": (
            "research_intake_review_is_review_input_only; "
            "non_executing_trial_readiness=false; runtime_safety_gate_required; no_tier_policy_change; "
            "no_live_profile_change; no_official_live_order_authority"
        ),
    }


def _observation_layer_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    broader = _as_dict(artifact.get("broader_observation"))
    checks = _as_dict(artifact.get("checks"))
    would_enter = _dict_rows(broader.get("would_enter_signals"))
    high_priority_no_action = _dict_rows(
        broader.get("high_priority_no_action_signals")
    )
    latest = would_enter[0] if would_enter else {}
    return {
        "p0_state": "waiting_for_executable_fresh_signal",
        "signal_observation_state": (
            "observation_active"
            if would_enter or high_priority_no_action
            else "quiet"
        ),
        "mainline_ready_signal_count": _int(
            checks.get("mainline_ready_signal_count")
        ),
        "broader_would_enter_count": len(would_enter),
        "broader_actionable_would_enter_count": _int(
            checks.get("broader_actionable_would_enter_signal_count")
        ),
        "high_priority_no_action_count": len(high_priority_no_action),
        "latest_observe_only_would_enter": {
            "strategy_group_id": str(latest.get("strategy_group_id") or ""),
            "symbol": str(latest.get("symbol") or ""),
            "side": str(latest.get("side") or ""),
            "confidence": str(latest.get("confidence") or ""),
            "not_live_signal": True,
        }
        if latest
        else {},
    }


def _role_review_rows(
    *,
    signal_coverage_artifact: dict[str, Any],
    research_intake_review_artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    intake_groups = {
        str(row.get("strategy_group_id") or "")
        for row in _dict_rows(research_intake_review_artifact.get("candidate_rows"))
    }
    intake_groups.update(
        str(row.get("strategy_group_id") or "")
        for row in _dict_rows(
            research_intake_review_artifact.get("strategy_decision_provenance_rows")
        )
    )
    rows: list[dict[str, Any]] = []
    for signal in _dict_rows(
        _as_dict(signal_coverage_artifact.get("broader_observation")).get(
            "would_enter_signals"
        )
    ):
        group = str(signal.get("strategy_group_id") or "")
        if group != "RBR-001":
            continue
        linked = "RBR2-001" if "RBR2-001" in intake_groups else "RBR2-001"
        rows.append(
            {
                "source_observation_strategy_group_id": group,
                "source_observation_symbol": str(signal.get("symbol") or ""),
                "source_observation_side": str(signal.get("side") or ""),
                "source_observation_type": "observe_only_would_enter",
                "linked_intake_strategy_group_id": linked,
                "role_review_outcome": "review_range_detector_role_not_live_candidate",
                "required_next_evidence": (
                    "compare_rbr001_observe_only_signal_with_rbr2_range_detector_role"
                ),
                "next_checkpoint": (
                    "RBR_RBR2_role_review_range_detector_classifier_merge_note"
                ),
                "authority_boundary": (
                    "role_review_only; runtime_safety_gate_required; "
                    "no_official_live_order_authority; no_finalgate_no_operation_layer"
                ),
                "reason_codes": [
                    str(item) for item in signal.get("reason_codes") or []
                ],
            }
        )
    return rows


def _no_action_attribution_queue(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _dict_rows(
        _as_dict(artifact.get("broader_observation")).get(
            "high_priority_no_action_signals"
        )
    ):
        group = str(row.get("strategy_group_id") or "unknown")
        rows.append(
            {
                "strategy_group_id": group,
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "confidence": str(row.get("confidence") or ""),
                "attribution_class": _no_action_attribution_class(row),
                "reason_codes": [
                    str(item) for item in row.get("reason_codes") or []
                ],
                "required_next_evidence": _no_action_required_next_evidence(row),
                "next_checkpoint": _no_action_next_checkpoint(row),
                "authority_boundary": (
                    "no_action_attribution_only; runtime_safety_gate_required; "
                    "no_official_live_order_authority"
                ),
            }
        )
    return rows


def _no_action_attribution_class(row: dict[str, Any]) -> str:
    text = " ".join(
        [
            str(row.get("policy_l2_readiness") or ""),
            str(row.get("policy_recommended_action") or ""),
            " ".join(str(item) for item in row.get("reason_codes") or []),
        ]
    )
    if "squeeze" in text or "rally" in text:
        return "market_structure_or_path_risk"
    if "rewrite" in text:
        return "side_specific_rewrite"
    if "classifier" in text or "volume" in text:
        return "classifier_or_threshold"
    if "fact" in text or "stale" in text:
        return "fact_source_or_freshness"
    return "review_required"


def _no_action_required_next_evidence(row: dict[str, Any]) -> str:
    klass = _no_action_attribution_class(row)
    if klass == "fact_source_or_freshness":
        return "freshness_and_fact_source_mapping"
    if klass == "side_specific_rewrite":
        return "side_specific_rewrite_review"
    if klass == "classifier_or_threshold":
        return "classifier_threshold_review"
    if klass == "market_structure_or_path_risk":
        return "market_structure_and_path_risk_review"
    return "next_high_priority_replay_or_market_observation"


def _no_action_next_checkpoint(row: dict[str, Any]) -> str:
    group = str(row.get("strategy_group_id") or "unknown")
    return f"{group}_{_no_action_required_next_evidence(row)}"


def _high_priority_no_action_by_group(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _dict_rows(
        _as_dict(artifact.get("broader_observation")).get("high_priority_no_action_signals")
    )
    result: dict[str, dict[str, Any]] = {}
    priority_rank = {"P0_5": 0, "P1": 1, "P2": 2}
    for row in rows:
        if str(row.get("signal_type") or "") != "no_action":
            continue
        group = str(row.get("strategy_group_id") or "unknown")
        current = result.get(group)
        if current is None or priority_rank.get(str(row.get("coverage_review_priority")), 9) < priority_rank.get(str(current.get("coverage_review_priority")), 9):
            result[group] = row
    return result


def _no_action_reason(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    summary = str(row.get("human_summary") or "").strip()
    codes = ",".join(str(item) for item in row.get("reason_codes") or [])
    if summary and codes:
        return f"no_action:{summary} codes:{codes}"
    return summary or (f"no_action_codes:{codes}" if codes else "")


def _current_tier_by_group(policy: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for group, data in _as_dict(policy.get("current_strategy_groups")).items():
        output[str(group)] = str(_as_dict(data).get("tier") or "unknown")
    known_new = _as_dict(_as_dict(policy.get("new_strategy_group_defaults")).get("known_new_groups"))
    for base, tier in known_new.items():
        output.setdefault(f"{base}-001", str(tier or "unknown"))
    return output


def _default_next_step(rows: list[dict[str, Any]], forbidden_effects: list[str]) -> str:
    if forbidden_effects:
        return "stop_and_repair_forbidden_source_effects"
    if any(
        str(row.get("next_checkpoint") or "").startswith("run_post_revision_stage_review")
        for row in rows
    ):
        return "run_post_revision_stage_review_before_any_tier_policy_change"
    if any(row.get("asset_decision") == "revise" for row in rows):
        return "execute_or_verify_top_revision_checkpoints_without_live_authority_expansion"
    if any(row.get("asset_decision") == "promote" for row in rows):
        return "run_strategy_asset_tier_review_before_policy_change"
    if any(row.get("asset_decision") == "park" for row in rows):
        return "keep_parked_groups_out_of_signal_observation_active_work"
    if rows:
        return "continue_waiting_for_market_and_refresh_strategy_asset_state"
    return "continue_signal_coverage_monitoring"


def _forbidden_effects(*source_artifacts: tuple[str, dict[str, Any]]) -> list[str]:
    return source_forbidden_effects(
        source_artifacts,
        true_keys=(
            "server_files_mutated",
            "runtime_started",
            "strategy_parameters_changed",
            "tier_policy_changed",
            "shadow_candidate_created",
            "execution_intent_created",
            "final_gate_called",
            "calls_finalgate",
            "operation_layer_called",
            "calls_operation_layer",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "calls_exchange_write",
            "places_order",
            "withdrawal_or_transfer_created",
        ),
        source_names=("safety_invariants", "interaction"),
        true_effect_source_label=None,
        source_effect_includes_source_name=True,
    )


def _unscoped_promote_effects(rows: list[dict[str, Any]]) -> list[str]:
    effects: list[str] = []
    for row in rows:
        if row.get("asset_decision") != "promote":
            continue
        scope = str(row.get("promotion_scope") or "not_applicable")
        if scope not in ALLOWED_PROMOTION_SCOPES:
            effects.append(
                "strategy_asset_state.{}.unscoped_promote:{}".format(
                    row.get("strategy_group_id") or "unknown",
                    scope,
                )
            )
    return effects


def _one_row_per_group(rows: list[dict[str, Any]]) -> bool:
    groups = [str(row.get("strategy_group_id") or "unknown") for row in rows]
    return len(groups) == len(set(groups))


def _asset_state_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Tier | Type | Decision | Scope | Next |\n| --- | --- | --- | --- | --- | --- |\n| none | - | - | - | - | - |"
    output = [
        "| StrategyGroup | Tier | Type | Decision | Scope | Next |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                row.get("opportunity_type"),
                row.get("current_decision"),
                row.get("promotion_scope"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _observation_layer_table(summary: dict[str, Any]) -> str:
    latest = _as_dict(summary.get("latest_observe_only_would_enter"))
    return "\n".join(
        [
            "| Layer | Value |",
            "| --- | --- |",
            f"| P0 | `{summary.get('p0_state', 'unknown')}` |",
            f"| Signal Observation | `{summary.get('signal_observation_state', 'unknown')}` |",
            f"| Broader would-enter | `{summary.get('broader_would_enter_count', 0)}` |",
            f"| High-priority no-action | `{summary.get('high_priority_no_action_count', 0)}` |",
            "| Latest observe-only would-enter | `{}` / `{}` / `{}` |".format(
                latest.get("strategy_group_id") or "none",
                latest.get("symbol") or "-",
                latest.get("side") or "-",
            ),
        ]
    )


def _role_review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Source | Linked Intake | Outcome | Next |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| Source | Linked Intake | Outcome | Next |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("source_observation_strategy_group_id"),
                row.get("linked_intake_strategy_group_id"),
                row.get("role_review_outcome"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _no_action_attribution_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Symbol | Class | Next |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| StrategyGroup | Symbol | Class | Next |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("symbol"),
                row.get("attribution_class"),
                row.get("next_checkpoint"),
            )
        )
    return "\n".join(output)


def _join_reason_parts(parts: list[str]) -> str:
    return "; ".join(part for part in (p.strip() for p in parts) if part)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _load_optional_json_object(path: Path) -> dict[str, Any] | None:
    return _load_json_object(path) if path.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opportunity-review-work-loop-json", required=True)
    parser.add_argument("--signal-coverage-json", required=True)
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--post-revision-replay-review-json")
    parser.add_argument("--capture-gap-audit-json")
    parser.add_argument("--research-intake-review-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    artifact = build_strategygroup_strategy_asset_state(
        opportunity_review_work_loop_artifact=_load_json_object(
            Path(args.opportunity_review_work_loop_json).expanduser()
        ),
        signal_coverage_artifact=_load_json_object(
            Path(args.signal_coverage_json).expanduser()
        ),
        tier_policy=_load_json_object(Path(args.tier_policy_json).expanduser()),
        post_revision_replay_artifact=_load_optional_json_object(
            Path(args.post_revision_replay_review_json).expanduser()
        )
        if args.post_revision_replay_review_json
        else None,
        capture_gap_audit_artifact=_load_optional_json_object(
            Path(args.capture_gap_audit_json).expanduser()
        )
        if args.capture_gap_audit_json
        else None,
        research_intake_review_artifact=_load_optional_json_object(
            Path(args.research_intake_review_json).expanduser()
        )
        if args.research_intake_review_json
        else None,
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(render_owner_progress_markdown(artifact), encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
