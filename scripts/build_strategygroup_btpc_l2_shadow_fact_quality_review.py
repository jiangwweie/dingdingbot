#!/usr/bin/env python3
"""Build the local BTPC L2 shadow fact-quality review packet.

This review consumes local opportunity/replay/readiness artifacts and classifies
BTPC-001 fact gaps by the boundary they affect. It does not fetch market data,
change tier policy, promote BTPC, call FinalGate, call Operation Layer, or place
orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.json"
)
DEFAULT_L2_READINESS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.json"
)
DEFAULT_REPLAY_LAB_JSON = REPO_ROOT / "output/runtime-monitor/latest-runtime-replay-lab.json"
DEFAULT_BTPC_HANDOFF_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/BTPC-001/handoff.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.md"
)


EXPECTED_BTPC_GAPS = {
    "historical_open_interest_window_missing": {
        "required_fact": "historical_open_interest_window",
        "fact_class": "derivatives",
        "boundary_effect": "blocks_promotion_beyond_l2_review",
        "next_local_action": "attach_historical_open_interest_window_or_document_proxy",
    },
    "historical_global_long_short_ratio_window_missing": {
        "required_fact": "historical_global_long_short_ratio_window",
        "fact_class": "derivatives",
        "boundary_effect": "blocks_promotion_beyond_l2_review",
        "next_local_action": "attach_global_long_short_ratio_window_or_document_proxy",
    },
    "top_trader_position_ratio_window_missing": {
        "required_fact": "top_trader_position_ratio_window",
        "fact_class": "derivatives",
        "boundary_effect": "blocks_promotion_beyond_l2_review",
        "next_local_action": "attach_top_trader_position_ratio_window_or_document_proxy",
    },
    "real_exchange_margin_liquidation_model_missing": {
        "required_fact": "real_exchange_margin_liquidation_model",
        "fact_class": "risk",
        "boundary_effect": "blocks_any_btpc_real_order_eligibility",
        "next_local_action": "map_research_leverage_to_exchange_margin_liquidation_model",
    },
    "short_squeeze_risk_not_runtime_blocking": {
        "required_fact": "short_squeeze_risk",
        "fact_class": "derivatives",
        "boundary_effect": "strategy_review_pending_not_runtime_blocking",
        "next_local_action": "record_short_squeeze_review_rule_before_promotion",
    },
}


def build_btpc_l2_shadow_fact_quality_review(
    *,
    opportunity_decision_loop_packet: dict[str, Any],
    l2_readiness_packet: dict[str, Any],
    replay_lab_packet: dict[str, Any],
    btpc_handoff: dict[str, Any],
) -> dict[str, Any]:
    btpc_row = _find_row(
        _dict_rows(opportunity_decision_loop_packet.get("decision_rows")),
        "BTPC-001",
    )
    readiness_row = _find_row(
        _dict_rows(l2_readiness_packet.get("readiness_rows")), "BTPC-001"
    )
    replay_summary = _replay_summary_for_btpc(btpc_row, replay_lab_packet)
    fact_rows = _fact_rows(btpc_row)
    forbidden_effects = _forbidden_effects(
        opportunity_decision_loop_packet,
        l2_readiness_packet,
        replay_lab_packet,
        btpc_handoff,
    )
    missing_classification = [
        str(row.get("gap")) for row in fact_rows if row.get("known_gap") is not True
    ]
    l2_enabled = (
        btpc_row.get("tier_state") == "l2_shadow_candidate_observation_enabled"
        or readiness_row.get("l2_readiness") == "l2_shadow_candidate_observation_enabled"
    )
    replay_covered = replay_summary["covered"] is True
    boundary_ok = _btpc_boundary_ok(btpc_handoff)
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not btpc_row:
        status = "btpc_fact_quality_not_applicable"
    elif missing_classification:
        status = "btpc_fact_quality_review_needs_gap_classification"
    elif not l2_enabled or not replay_covered or not boundary_ok:
        status = "btpc_fact_quality_review_incomplete"
    else:
        status = "btpc_l2_shadow_fact_quality_review_ready"

    promotion_blockers = [
        row
        for row in fact_rows
        if row["boundary_effect"] in {
            "blocks_promotion_beyond_l2_review",
            "blocks_any_btpc_real_order_eligibility",
            "strategy_review_pending_not_runtime_blocking",
        }
    ]
    real_order_blockers = [
        row
        for row in fact_rows
        if row["boundary_effect"] == "blocks_any_btpc_real_order_eligibility"
    ]
    return {
        "schema": "brc.btpc_l2_shadow_fact_quality_review.v1",
        "scope": "btpc_l2_shadow_fact_quality_review",
        "status": status,
        "source_status": {
            "opportunity_decision_loop": opportunity_decision_loop_packet.get("status"),
            "l2_readiness": l2_readiness_packet.get("status"),
            "replay_lab": replay_lab_packet.get("status"),
            "btpc_handoff": btpc_handoff.get("status"),
        },
        "interaction": {
            "level": "L0_local_btpc_l2_shadow_fact_quality_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "fact_gap_count": len(fact_rows),
            "classified_fact_gap_count": len(fact_rows) - len(missing_classification),
            "fact_source_pending_count": sum(
                1 for row in fact_rows if row.get("coverage_status") == "fact_source_pending"
            ),
            "strategy_review_pending_count": sum(
                1
                for row in fact_rows
                if row.get("coverage_status") == "strategy_review_pending"
            ),
            "promotion_blocker_count": len(promotion_blockers),
            "real_order_eligibility_blocker_count": len(real_order_blockers),
            "replay_fixture_count": replay_summary["sample_count"],
            "would_enter_replay_count": replay_summary["would_enter_sample_count"],
            "missing_derivatives_context_case_count": (
                1 if "missing_derivatives_context" in replay_summary["fixture_cases"] else 0
            ),
            "forbidden_effect_count": len(forbidden_effects),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
        },
        "btpc_state": {
            "current_tier": btpc_row.get("current_tier"),
            "tier_state": btpc_row.get("tier_state") or readiness_row.get("l2_readiness"),
            "decision_action": btpc_row.get("decision_action"),
            "l2_shadow_observation_enabled": l2_enabled,
            "replay_covered": replay_covered,
            "handoff_boundary_ok": boundary_ok,
        },
        "fact_rows": fact_rows,
        "replay_summary": replay_summary,
        "decision": {
            "l2_shadow_observation_can_continue": (
                status == "btpc_l2_shadow_fact_quality_review_ready"
            ),
            "fact_sources_pending": bool(fact_rows),
            "tier_policy_change_recommended_now": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": _default_next_step(status, fact_rows),
        },
        "operator_command_plan": {
            "not_executed": True,
            "starts_runtime": False,
            "changes_strategy_parameters": False,
            "changes_tier_policy": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "calls_final_gate": False,
            "calls_operation_layer": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
        },
        "safety_invariants": {
            "local_btpc_fact_quality_review_only": True,
            "input_is_not_execution_authority": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "l2_promotion_authorized": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    counts = _as_dict(packet.get("counts"))
    decision = _as_dict(packet.get("decision"))
    lines = [
        "# BTPC L2 Shadow Fact Quality Review",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Fact gaps: `{counts.get('fact_gap_count', 0)}`",
        f"- Classified: `{counts.get('classified_fact_gap_count', 0)}`",
        f"- Promotion blockers: `{counts.get('promotion_blocker_count', 0)}`",
        f"- Real-order blockers: `{counts.get('real_order_eligibility_blocker_count', 0)}`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Fact Rows",
        "",
        _fact_table(_dict_rows(packet.get("fact_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _fact_rows(btpc_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _dict_rows(btpc_row.get("gap_work_items")):
        gap = str(item.get("gap") or "")
        spec = EXPECTED_BTPC_GAPS.get(gap, {})
        boundary_effect = str(spec.get("boundary_effect") or "unclassified_gap")
        rows.append(
            {
                "gap": gap,
                "required_fact": spec.get("required_fact") or "unknown",
                "fact_class": spec.get("fact_class") or "unknown",
                "coverage_status": item.get("coverage_status"),
                "work_type": item.get("work_type"),
                "owner_priority": item.get("owner_priority"),
                "scheduled": item.get("scheduled") is True,
                "blocks_l2_progression": item.get("blocks_l2_progression") is True,
                "boundary_effect": boundary_effect,
                "known_gap": bool(spec),
                "shadow_observation_can_continue": (
                    item.get("blocks_l2_progression") is not True
                    and boundary_effect != "unclassified_gap"
                ),
                "promotion_or_real_order_blocker": boundary_effect
                in {
                    "blocks_promotion_beyond_l2_review",
                    "blocks_any_btpc_real_order_eligibility",
                    "strategy_review_pending_not_runtime_blocking",
                },
                "next_local_action": spec.get("next_local_action")
                or item.get("next_stage_decision")
                or "classify_gap_before_next_review",
                "validation_command": item.get("validation_command"),
                "real_order_authority": False,
                "l4_scope_change_recommended": False,
            }
        )
    return rows


def _replay_summary_for_btpc(
    btpc_row: dict[str, Any],
    replay_lab_packet: dict[str, Any],
) -> dict[str, Any]:
    row_summary = _as_dict(btpc_row.get("replay_verification"))
    samples = [
        row
        for row in _dict_rows(replay_lab_packet.get("l2_shadow_replay_samples"))
        if row.get("strategy_group_id") == "BTPC-001"
    ]
    fixture_cases = sorted(
        {
            str(item)
            for item in row_summary.get("fixture_cases") or []
            if str(item or "").strip()
        }
        | {
            str(row.get("fixture_case"))
            for row in samples
            if str(row.get("fixture_case") or "").strip()
        }
    )
    if row_summary:
        return {
            "covered": bool(row_summary.get("covered")),
            "sample_count": _int(row_summary.get("sample_count")),
            "would_enter_sample_count": _int(row_summary.get("would_enter_sample_count")),
            "no_action_sample_count": _int(row_summary.get("no_action_sample_count")),
            "revise_sample_count": _int(row_summary.get("revise_sample_count")),
            "non_executing_boundary_ok": bool(
                row_summary.get("non_executing_boundary_ok")
            ),
            "fixture_cases": fixture_cases,
        }
    return {
        "covered": bool(samples),
        "sample_count": len(samples),
        "would_enter_sample_count": sum(
            1 for row in samples if "would_enter" in str(row.get("signal_status") or "")
        ),
        "no_action_sample_count": sum(
            1
            for row in samples
            if row.get("blocker_class") == "waiting_for_market"
            or str(row.get("signal_status") or "").startswith("no_signal")
        ),
        "revise_sample_count": sum(
            1 for row in samples if row.get("review_recommendation") == "revise"
        ),
        "non_executing_boundary_ok": all(
            row.get("real_order_allowed") is not True
            and row.get("exchange_write_allowed") is not True
            and row.get("operation_layer_submit_allowed") is not True
            for row in samples
        ),
        "fixture_cases": fixture_cases,
    }


def _btpc_boundary_ok(handoff: dict[str, Any]) -> bool:
    boundary = _as_dict(handoff.get("execution_boundary"))
    risk_defaults = _as_dict(handoff.get("risk_defaults"))
    return (
        boundary.get("final_gate_input") is False
        and boundary.get("operation_layer_input") is False
        and boundary.get("real_submit_authorized") is False
        and risk_defaults.get("risk_tier") == "not_live_order_eligible"
        and str(risk_defaults.get("max_notional_per_action_usdt")) == "0"
        and _int(risk_defaults.get("max_active_positions")) == 0
    )


def _default_next_step(status: str, fact_rows: list[dict[str, Any]]) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_fact_quality_source_forbidden_effects"
    if status == "btpc_fact_quality_not_applicable":
        return "continue_signal_coverage_until_btpc_l2_shadow_row_exists"
    if status == "btpc_fact_quality_review_needs_gap_classification":
        return "classify_unmapped_btpc_fact_gaps_before_l2_quality_review"
    if status == "btpc_fact_quality_review_incomplete":
        return "repair_btpc_l2_shadow_fact_quality_review_inputs"
    if any(row.get("boundary_effect") == "blocks_any_btpc_real_order_eligibility" for row in fact_rows):
        return "attach_btpc_derivatives_fact_sources_and_margin_model_for_l2_quality_review"
    return "continue_btpc_l2_shadow_observation_with_fact_gap_tracking"


def _forbidden_effects(*packets: dict[str, Any]) -> list[str]:
    effects: list[str] = []
    for index, packet in enumerate(packets):
        safety = _as_dict(packet.get("safety_invariants"))
        for item in safety.get("source_forbidden_effects") or []:
            effects.append(f"packet_{index}.{item}")
        for key in (
            "server_files_mutated",
            "runtime_started",
            "strategy_parameters_changed",
            "tier_policy_changed",
            "shadow_candidate_created",
            "execution_intent_created",
            "final_gate_called",
            "operation_layer_called",
            "order_created",
            "order_lifecycle_called",
            "exchange_write_called",
            "withdrawal_or_transfer_created",
        ):
            if safety.get(key) is True:
                effects.append(f"packet_{index}.safety.{key}")
    boundary = _as_dict(packets[-1].get("execution_boundary")) if packets else {}
    if boundary.get("real_submit_authorized") is True:
        effects.append("btpc_handoff.execution_boundary.real_submit_authorized")
    return sorted(set(effects))


def _fact_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Gap | Fact | Class | Coverage | Effect | Next |\n| --- | --- | --- | --- | --- | --- |\n| none | - | - | - | - | - |"
    output = [
        "| Gap | Fact | Class | Coverage | Effect | Next |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("gap"),
                row.get("required_fact"),
                row.get("fact_class"),
                row.get("coverage_status"),
                row.get("boundary_effect"),
                row.get("next_local_action"),
            )
        )
    return "\n".join(output)


def _find_row(rows: list[dict[str, Any]], strategy_group_id: str) -> dict[str, Any]:
    return next(
        (
            row
            for row in rows
            if str(row.get("strategy_group_id") or "") == strategy_group_id
        ),
        {},
    )


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--opportunity-decision-loop-json",
        default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON),
    )
    parser.add_argument("--l2-readiness-json", default=str(DEFAULT_L2_READINESS_JSON))
    parser.add_argument("--replay-lab-json", default=str(DEFAULT_REPLAY_LAB_JSON))
    parser.add_argument("--btpc-handoff-json", default=str(DEFAULT_BTPC_HANDOFF_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_l2_shadow_fact_quality_review(
        opportunity_decision_loop_packet=_load_json_object(
            Path(args.opportunity_decision_loop_json).expanduser()
        ),
        l2_readiness_packet=_load_json_object(
            Path(args.l2_readiness_json).expanduser()
        ),
        replay_lab_packet=_load_json_object(Path(args.replay_lab_json).expanduser()),
        btpc_handoff=_load_json_object(Path(args.btpc_handoff_json).expanduser()),
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(build_owner_progress_markdown(packet), encoding="utf-8")
    print(payload)
    return 0 if packet["status"] != "blocked_forbidden_effect" else 2


if __name__ == "__main__":
    raise SystemExit(main())
