#!/usr/bin/env python3
"""Build the StrategyGroup quality closure wave packet.

This command turns current StrategyGroup capture-audit and decision-ledger
evidence into review packets, Owner cards, identity-review packets, MPG member
review rows, and forward/no-action ledger rollups. It is local/read-only
decision support and never creates live authority.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_DECISION_LEDGER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
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
IDENTITY_REVIEW_GROUPS = ("MI-001", "CPM-RO-001")
VISIBILITY_GROUPS = ("MPG-001", "SOR-001", "FBS-001")

OWNER_REVIEW_LABEL = {
    "promote": "晋级复核",
    "revise": "调整",
    "park": "暂停",
    "kill": "停用",
    "keep_observing": "待复盘",
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
        "--decision-ledger-json",
        default=str(DEFAULT_DECISION_LEDGER_JSON),
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

    packet = build_quality_closure_wave(
        capture_gap_audit=_load_json_object(Path(args.capture_gap_audit_json)),
        decision_ledger=_load_json_object(Path(args.decision_ledger_json)),
        registry=_load_json_object(Path(args.registry_json)),
        tier_policy=_load_json_object(Path(args.tier_policy_json)),
        mpg_replay_corpus=_load_json_object(Path(args.mpg_replay_corpus_json)),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.write_text(_markdown(packet, output_json, output_md), encoding="utf-8")
    print(json.dumps({"status": packet["status"], "output_json": str(output_json)}, ensure_ascii=False))
    return 0


def build_quality_closure_wave(
    *,
    capture_gap_audit: dict[str, Any],
    decision_ledger: dict[str, Any],
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    mpg_replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    registry_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(registry.get("rows"))
    }
    ledger_by_group = {
        str(row.get("strategy_group_id")): row
        for row in _dict_rows(decision_ledger.get("ledger_rows"))
    }
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
            ledger_by_group=ledger_by_group,
            registry_by_group=registry_by_group,
            current_tiers=current_tiers,
        )
        for group in PRIORITY_CAPTURE_GROUPS
    ]
    owner_cards = [
        _owner_card(
            group,
            registry_row=registry_by_group.get(group, {}),
            ledger_row=ledger_by_group.get(group, {}),
            audit_row=audit_by_group.get(group, {}),
            current_tier=current_tiers.get(group, "unknown"),
        )
        for group in sorted(set(registry_by_group) | set(ledger_by_group))
    ]
    identity_review_packets = [
        _identity_review_row(
            group,
            audit_row=audit_by_group.get(group, {}),
            closure_row=closure_by_group.get(group, {}),
            ledger_row=ledger_by_group.get(group, {}),
        )
        for group in IDENTITY_REVIEW_GROUPS
    ]
    mpg_member_tiering_review = _mpg_member_tiering_review(
        registry_by_group.get("MPG-001", {}),
        mpg_replay_corpus,
    )
    forward_no_action_ledger_extension = _forward_no_action_ledger_extension(
        capture_gap_audit,
        ledger_by_group,
    )
    owner_confirmation_checkpoint = _owner_confirmation_checkpoint(
        priority_capture_closure,
        identity_review_packets,
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
            "from current audit/ledger sources into one comparable packet."
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
            "decision_ledger": decision_ledger.get("status"),
            "registry": registry.get("status"),
            "tier_policy_groups": len(current_tiers),
            "mpg_replay_sample_count": len(_dict_rows(mpg_replay_corpus.get("replay_samples"))),
        },
        "priority_order": [
            "priority_1_btpc_lsr_brf_capture_closure",
            "priority_2_owner_cards_v1_from_ledger",
            "priority_3_mi_cpm_registry_identity_review",
            "priority_4_mpg_member_tiering_exit_decay_review",
            "priority_5_forward_outcome_no_action_ledger_extension",
        ],
        "priority_1_capture_closure": {
            "status": "ready_for_owner_review",
            "rows": priority_capture_closure,
        },
        "priority_2_owner_cards_v1": {
            "status": "ready",
            "card_count": len(owner_cards),
            "cards": owner_cards,
        },
        "priority_3_identity_review": {
            "status": "ready_for_owner_review",
            "rows": identity_review_packets,
        },
        "priority_4_mpg_member_tiering_exit_decay_review": mpg_member_tiering_review,
        "priority_5_forward_outcome_no_action_ledger_extension": forward_no_action_ledger_extension,
        "owner_confirmation_checkpoint": owner_confirmation_checkpoint,
        "interaction": {
            "level": "L0_local_strategy_quality_closure",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
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
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "exchange_write_called": False,
            "real_order_authority": False,
            "preview_or_replay_treated_as_live_signal": False,
        },
    }


def _priority_capture_row(
    group: str,
    *,
    audit_by_group: dict[str, dict[str, Any]],
    closure_by_group: dict[str, dict[str, Any]],
    ledger_by_group: dict[str, dict[str, Any]],
    registry_by_group: dict[str, dict[str, Any]],
    current_tiers: dict[str, str],
) -> dict[str, Any]:
    audit = audit_by_group.get(group, {})
    closure = closure_by_group.get(group, {})
    ledger = ledger_by_group.get(group, {})
    registry = registry_by_group.get(group, {})
    diagnosis = {
        "BTPC-001": "stale_fact_source_classifier_attribution_is_too_coarse",
        "LSR-001": "side_specific_short_revival_rewrite_needs_closure",
        "BRF-001": "bear_rally_failure_short_has_review_worthy_window_but_squeeze_requiredfacts_need_review",
    }.get(group, "capture_quality_review")
    return {
        "strategy_group_id": group,
        "current_tier": current_tiers.get(group, "unknown"),
        "ledger_decision": ledger.get("decision", "unknown"),
        "owner_review_label": OWNER_REVIEW_LABEL.get(str(ledger.get("decision")), "待复盘"),
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
        "required_next_evidence": ledger.get(
            "required_next_evidence",
            registry.get("required_next_evidence", "continue_review"),
        ),
        "next_checkpoint": ledger.get("next_checkpoint", "continue_review"),
        "owner_decision_required_now": False,
        "owner_policy_decision_after_packet": group in {"BRF-001"},
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _owner_card(
    group: str,
    *,
    registry_row: dict[str, Any],
    ledger_row: dict[str, Any],
    audit_row: dict[str, Any],
    current_tier: str,
) -> dict[str, Any]:
    decision = str(ledger_row.get("decision") or "keep_observing")
    risk_gaps = _risk_gap_items(registry_row)
    return {
        "strategy_group_id": group,
        "owner_label": registry_row.get("owner_label") or group,
        "one_line": registry_row.get("edge_thesis") or _fallback_one_line(group, decision),
        "market_opportunity": registry_row.get("regime_fit") or "current registry identity is incomplete",
        "trade_logic": registry_row.get("trade_logic") or "review-only strategy identity; no execution authority",
        "current_tier": current_tier,
        "actionable_now": False,
        "owner_visible_status": _owner_visible_status(decision),
        "review_recommendation": decision,
        "owner_review_label": OWNER_REVIEW_LABEL.get(decision, "待复盘"),
        "why_not_live": _why_not_live(registry_row, ledger_row),
        "missing_evidence": ledger_row.get("required_next_evidence")
        or registry_row.get("required_next_evidence")
        or "strategy identity or evidence still needs review",
        "main_risks": risk_gaps[:5],
        "system_next_action": ledger_row.get("next_checkpoint", "continue_strategy_review"),
        "owner_decision_later": decision in {"promote", "park", "kill", "revise"},
        "live_permission_change_recommended_now": False,
    }


def _identity_review_row(
    group: str,
    *,
    audit_row: dict[str, Any],
    closure_row: dict[str, Any],
    ledger_row: dict[str, Any],
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
        "ledger_decision": ledger_row.get("decision", "revise"),
        "identity_problem": (
            "strong_would_enter_but_smoke_or_member_identity_unclear"
            if group == "MI-001"
            else "would_enter_present_but_registry_scope_unclear"
        ),
        "owner_decision_options": options,
        "system_recommendation": "prepare_identity_packet_only_no_tier_change",
        "owner_policy_decision_required": True,
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
        "owner_policy_decision_required": True,
        "live_permission_change_recommended_now": False,
        "authority_boundary": _review_only_boundary(),
    }


def _forward_no_action_ledger_extension(
    capture_gap_audit: dict[str, Any],
    ledger_by_group: dict[str, dict[str, Any]],
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
                "ledger_decision": _as_dict(ledger_by_group.get(group)).get("decision", "keep_observing"),
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
    identity_review_packets: list[dict[str, Any]],
    mpg_member_tiering_review: dict[str, Any],
) -> dict[str, Any]:
    decisions = []
    for row in priority_capture_closure:
        if row.get("owner_policy_decision_after_packet"):
            decisions.append(
                {
                    "strategy_group_id": row["strategy_group_id"],
                    "decision_type": "promote_or_keep_l1_review",
                    "current_recommendation": row["ledger_decision"],
                }
            )
    for row in identity_review_packets:
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


def _closure_rows_by_group(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    closure = _as_dict(packet.get("priority_line_closure"))
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


def _why_not_live(registry_row: dict[str, Any], ledger_row: dict[str, Any]) -> str:
    if registry_row.get("actionable_now") is False:
        return str(registry_row.get("actionable_now_reason") or "runtime_state_only")
    if ledger_row:
        return "decision-ledger evidence is review-only and cannot authorize execution"
    return "no current runtime authority"


def _risk_gap_items(registry_row: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for risk_class, payload in sorted(_as_dict(registry_row.get("risk_gaps")).items()):
        for item in _as_dict(payload).get("items") or []:
            output.append(f"{risk_class}:{item}")
    return output


def _fallback_one_line(group: str, decision: str) -> str:
    return f"{group} is currently {decision} in the StrategyGroup Decision Ledger."


def _review_only_boundary() -> str:
    return (
        "local_review_only; no FinalGate; no Operation Layer; no exchange write; "
        "no tier policy change; no live profile change; no real order authority"
    )


def _markdown(packet: dict[str, Any], output_json: Path, output_md: Path) -> str:
    lines = [
        "# StrategyGroup Quality Closure Wave",
        "",
        "## Summary",
        "",
        f"- Status: `{packet['status']}`",
        f"- Closed problem: {packet['closed_engineering_problem']}",
        f"- Capability unlocked: {packet['capability_unlocked']}",
        f"- Next bottleneck: {packet['next_engineering_bottleneck']}",
        "- Real order authority: `false`",
        "- Live permission change: `false`",
        "",
        "## Priority 1 Capture Closure",
        "",
        "| StrategyGroup | Tier | Decision | Would enter | High-priority no_action | Forward positives | Next |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in packet["priority_1_capture_closure"]["rows"]:
        lines.append(
            "| `{}` | `{}` | `{}` | {} | {} | {} / {} | `{}` |".format(
                row["strategy_group_id"],
                row["current_tier"],
                row["ledger_decision"],
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
            "## Priority 2 Owner Cards",
            "",
            "| StrategyGroup | Label | Tier | Owner status | Review | Missing evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for card in packet["priority_2_owner_cards_v1"]["cards"]:
        lines.append(
            "| `{}` | {} | `{}` | {} | `{}` | `{}` |".format(
                card["strategy_group_id"],
                card["owner_label"],
                card["current_tier"],
                card["owner_visible_status"],
                card["review_recommendation"],
                card["missing_evidence"],
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
    for row in packet["priority_3_identity_review"]["rows"]:
        lines.append(
            "| `{}` | {} | {} | `{}` | {} |".format(
                row["strategy_group_id"],
                row["would_enter_count"],
                row["would_enter_forward_positive_count"],
                row["identity_problem"],
                ", ".join(f"`{item}`" for item in row["owner_decision_options"]),
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
    for row in packet["priority_4_mpg_member_tiering_exit_decay_review"]["member_rows"]:
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
    for row in packet["priority_5_forward_outcome_no_action_ledger_extension"]["rows"]:
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
    checkpoint = packet["owner_confirmation_checkpoint"]
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
    for key, value in packet["safety_invariants"].items():
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
