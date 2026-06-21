#!/usr/bin/env python3
"""Build the BTPC L2 keep/revise/fact-source decision packet.

This command turns the BTPC proxy replay quality rollup into a stable local
decision artifact. It is a P0.5 review step: it can decide what local work comes
next for BTPC L2 shadow observation, but it cannot promote BTPC, satisfy live
RequiredFacts, call FinalGate, call Operation Layer, or place orders.
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
DEFAULT_BTPC_PROXY_REPLAY_QUALITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.md"
)


ACTION_SPECS = {
    "attach_live_derivatives_fact_sources_before_btpc_live_eligibility": {
        "decision_area": "live_fact_source",
        "owner_priority": "P0.5",
        "action": "attach_live_derivatives_fact_sources_before_btpc_live_eligibility",
        "reason": "proxy_replay_resolves_missing_derivatives_context_for_l2_review_only",
        "completion_signal": "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority",
        "validation_command": "python3 scripts/build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py",
    },
    "review_btpc_strong_uptrend_conflict_disable_rule": {
        "decision_area": "classifier_rule",
        "owner_priority": "P0.5",
        "action": "review_btpc_strong_uptrend_conflict_disable_rule",
        "reason": "strong_uptrend_conflict_case_remains_revise_before_promotion",
        "completion_signal": "btpc_strong_uptrend_conflict_rule_review_recorded",
        "validation_command": "PYTHONDONTWRITEBYTECODE=1 pytest -q tests/unit/test_strategygroup_btpc_l2_keep_revise_fact_source_decision.py",
    },
    "review_btpc_freshness_or_classifier_stale_signal_rule": {
        "decision_area": "classifier_rule",
        "owner_priority": "P0.5",
        "action": "review_btpc_freshness_or_classifier_stale_signal_rule",
        "reason": "stale_signal_case_remains_revise_before_promotion",
        "completion_signal": "btpc_freshness_or_classifier_stale_signal_rule_review_recorded",
        "validation_command": "PYTHONDONTWRITEBYTECODE=1 pytest -q tests/unit/test_strategygroup_btpc_l2_keep_revise_fact_source_decision.py",
    },
    "continue_btpc_l2_shadow_observation_with_proxy_context": {
        "decision_area": "observation",
        "owner_priority": "P0.5",
        "action": "continue_btpc_l2_shadow_observation_with_proxy_context",
        "reason": "would_enter_proxy_reviewable_cases_exist_but_do_not_grant_live_authority",
        "completion_signal": "btpc_l2_shadow_observation_continues_with_proxy_context",
        "validation_command": "python3 scripts/run_strategygroup_runtime_local_monitor_sequence.py --daily-check-mode cache --owner-progress",
    },
}


def build_btpc_l2_keep_revise_fact_source_decision(
    *,
    opportunity_decision_loop_packet: dict[str, Any],
    btpc_proxy_replay_quality_packet: dict[str, Any],
) -> dict[str, Any]:
    btpc_quality_row = _btpc_strategy_quality_row(opportunity_decision_loop_packet)
    proxy_rollup = _as_dict(btpc_quality_row.get("btpc_proxy_replay_quality"))
    forbidden_effects = _forbidden_effects(
        opportunity_decision_loop_packet,
        btpc_proxy_replay_quality_packet,
        btpc_quality_row,
    )
    source_ready = _source_ready(btpc_quality_row, proxy_rollup)
    action_rows = _action_rows(
        action_items=[str(item) for item in proxy_rollup.get("action_items") or []],
        case_rows=_dict_rows(btpc_proxy_replay_quality_packet.get("case_rows")),
    )
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not source_ready:
        status = "btpc_l2_decision_waiting_for_proxy_quality_rollup"
    elif action_rows:
        status = "btpc_l2_keep_revise_fact_source_decision_ready"
    else:
        status = "btpc_l2_decision_no_action_items"

    return {
        "schema": "brc.btpc_l2_keep_revise_fact_source_decision.v1",
        "scope": "btpc_l2_keep_revise_fact_source_decision",
        "status": status,
        "source_status": {
            "opportunity_decision_loop": opportunity_decision_loop_packet.get("status"),
            "btpc_proxy_replay_quality_review": btpc_proxy_replay_quality_packet.get(
                "status"
            ),
            "btpc_strategy_quality_decision": btpc_quality_row.get(
                "strategy_quality_decision"
            ),
        },
        "interaction": {
            "level": "L0_local_btpc_l2_keep_revise_fact_source_decision",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "action_item_count": len(action_rows),
            "live_fact_source_action_count": sum(
                1 for row in action_rows if row.get("decision_area") == "live_fact_source"
            ),
            "classifier_rule_action_count": sum(
                1 for row in action_rows if row.get("decision_area") == "classifier_rule"
            ),
            "observation_action_count": sum(
                1 for row in action_rows if row.get("decision_area") == "observation"
            ),
            "proxy_replay_case_count": _int(proxy_rollup.get("case_count")),
            "proxy_reviewable_would_enter_count": _int(
                proxy_rollup.get("proxy_reviewable_would_enter_count")
            ),
            "revise_case_count": _int(proxy_rollup.get("revise_case_count")),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "current_tier": btpc_quality_row.get("current_tier"),
            "tier_state": btpc_quality_row.get("tier_state"),
            "strategy_quality_decision": btpc_quality_row.get(
                "strategy_quality_decision"
            ),
            "next_stage": btpc_quality_row.get("next_stage"),
            "l2_shadow_observation_can_continue": status
            == "btpc_l2_keep_revise_fact_source_decision_ready",
            "revise_before_promotion": bool(action_rows),
            "live_required_facts_satisfied": False,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
            "real_order_authority": False,
        },
        "action_rows": action_rows,
        "decision": {
            "keep_l2_shadow_observation": (
                status == "btpc_l2_keep_revise_fact_source_decision_ready"
            ),
            "revise_fact_classifier_inputs_before_promotion": bool(action_rows),
            "attach_live_fact_sources_before_live_eligibility": any(
                row.get("decision_area") == "live_fact_source" for row in action_rows
            ),
            "classifier_review_required_before_promotion": any(
                row.get("decision_area") == "classifier_rule" for row in action_rows
            ),
            "proxy_decision_satisfies_live_required_facts": False,
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
            "local_btpc_l2_decision_only": True,
            "proxy_decision_is_not_live_required_fact": True,
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
        "# BTPC L2 Keep / Revise / Fact Source Decision",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Action items: `{counts.get('action_item_count', 0)}`",
        f"- Live fact-source actions: `{counts.get('live_fact_source_action_count', 0)}`",
        f"- Classifier-rule actions: `{counts.get('classifier_rule_action_count', 0)}`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Actions",
        "",
        _action_table(_dict_rows(packet.get("action_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _btpc_strategy_quality_row(packet: dict[str, Any]) -> dict[str, Any]:
    quality = _as_dict(packet.get("strategy_quality_decisions"))
    for row in _dict_rows(quality.get("rows")):
        if row.get("strategy_group_id") == "BTPC-001":
            return row
    return {}


def _source_ready(btpc_quality_row: dict[str, Any], proxy_rollup: dict[str, Any]) -> bool:
    return (
        btpc_quality_row.get("strategy_quality_decision")
        == "keep_l2_shadow_and_revise_fact_classifier_inputs"
        and btpc_quality_row.get("real_order_authority") is False
        and btpc_quality_row.get("candidate_or_finalgate_authority") is False
        and proxy_rollup.get("ready") is True
        and proxy_rollup.get("live_required_facts_satisfied") is False
        and proxy_rollup.get("real_order_authority") is False
        and proxy_rollup.get("l4_scope_change_recommended") is False
    )


def _action_rows(
    *,
    action_items: list[str],
    case_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    decision_cases = _cases_by_decision(case_rows)
    for item in action_items:
        spec = ACTION_SPECS.get(item)
        if not spec:
            continue
        row = dict(spec)
        row["source_action_item"] = item
        row["evidence_cases"] = decision_cases.get(item, [])
        row["live_required_fact_authority"] = False
        row["l2_promotion_authority"] = False
        row["l4_scope_change_recommended"] = False
        row["real_order_authority"] = False
        row["candidate_or_finalgate_authority"] = False
        row["operation_layer_authority"] = False
        row["exchange_write_authority"] = False
        output.append(row)
    return output


def _cases_by_decision(case_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {
        "attach_live_derivatives_fact_sources_before_btpc_live_eligibility": [],
        "review_btpc_strong_uptrend_conflict_disable_rule": [],
        "review_btpc_freshness_or_classifier_stale_signal_rule": [],
        "continue_btpc_l2_shadow_observation_with_proxy_context": [],
    }
    for row in case_rows:
        fixture = str(row.get("fixture_case") or "unknown")
        decision = str(row.get("proxy_replay_quality_decision") or "")
        if decision == "revise_live_fact_collection_but_l2_proxy_reviewable":
            mapping[
                "attach_live_derivatives_fact_sources_before_btpc_live_eligibility"
            ].append(fixture)
        if decision == "revise_conflict_disable_before_l2_promotion":
            mapping["review_btpc_strong_uptrend_conflict_disable_rule"].append(fixture)
        if decision == "revise_freshness_or_classifier_before_l2_promotion":
            mapping["review_btpc_freshness_or_classifier_stale_signal_rule"].append(
                fixture
            )
        if decision == "keep_observing_l2_shadow_with_proxy_context":
            mapping["continue_btpc_l2_shadow_observation_with_proxy_context"].append(
                fixture
            )
    return mapping


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
    opportunity_decision = _as_dict(packets[0].get("decision")) if packets else {}
    if opportunity_decision.get("real_order_scope_change_recommended") is True:
        effects.append("opportunity_decision.real_order_scope_change_recommended")
    if opportunity_decision.get("l4_promotion_recommended") is True:
        effects.append("opportunity_decision.l4_promotion_recommended")
    proxy_decision = _as_dict(packets[1].get("decision")) if len(packets) > 1 else {}
    if proxy_decision.get("proxy_replay_satisfies_live_required_facts") is True:
        effects.append("btpc_proxy_replay.proxy_replay_satisfies_live_required_facts")
    btpc_row = packets[2] if len(packets) > 2 else {}
    if btpc_row.get("real_order_authority") is True:
        effects.append("btpc_quality_row.real_order_authority")
    if btpc_row.get("candidate_or_finalgate_authority") is True:
        effects.append("btpc_quality_row.candidate_or_finalgate_authority")
    if btpc_row.get("not_l4_scope_change") is False:
        effects.append("btpc_quality_row.not_l4_scope_change_false")
    return sorted(set(effects))


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_l2_decision_source_forbidden_effects"
    if status == "btpc_l2_decision_waiting_for_proxy_quality_rollup":
        return "rerun_btpc_proxy_replay_quality_and_final_opportunity_decision_loop"
    if status == "btpc_l2_decision_no_action_items":
        return "continue_btpc_l2_shadow_observation_until_action_items_exist"
    return "execute_btpc_l2_fact_source_and_classifier_review_tasks_locally"


def _action_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Area | Action | Evidence | Real order |\n| --- | --- | --- | --- |\n| none | - | - | - |"
    output = [
        "| Area | Action | Evidence | Real order |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` |".format(
                row.get("decision_area"),
                row.get("action"),
                ",".join(str(item) for item in row.get("evidence_cases") or []),
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
        "--opportunity-decision-loop-json",
        default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON),
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-json",
        default=str(DEFAULT_BTPC_PROXY_REPLAY_QUALITY_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_l2_keep_revise_fact_source_decision(
        opportunity_decision_loop_packet=_load_json_object(
            Path(args.opportunity_decision_loop_json).expanduser()
        ),
        btpc_proxy_replay_quality_packet=_load_json_object(
            Path(args.btpc_proxy_replay_quality_json).expanduser()
        ),
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
