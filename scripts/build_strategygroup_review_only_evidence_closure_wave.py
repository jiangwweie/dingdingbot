#!/usr/bin/env python3
"""Build the review-only StrategyGroup evidence closure wave.

This command consumes the confirmed review-only policy artifact plus current local
StrategyGroup evidence and projects three phases:

1. Owner perception projection.
2. Review-only evidence closure artifacts.
3. Next Owner policy package.

It is local review support only. It never mutates registry authority, tier
policy, live profile, FinalGate, Operation Layer, exchange state, or orders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    review_only_forbidden_effects,
    review_only_interaction,
    review_only_legacy_authority_mirror_true_keys,
    review_only_safety_invariants,
)

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-evidence-closure-wave.md"
)
DEFAULT_OUTPUT_OWNER_PROGRESS = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-review-only-owner-progress.md"
)

FORBIDDEN_EFFECTS = review_only_forbidden_effects()
LEGACY_AUTHORITY_MIRROR_TRUE_KEYS = review_only_legacy_authority_mirror_true_keys()

POLICY_REVIEW_ORDER = (
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
    "MPG-001",
)

NEXT_OWNER_POLICY_SPECS = {
    "BRF-001": {
        "policy_item_id": "BRF-001:next_policy_decision",
        "owner_policy_type": "promote_review_continuation",
        "question": "BRF-001 是否继续进入上层 promote review 证据线，而不改变实盘范围。",
        "default_recommendation": "continue_promote_review_evidence_lane_without_live_scope_change",
        "strategy_review_checkpoint_if_approved": "build_brf_requiredfacts_squeeze_classifier_replay_pack",
        "blocked_policy_effects": ["tier_policy_change", "live_scope_change"],
        "options": [
            "continue_promote_review_evidence_lane",
            "keep_l1_observe_until_forward_outcome_completes",
            "pause_until_squeeze_classifier_is_stronger",
        ],
    },
    "BTPC-001": {
        "policy_item_id": "BTPC-001:next_policy_decision",
        "owner_policy_type": "l2_shadow_revise_or_park",
        "question": "BTPC-001 是否保持 L2 shadow 并继续修 fact-source/classifier，而不是放松 gate 或停车。",
        "default_recommendation": "keep_l2_shadow_revise_fact_source_classifier_without_gate_relaxation",
        "strategy_review_checkpoint_if_approved": "run_btpc_false_positive_and_fact_attachment_review",
        "blocked_policy_effects": ["stale_gate_relaxation", "tier_policy_change"],
        "options": [
            "keep_l2_shadow_revise_sources",
            "wait_for_live_fact_source_attachment",
            "prepare_conditional_gate_relax_review",
            "park_btpc_until_edge_reappears",
        ],
    },
    "LSR-001": {
        "policy_item_id": "LSR-001:next_policy_decision",
        "owner_policy_type": "short_revival_rewrite",
        "question": "LSR-001 是否正式化 short-revival rewrite 作为下一轮复核方向。",
        "default_recommendation": "formalize_short_revival_rewrite_without_live_scope_change",
        "strategy_review_checkpoint_if_approved": "build_lsr_range_context_requiredfacts_replay_pack",
        "blocked_policy_effects": ["live_scope_change", "l1_to_l2_promotion"],
        "options": [
            "formalize_short_revival_rewrite",
            "keep_l1_generic_observe",
            "park_lsr_until_sample_size_improves",
        ],
    },
    "MI-001": {
        "policy_item_id": "MI-001:next_policy_decision",
        "owner_policy_type": "registry_identity",
        "question": "MI-001 应作为正式候选、MPG 子能力、观察资产，还是停车。",
        "default_recommendation": "open_formal_candidate_review_with_overlap_and_concentration_checks",
        "strategy_review_checkpoint_if_approved": "build_mi_registry_handoff_draft_without_admission",
        "blocked_policy_effects": ["registry_admission", "live_scope_change"],
        "options": [
            "formal_candidate_review",
            "mpg_support_capability_review",
            "observe_asset_only",
            "park_mi",
        ],
    },
    "CPM-RO-001": {
        "policy_item_id": "CPM-RO-001:next_policy_decision",
        "owner_policy_type": "registry_identity",
        "question": "CPM-RO-001 应独立、合并、作为观察资产，还是停车。",
        "default_recommendation": "keep_observation_asset_and_run_merge_review",
        "strategy_review_checkpoint_if_approved": "build_cpm_ro_merge_target_review_without_registry_admission",
        "blocked_policy_effects": ["registry_admission", "live_scope_change"],
        "options": [
            "independent_strategy_review",
            "merge_into_existing_family",
            "observe_asset_only",
            "park_cpm_ro",
        ],
    },
    "MPG-001": {
        "policy_item_id": "MPG-001:next_policy_decision",
        "owner_policy_type": "member_role_exit_decay_boundary",
        "question": "MPG-001 是否接受 member role / exit-decay / risk boundary 分层，且不扩 member 实盘范围。",
        "default_recommendation": "accept_member_role_split_and_decay_review_without_member_live_scope_expansion",
        "strategy_review_checkpoint_if_approved": "build_mpg_member_scoring_and_decay_controls",
        "blocked_policy_effects": ["mpg_member_live_scope_expansion", "live_profile_change"],
        "options": [
            "accept_member_role_split",
            "keep_mpg_single_l4_box",
            "freeze_member_review",
        ],
    },
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-only-policy-confirmation-json")
    parser.add_argument("--capture-gap-audit-json")
    parser.add_argument("--quality-closure-wave-json")
    parser.add_argument("--owner-policy-package-json")
    parser.add_argument("--btpc-fact-quality-json")
    parser.add_argument("--btpc-source-mapping-json")
    parser.add_argument("--btpc-classifier-review-json")
    parser.add_argument("--btpc-keep-revise-json")
    parser.add_argument("--btpc-proxy-replay-json")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--output-owner-progress",
        default=str(DEFAULT_OUTPUT_OWNER_PROGRESS),
    )
    args = parser.parse_args(argv)

    closure_artifact = build_review_only_evidence_closure_wave(
        review_only_policy_confirmation=_load_json_object(
            Path(args.review_only_policy_confirmation_json)
        )
        if args.review_only_policy_confirmation_json
        else {},
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json))
        if args.capture_gap_audit_json
        else {},
        quality_closure_wave=_load_json_object(Path(args.quality_closure_wave_json))
        if args.quality_closure_wave_json
        else {},
        owner_policy_package=_load_json_object(Path(args.owner_policy_package_json))
        if args.owner_policy_package_json
        else {},
        btpc_fact_quality=_load_json_object(Path(args.btpc_fact_quality_json), required=False)
        if args.btpc_fact_quality_json
        else {},
        btpc_source_mapping=_load_json_object(
            Path(args.btpc_source_mapping_json), required=False
        )
        if args.btpc_source_mapping_json
        else {},
        btpc_classifier_review=_load_json_object(
            Path(args.btpc_classifier_review_json),
            required=False,
        )
        if args.btpc_classifier_review_json
        else {},
        btpc_keep_revise=_load_json_object(
            Path(args.btpc_keep_revise_json), required=False
        )
        if args.btpc_keep_revise_json
        else {},
        btpc_proxy_replay=_load_json_object(
            Path(args.btpc_proxy_replay_json), required=False
        )
        if args.btpc_proxy_replay_json
        else {},
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_owner_progress = Path(args.output_owner_progress)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_owner_progress.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(closure_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(closure_artifact, output_json, output_md), encoding="utf-8")
    output_owner_progress.write_text(
        _owner_progress_markdown(closure_artifact, output_owner_progress),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": closure_artifact["status"], "output_json": str(output_json)},
            ensure_ascii=False,
        )
    )
    return 0


def build_review_only_evidence_closure_wave(
    *,
    review_only_policy_confirmation: dict[str, Any],
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_policy_package: dict[str, Any] | None = None,
    btpc_fact_quality: dict[str, Any] | None = None,
    btpc_source_mapping: dict[str, Any] | None = None,
    btpc_classifier_review: dict[str, Any] | None = None,
    btpc_keep_revise: dict[str, Any] | None = None,
    btpc_proxy_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owner_policy_package = owner_policy_package or {}
    _validate_inputs(
        review_only_policy_confirmation=review_only_policy_confirmation,
        capture_gap_audit=capture_gap_audit,
        quality_closure_wave=quality_closure_wave,
        owner_policy_package=owner_policy_package,
    )

    evidence_context = _evidence_context(
        capture_gap_audit=capture_gap_audit,
        quality_closure_wave=quality_closure_wave,
        owner_policy_package=owner_policy_package,
        btpc_fact_quality=btpc_fact_quality or {},
        btpc_source_mapping=btpc_source_mapping or {},
        btpc_classifier_review=btpc_classifier_review or {},
        btpc_keep_revise=btpc_keep_revise or {},
        btpc_proxy_replay=btpc_proxy_replay or {},
    )
    evidence_artifacts = [
        _evidence_artifact_for(group, review_only_policy_confirmation, evidence_context)
        for group in POLICY_REVIEW_ORDER
    ]
    owner_progress_projection = _owner_progress_projection(
        review_only_policy_confirmation,
        evidence_artifacts,
    )
    next_owner_policy_package = _next_owner_policy_package(evidence_artifacts)

    return {
        "schema": "brc.strategygroup_review_only_evidence_closure_wave.v1",
        "scope": "strategy_perception_evidence_closure_phases_1_to_3",
        "status": "review_only_evidence_closure_wave_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase_status": {
            "phase_1_owner_perception_projection": "ready",
            "phase_2_evidence_closure_queue": "ready",
            "phase_3_next_owner_policy_package": "ready_for_owner_policy",
        },
        "closed_problem": (
            "P0 waiting_for_market is now separated from active Signal "
            "Observation review evidence closure and next Owner policy points."
        ),
        "owner_progress_projection": owner_progress_projection,
        "evidence_closure_artifacts": evidence_artifacts,
        "next_owner_policy_package": next_owner_policy_package,
        "completion_boundary": {
            "current_stage": "review_only_evidence_closure_wave_ready",
            "owner_policy_confirmation_required_now": True,
            "runtime_owner_intervention_required": False,
            "owner_policy_required_for": [
                item["policy_item_id"]
                for item in next_owner_policy_package["owner_policy_items"]
            ],
            "allowed_without_owner_input": [
                "refresh read-only evidence",
                "rerun local review-only artifact generation",
                "keep P0 live-submit standby waiting for fresh signal",
            ],
            "blocked_until_separate_owner_confirmation": [
                "promote",
                "park",
                "kill",
                "registry_admission",
                "tier_policy_change",
                "live_profile_change",
                "mpg_member_live_scope_expansion",
                "real_order_scope_expansion",
            ],
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
        "source_status": {
            "review_only_policy_confirmation": review_only_policy_confirmation.get("status"),
            "capture_gap_audit": capture_gap_audit.get("status"),
            "quality_closure_wave": quality_closure_wave.get("status"),
            "owner_policy_package": owner_policy_package.get("status"),
        },
    }


def _validate_inputs(
    *,
    review_only_policy_confirmation: dict[str, Any],
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_policy_package: dict[str, Any],
) -> None:
    expected = {
        "review_only_policy_confirmation": (
            review_only_policy_confirmation,
            "review_only_policy_confirmation_ready",
        ),
        "capture_gap_audit": (capture_gap_audit, "strategy_capture_gap_audit_ready"),
        "quality_closure_wave": (quality_closure_wave, "quality_closure_wave_ready"),
        "owner_policy_package": (owner_policy_package, "owner_policy_package_ready"),
    }
    bad_statuses = [
        f"{name}={artifact.get('status')}"
        for name, (artifact, expected_status) in expected.items()
        if artifact.get("status") != expected_status
    ]
    if bad_statuses:
        raise ValueError("inputs are not ready: " + ", ".join(bad_statuses))
    for name, (artifact, _) in expected.items():
        safety = _as_dict(artifact.get("safety_invariants"))
        forbidden = [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]
        if forbidden:
            raise ValueError(f"{name} has forbidden effects: {forbidden}")
        legacy_mirrors = [
            key
            for key in LEGACY_AUTHORITY_MIRROR_TRUE_KEYS
            if safety.get(key) is True
        ]
        if legacy_mirrors:
            raise ValueError(
                f"{name} has legacy authority mirrors: {legacy_mirrors}"
            )


def _evidence_context(
    *,
    capture_gap_audit: dict[str, Any],
    quality_closure_wave: dict[str, Any],
    owner_policy_package: dict[str, Any],
    btpc_fact_quality: dict[str, Any],
    btpc_source_mapping: dict[str, Any],
    btpc_classifier_review: dict[str, Any],
    btpc_keep_revise: dict[str, Any],
    btpc_proxy_replay: dict[str, Any],
) -> dict[str, Any]:
    return {
        "capture_rows": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows"))
        },
        "quality_rows": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(
                _as_dict(quality_closure_wave.get("wave_2_capture_quality_closure")).get("rows")
            )
        },
        "strategy_policy_items": {
            str(row.get("strategy_group_id")): row
            for row in _dict_rows(
                _as_dict(quality_closure_wave.get("wave_1_strategy_explainer")).get("policy_items")
            )
        },
        "owner_policy_items": {
            str(row.get("strategy_group_id")): row
            for row in _policy_items(owner_policy_package)
        },
        "mpg_member_review": _as_dict(
            quality_closure_wave.get("wave_3_mpg_member_deepening")
        ),
        "btpc": {
            "fact_quality": btpc_fact_quality,
            "source_mapping": btpc_source_mapping,
            "classifier_review": btpc_classifier_review,
            "keep_revise": btpc_keep_revise,
            "proxy_replay": btpc_proxy_replay,
        },
    }


def _evidence_artifact_for(
    group: str,
    policy_confirmation: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    confirmed = _confirmed_policy_for_group(policy_confirmation, group)
    capture = _as_dict(context["capture_rows"].get(group))
    quality = _as_dict(context["quality_rows"].get(group))
    strategy_policy_item = _as_dict(context["strategy_policy_items"].get(group))
    owner_policy_item = _as_dict(context["owner_policy_items"].get(group))
    spec = NEXT_OWNER_POLICY_SPECS[group]

    base = {
        "queue_id": confirmed.get("queue_id") or f"signal-observation-{group.lower()}",
        "strategy_group_id": group,
        "status": "review_only_evidence_artifact_ready",
        "review_only": True,
        "confirmed_review_only_policy_effect": confirmed.get("review_only_policy_effect"),
        "source_counts": _source_counts(capture),
        "dominant_blocker_classes": capture.get("dominant_blocker_classes", []),
        "owner_label": strategy_policy_item.get("owner_label") or group,
        "current_tier": strategy_policy_item.get("current_tier") or quality.get("current_tier"),
        "strategy_review_checkpoint": strategy_policy_item.get("strategy_review_checkpoint"),
        "why_not_live": owner_policy_item.get("why_not_live") or _generic_why_not_live(),
        "evidence_for": list(_list(owner_policy_item.get("evidence_for"))),
        "evidence_against": list(_list(owner_policy_item.get("evidence_against"))),
        "closure_findings": [],
        "closure_result": "",
        "next_owner_policy_item": {
            "policy_item_id": spec["policy_item_id"],
            "owner_policy_type": spec["owner_policy_type"],
            "owner_policy_question": spec["question"],
            "default_recommendation": spec["default_recommendation"],
            "owner_policy_options": spec["options"],
            "strategy_review_checkpoint_if_approved": spec["strategy_review_checkpoint_if_approved"],
            "blocked_policy_effects": spec["blocked_policy_effects"],
        },
        "safety_invariants": _safety_invariants(),
    }

    if group == "BRF-001":
        base["closure_findings"] = [
            "bear-rally failure short structure exists in observe-only audit",
            "forward outcome for the latest would_enter is still pending",
            "squeeze classifier and RequiredFacts review remain review-only prerequisites",
        ]
        base["closure_result"] = (
            "promote_review_evidence_lane_can_continue_without_live_scope_change"
        )
    elif group == "BTPC-001":
        btpc = context["btpc"]
        base["btpc_attribution"] = _btpc_attribution(btpc)
        base["closure_findings"] = [
            "stale gate attribution is real and should not be hidden as no opportunity",
            "live derivatives mappings are identified but not attached as live RequiredFacts",
            "classifier rule review is recorded but does not authorize promotion or live submit",
        ]
        base["closure_result"] = (
            "keep_l2_shadow_and_revise_fact_source_classifier_before_any_gate_relaxation"
        )
    elif group == "LSR-001":
        base["closure_findings"] = [
            "short-revival would_enter evidence exists but sample size remains small",
            "long preview and side-specific short semantics still need policy separation",
            "range-context RequiredFacts should be formalized before any tier change",
        ]
        base["closure_result"] = (
            "formalize_short_revival_rewrite_review_without_live_scope_change"
        )
    elif group == "MI-001":
        base["closure_findings"] = [
            "MI has strong would_enter and forward-positive concentration",
            "registry identity is unresolved and must not be treated as admission",
            "overlap with MPG or adjacent momentum capability requires review",
        ]
        base["closure_result"] = (
            "open_formal_candidate_review_without_registry_admission"
        )
    elif group == "CPM-RO-001":
        base["closure_findings"] = [
            "CPM-RO has meaningful would_enter evidence but mixed forward quality",
            "merge target across CPM, RBR, or momentum families is unresolved",
            "observation asset status is safer than independent admission now",
        ]
        base["closure_result"] = (
            "keep_observation_asset_and_run_merge_review_without_registry_admission"
        )
    elif group == "MPG-001":
        mpg_member_review = context["mpg_member_review"]
        base["member_review"] = {
            "status": mpg_member_review.get("status"),
            "member_count": mpg_member_review.get("member_count"),
            "exit_decay_review": mpg_member_review.get("exit_decay_review"),
            "member_rows": mpg_member_review.get("member_rows", []),
        }
        base["closure_findings"] = [
            "MPG remains the selected L4 live lane but has no executable fresh signal now",
            "member roles and exit-decay controls are ready for policy review",
            "no member receives live scope from this review artifact",
        ]
        base["closure_result"] = (
            "member_role_exit_decay_review_ready_without_member_live_scope_expansion"
        )
    return base


def _source_counts(capture_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "would_enter_count": _int(capture_row.get("would_enter_count")),
        "no_action_count": _int(capture_row.get("no_action_count")),
        "high_priority_no_action_count": _int(
            capture_row.get("high_priority_no_action_count")
        ),
        "would_enter_forward_positive_count": _int(
            capture_row.get("would_enter_forward_positive_count")
        ),
        "missed_no_action_forward_positive_count": _int(
            capture_row.get("missed_no_action_forward_positive_count")
        ),
        "positive_forward_outcome_count": _int(
            capture_row.get("positive_forward_outcome_count")
        ),
    }


def _btpc_attribution(btpc: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fact_quality_counts = _as_dict(btpc["fact_quality"].get("counts"))
    source_mapping_counts = _as_dict(btpc["source_mapping"].get("counts"))
    classifier_counts = _as_dict(btpc["classifier_review"].get("counts"))
    keep_revise_counts = _as_dict(btpc["keep_revise"].get("counts"))
    proxy_counts = _as_dict(btpc["proxy_replay"].get("counts"))
    return {
        "fact_gap_count": _int(fact_quality_counts.get("fact_gap_count")),
        "fact_source_pending_count": _int(
            fact_quality_counts.get("fact_source_pending_count")
        ),
        "expected_live_fact_source_count": _int(
            source_mapping_counts.get("expected_live_fact_source_count")
        ),
        "source_attachment_pending_count": _int(
            source_mapping_counts.get("source_attachment_pending_count")
        ),
        "live_required_fact_gap_count": _int(
            source_mapping_counts.get("live_required_fact_gap_count")
        ),
        "classifier_rule_review_count": _int(
            classifier_counts.get("rule_review_count")
        ),
        "implementation_ready_count": _int(
            classifier_counts.get("implementation_ready_count")
        ),
        "proxy_reviewable_would_enter_count": _int(
            keep_revise_counts.get("proxy_reviewable_would_enter_count")
        ),
        "revise_case_count": _int(keep_revise_counts.get("revise_case_count")),
        "proxy_replay_case_count": _int(proxy_counts.get("replay_case_count")),
        "review_outcome_state": _as_dict(
            btpc["keep_revise"].get("review_outcome_state")
        ),
    }


def _owner_progress_projection(
    policy_confirmation: dict[str, Any],
    evidence_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    source_snapshot = _as_dict(policy_confirmation.get("owner_perception_snapshot"))
    artifact_by_group = {
        str(artifact["strategy_group_id"]): artifact for artifact in evidence_artifacts
    }
    rows = []
    for row in _dict_rows(source_snapshot.get("rows")):
        group = str(row.get("strategy_group_id"))
        artifact = artifact_by_group.get(group)
        rows.append(
            {
                "strategy_group_id": group,
                "owner_state": row.get("owner_state"),
                "confirmed_effect": row.get("confirmed_effect"),
                "next_queue_id": row.get("next_queue_id"),
                "evidence_closure_status": artifact.get("status") if artifact else "not_selected",
                "closure_result": artifact.get("closure_result") if artifact else None,
                "no_live_permission": True,
            }
        )
    return {
        "status": "owner_progress_projection_ready",
        "owner_summary": (
            "主链路等待可执行机会；Signal Observation 复核证据已进入闭合；"
            "实盘权限没有变化。"
        ),
        "p0_state": source_snapshot.get("p0_state", "waiting_for_market"),
        "p0_owner_label": "主链路等待机会",
        "signal_observation_review_state": "review_only_evidence_closure_active",
        "signal_observation_owner_label": "策略复核证据运行中",
        "queue_count": source_snapshot.get("queue_count", len(evidence_artifacts) + 1),
        "evidence_artifact_count": len(evidence_artifacts),
        "next_owner_policy_item_count": len(evidence_artifacts),
        "no_live_permission": True,
        "owner_intervention_required": False,
        "owner_policy_confirmation_required_after_wave": True,
        "rows": rows,
    }


def _next_owner_policy_package(
    evidence_artifacts: list[dict[str, Any]]
) -> dict[str, Any]:
    policy_items = []
    for artifact in evidence_artifacts:
        next_policy_item = dict(artifact["next_owner_policy_item"])
        next_policy_item.update(
            {
                "strategy_group_id": artifact["strategy_group_id"],
                "source_queue_id": artifact["queue_id"],
                "owner_policy_ready": True,
                "review_only": True,
                "default_recommendation": next_policy_item["default_recommendation"],
                "evidence_for": artifact["evidence_for"],
                "evidence_against": artifact["evidence_against"],
                "closure_findings": artifact["closure_findings"],
                "closure_result": artifact["closure_result"],
                "why_not_live": artifact["why_not_live"],
                "does_not_authorize_live_execution": True,
            }
        )
        policy_items.append(next_policy_item)
    return {
        "schema": "brc.strategygroup_next_owner_policy_package.v1",
        "status": "next_owner_policy_package_ready",
        "owner_policy_confirmation_required_now": True,
        "runtime_owner_intervention_required": False,
        "owner_policy_item_count": len(policy_items),
        "owner_policy_items": policy_items,
        "default_recommendations": [
            {
                "policy_item_id": policy_item["policy_item_id"],
                "strategy_group_id": policy_item["strategy_group_id"],
                "default_recommendation": policy_item["default_recommendation"],
            }
            for policy_item in policy_items
        ],
        "blocked_policy_effects": [
            "promote",
            "park",
            "kill",
            "registry_admission",
            "tier_policy_change",
            "live_profile_change",
            "mpg_member_live_scope_expansion",
            "real_order_scope_expansion",
        ],
        "safety_invariants": _safety_invariants(),
    }


def _confirmed_policy_for_group(
    policy_confirmation: dict[str, Any],
    group: str,
) -> dict[str, Any]:
    rows = _dict_rows(policy_confirmation.get("confirmed_policy_items"))
    if not rows:
        rows = _dict_rows(policy_confirmation.get("confirmed_decisions"))
    for row in rows:
        if row.get("strategy_group_id") == group:
            return row
    return {}


def _interaction() -> dict[str, Any]:
    return review_only_interaction(
        "L0_local_review_only_evidence_closure_wave",
        mutation_key="mutates_remote_files",
    )


def _safety_invariants() -> dict[str, Any]:
    return review_only_safety_invariants(
        include_runtime_started=True,
        include_authority_mirrors=False,
    )


def _markdown(artifact: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Review-Only Evidence Closure Wave",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Closed problem: {artifact['closed_problem']}",
        "- Live permission change: `false`",
        "- Owner policy confirmation required now: `true`",
        "",
        "## Phase Status",
        "",
        "| Phase | Status |",
        "| --- | --- |",
    ]
    for key, value in artifact["phase_status"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(_owner_projection_lines(artifact["owner_progress_projection"]))
    lines.extend(
        [
            "",
            "## Evidence Closure Artifacts",
            "",
            "| Queue | StrategyGroup | Closure result | Next policy_item |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in artifact["evidence_closure_artifacts"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row["queue_id"],
                row["strategy_group_id"],
                row["closure_result"],
                row["next_owner_policy_item"]["policy_item_id"],
            )
        )
    lines.extend(
        [
            "",
            "## Next Owner Policy Package",
            "",
            "| Policy item | StrategyGroup | Default recommendation |",
            "| --- | --- | --- |",
        ]
    )
    for policy_item in artifact["next_owner_policy_package"]["owner_policy_items"]:
        lines.append(
            "| `{}` | `{}` | `{}` |".format(
                policy_item["policy_item_id"],
                policy_item["strategy_group_id"],
                policy_item["default_recommendation"],
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            f"- Current stage: `{artifact['completion_boundary']['current_stage']}`",
            "- Owner policy confirmation required now: `true`",
            "- Runtime Owner intervention required: `false`",
            "- Blocked until separate Owner confirmation: "
            + ", ".join(
                f"`{item}`"
                for item in artifact["completion_boundary"][
                    "blocked_until_separate_owner_confirmation"
                ]
            ),
            "",
            "## Safety",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    for key, value in artifact["safety_invariants"].items():
        lines.append(f"| `{key}` | `{str(value).lower()}` |")
    lines.extend(
        [
            "",
            "## Output",
            "",
            f"- JSON: `{output_json}`",
            f"- Markdown: `{output_md}`",
            "",
        ]
    )
    return "\n".join(lines)


def _owner_progress_markdown(artifact: dict[str, Any], output_path: Path) -> str:
    lines = [
        "## StrategyGroup Owner Progress",
        "",
        f"- 报告时间: {artifact['generated_at_utc']}",
        "- 主链路: 等待可执行机会",
        "- Signal Observation: review-only 证据闭合已完成",
        "- 实盘权限变化: 否",
        "- Owner 当前要决策: 是，限于策略政策方向",
        "- Runtime Owner 介入: 否",
        "",
    ]
    lines.extend(_owner_projection_lines(artifact["owner_progress_projection"]))
    lines.extend(
        [
            "",
            "## Next Policy Decisions",
            "",
            "| Policy item | Default recommendation |",
            "| --- | --- |",
        ]
    )
    for policy_item in artifact["next_owner_policy_package"]["owner_policy_items"]:
        lines.append(
            f"| `{policy_item['policy_item_id']}` | `{policy_item['default_recommendation']}` |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- 不授权真实下单、FinalGate、Operation Layer、tier policy、live profile、registry admission 或 member live scope expansion。",
            f"- Output: `{output_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _owner_projection_lines(projection: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Owner Progress Projection",
        "",
        f"- Owner summary: {projection['owner_summary']}",
        f"- P0 state: `{projection['p0_state']}`",
        "- Signal Observation review state: "
        f"`{projection['signal_observation_review_state']}`",
        f"- Evidence artifacts: `{projection['evidence_artifact_count']}`",
        f"- No live permission: `{str(projection['no_live_permission']).lower()}`",
        "",
        "| StrategyGroup | Owner state | Closure status | Closure result | Live permission |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in projection["rows"]:
        lines.append(
            "| `{}` | {} | `{}` | `{}` | `false` |".format(
                row["strategy_group_id"],
                row.get("owner_state") or "-",
                row.get("evidence_closure_status") or "-",
                row.get("closure_result") or "-",
            )
        )
    return lines


def _load_json_object(path: Path, *, required: bool = True) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if not required:
            return {}
        raise SystemExit(f"missing JSON input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON input: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON input must be an object: {path}")
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _policy_items(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return _dict_rows(artifact.get("owner_policy_items"))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _generic_why_not_live() -> str:
    return (
        "review-only evidence requires fresh signal, live RequiredFacts, "
        "candidate/auth evidence, action-time FinalGate, official Operation "
        "Layer, protection, account, and exchange facts before any live submit."
    )


if __name__ == "__main__":
    raise SystemExit(main())
