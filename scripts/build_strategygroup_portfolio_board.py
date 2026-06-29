#!/usr/bin/env python3
"""Build the StrategyGroup Portfolio Board and trial-candidate pool.

This command projects current local review evidence into a StrategyGroup
portfolio view. It is evidence-driven and review-only: weak or missing evidence
becomes an engineering continuation item, not a live permission grant.
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
    review_only_interaction,
    review_only_safety_invariants,
)

DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_REGISTRY_BASELINE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.md"
)
DEFAULT_TRIAL_POOL_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-trial-candidate-pool.md"
)

SCHEMA = "brc.strategygroup_portfolio_board.v1"

ACTIVE_REVIEW_ORDER = (
    "MPG-001",
    "BRF-001",
    "BTPC-001",
    "LSR-001",
    "MI-001",
    "CPM-RO-001",
    "FBS-001",
    "SOR-001",
    "VCB-001",
    "RBR-001",
)

FORBIDDEN_EFFECTS = (
    "strategy_parameters_changed",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "execution_intent_created",
    "creates_execution_intent",
    "final_gate_called",
    "calls_finalgate",
    "operation_layer_called",
    "calls_operation_layer",
    "order_created",
    "places_order",
    "exchange_write_called",
    "calls_exchange_write",
    "preview_or_replay_treated_as_live_signal",
)

POLICY_DECISION_STAGES = {
    "promote_review",
    "identity_review",
    "park",
}

DEFAULT_REVIEW_CHECKPOINTS = {
    "MPG-001": "keep_p0_standby_and_complete_member_role_exit_decay_review",
    "BRF-001": "build_brf_squeeze_requiredfacts_forward_outcome_v2",
    "BTPC-001": "attach_btpc_live_fact_sources_then_rerun_false_negative_review",
    "LSR-001": "build_lsr_short_revival_v2_range_context_fixture",
    "MI-001": "open_mi_identity_overlap_symbol_concentration_review",
    "CPM-RO-001": "open_cpm_ro_semantic_source_merge_quality_review",
    "FBS-001": "run_fbs_derivatives_fact_coverage_visibility_review",
    "SOR-001": "run_sor_session_no_action_visibility_review",
    "VCB-001": "run_vcb_false_breakout_classifier_review",
    "RBR-001": "keep_parked_until_material_new_edge_evidence",
}

OWNER_LABEL_FALLBACKS = {
    "MPG-001": "动量延续",
    "BRF-001": "熊市反弹失败",
    "BTPC-001": "熊市回抽延续",
    "LSR-001": "流动性扫盘/短线复活",
    "MI-001": "动量冲击",
    "CPM-RO-001": "CPM 回补观察",
    "FBS-001": "资金费率/基差压力",
    "SOR-001": "开盘区间结构",
    "VCB-001": "波动压缩突破",
    "RBR-001": "区间边界回归",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-gap-audit-json", required=True)
    parser.add_argument("--review-deep-dive-json")
    parser.add_argument("--owner-policy-package-json")
    parser.add_argument("--quality-closure-wave-json")
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--registry-baseline-json", default=str(DEFAULT_REGISTRY_BASELINE_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--output-trial-pool-md", default=str(DEFAULT_TRIAL_POOL_MD))
    args = parser.parse_args(argv)

    board_artifact = build_strategygroup_portfolio_board(
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        review_deep_dive=_read_optional_json(Path(args.review_deep_dive_json))
        if args.review_deep_dive_json
        else None,
        owner_policy_package=_read_optional_json(
            Path(args.owner_policy_package_json)
        )
        if args.owner_policy_package_json
        else None,
        quality_closure_wave=_read_optional_json(Path(args.quality_closure_wave_json))
        if args.quality_closure_wave_json
        else None,
        tier_policy=_read_optional_json(Path(args.tier_policy_json)),
        registry_baseline=_read_optional_json(Path(args.registry_baseline_json)),
    )

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_trial_pool = Path(args.output_trial_pool_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(board_artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_portfolio_markdown(board_artifact, output_json), encoding="utf-8")
    output_trial_pool.write_text(
        _trial_pool_markdown(board_artifact, output_trial_pool), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": board_artifact["status"],
                "portfolio_row_count": board_artifact["portfolio_summary"][
                    "portfolio_row_count"
                ],
                "trial_candidate_count": board_artifact["trial_candidate_pool"][
                    "candidate_count"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_strategygroup_portfolio_board(
    *,
    capture_gap_audit: dict[str, Any],
    review_deep_dive: dict[str, Any] | None = None,
    owner_policy_package: dict[str, Any] | None = None,
    quality_closure_wave: dict[str, Any] | None = None,
    tier_policy: dict[str, Any] | None = None,
    registry_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_safety("capture_gap_audit", capture_gap_audit)
    for name, source_artifact in (
        ("review_deep_dive", review_deep_dive),
        ("owner_policy_package", owner_policy_package),
        ("quality_closure_wave", quality_closure_wave),
        ("tier_policy", tier_policy),
        ("registry_baseline", registry_baseline),
    ):
        if source_artifact:
            _validate_safety(name, source_artifact)

    audit_rows = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows"))
        if row.get("strategy_group_id")
    }
    capture_gap_recommendations = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(capture_gap_audit.get("observation_recommendations"))
        if row.get("strategy_group_id")
    }
    registry_rows = _registry_rows_by_id(registry_baseline or {})
    tier_rows = _tier_rows_by_id(tier_policy or {})
    deep_dive_rows = _deep_dive_rows_by_id(review_deep_dive or {})
    owner_policy_items = _owner_policy_items_by_id(owner_policy_package or {})
    quality_index = _quality_index_by_id(quality_closure_wave or {})

    source_gaps = _source_gaps(
        capture_gap_audit=capture_gap_audit,
        review_deep_dive=review_deep_dive,
        owner_policy_package=owner_policy_package,
        quality_closure_wave=quality_closure_wave,
        tier_policy=tier_policy,
        registry_baseline=registry_baseline,
    )

    portfolio_rows = [
        _portfolio_row(
            strategy_group_id=strategy_group_id,
            audit_row=audit_rows.get(strategy_group_id, {}),
            capture_gap_recommendation=capture_gap_recommendations.get(strategy_group_id, {}),
            registry_row=registry_rows.get(strategy_group_id, {}),
            tier_row=tier_rows.get(strategy_group_id, {}),
            tier_policy=tier_policy or {},
            deep_dive_row=deep_dive_rows.get(strategy_group_id, {}),
            owner_policy_item=owner_policy_items.get(strategy_group_id, {}),
            quality_row=quality_index.get(strategy_group_id, {}),
        )
        for strategy_group_id in ACTIVE_REVIEW_ORDER
    ]

    engineering_queue = [
        _engineering_queue_item(row)
        for row in portfolio_rows
        if row["engineering_continue"] is True
    ]
    owner_policy_queue = [
        _owner_policy_queue_item(row)
        for row in portfolio_rows
        if row["owner_policy_required"] is True
    ]
    trial_candidate_pool = _trial_candidate_pool(portfolio_rows)
    registry_only_rows = _registry_only_rows(registry_rows, audit_rows)

    runtime_posture = _runtime_posture(capture_gap_audit)
    status = (
        "portfolio_board_ready"
        if len(portfolio_rows) == len(ACTIVE_REVIEW_ORDER)
        and not _forbidden_effects(_safety_invariants())
        else "portfolio_board_needs_work"
    )

    return {
        "schema": SCHEMA,
        "scope": "strategygroup_portfolio_board_review_only",
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_posture": runtime_posture,
        "portfolio_summary": {
            "portfolio_row_count": len(portfolio_rows),
            "active_review_strategy_groups": list(ACTIVE_REVIEW_ORDER),
            "registry_only_strategy_groups": [
                row["strategy_group_id"] for row in registry_only_rows
            ],
            "evidence_stage_counts": _count_by(portfolio_rows, "evidence_stage"),
            "execution_tier_counts": _count_by(portfolio_rows, "execution_tier"),
            "engineering_continuation_count": len(engineering_queue),
            "owner_policy_queue_count": len(owner_policy_queue),
            "trial_candidate_count": trial_candidate_pool["candidate_count"],
        },
        "portfolio_rows": portfolio_rows,
        "trial_candidate_pool": trial_candidate_pool,
        "engineering_continuation_queue": engineering_queue,
        "owner_policy_queue": owner_policy_queue,
        "registry_context": {
            "registry_row_count": len(registry_rows),
            "registry_only_rows": registry_only_rows,
            "registry_only_note": (
                "These registry assets were not in the latest active capture "
                "audit rows and are not forced into the current review board."
            ),
        },
        "owner_progress_projection": {
            "p0_state": runtime_posture["p0_state"],
            "p0_state_source": runtime_posture["p0_state_source"],
            "signal_observation_state": "portfolio_screening_active",
            "owner_summary": (
                "P0 waits for a real executable signal; Signal Observation "
                "has an active StrategyGroup portfolio board, engineering "
                "evidence queue, and review-only trial-candidate pool; no "
                "live permission changed."
            ),
            "owner_intervention_required": False,
            "owner_policy_confirmation_required_later": bool(owner_policy_queue),
            "no_live_permission": True,
        },
        "source_status": {
            "capture_gap_audit": str(capture_gap_audit.get("status") or "unknown"),
            "review_deep_dive": _review_deep_dive_source_status(review_deep_dive),
            "owner_policy_package": str(
                (owner_policy_package or {}).get("status") or "missing"
            ),
            "quality_closure_wave": str(
                (quality_closure_wave or {}).get("status") or "missing"
            ),
            "tier_policy": str((tier_policy or {}).get("status") or "missing"),
            "registry_baseline": str(
                (registry_baseline or {}).get("status") or "missing"
            ),
            "source_gaps": source_gaps,
        },
        "interaction": _interaction(),
        "safety_invariants": _safety_invariants(),
    }


def _portfolio_row(
    *,
    strategy_group_id: str,
    audit_row: dict[str, Any],
    capture_gap_recommendation: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    tier_policy: dict[str, Any],
    deep_dive_row: dict[str, Any],
    owner_policy_item: dict[str, Any],
    quality_row: dict[str, Any],
) -> dict[str, Any]:
    execution_tier, execution_tier_source = _execution_tier(
        strategy_group_id=strategy_group_id,
        tier_row=tier_row,
        registry_row=registry_row,
        tier_policy=tier_policy,
    )
    evidence_stage, stage_reasons = _evidence_stage(
        strategy_group_id=strategy_group_id,
        audit_row=audit_row,
        registry_row=registry_row,
        execution_tier=execution_tier,
        deep_dive_row=deep_dive_row,
        quality_row=quality_row,
    )
    strategy_review_checkpoint = (
        str(quality_row.get("next_checkpoint") or "")
        or str(deep_dive_row.get("strategy_review_checkpoint_if_approved") or "")
        or str(owner_policy_item.get("next_if_approved") or "")
        or DEFAULT_REVIEW_CHECKPOINTS[strategy_group_id]
    )
    evidence_gaps = _evidence_gaps(
        strategy_group_id=strategy_group_id,
        audit_row=audit_row,
        registry_row=registry_row,
        tier_row=tier_row,
        evidence_stage=evidence_stage,
    )
    forward_summary = _cost_after_result_summary(audit_row)
    owner_policy_required = _owner_policy_required(
        evidence_stage=evidence_stage,
        strategy_group_id=strategy_group_id,
        deep_dive_row=deep_dive_row,
    )
    if (
        evidence_stage == "park"
        and str(registry_row.get("current_decision_ref") or "") == "park"
    ):
        owner_policy_required = False
    trial_eligible = registry_row.get("trial_eligible") is True
    return {
        "strategy_group_id": strategy_group_id,
        "owner_label": _owner_label(strategy_group_id, registry_row, owner_policy_item),
        "execution_tier": execution_tier,
        "execution_tier_source": execution_tier_source,
        "evidence_stage": evidence_stage,
        "evidence_stage_reasons": stage_reasons,
        "evidence_strength": _evidence_strength(audit_row, evidence_stage),
        "recent_opportunity_count": _int(audit_row.get("would_enter_count")),
        "no_action_count": _int(audit_row.get("no_action_count")),
        "high_priority_no_action_count": _int(
            audit_row.get("high_priority_no_action_count")
        ),
        "missed_no_action_forward_positive_count": _int(
            audit_row.get("missed_no_action_forward_positive_count")
        ),
        "would_enter_forward_positive_count": _int(
            audit_row.get("would_enter_forward_positive_count")
        ),
        "dominant_blocker_classes": _dict_rows(
            audit_row.get("dominant_blocker_classes")
        ),
        "cost_after_result_summary": forward_summary,
        "forward_outcome_summary": audit_row.get("would_enter_forward_outcome_summary")
        if isinstance(audit_row.get("would_enter_forward_outcome_summary"), dict)
        else {"event_count": 0, "by_window": {}},
        "capture_gap_recommendation_provenance": {
            "recommendation": str(
                capture_gap_recommendation.get("observation_recommendation") or "none"
            ),
            "next_checkpoint": str(capture_gap_recommendation.get("next_checkpoint") or ""),
            "source_role": "capture_gap_observation_provenance",
        },
        "registry_decision_ref": str(registry_row.get("current_decision_ref") or ""),
        "strategy_review_checkpoint": strategy_review_checkpoint,
        "engineering_continue": _engineering_continue(
            evidence_stage=evidence_stage,
            evidence_gaps=evidence_gaps,
        ),
        "evidence_gaps": evidence_gaps,
        "owner_policy_required": owner_policy_required,
        "owner_policy_required_now": False,
        "owner_policy_source": _owner_policy_source(
            owner_policy_required, evidence_stage, deep_dive_row
        ),
        "trial_eligible": trial_eligible,
        "trial_eligible_source": "registry_baseline" if trial_eligible else "not_registry_trial_eligible",
        "live_permission_change": False,
        "live_permission_change_recommended_now": False,
        "does_not_authorize_live_execution": True,
        "blocked_policy_effects": [
            "registry_admission",
            "tier_policy_change",
            "live_profile_change",
            "order_sizing_change",
            "mpg_member_live_scope_expansion",
            "real_order_scope_expansion",
        ],
        "last_evidence_ref": _last_evidence_ref(strategy_group_id, audit_row, registry_row),
    }


def _execution_tier(
    *,
    strategy_group_id: str,
    tier_row: dict[str, Any],
    registry_row: dict[str, Any],
    tier_policy: dict[str, Any],
) -> tuple[str, str]:
    tier = tier_row.get("tier")
    if isinstance(tier, str) and tier:
        return tier, "tier_policy.current_strategy_groups"
    registry_tier = registry_row.get("default_tier")
    if isinstance(registry_tier, str) and registry_tier:
        return registry_tier, "registry_baseline.default_tier"
    defaults = tier_policy.get("new_strategy_group_defaults")
    if isinstance(defaults, dict):
        known = defaults.get("known_new_groups")
        short_id = strategy_group_id.split("-", 1)[0]
        if isinstance(known, dict):
            for key in (strategy_group_id, short_id):
                known_tier = known.get(key)
                if isinstance(known_tier, str) and known_tier:
                    return known_tier, "tier_policy.new_strategy_group_defaults"
    return "unknown", "no_tier_policy_or_registry_evidence"


def _evidence_stage(
    *,
    strategy_group_id: str,
    audit_row: dict[str, Any],
    registry_row: dict[str, Any],
    execution_tier: str,
    deep_dive_row: dict[str, Any],
    quality_row: dict[str, Any],
) -> tuple[str, list[str]]:
    if (
        strategy_group_id == "MPG-001"
        and execution_tier == "L4"
        and registry_row.get("trial_eligible") is True
    ):
        return "trial_waiting", [
            "execution_tier=L4",
            "registry_trial_eligible=true",
            "selected_p0_lane=true",
        ]

    decision = str(quality_row.get("strategy_asset_current_decision") or "")
    if decision and decision != "unknown":
        return _normalize_decision_stage(decision), [
            f"strategy_asset_current_decision={decision}"
        ]
    if decision:
        return "insufficient_evidence", [
            "strategy_asset_current_decision=unknown"
        ]

    registry_decision = str(registry_row.get("current_decision_ref") or "")
    if registry_decision == "park":
        return "park", ["registry_current_decision_ref=park"]

    recommendation = str(
        deep_dive_row.get("recommended_owner_policy") or ""
    )
    owner_policy_type = str(
        deep_dive_row.get("owner_policy_type")
        or deep_dive_row.get("decision_type")
        or ""
    )
    if "promote_review" in recommendation or "promote" in owner_policy_type:
        return "promote_review", [f"deep_dive_owner_policy_type={owner_policy_type}"]
    if "registry_identity" in owner_policy_type:
        return "identity_review", [f"deep_dive_owner_policy_type={owner_policy_type}"]
    if "revise" in recommendation or "rewrite" in owner_policy_type:
        return "revise", [f"deep_dive_owner_policy_type={owner_policy_type}"]

    blockers = {str(row.get("key")) for row in _dict_rows(audit_row.get("dominant_blocker_classes"))}
    would_enter = _int(audit_row.get("would_enter_count"))
    positive = _int(audit_row.get("would_enter_forward_positive_count"))
    event_count = _int(_as_dict(audit_row.get("forward_outcome_summary")).get("event_count"))
    if "stale_data_or_signal" in blockers:
        return "revise", ["dominant_blocker=stale_data_or_signal"]
    if would_enter > 0 and not registry_row:
        return "identity_review", ["would_enter_present_without_registry_row"]
    if event_count == 0 and execution_tier in {"L3", "L4"}:
        return "coverage_visibility_review", ["no_recent_capture_events_for_observation_lane"]
    if would_enter > 0 and positive > 0:
        return "observe", ["would_enter_forward_positive_but_no_promotion_decision"]
    return "insufficient_evidence", ["no_decision_or_capture_evidence"]


def _normalize_decision_stage(decision: str) -> str:
    if decision == "keep_observing":
        return "observe"
    if decision == "promote_review_only":
        return "promote_review"
    if decision in {
        "promote_review",
        "revise",
        "identity_review",
        "coverage_visibility_review",
        "park",
        "kill",
    }:
        return decision
    return "insufficient_evidence"


def _evidence_strength(audit_row: dict[str, Any], evidence_stage: str) -> str:
    would_enter = _int(audit_row.get("would_enter_count"))
    positive = _int(audit_row.get("would_enter_forward_positive_count"))
    high_no_action = _int(audit_row.get("high_priority_no_action_count"))
    if evidence_stage == "trial_waiting":
        return "policy_trial_lane_waiting_for_market"
    if evidence_stage == "park":
        return "parked_despite_observation_evidence"
    if would_enter >= 10 and positive / max(would_enter, 1) >= 0.7:
        return "strong_observe_only_evidence"
    if would_enter > 0 and positive > 0:
        return "material_observe_only_evidence"
    if high_no_action > 0:
        return "material_no_action_gap"
    return "insufficient_recent_evidence"


def _evidence_gaps(
    *,
    strategy_group_id: str,
    audit_row: dict[str, Any],
    registry_row: dict[str, Any],
    tier_row: dict[str, Any],
    evidence_stage: str,
) -> list[str]:
    gaps: list[str] = []
    if not registry_row:
        gaps.append("registry_identity_or_registry_row_missing")
    if not tier_row and not registry_row.get("default_tier"):
        gaps.append("execution_tier_not_in_policy_or_registry")
    if _int(_as_dict(audit_row.get("forward_outcome_summary")).get("event_count")) == 0:
        gaps.append("no_recent_forward_outcome_events_in_capture_audit")
    would_enter_summary = _as_dict(audit_row.get("would_enter_forward_outcome_summary"))
    for window, summary in _as_dict(would_enter_summary.get("by_window")).items():
        if _int(_as_dict(summary).get("pending")) > 0:
            gaps.append(f"would_enter_forward_outcome_pending:{window}")
    if evidence_stage == "promote_review" and _int(
        audit_row.get("would_enter_forward_positive_count")
    ) == 0:
        gaps.append("promote_review_forward_positive_not_completed")
    if evidence_stage == "revise" and _int(audit_row.get("high_priority_no_action_count")):
        gaps.append("no_action_or_classifier_attribution_needs_closure")
    if evidence_stage == "coverage_visibility_review":
        gaps.append("coverage_visibility_or_routing_needs_closure")
    if evidence_stage == "identity_review":
        gaps.append("formal_candidate_vs_sub_capability_vs_observe_asset_unresolved")
    if strategy_group_id == "MPG-001":
        gaps.append("real_fresh_signal_absent_for_p0_live_lane")
    return _dedupe(gaps)


def _cost_after_result_summary(audit_row: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(audit_row.get("would_enter_forward_outcome_summary"))
    by_window = _as_dict(summary.get("by_window"))
    result: dict[str, Any] = {}
    for window in ("4h", "12h", "24h"):
        row = _as_dict(by_window.get(window))
        completed = _int(row.get("completed"))
        tradable = _int(row.get("tradable_mfe_after_cost_count"))
        pending = _int(row.get("pending"))
        unavailable = _int(row.get("unavailable")) + _int(row.get("unknown"))
        result[window] = {
            "completed": completed,
            "tradable_mfe_after_cost_count": tradable,
            "pending": pending,
            "unavailable_or_unknown": unavailable,
            "tradable_completed_ratio": _ratio(tradable, completed),
        }
    return result


def _owner_policy_required(
    *,
    evidence_stage: str,
    strategy_group_id: str,
    deep_dive_row: dict[str, Any],
) -> bool:
    if evidence_stage in POLICY_DECISION_STAGES:
        return True
    if strategy_group_id == "MPG-001" and deep_dive_row:
        return True
    return False


def _owner_policy_source(
    owner_policy_required: bool,
    evidence_stage: str,
    deep_dive_row: dict[str, Any],
) -> str:
    if not owner_policy_required:
        return "none"
    if deep_dive_row:
        return "review_only_deep_dive_owner_policy"
    return f"evidence_stage:{evidence_stage}"


def _engineering_continue(*, evidence_stage: str, evidence_gaps: list[str]) -> bool:
    if evidence_stage in {"kill"}:
        return False
    if evidence_gaps:
        return True
    return evidence_stage in {
        "promote_review",
        "revise",
        "identity_review",
        "coverage_visibility_review",
        "observe",
        "trial_waiting",
    }


def _trial_candidate_pool(portfolio_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    excluded = []
    for row in portfolio_rows:
        stage = row["evidence_stage"]
        strength = row["evidence_strength"]
        in_pool = False
        pool_stage = ""
        if row["strategy_group_id"] == "MPG-001" and row["execution_tier"] == "L4":
            in_pool = True
            pool_stage = "selected_live_lane_waiting_for_market"
        elif stage == "promote_review":
            in_pool = True
            pool_stage = "promote_review_candidate"
        elif stage == "identity_review" and strength in {
            "strong_observe_only_evidence",
            "material_observe_only_evidence",
        }:
            in_pool = True
            pool_stage = "identity_candidate_review"
        elif row["strategy_group_id"] == "LSR-001" and stage == "revise":
            in_pool = True
            pool_stage = "rewrite_candidate_after_revision"

        if in_pool:
            candidates.append(
                {
                    "strategy_group_id": row["strategy_group_id"],
                    "pool_stage": pool_stage,
                    "execution_tier": row["execution_tier"],
                    "evidence_stage": stage,
                    "trial_eligible": row["trial_eligible"],
                    "live_permission_change": False,
                    "trial_blockers": _dedupe(
                        [
                            *row["evidence_gaps"],
                            "owner_policy_scope_not_confirmed"
                            if row["owner_policy_required"]
                            else "",
                            "real_fresh_signal_absent"
                            if row["strategy_group_id"] == "MPG-001"
                            else "",
                        ]
                    ),
                    "strategy_review_checkpoint": row["strategy_review_checkpoint"],
                }
            )
        else:
            excluded.append(
                {
                    "strategy_group_id": row["strategy_group_id"],
                    "reason": f"not_trial_pool_stage:{stage}",
                    "strategy_review_checkpoint": row["strategy_review_checkpoint"],
                }
            )
    return {
        "status": "trial_candidate_pool_ready",
        "candidate_count": len(candidates),
        "eligible_now_count": sum(1 for row in candidates if row["trial_eligible"]),
        "live_permission_change_count": 0,
        "rows": candidates,
        "excluded_rows": excluded,
        "boundary": (
            "Trial candidate pool is review-only. It does not authorize live "
            "execution, registry admission, tier change, live profile change, "
            "or order submission."
        ),
    }


def _runtime_posture(capture_gap_audit: dict[str, Any]) -> dict[str, Any]:
    owner_state = _as_dict(capture_gap_audit.get("owner_visibility_state"))
    runtime = _as_dict(capture_gap_audit.get("runtime_baseline"))
    p0_state = str(owner_state.get("p0_state") or "")
    return {
        "p0_state": p0_state or "unknown_runtime_state",
        "p0_state_source": (
            "strategy_capture_gap_audit.owner_visibility_state.p0_state"
            if p0_state
            else "missing_capture_gap_owner_visibility_state_p0_state"
        ),
        "signal_observation_state": str(
            owner_state.get("signal_observation_state") or "portfolio_screening_active"
        ),
        "p0_safe_standby": runtime.get("blockers") in ([], None),
        "observation_active": owner_state.get("observation_active") is True,
        "runtime_owner_intervention_required": False,
        "no_live_permission": True,
        "runtime_status_source": "strategy_capture_gap_audit.owner_visibility_state",
    }


def _engineering_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": row["strategy_group_id"],
        "evidence_stage": row["evidence_stage"],
        "strategy_review_checkpoint": row["strategy_review_checkpoint"],
        "evidence_gaps": row["evidence_gaps"],
        "blocked_until": (
            "owner_policy_confirmation"
            if row["owner_policy_required"] and row["evidence_stage"] in {"park"}
            else "engineering_evidence_closure"
        ),
        "does_not_authorize_live_execution": True,
    }


def _owner_policy_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": row["strategy_group_id"],
        "evidence_stage": row["evidence_stage"],
        "policy_source": row["owner_policy_source"],
        "policy_kind": _policy_kind(row),
        "strategy_review_checkpoint_before_policy": row["strategy_review_checkpoint"],
        "runtime_owner_intervention_required": False,
        "live_permission_change": False,
        "does_not_authorize_live_execution": True,
    }


def _policy_kind(row: dict[str, Any]) -> str:
    if row["evidence_stage"] == "identity_review":
        return "formal_candidate_vs_sub_capability_vs_observe_or_park"
    if row["evidence_stage"] == "promote_review":
        return "continue_promote_review_without_tier_or_live_change"
    if row["evidence_stage"] == "park":
        return "keep_parked_or_reopen_only_with_new_edge"
    if row["strategy_group_id"] == "MPG-001":
        return "member_role_exit_decay_without_live_scope_expansion"
    return "strategy_policy_direction"


def _registry_only_rows(
    registry_rows: dict[str, dict[str, Any]], audit_rows: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "strategy_group_id": strategy_group_id,
            "owner_label": _owner_label(strategy_group_id, row, {}),
            "default_tier": str(row.get("default_tier") or "unknown"),
            "trial_eligible": row.get("trial_eligible") is True,
            "reason": "registry_asset_not_in_latest_active_capture_audit",
        }
        for strategy_group_id, row in sorted(registry_rows.items())
        if strategy_group_id not in audit_rows
    ]


def _source_gaps(
    *,
    capture_gap_audit: dict[str, Any],
    review_deep_dive: dict[str, Any] | None,
    owner_policy_package: dict[str, Any] | None,
    quality_closure_wave: dict[str, Any] | None,
    tier_policy: dict[str, Any] | None,
    registry_baseline: dict[str, Any] | None,
) -> list[str]:
    gaps = []
    if capture_gap_audit.get("status") != "strategy_capture_gap_audit_ready":
        gaps.append("capture_gap_audit_not_ready")
    if not review_deep_dive:
        gaps.append("review_deep_dive_missing")
    if not owner_policy_package:
        gaps.append("owner_policy_package_missing")
    if not quality_closure_wave:
        gaps.append("quality_closure_wave_missing")
    if not tier_policy:
        gaps.append("tier_policy_missing")
    if not registry_baseline:
        gaps.append("registry_baseline_missing")
    return gaps


def _review_deep_dive_source_status(artifact: dict[str, Any] | None) -> str:
    status = str((artifact or {}).get("status") or "missing")
    if status == "review_only_deep_dive_ready_for_owner_policy":
        return "review_only_deep_dive_ready_for_owner_policy"
    return status


def _owner_label(
    strategy_group_id: str, registry_row: dict[str, Any], owner_policy_item: dict[str, Any]
) -> str:
    for payload in (registry_row, owner_policy_item):
        value = payload.get("owner_label")
        if isinstance(value, str) and value:
            return value
    return OWNER_LABEL_FALLBACKS.get(strategy_group_id, strategy_group_id)


def _last_evidence_ref(
    strategy_group_id: str, audit_row: dict[str, Any], registry_row: dict[str, Any]
) -> str:
    if audit_row:
        return "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
    refs = registry_row.get("evidence_refs")
    if isinstance(refs, list) and refs:
        first = refs[0] if isinstance(refs[0], dict) else {}
        path = first.get("path")
        if isinstance(path, str) and path:
            return path
    return f"missing_evidence_ref:{strategy_group_id}"


def _registry_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(artifact.get("rows"))
        if row.get("strategy_group_id")
    }


def _tier_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = artifact.get("current_strategy_groups")
    if not isinstance(rows, dict):
        return {}
    return {
        str(strategy_group_id): row
        for strategy_group_id, row in rows.items()
        if isinstance(row, dict)
    }


def _deep_dive_rows_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = _dict_rows(artifact.get("deep_dive_artifacts"))
    return {
        str(row.get("strategy_group_id")): row
        for row in rows
        if row.get("strategy_group_id")
    }


def _owner_policy_items_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policy_items = _dict_rows(artifact.get("owner_policy_items"))
    return {
        str(row.get("strategy_group_id")): row
        for row in policy_items
        if row.get("strategy_group_id")
    }


def _quality_index_by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for section_key in (
        "priority_1_capture_closure",
        "priority_3_identity_review",
    ):
        section = _as_dict(artifact.get(section_key))
        for row in _dict_rows(section.get("rows")):
            if row.get("strategy_group_id"):
                rows[str(row["strategy_group_id"])] = row
    return rows


def _validate_safety(name: str, artifact: dict[str, Any]) -> None:
    safety = _as_dict(artifact.get("safety_invariants"))
    forbidden = _forbidden_effects(safety)
    if forbidden:
        raise ValueError(f"{name} has forbidden effects: {forbidden}")


def _forbidden_effects(safety: dict[str, Any]) -> list[str]:
    return [key for key in FORBIDDEN_EFFECTS if safety.get(key) is True]


def _interaction() -> dict[str, Any]:
    return review_only_interaction("L0_local_strategygroup_portfolio_board")


def _safety_invariants() -> dict[str, bool]:
    return review_only_safety_invariants(include_order_sizing_changed=True)


def _portfolio_markdown(board_artifact: dict[str, Any], output_json: Path) -> str:
    lines = [
        "## StrategyGroup Portfolio Board v0",
        "",
        f"- Status: `{board_artifact['status']}`",
        f"- Portfolio rows: `{board_artifact['portfolio_summary']['portfolio_row_count']}`",
        "- P0 state: "
        + f"`{board_artifact['runtime_posture']['p0_state']}`",
        "- Signal Observation state: "
        + f"`{board_artifact['runtime_posture']['signal_observation_state']}`",
        "- Runtime Owner intervention required: 否",
        "- Live permission change: 否",
        f"- Output: `{output_json}`",
        "",
        "## Portfolio Rows",
        "",
        "| StrategyGroup | Tier | Evidence stage | Opportunities | Cost-after result | Strategy review checkpoint |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in board_artifact["portfolio_rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['strategy_group_id']}`",
                    f"`{row['execution_tier']}`",
                    f"`{row['evidence_stage']}`",
                    str(row["recent_opportunity_count"]),
                    _result_cell(row["cost_after_result_summary"]),
                    f"`{row['strategy_review_checkpoint']}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Engineering Continuation Queue",
            "",
            "| StrategyGroup | Stage | Review checkpoint | Evidence gaps |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in board_artifact["engineering_continuation_queue"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item['strategy_group_id']}`",
                    f"`{item['evidence_stage']}`",
                    f"`{item['strategy_review_checkpoint']}`",
                    _list_or_none([str(value) for value in item["evidence_gaps"]]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- 该看板只做本地 review-only 策略组合治理。",
            "- 不授权真实下单、registry admission、tier policy、live profile、order sizing、FinalGate 或 Operation Layer。",
        ]
    )
    return "\n".join(lines) + "\n"


def _trial_pool_markdown(board_artifact: dict[str, Any], output_path: Path) -> str:
    pool = board_artifact["trial_candidate_pool"]
    lines = [
        "## StrategyGroup Trial Candidate Pool v0",
        "",
        f"- Status: `{pool['status']}`",
        f"- Candidate count: `{pool['candidate_count']}`",
        f"- Trial eligible count: `{pool['eligible_now_count']}`",
        "- Live permission change count: `0`",
        f"- Output: `{output_path}`",
        "",
        "## Candidates",
        "",
        "| StrategyGroup | Pool stage | Tier | Evidence stage | Trial eligible | Strategy review checkpoint |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in pool["rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['strategy_group_id']}`",
                    f"`{row['pool_stage']}`",
                    f"`{row['execution_tier']}`",
                    f"`{row['evidence_stage']}`",
                    _yes_no(bool(row["trial_eligible"])),
                    f"`{row['strategy_review_checkpoint']}`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Boundary", "", pool["boundary"]])
    return "\n".join(lines) + "\n"


def _result_cell(summary: dict[str, Any]) -> str:
    cells = []
    for window in ("4h", "12h", "24h"):
        row = _as_dict(summary.get(window))
        completed = _int(row.get("completed"))
        tradable = _int(row.get("tradable_mfe_after_cost_count"))
        pending = _int(row.get("pending"))
        if completed or tradable or pending:
            cells.append(f"{window}:{tradable}/{completed}+{pending}p")
    return ", ".join(cells) if cells else "none"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON at {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_object(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _dedupe(values: Any) -> list[str]:
    return [value for value in dict.fromkeys(str(item) for item in values if item)]


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


if __name__ == "__main__":
    raise SystemExit(main())
