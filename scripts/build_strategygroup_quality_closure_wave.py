#!/usr/bin/env python3
"""Build the StrategyGroup quality closure wave artifact.

This command turns current StrategyGroup capture-audit and Strategy Asset State
evidence into review artifacts, Owner policy_items, identity-review artifacts,
MPG member review rows, and forward/no-action rollups. It is local/read-only
decision support and never creates live authority.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import non_executing_interaction  # noqa: E402

DEFAULT_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_STRATEGY_ASSET_STATE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.json"
)
DEFAULT_REGISTRY_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_MPG_REPLAY_CORPUS_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.md"
)

PRIORITY_CAPTURE_GROUPS = ("BTPC-001", "LSR-001", "BRF-001")
WAVE_1_REQUIRED_GROUPS = (
    "MPG-001",
    "BTPC-001",
    "LSR-001",
    "BRF-001",
    "MI-001",
    "CPM-RO-001",
)
WAVE_1_VISIBILITY_GROUPS = ("FBS-001", "SOR-001", "VCB-001", "TEQ-001")
WAVE_2_CAPTURE_GROUPS = ("BTPC-001", "LSR-001", "BRF-001", "VCB-001", "RBR-001")
IDENTITY_REVIEW_GROUPS = ("MI-001", "CPM-RO-001")
VISIBILITY_GROUPS = ("MPG-001", "SOR-001", "FBS-001")

OWNER_REVIEW_LABEL = {
    "promote": "晋级复核",
    "revise": "调整",
    "park": "暂停",
    "kill": "停用",
    "keep_observing": "待复盘",
}

WAVE_2_CAPTURE_SPECS = {
    "BTPC-001": {
        "current_problem": "169/169 windows are attributed to stale gate or fact-source blocking.",
        "closure_action": "review_stale_gate_fact_source_classifier_attribution",
        "review_outcome": "revise",
    },
    "LSR-001": {
        "current_problem": "side-specific short-revival has would-enter evidence but needs range-context review.",
        "closure_action": "side_specific_short_revival_range_context_review",
        "review_outcome": "revise",
    },
    "BRF-001": {
        "current_problem": "bear-rally failure short structure appeared, but squeeze and RequiredFacts review are incomplete.",
        "closure_action": "forward_outcome_squeeze_classifier_requiredfacts_review",
        "review_outcome": "promote_review",
    },
    "VCB-001": {
        "current_problem": "breakout structure appeared but true/false breakout quality is not strong enough for promotion.",
        "closure_action": "true_false_breakout_classifier_review",
        "review_outcome": "keep_observing_or_revise",
    },
    "RBR-001": {
        "current_problem": "positive observe-only samples exist, but the lane remains parked without materially new edge evidence.",
        "closure_action": "material_new_edge_review_before_reactivation",
        "review_outcome": "park_unless_new_edge",
    },
}

MPG_MEMBER_REVIEW_ROWS = [
    {
        "member_id": "TSI-001",
        "provisional_role": "core_member_candidate",
        "review_focus": "right_tail_return_vs_drawdown_decay",
        "recommended_action": "keep_core_candidate_but_require_decay_control",
    },
    {
        "member_id": "MHI-001",
        "provisional_role": "high_risk_member",
        "review_focus": "high_return_high_drawdown_survivability",
        "recommended_action": "downshift_or_park_review_before_live_expansion",
    },
    {
        "member_id": "PPO-001",
        "provisional_role": "support_member",
        "review_focus": "middle_return_middle_drawdown_stability",
        "recommended_action": "keep_observing_as_support_member",
    },
    {
        "member_id": "DMI-001",
        "provisional_role": "ignition_support_or_independent_observer",
        "review_focus": "member_vs_independent_strategy_boundary",
        "recommended_action": "identity_boundary_review",
    },
    {
        "member_id": "WPR-001",
        "provisional_role": "confirmation_member",
        "review_focus": "conservative_momentum_confirmation_value",
        "recommended_action": "keep_as_confirmation_candidate",
    },
    {
        "member_id": "MFI-001",
        "provisional_role": "risk_damper_or_scorer",
        "review_focus": "low_drawdown_low_return_filter_value",
        "recommended_action": "keep_as_scorer_not_primary_member",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-gap-audit-json",
        default=str(DEFAULT_CAPTURE_GAP_AUDIT_JSON),
    )
    parser.add_argument(
        "--strategy-asset-state-json",
        dest="strategy_asset_state_source_json",
        metavar="STRATEGY_ASSET_STATE_JSON",
        default=str(DEFAULT_STRATEGY_ASSET_STATE_JSON),
    )
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument(
        "--mpg-replay-corpus-json",
        default=str(DEFAULT_MPG_REPLAY_CORPUS_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_quality_closure_wave(
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        strategy_asset_state_source=_load_json_object(
            Path(args.strategy_asset_state_source_json)
        ),
        registry=_load_json_object(Path(args.registry_json)),
        tier_policy=_load_json_object(Path(args.tier_policy_json)),
        mpg_replay_corpus=_load_json_object(Path(args.mpg_replay_corpus_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(artifact, output_json, output_md), encoding="utf-8")
    print(json.dumps({"status": artifact["status"], "output_json": str(output_json)}, ensure_ascii=False))
    return 0


def build_quality_closure_wave(
    *,
    capture_gap_audit: dict[str, Any],
    strategy_asset_state_source: dict[str, Any],
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    mpg_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    registry_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(registry.get("rows"))
    }
    strategy_asset_by_group, strategy_asset_state_source_info = (
        _strategy_asset_rows_by_group(strategy_asset_state_source)
    )
    audit_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows"))
    }
    closure_by_group = _closure_rows_by_group(capture_gap_audit)
    current_tiers = _current_tiers(tier_policy, registry_by_group)

    priority_capture_closure = [
        _priority_capture_row(
            group,
            audit_by_group=audit_by_group,
            closure_by_group=closure_by_group,
            strategy_asset_by_group=strategy_asset_by_group,
            registry_by_group=registry_by_group,
            current_tiers=current_tiers,
        )
        for group in PRIORITY_CAPTURE_GROUPS
    ]
    owner_policy_items = [
        _owner_policy_item(
            group,
            registry_row=registry_by_group.get(group, {}),
            strategy_asset_row=strategy_asset_by_group.get(group, {}),
            audit_row=audit_by_group.get(group, {}),
            current_tier=current_tiers.get(group, "unknown"),
        )
        for group in sorted(set(registry_by_group) | set(strategy_asset_by_group))
    ]
    identity_review_rows = [
        _identity_review_row(
            group,
            audit_row=audit_by_group.get(group, {}),
            closure_row=closure_by_group.get(group, {}),
            strategy_asset_row=strategy_asset_by_group.get(group, {}),
        )
        for group in IDENTITY_REVIEW_GROUPS
    ]
    mpg_member_tiering_review = _mpg_member_tiering_review(
        registry_by_group.get("MPG-001", {}),
        mpg_replay_corpus,
    )
    wave_1_strategy_explainer = _wave_1_strategy_explainer(owner_policy_items)
    wave_2_capture_quality_closure = _wave_2_capture_quality_closure(
        audit_by_group=audit_by_group,
        closure_by_group=closure_by_group,
        strategy_asset_by_group=strategy_asset_by_group,
        registry_by_group=registry_by_group,
        current_tiers=current_tiers,
    )
    wave_3_mpg_member_deepening = _wave_3_mpg_member_deepening(
        mpg_member_tiering_review
    )
    forward_no_action_ledger_extension = _forward_no_action_ledger_extension(
        capture_gap_audit,
        strategy_asset_by_group,
    )
    owner_confirmation_checkpoint = _owner_confirmation_checkpoint(
        priority_capture_closure,
        identity_review_rows,
        mpg_member_tiering_review,
    )

    return {
        "schema": "brc.strategygroup_quality_closure_wave.v1",
        "scope": "P0_5_strategygroup_quality_closure",
        "status": "quality_closure_wave_ready",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "closed_engineering_problem": (
            "Strategy capture findings, identity ambiguity, Owner explanation, "
            "MPG member review, and forward/no-action evidence are now projected "
            "from current audit/ledger sources into one comparable review artifact."
        ),
        "capability_unlocked": (
            "Owner can review strategy-quality decisions without reading raw "
            "would_enter/no_action samples, while runtime authority remains false."
        ),
        "next_engineering_bottleneck": (
            "Owner policy decision is required before promote, park, kill, lane "
            "change, or live-profile changes."
        ),
        "source_status": {
            "capture_gap_audit": capture_gap_audit.get("status"),
            "strategy_asset_state": strategy_asset_state_source.get("status"),
            "strategy_asset_state_source": strategy_asset_state_source_info,
            "registry": registry.get("status"),
            "tier_policy_groups": len(current_tiers),
            "mpg_replay_sample_count": len(_dict_rows(mpg_replay_corpus.get("replay_samples"))),
        },
        "strategy_asset_state_source": strategy_asset_state_source_info,
        "priority_order": [
            "wave_1_strategy_explainer",
            "wave_2_capture_quality_closure",
            "wave_3_mpg_member_deepening",
            "priority_1_btpc_lsr_brf_capture_closure",
            "priority_2_owner_policy_items_v1_from_ledger",
            "priority_3_mi_cpm_registry_identity_review",
            "priority_4_mpg_member_tiering_exit_decay_review",
            "priority_5_forward_outcome_no_action_ledger_extension",
        ],
        "wave_1_strategy_explainer": wave_1_strategy_explainer,
        "wave_2_capture_quality_closure": wave_2_capture_quality_closure,
        "wave_3_mpg_member_deepening": wave_3_mpg_member_deepening,
        "priority_1_capture_closure": {
            "status": "ready_for_owner_review",
            "rows": priority_capture_closure,
        },
        "priority_2_owner_policy_items_v1": {
            "status": "ready",
            "policy_item_count": len(owner_policy_items),
            "policy_items": owner_policy_items,
        },
        "priority_3_identity_review": {
            "status": "ready_for_owner_review",
            "rows": identity_review_rows,
        },
        "priority_4_mpg_member_tiering_exit_decay_review": mpg_member_tiering_review,
        "priority_5_forward_outcome_no_action_ledger_extension": forward_no_action_ledger_extension,
        "owner_confirmation_checkpoint": owner_confirmation_checkpoint,
        "interaction": non_executing_interaction(
            "L0_local_strategy_quality_closure"
        ),
        "safety_invariants": {
            "local_review_only": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "live_profile_changed": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
            "preview_or_replay_treated_as_live_signal": False,
        },
    }


def _wave_1_strategy_explainer(owner_policy_items: list[dict[str, Any]]) -> dict[str, Any]:
    policy_items_by_group = {str(policy_item.get("strategy_group_id")): policy_item for policy_item in owner_policy_items}
    required_groups = list(WAVE_1_REQUIRED_GROUPS)
    visibility_groups = list(WAVE_1_VISIBILITY_GROUPS)
    required_missing = [
        group for group in required_groups + visibility_groups if group not in policy_items_by_group
    ]
    policy_items = [
        _wave_1_policy_item(policy_items_by_group[group])
        for group in required_groups + visibility_groups
        if group in policy_items_by_group
    ]
    return {
        "status": "ready" if not required_missing else "incomplete_missing_policy_items",
        "purpose": "turn StrategyGroup ids into Owner-readable strategy assets",
        "required_groups": required_groups,
        "visibility_groups": visibility_groups,
        "policy_item_count": len(policy_items),
        "missing_required_policy_items": required_missing,
        "done_when": {
            "strategy_assets_are_owner_readable": not required_missing,
            "policy_items_explain_why_not_live": all(policy_item["why_not_live"] for policy_item in policy_items),
            "policy_items_separate_owner_policy_from_system_action": all(
                policy_item["owner_policy_review_scope"]
                and policy_item["strategy_review_checkpoint"]
                for policy_item in policy_items
            ),
        },
        "policy_items": policy_items,
        "authority_boundary": _review_only_boundary(),
    }


def _wave_1_policy_item(policy_item: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": policy_item["strategy_group_id"],
        "owner_label": policy_item["owner_label"],
        "current_tier": policy_item["current_tier"],
        "eats_market_structure": policy_item["market_opportunity"],
        "trade_logic": policy_item["trade_logic"],
        "why_not_live": policy_item["why_not_live"],
        "current_risk": policy_item["main_risks"] or ["strategy_quality_or_identity_risk_not_yet_closed"],
        "missing_facts": policy_item["missing_evidence"],
        "owner_policy_review_scope": _owner_policy_review_scope(policy_item),
        "strategy_review_checkpoint": policy_item["strategy_review_checkpoint"],
        "next_evidence": policy_item["missing_evidence"],
        "live_permission_change_recommended_now": False,
    }


def _wave_2_capture_quality_closure(
    *,
    audit_by_group: dict[str, dict[str, Any]],
    closure_by_group: dict[str, dict[str, Any]],
    strategy_asset_by_group: dict[str, dict[str, Any]],
    registry_by_group: dict[str, dict[str, Any]],
    current_tiers: dict[str, str],
) -> dict[str, Any]:
    rows = [
        _wave_2_capture_row(
            group,
            audit_row=audit_by_group.get(group, {}),
            closure_row=closure_by_group.get(group, {}),
            strategy_asset_row=strategy_asset_by_group.get(group, {}),
            registry_row=registry_by_group.get(group, {}),
            current_tier=current_tiers.get(group, "unknown"),
        )
        for group in WAVE_2_CAPTURE_GROUPS
    ]
    return {
        "status": "ready_for_owner_review",
        "purpose": "answer where capture quality failed without changing live authority",
        "rows": rows,
        "done_when": {
            "btpc_lsr_brf_have_closure_rows": all(
                group in {row["strategy_group_id"] for row in rows}
                for group in PRIORITY_CAPTURE_GROUPS
            ),
            "vcb_rbr_are_not_hidden_in_forward_rollup": all(
                group in {row["strategy_group_id"] for row in rows}
                for group in ("VCB-001", "RBR-001")
            ),
            "all_rows_are_review_only": all(
                row["live_permission_change_recommended_now"] is False
                and row["authority_boundary"] == _review_only_boundary()
                for row in rows
            ),
        },
        "authority_boundary": _review_only_boundary(),
    }


def _wave_2_capture_row(
    group: str,
    *,
    audit_row: dict[str, Any],
    closure_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
    registry_row: dict[str, Any],
    current_tier: str,
) -> dict[str, Any]:
    spec = WAVE_2_CAPTURE_SPECS[group]
    strategy_asset_current_decision = str(
        strategy_asset_row.get("current_decision") or "unknown"
    )
    return {
        "strategy_group_id": group,
        "owner_label": registry_row.get("owner_label") or group,
        "current_tier": current_tier,
        "current_problem": spec["current_problem"],
        "closure_action": spec["closure_action"],
        "review_outcome": spec["review_outcome"],
        "strategy_asset_current_decision": strategy_asset_current_decision,
        "would_enter_count": _int(audit_row.get("would_enter_count") or closure_row.get("would_enter_count")),
        "no_action_count": _int(audit_row.get("no_action_count") or closure_row.get("no_action_count")),
        "high_priority_no_action_count": _int(
            audit_row.get("high_priority_no_action_count")
            or closure_row.get("high_priority_no_action_count")
        ),
        "would_enter_forward_positive_count": _int(
            audit_row.get("would_enter_forward_positive_count")
            or closure_row.get("would_enter_forward_positive_count")
        ),
        "missed_no_action_forward_positive_count": _int(
            audit_row.get("missed_no_action_forward_positive_count")
            or closure_row.get("missed_no_action_forward_positive_count")
        ),
        "dominant_blocker_classes": audit_row.get("dominant_blocker_classes", []),
        "next_checkpoint": strategy_asset_row.get("next_checkpoint")
        or registry_row.get("required_next_evidence")
        or spec["closure_action"],
        "owner_policy_confirmation_required_later": strategy_asset_current_decision
        in {"promote", "park", "kill"},
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _wave_3_mpg_member_deepening(
    mpg_member_tiering_review: dict[str, Any],
) -> dict[str, Any]:
    member_rows = _dict_rows(mpg_member_tiering_review.get("member_rows"))
    member_ids = {str(row.get("member_id")) for row in member_rows}
    required_member_ids = {str(row["member_id"]) for row in MPG_MEMBER_REVIEW_ROWS}
    return {
        "status": "ready_for_owner_review",
        "purpose": "explain MPG member roles, drawdown risk, and exit/decay review before live scope expansion",
        "strategy_group_id": "MPG-001",
        "current_tier": mpg_member_tiering_review.get("current_tier"),
        "member_count": len(member_rows),
        "member_rows": member_rows,
        "exit_decay_review": mpg_member_tiering_review.get("exit_decay_review"),
        "done_when": {
            "six_member_roles_present": required_member_ids.issubset(member_ids),
            "exit_horizons_present": bool(
                _as_dict(mpg_member_tiering_review.get("exit_decay_review")).get(
                    "exit_horizons_to_review"
                )
            ),
            "decay_controls_present": bool(
                _as_dict(mpg_member_tiering_review.get("exit_decay_review")).get(
                    "decay_controls_to_review"
                )
            ),
            "no_live_scope_expansion": mpg_member_tiering_review.get(
                "live_permission_change_recommended_now"
            )
            is False,
        },
        "owner_policy_confirmation_required": True,
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _priority_capture_row(
    group: str,
    *,
    audit_by_group: dict[str, dict[str, Any]],
    closure_by_group: dict[str, dict[str, Any]],
    strategy_asset_by_group: dict[str, dict[str, Any]],
    registry_by_group: dict[str, dict[str, Any]],
    current_tiers: dict[str, str],
) -> dict[str, Any]:
    audit = audit_by_group.get(group, {})
    closure = closure_by_group.get(group, {})
    strategy_asset_row = strategy_asset_by_group.get(group, {})
    registry = registry_by_group.get(group, {})
    diagnosis = {
        "BTPC-001": "stale_fact_source_classifier_attribution_is_too_coarse",
        "LSR-001": "side_specific_short_revival_rewrite_needs_closure",
        "BRF-001": "bear_rally_failure_short_has_review_worthy_window_but_squeeze_requiredfacts_need_review",
    }.get(group, "capture_quality_review")
    return {
        "strategy_group_id": group,
        "current_tier": current_tiers.get(group, "unknown"),
        "strategy_asset_current_decision": strategy_asset_row.get(
            "current_decision",
            "unknown",
        ),
        "owner_review_label": OWNER_REVIEW_LABEL.get(
            str(strategy_asset_row.get("current_decision")),
            "待复盘",
        ),
        "would_enter_count": _int(audit.get("would_enter_count") or closure.get("would_enter_count")),
        "high_priority_no_action_count": _int(
            audit.get("high_priority_no_action_count") or closure.get("high_priority_no_action_count")
        ),
        "would_enter_forward_positive_count": _int(
            audit.get("would_enter_forward_positive_count")
            or closure.get("would_enter_forward_positive_count")
        ),
        "missed_no_action_forward_positive_count": _int(
            audit.get("missed_no_action_forward_positive_count")
            or closure.get("missed_no_action_forward_positive_count")
        ),
        "dominant_blocker_classes": audit.get("dominant_blocker_classes", []),
        "diagnosis": diagnosis,
        "required_next_evidence": strategy_asset_row.get(
            "required_next_evidence",
            registry.get("required_next_evidence", "continue_review"),
        ),
        "next_checkpoint": strategy_asset_row.get(
            "next_checkpoint",
            "continue_review",
        ),
        "owner_policy_confirmation_required_now": False,
        "owner_policy_confirmation_after_review": group in {"BRF-001"},
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _owner_policy_item(
    group: str,
    *,
    registry_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
    audit_row: dict[str, Any],
    current_tier: str,
) -> dict[str, Any]:
    decision = str(strategy_asset_row.get("current_decision") or "unknown")
    risk_gaps = _risk_gap_items(registry_row)
    return {
        "strategy_group_id": group,
        "owner_label": registry_row.get("owner_label") or group,
        "one_line": registry_row.get("edge_thesis") or _default_one_line(group, decision),
        "market_opportunity": registry_row.get("regime_fit") or "current registry identity is incomplete",
        "trade_logic": registry_row.get("trade_logic") or "review-only strategy identity; no execution authority",
        "current_tier": current_tier,
        "owner_visible_status": _owner_visible_status(decision),
        "review_recommendation": decision,
        "owner_review_label": OWNER_REVIEW_LABEL.get(decision, "待复盘"),
        "why_not_live": _why_not_live(registry_row, strategy_asset_row),
        "missing_evidence": strategy_asset_row.get("required_next_evidence")
        or registry_row.get("required_next_evidence")
        or "strategy identity or evidence still needs review",
        "main_risks": risk_gaps[:5],
        "strategy_review_checkpoint": strategy_asset_row.get(
            "next_checkpoint",
            "continue_strategy_review",
        ),
        "owner_policy_confirmation_later": decision
        in {"promote", "park", "kill", "revise"},
        "live_permission_change_recommended_now": False,
    }


def _identity_review_row(
    group: str,
    *,
    audit_row: dict[str, Any],
    closure_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
) -> dict[str, Any]:
    would_enter = _int(audit_row.get("would_enter_count") or closure_row.get("would_enter_count"))
    forward_positive = _int(
        audit_row.get("would_enter_forward_positive_count")
        or closure_row.get("would_enter_forward_positive_count")
    )
    options = (
        [
            "keep_as_smoke_lane",
            "map_as_mpg_member_or_support_capability",
            "promote_to_formal_candidate_review",
            "park_until_identity_evidence_improves",
        ]
        if group == "MI-001"
        else [
            "keep_as_observation_asset",
            "merge_into_existing_capture_family",
            "park_as_mixed_quality_lane",
            "kill_if_forward_quality_decays",
        ]
    )
    return {
        "strategy_group_id": group,
        "would_enter_count": would_enter,
        "would_enter_forward_positive_count": forward_positive,
        "strategy_asset_current_decision": strategy_asset_row.get(
            "current_decision",
            "unknown",
        ),
        "identity_problem": (
            "strong_would_enter_but_smoke_or_member_identity_unclear"
            if group == "MI-001"
            else "would_enter_present_but_registry_scope_unclear"
        ),
        "owner_policy_options": options,
        "system_recommendation": "prepare_registry_identity_review_no_tier_change",
        "owner_policy_confirmation_required": True,
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _mpg_member_tiering_review(
    mpg_registry_row: dict[str, Any],
    mpg_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    replay_samples = _dict_rows(mpg_replay_corpus.get("replay_samples"))
    blocker_counts = Counter(str(row.get("blocker_class") or "unknown") for row in replay_samples)
    owner_state_counts = Counter(str(row.get("expected_owner_state") or "unknown") for row in replay_samples)
    return {
        "status": "ready_for_owner_review",
        "strategy_group_id": "MPG-001",
        "current_tier": mpg_registry_row.get("default_tier", "L4"),
        "review_basis": "registry_plus_replay_corpus_plus_owner_supplied_member_strengthening_summary",
        "replay_sample_count": len(replay_samples),
        "replay_blocker_counts": dict(sorted(blocker_counts.items())),
        "expected_owner_state_counts": dict(sorted(owner_state_counts.items())),
        "member_rows": MPG_MEMBER_REVIEW_ROWS,
        "exit_decay_review": {
            "status": "needed_before_any_live_scope_expansion",
            "exit_horizons_to_review": ["6h", "12h", "24h", "72h"],
            "decay_controls_to_review": [
                "momentum_exhaustion_disable",
                "member_specific_decay",
                "rolling_window_decay_detection",
                "post_right_tail_giveback_control",
            ],
        },
        "owner_policy_confirmation_required": True,
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _forward_no_action_ledger_extension(
    capture_gap_audit: dict[str, Any],
    strategy_asset_by_group: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for row in _dict_rows(capture_gap_audit.get("strategy_expectation_rows")):
        group = str(row.get("strategy_group_id"))
        rows.append(
            {
                "strategy_group_id": group,
                "would_enter_count": _int(row.get("would_enter_count")),
                "no_action_count": _int(row.get("no_action_count")),
                "high_priority_no_action_count": _int(row.get("high_priority_no_action_count")),
                "would_enter_forward_positive_count": _int(row.get("would_enter_forward_positive_count")),
                "missed_no_action_forward_positive_count": _int(row.get("missed_no_action_forward_positive_count")),
                "strategy_asset_current_decision": _as_dict(
                    strategy_asset_by_group.get(group)
                ).get("current_decision", "unknown"),
                "ledger_extension_class": _ledger_extension_class(row),
            }
        )
    return {
        "status": "ready",
        "row_count": len(rows),
        "rows": rows,
        "summary": {
            "would_enter_total": _int(
                _as_dict(capture_gap_audit.get("system_observation_summary")).get("would_enter_count")
            ),
            "high_priority_no_action_total": _int(
                _as_dict(capture_gap_audit.get("system_observation_summary")).get("high_priority_no_action_count")
            ),
            "forward_outcome_status_split_present": True,
        },
        "authority_boundary": _review_only_boundary(),
    }


def _owner_confirmation_checkpoint(
    priority_capture_closure: list[dict[str, Any]],
    identity_review_rows: list[dict[str, Any]],
    mpg_member_tiering_review: dict[str, Any],
) -> dict[str, Any]:
    decisions = []
    for row in priority_capture_closure:
        if row.get("owner_policy_confirmation_after_review"):
            decisions.append(
                {
                    "strategy_group_id": row["strategy_group_id"],
                    "decision_type": "promote_or_keep_l1_review",
                    "current_recommendation": row["strategy_asset_current_decision"],
                }
            )
    for row in identity_review_rows:
        decisions.append(
            {
                "strategy_group_id": row["strategy_group_id"],
                "decision_type": "registry_identity",
                "current_recommendation": row["system_recommendation"],
            }
        )
    decisions.append(
        {
            "strategy_group_id": "MPG-001",
            "decision_type": "member_tiering_exit_decay",
            "current_recommendation": "review_member_roles_before_live_scope_expansion",
        }
    )
    return {
        "owner_confirmation_required": True,
        "runtime_owner_intervention_required": False,
        "decision_count": len(decisions),
        "decisions": decisions,
        "hard_stop": (
            "Do not promote, park, kill, change tier policy, change live profile, "
            "or expand real-order scope without Owner confirmation."
        ),
        "mpg_member_review_status": mpg_member_tiering_review.get("status"),
    }


def _closure_rows_by_group(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    closure = _as_dict(artifact.get("priority_line_closure"))
    rows: list[dict[str, Any]] = []
    for key in (
        "phase2_priority_strategy_lines",
        "phase3_registry_identity_review",
        "phase4_visibility_review",
    ):
        rows.extend(_dict_rows(closure.get(key)))
    return {str(row.get("strategy_group_id")): row for row in rows}


def _current_tiers(
    tier_policy: dict[str, Any],
    registry_by_group: dict[str, dict[str, Any]],
) -> dict[str, str]:
    output = {
        group: str(_as_dict(data).get("tier") or "unknown")
        for group, data in _as_dict(tier_policy.get("current_strategy_groups")).items()
    }
    known_new = _as_dict(_as_dict(tier_policy.get("new_strategy_group_defaults")).get("known_new_groups"))
    for base, tier in known_new.items():
        output.setdefault(f"{base}-001", str(tier or "unknown"))
    for group, row in registry_by_group.items():
        output.setdefault(group, str(row.get("default_tier") or "unknown"))
    return output


def _ledger_extension_class(row: dict[str, Any]) -> str:
    if _int(row.get("would_enter_count")) > 0:
        return "would_enter_observed"
    if _int(row.get("high_priority_no_action_count")) > 0:
        return "high_priority_no_action_observed"
    return "visibility_only_or_no_recent_structure"


def _owner_policy_review_scope(policy_item: dict[str, Any]) -> str:
    decision = str(policy_item.get("review_recommendation") or "unknown")
    if policy_item.get("strategy_group_id") in {"MI-001", "CPM-RO-001"}:
        return "decide registry identity from review artifact"
    if policy_item.get("strategy_group_id") == "MPG-001":
        return "decide member tiering and exit-decay policy from review artifact"
    if decision == "promote":
        return "decide promote review outcome from review evidence"
    if decision == "revise":
        return "approve or reject revised strategy direction from review evidence"
    if decision == "park":
        return "confirm park decision or request materially new evidence"
    if decision == "kill":
        return "confirm kill decision after review evidence"
    return "no immediate Owner action; review only if evidence changes"


def _owner_visible_status(decision: str) -> str:
    if decision == "promote":
        return "待复盘"
    if decision == "revise":
        return "待调整"
    if decision == "park":
        return "已暂停"
    if decision == "kill":
        return "停用复核"
    return "等待机会"


def _why_not_live(
    registry_row: dict[str, Any],
    strategy_asset_row: dict[str, Any],
) -> str:
    if registry_row:
        return "registry-baseline rows are strategy assets only and cannot authorize execution"
    if strategy_asset_row:
        return "strategy-asset-state evidence is review-only and cannot authorize execution"
    return "no current runtime authority"


def _risk_gap_items(registry_row: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for risk_class, payload in sorted(_as_dict(registry_row.get("risk_gaps")).items()):
        for item in _as_dict(payload).get("items") or []:
            output.append(f"{risk_class}:{item}")
    return output


def _default_one_line(group: str, decision: str) -> str:
    return f"{group} is currently {decision} in Strategy Asset State."


def _review_only_boundary() -> str:
    return (
        "local_review_only; no FinalGate; no Operation Layer; no exchange write; "
        "no tier policy change; no live profile change; no real order authority"
    )


def _markdown(artifact: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Quality Closure Wave",
        "",
        "## Summary",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Closed problem: {artifact['closed_engineering_problem']}",
        f"- Capability unlocked: {artifact['capability_unlocked']}",
        f"- Next bottleneck: {artifact['next_engineering_bottleneck']}",
        "- Live permission change: `false`",
        "",
        "## Wave 1 Strategy Explainer",
        "",
        "| StrategyGroup | Label | Tier | Eats structure | Why not live | Owner can decide | Strategy checkpoint |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for policy_item in artifact["wave_1_strategy_explainer"]["policy_items"]:
        lines.append(
            "| `{}` | {} | `{}` | {} | `{}` | {} | `{}` |".format(
                policy_item["strategy_group_id"],
                policy_item["owner_label"],
                policy_item["current_tier"],
                policy_item["eats_market_structure"],
                policy_item["why_not_live"],
                policy_item["owner_policy_review_scope"],
                policy_item["strategy_review_checkpoint"],
            )
        )
    lines.extend(
        [
            "",
            "## Wave 2 Capture Quality Closure",
            "",
            "| StrategyGroup | Problem | Checkpoint | Review | Would enter | High-priority no_action | WE positive | Missed NA positive |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in artifact["wave_2_capture_quality_closure"]["rows"]:
        lines.append(
            "| `{}` | {} | `{}` | `{}` | {} | {} | {} | {} |".format(
                row["strategy_group_id"],
                row["current_problem"],
                row["closure_action"],
                row["review_outcome"],
                row["would_enter_count"],
                row["high_priority_no_action_count"],
                row["would_enter_forward_positive_count"],
                row["missed_no_action_forward_positive_count"],
            )
        )
    lines.extend(
        [
            "",
            "## Wave 3 MPG Member Deepening",
            "",
            "| Member | Role | Review focus | Recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in artifact["wave_3_mpg_member_deepening"]["member_rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row["member_id"],
                row["provisional_role"],
                row["review_focus"],
                row["recommended_action"],
            )
        )
    lines.extend(
        [
            "",
        "## Priority 1 Capture Closure",
        "",
        "| StrategyGroup | Tier | Strategy Asset decision | Would enter | High-priority no_action | Forward positives | Next |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in artifact["priority_1_capture_closure"]["rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} / {} | `{}` |".format(
                row["strategy_group_id"],
                row["current_tier"],
                row["strategy_asset_current_decision"],
                row["would_enter_count"],
                row["high_priority_no_action_count"],
                row["would_enter_forward_positive_count"],
                row["missed_no_action_forward_positive_count"],
                row["next_checkpoint"],
            )
        )
    lines.extend(
        [
            "",
            "## Priority 2 Owner Policy items",
            "",
            "| StrategyGroup | Label | Tier | Owner status | Review | Missing evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for policy_item in artifact["priority_2_owner_policy_items_v1"]["policy_items"]:
        lines.append(
            "| `{}` | {} | `{}` | {} | `{}` | `{}` |".format(
                policy_item["strategy_group_id"],
                policy_item["owner_label"],
                policy_item["current_tier"],
                policy_item["owner_visible_status"],
                policy_item["review_recommendation"],
                policy_item["missing_evidence"],
            )
        )
    lines.extend(
        [
            "",
            "## Priority 3 Identity Review",
            "",
            "| StrategyGroup | Would enter | Forward positive | Problem | Options |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in artifact["priority_3_identity_review"]["rows"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | {} |".format(
                row["strategy_group_id"],
                row["would_enter_count"],
                row["would_enter_forward_positive_count"],
                row["identity_problem"],
                ", ".join(f"`{item}`" for item in row["owner_policy_options"]),
            )
        )
    lines.extend(
        [
            "",
            "## Priority 4 MPG Member Review",
            "",
            "| Member | Role | Review focus | Recommendation |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in artifact["priority_4_mpg_member_tiering_exit_decay_review"]["member_rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row["member_id"],
                row["provisional_role"],
                row["review_focus"],
                row["recommended_action"],
            )
        )
    lines.extend(
        [
            "",
            "## Priority 5 Forward / No-Action Ledger Extension",
            "",
            "| StrategyGroup | Class | Would enter | No action | High-priority no_action | WE positive | Missed NA positive |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in artifact["priority_5_forward_outcome_no_action_ledger_extension"]["rows"]:
        lines.append(
            "| `{}` | `{}` | {} | {} | {} | {} | {} |".format(
                row["strategy_group_id"],
                row["ledger_extension_class"],
                row["would_enter_count"],
                row["no_action_count"],
                row["high_priority_no_action_count"],
                row["would_enter_forward_positive_count"],
                row["missed_no_action_forward_positive_count"],
            )
        )
    checkpoint = artifact["owner_confirmation_checkpoint"]
    lines.extend(
        [
            "",
            "## Owner Confirmation Checkpoint",
            "",
            f"- Owner confirmation required: `{str(checkpoint['owner_confirmation_required']).lower()}`",
            f"- Runtime Owner intervention required: `{str(checkpoint['runtime_owner_intervention_required']).lower()}`",
            f"- Decision count: `{checkpoint['decision_count']}`",
            f"- Hard stop: {checkpoint['hard_stop']}",
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
        ]
    )
    return "\n".join(lines) + "\n"


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _strategy_asset_rows_by_group(
    strategy_asset_state_source: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    strategy_asset_state = _as_dict(
        strategy_asset_state_source.get("strategy_asset_state")
    )
    asset_rows = _dict_rows(strategy_asset_state.get("asset_rows"))
    if asset_rows:
        rows = [
            _strategy_asset_row_from_strategy_asset_state(row)
            for row in asset_rows
        ]
        return _rows_by_group(rows), {
            "source": "strategy_asset_state.asset_rows",
            "row_count": len(rows),
            "missing_current_decision_count": _missing_current_decision_count(asset_rows),
        }
    return {}, {
        "source": "missing_strategy_asset_state",
        "row_count": 0,
        "missing_current_decision_count": 0,
    }


def _strategy_asset_row_from_strategy_asset_state(
    row: dict[str, Any],
) -> dict[str, Any]:
    promotion_target = str(row.get("promotion_target") or "not_applicable")
    decision = str(row.get("current_decision") or "unknown")
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or "unknown"),
        "tier": str(row.get("current_tier") or "unknown"),
        "current_decision": _display_decision(decision, promotion_target),
        "promotion_scope": _display_promotion_scope(row),
        "promotion_target": promotion_target,
        "required_next_evidence": str(row.get("required_next_evidence") or ""),
        "next_checkpoint": str(row.get("next_checkpoint") or ""),
        "reason": str(row.get("reason") or ""),
    }


def _display_decision(decision: str, promotion_target: str) -> str:
    if decision == "promote" and promotion_target == "promotion_evidence_review_only":
        return "promote_review_only"
    return decision


def _display_promotion_scope(row: dict[str, Any]) -> str:
    scope = str(row.get("promotion_scope") or "")
    if scope:
        return scope
    if row.get("trial_eligible") is True:
        return "trial_eligible"
    return "not_applicable"


def _missing_current_decision_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if not str(row.get("current_decision") or "").strip())


def _rows_by_group(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("strategy_group_id")): row for row in rows}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
