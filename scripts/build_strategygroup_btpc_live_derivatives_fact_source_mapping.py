#!/usr/bin/env python3
"""Build the BTPC live derivatives fact-source mapping packet.

This command converts the BTPC L2 keep/revise decision into a local source-map
artifact for future live eligibility review. It maps the live derivatives and
margin facts that must be attached before BTPC can ever be considered for live
RequiredFacts, while explicitly keeping those facts unsatisfied and keeping
FinalGate, Operation Layer, exchange writes, and real orders out of scope.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BTPC_L2_DECISION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_BTPC_HANDOFF_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/BTPC-001/handoff.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.md"
)


EXPECTED_LIVE_FACT_SOURCES = {
    "funding_72h": {
        "fact_class": "derivatives",
        "source_route": "perp_funding_rate_history_window",
        "source_category": "exchange_public_derivatives_market_data",
        "purpose": "review sustained funding stress before bearish continuation eligibility",
        "window_requirement": "72h",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "perp_spot_premium": {
        "fact_class": "derivatives",
        "source_route": "perp_mark_index_or_spot_premium_window",
        "source_category": "exchange_public_derivatives_market_data",
        "purpose": "separate futures premium stress from spot-only price movement",
        "window_requirement": "closed_1h_context_window",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "open_interest_or_crowding_proxy": {
        "fact_class": "derivatives",
        "source_route": "open_interest_snapshot_or_crowding_proxy",
        "source_category": "exchange_public_derivatives_market_data",
        "purpose": "avoid treating unbacked price action as derivatives crowding",
        "window_requirement": "latest_plus_recent_context",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "historical_open_interest_window": {
        "fact_class": "derivatives",
        "source_route": "open_interest_history_window",
        "source_category": "exchange_public_derivatives_market_data",
        "purpose": "confirm crowding direction and OI expansion/contraction context",
        "window_requirement": "historical_window_from_btpc_handoff",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "historical_global_long_short_ratio_window": {
        "fact_class": "derivatives",
        "source_route": "global_long_short_account_ratio_history_window",
        "source_category": "exchange_public_derivatives_positioning_data",
        "purpose": "review broad account-positioning skew before short continuation review",
        "window_requirement": "historical_window_from_btpc_handoff",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "top_trader_position_ratio_window": {
        "fact_class": "derivatives",
        "source_route": "top_trader_position_ratio_history_window",
        "source_category": "exchange_public_derivatives_positioning_data",
        "purpose": "review top-trader crowding before promotion beyond L2 shadow",
        "window_requirement": "historical_window_from_btpc_handoff",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
    "short_squeeze_risk": {
        "fact_class": "derivatives",
        "source_route": "short_squeeze_disable_classifier_from_live_derivatives_features",
        "source_category": "strategy_classifier_from_live_derivatives_inputs",
        "purpose": "keep short-squeeze conflict as strategy-quality input before promotion",
        "window_requirement": "latest_plus_recent_context",
        "source_attachment_status": "mapping_ready_classifier_not_reviewed",
    },
    "real_exchange_margin_liquidation_model": {
        "fact_class": "risk",
        "source_route": "exchange_leverage_bracket_margin_and_symbol_filter_model",
        "source_category": "exchange_signed_or_public_rule_data",
        "purpose": "replace review-only leverage envelope before any BTPC live eligibility",
        "window_requirement": "action_time_exchange_rule_snapshot",
        "source_attachment_status": "mapping_ready_live_source_not_attached",
    },
}


def build_btpc_live_derivatives_fact_source_mapping(
    *,
    btpc_l2_decision_packet: dict[str, Any],
    btpc_handoff: dict[str, Any],
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(btpc_l2_decision_packet, btpc_handoff)
    action_present = _live_fact_source_action_present(btpc_l2_decision_packet)
    handoff_boundary_ok = _btpc_boundary_ok(btpc_handoff)
    required_facts = _required_fact_set(btpc_handoff)
    source_rows = _source_rows(required_facts)
    missing_handoff_facts = [
        row["required_fact"] for row in source_rows if row["present_in_handoff"] is False
    ]
    mapping_ready = (
        action_present
        and handoff_boundary_ok
        and not missing_handoff_facts
        and not forbidden_effects
    )
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not action_present:
        status = "btpc_live_derivatives_mapping_waiting_for_l2_decision_action"
    elif not handoff_boundary_ok or missing_handoff_facts:
        status = "btpc_live_derivatives_mapping_incomplete"
    else:
        status = "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority"

    return {
        "schema": "brc.btpc_live_derivatives_fact_source_mapping.v1",
        "scope": "btpc_live_derivatives_fact_source_mapping",
        "status": status,
        "source_status": {
            "btpc_l2_keep_revise_fact_source_decision": btpc_l2_decision_packet.get(
                "status"
            ),
            "btpc_handoff": btpc_handoff.get("status"),
        },
        "interaction": {
            "level": "L0_local_btpc_live_derivatives_fact_source_mapping",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "expected_live_fact_source_count": len(EXPECTED_LIVE_FACT_SOURCES),
            "mapping_ready_count": sum(
                1 for row in source_rows if row["mapping_ready"] is True
            ),
            "source_attachment_pending_count": sum(
                1 for row in source_rows if row["live_source_attached"] is False
            ),
            "live_required_fact_satisfied_count": 0,
            "live_required_fact_gap_count": len(source_rows),
            "missing_handoff_fact_count": len(missing_handoff_facts),
            "derivatives_fact_source_count": sum(
                1 for row in source_rows if row["fact_class"] == "derivatives"
            ),
            "risk_fact_source_count": sum(
                1 for row in source_rows if row["fact_class"] == "risk"
            ),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "mapping_ready": mapping_ready,
            "live_required_facts_satisfied": False,
            "live_eligibility_ready": False,
            "l2_shadow_observation_can_continue": mapping_ready,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
            "real_order_authority": False,
        },
        "source_rows": source_rows,
        "missing_handoff_facts": missing_handoff_facts,
        "decision": {
            "live_derivatives_fact_source_mapping_ready": mapping_ready,
            "attach_live_sources_before_btpc_live_eligibility": True,
            "mapping_satisfies_live_required_facts": False,
            "source_attachment_required_before_live_eligibility": True,
            "tier_policy_change_recommended_now": False,
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": _default_next_step(status),
        },
        "operator_command_plan": {
            "not_executed": True,
            "starts_runtime": False,
            "changes_strategy_parameters": False,
            "changes_live_profile": False,
            "changes_order_sizing_defaults": False,
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
            "local_btpc_live_fact_source_mapping_only": True,
            "mapping_is_not_live_required_fact": True,
            "input_is_not_execution_authority": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "runtime_started": False,
            "strategy_parameters_changed": False,
            "live_profile_changed": False,
            "order_sizing_defaults_changed": False,
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
            "does_not_lower_owner_selected_leverage": True,
            "does_not_change_live_profile_or_sizing_defaults": True,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    counts = _as_dict(packet.get("counts"))
    decision = _as_dict(packet.get("decision"))
    lines = [
        "# BTPC Live Derivatives Fact Source Mapping",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Source mappings: `{counts.get('mapping_ready_count', 0)}/{counts.get('expected_live_fact_source_count', 0)}`",
        f"- Source attachments pending: `{counts.get('source_attachment_pending_count', 0)}`",
        "- Live RequiredFacts satisfied by mapping: `false`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Source Rows",
        "",
        _source_table(_dict_rows(packet.get("source_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _source_rows(required_facts: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for required_fact, spec in EXPECTED_LIVE_FACT_SOURCES.items():
        present = required_fact in required_facts
        rows.append(
            {
                "required_fact": required_fact,
                "fact_class": spec["fact_class"],
                "source_category": spec["source_category"],
                "source_route": spec["source_route"],
                "purpose": spec["purpose"],
                "window_requirement": spec["window_requirement"],
                "present_in_handoff": present,
                "mapping_ready": present,
                "source_attachment_status": spec["source_attachment_status"],
                "live_source_attached": False,
                "live_required_fact_satisfied": False,
                "can_feed_l2_review": True,
                "can_feed_finalgate": False,
                "can_feed_operation_layer": False,
                "blocks_btpc_live_eligibility_until_attached": True,
                "real_order_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
                "l4_scope_change_recommended": False,
            }
        )
    return rows


def _live_fact_source_action_present(packet: dict[str, Any]) -> bool:
    return any(
        row.get("action")
        == "attach_live_derivatives_fact_sources_before_btpc_live_eligibility"
        and row.get("decision_area") == "live_fact_source"
        and row.get("real_order_authority") is False
        and row.get("candidate_or_finalgate_authority") is False
        and row.get("operation_layer_authority") is False
        and row.get("exchange_write_authority") is False
        for row in _dict_rows(packet.get("action_rows"))
    )


def _required_fact_set(handoff: dict[str, Any]) -> set[str]:
    facts: set[str] = set()
    for values in _as_dict(handoff.get("required_facts")).values():
        for item in values or []:
            facts.add(str(item))
    return facts


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
            "live_profile_changed",
            "order_sizing_defaults_changed",
            "tier_policy_changed",
            "l2_promotion_authorized",
            "l4_real_order_scope_expanded",
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
        interaction = _as_dict(packet.get("interaction"))
        for key in (
            "mutates_remote_files",
            "approaches_real_order",
            "calls_finalgate",
            "calls_operation_layer",
            "calls_exchange_write",
            "places_order",
        ):
            if interaction.get(key) is True:
                effects.append(f"packet_{index}.interaction.{key}")
    decision = _as_dict(packets[0].get("decision")) if packets else {}
    if decision.get("l2_promotion_recommended_now") is True:
        effects.append("btpc_l2_decision.l2_promotion_recommended_now")
    if decision.get("l4_scope_change_recommended") is True:
        effects.append("btpc_l2_decision.l4_scope_change_recommended")
    if decision.get("real_order_scope_change_recommended") is True:
        effects.append("btpc_l2_decision.real_order_scope_change_recommended")
    handoff = packets[1] if len(packets) > 1 else {}
    boundary = _as_dict(handoff.get("execution_boundary"))
    if boundary.get("final_gate_input") is True:
        effects.append("btpc_handoff.execution_boundary.final_gate_input")
    if boundary.get("operation_layer_input") is True:
        effects.append("btpc_handoff.execution_boundary.operation_layer_input")
    if boundary.get("real_submit_authorized") is True:
        effects.append("btpc_handoff.execution_boundary.real_submit_authorized")
    return sorted(set(effects))


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_live_fact_source_mapping_source_forbidden_effects"
    if status == "btpc_live_derivatives_mapping_waiting_for_l2_decision_action":
        return "rerun_btpc_l2_keep_revise_fact_source_decision_before_mapping"
    if status == "btpc_live_derivatives_mapping_incomplete":
        return "repair_btpc_handoff_required_facts_or_execution_boundary_before_mapping"
    return "review_btpc_conflict_and_freshness_classifier_rules_before_any_l2_promotion_review"


def _source_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Fact | Source route | Mapping | Live fact | Real order |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Fact | Source route | Mapping | Live fact | Real order |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("required_fact"),
                row.get("source_route"),
                row.get("mapping_ready"),
                row.get("live_required_fact_satisfied"),
                row.get("real_order_authority"),
            )
        )
    return "\n".join(output)


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
        "--btpc-l2-decision-json",
        default=str(DEFAULT_BTPC_L2_DECISION_JSON),
    )
    parser.add_argument("--btpc-handoff-json", default=str(DEFAULT_BTPC_HANDOFF_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_live_derivatives_fact_source_mapping(
        btpc_l2_decision_packet=_load_json_object(
            Path(args.btpc_l2_decision_json).expanduser()
        ),
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
