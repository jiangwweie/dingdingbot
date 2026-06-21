#!/usr/bin/env python3
"""Build the BTPC classifier rule review packet.

This command records the BTPC strong-uptrend conflict and freshness/stale-signal
rule review after proxy replay has exposed those cases. It is a local P0.5
classifier-review artifact only: it can prove the local evaluator has a
reviewed disable-rule shape, but it cannot promote BTPC, satisfy live
RequiredFacts, call FinalGate, call Operation Layer, or place orders.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.reference_price_action_evaluators import BTPC001PriceActionEvaluator

DEFAULT_BTPC_L2_DECISION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_BTPC_PROXY_REPLAY_QUALITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.json"
)
DEFAULT_BTPC_LIVE_SOURCE_MAPPING_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.md"
)


RULE_SPECS = {
    "review_btpc_strong_uptrend_conflict_disable_rule": {
        "rule_id": "btpc_strong_uptrend_conflict_disable_rule",
        "fixture_case": "strong_uptrend_conflict",
        "proxy_replay_quality_decision": "revise_conflict_disable_before_l2_promotion",
        "reason_code": "btpc_disable_strong_uptrend_conflict",
        "required_disable_state": "strong_uptrend_disable_state",
        "required_entry_state": "regime_trend_down_state",
        "completion_signal": "btpc_strong_uptrend_conflict_rule_review_recorded",
    },
    "review_btpc_freshness_or_classifier_stale_signal_rule": {
        "rule_id": "btpc_freshness_or_classifier_stale_signal_rule",
        "fixture_case": "stale_signal",
        "proxy_replay_quality_decision": "revise_freshness_or_classifier_before_l2_promotion",
        "reason_code": "btpc_disable_stale_signal_before_l2_review",
        "required_disable_state": "stale_signal",
        "required_entry_state": "pullback_structure_loss",
        "completion_signal": "btpc_freshness_or_classifier_stale_signal_rule_review_recorded",
    },
}


def build_btpc_classifier_rule_review(
    *,
    btpc_l2_decision_packet: dict[str, Any],
    btpc_proxy_replay_quality_packet: dict[str, Any],
    btpc_live_source_mapping_packet: dict[str, Any],
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        btpc_l2_decision_packet,
        btpc_proxy_replay_quality_packet,
        btpc_live_source_mapping_packet,
    )
    rule_rows = _rule_rows(
        btpc_l2_decision_packet=btpc_l2_decision_packet,
        btpc_proxy_replay_quality_packet=btpc_proxy_replay_quality_packet,
    )
    implemented_count = sum(1 for row in rule_rows if row["implementation_ready"] is True)
    expected_count = len(RULE_SPECS)
    source_mapping_ready = (
        btpc_live_source_mapping_packet.get("status")
        == "btpc_live_derivatives_fact_source_mapping_ready_without_live_authority"
    )
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif len(rule_rows) != expected_count:
        status = "btpc_classifier_rule_review_waiting_for_action_rows"
    elif implemented_count != expected_count or not source_mapping_ready:
        status = "btpc_classifier_rule_review_incomplete"
    else:
        status = "btpc_classifier_rule_review_recorded_without_live_authority"

    return {
        "schema": "brc.btpc_classifier_rule_review.v1",
        "scope": "btpc_classifier_rule_review",
        "status": status,
        "source_status": {
            "btpc_l2_keep_revise_fact_source_decision": btpc_l2_decision_packet.get(
                "status"
            ),
            "btpc_proxy_replay_quality_review": btpc_proxy_replay_quality_packet.get(
                "status"
            ),
            "btpc_live_derivatives_fact_source_mapping": (
                btpc_live_source_mapping_packet.get("status")
            ),
        },
        "interaction": {
            "level": "L0_local_btpc_classifier_rule_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "expected_rule_count": expected_count,
            "rule_review_count": len(rule_rows),
            "implementation_ready_count": implemented_count,
            "proxy_replay_case_link_count": sum(
                1 for row in rule_rows if row["proxy_replay_case_linked"] is True
            ),
            "live_required_fact_satisfied_count": 0,
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
            "forbidden_effect_count": len(forbidden_effects),
        },
        "btpc_state": {
            "strategy_group_id": "BTPC-001",
            "classifier_logic_version": BTPC001PriceActionEvaluator.logic_version,
            "classifier_rule_review_ready": (
                status == "btpc_classifier_rule_review_recorded_without_live_authority"
            ),
            "l2_shadow_observation_can_continue": (
                status == "btpc_classifier_rule_review_recorded_without_live_authority"
            ),
            "live_required_facts_satisfied": False,
            "l2_promotion_authority": False,
            "l4_scope_change_recommended": False,
            "real_order_authority": False,
        },
        "rule_rows": rule_rows,
        "decision": {
            "classifier_rule_review_recorded": (
                status == "btpc_classifier_rule_review_recorded_without_live_authority"
            ),
            "strong_uptrend_rule_recorded": any(
                row["rule_id"] == "btpc_strong_uptrend_conflict_disable_rule"
                and row["implementation_ready"] is True
                for row in rule_rows
            ),
            "freshness_rule_recorded": any(
                row["rule_id"] == "btpc_freshness_or_classifier_stale_signal_rule"
                and row["implementation_ready"] is True
                for row in rule_rows
            ),
            "classifier_review_satisfies_live_required_facts": False,
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
            "local_btpc_classifier_rule_review_only": True,
            "classifier_review_is_not_live_required_fact": True,
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
        "# BTPC Classifier Rule Review",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Rule reviews: `{counts.get('rule_review_count', 0)}/{counts.get('expected_rule_count', 0)}`",
        f"- Implementation ready: `{counts.get('implementation_ready_count', 0)}`",
        "- Live RequiredFacts satisfied by classifier review: `false`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Rule Rows",
        "",
        _rule_table(_dict_rows(packet.get("rule_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _rule_rows(
    *,
    btpc_l2_decision_packet: dict[str, Any],
    btpc_proxy_replay_quality_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    action_rows = {
        str(row.get("action")): row
        for row in _dict_rows(btpc_l2_decision_packet.get("action_rows"))
    }
    case_rows = {
        str(row.get("fixture_case")): row
        for row in _dict_rows(btpc_proxy_replay_quality_packet.get("case_rows"))
    }
    rows: list[dict[str, Any]] = []
    for action, spec in RULE_SPECS.items():
        source_action = action_rows.get(action)
        if not source_action:
            continue
        case = case_rows.get(spec["fixture_case"], {})
        proxy_decision = str(case.get("proxy_replay_quality_decision") or "")
        implementation_ready = (
            BTPC001PriceActionEvaluator.logic_version == "btpc-001-price-action-v1"
        )
        rows.append(
            {
                "action": action,
                "rule_id": spec["rule_id"],
                "fixture_case": spec["fixture_case"],
                "source_action_present": True,
                "source_action_reason": source_action.get("reason"),
                "proxy_replay_case_linked": bool(case),
                "proxy_replay_quality_decision": proxy_decision,
                "expected_proxy_replay_quality_decision": spec[
                    "proxy_replay_quality_decision"
                ],
                "proxy_decision_matches": proxy_decision
                == spec["proxy_replay_quality_decision"],
                "implementation_ref": "src/domain/reference_price_action_evaluators.py",
                "implementation_status": (
                    "local_classifier_revision_executed"
                    if implementation_ready
                    else "implementation_pending"
                ),
                "implementation_ready": implementation_ready,
                "classifier_logic_version": BTPC001PriceActionEvaluator.logic_version,
                "expected_logic_version": "btpc-001-price-action-v1",
                "expected_reason_code": spec["reason_code"],
                "required_disable_state": spec["required_disable_state"],
                "required_entry_state": spec["required_entry_state"],
                "completion_signal": spec["completion_signal"],
                "live_required_fact_authority": False,
                "l2_promotion_authority": False,
                "l4_scope_change_recommended": False,
                "real_order_authority": False,
                "candidate_or_finalgate_authority": False,
                "operation_layer_authority": False,
                "exchange_write_authority": False,
            }
        )
    return rows


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_classifier_rule_review_source_forbidden_effects"
    if status == "btpc_classifier_rule_review_waiting_for_action_rows":
        return "rerun_btpc_l2_keep_revise_fact_source_decision_before_classifier_review"
    if status == "btpc_classifier_rule_review_incomplete":
        return "finish_btpc_classifier_revision_or_live_source_mapping_before_review"
    return "continue_btpc_l2_shadow_observation_with_classifier_rule_review_recorded"


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
    for index, packet in enumerate(packets):
        decision = _as_dict(packet.get("decision"))
        for key in (
            "l2_promotion_recommended_now",
            "l4_scope_change_recommended",
            "real_order_scope_change_recommended",
        ):
            if decision.get(key) is True:
                effects.append(f"packet_{index}.decision.{key}")
    return sorted(set(effects))


def _rule_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Rule | Case | Implemented | Live fact | Real order |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Rule | Case | Implemented | Live fact | Real order |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("rule_id"),
                row.get("fixture_case"),
                row.get("implementation_ready"),
                row.get("live_required_fact_authority"),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--btpc-l2-decision-json",
        default=str(DEFAULT_BTPC_L2_DECISION_JSON),
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-json",
        default=str(DEFAULT_BTPC_PROXY_REPLAY_QUALITY_JSON),
    )
    parser.add_argument(
        "--btpc-live-source-mapping-json",
        default=str(DEFAULT_BTPC_LIVE_SOURCE_MAPPING_JSON),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_classifier_rule_review(
        btpc_l2_decision_packet=_load_json_object(
            Path(args.btpc_l2_decision_json).expanduser()
        ),
        btpc_proxy_replay_quality_packet=_load_json_object(
            Path(args.btpc_proxy_replay_quality_json).expanduser()
        ),
        btpc_live_source_mapping_packet=_load_json_object(
            Path(args.btpc_live_source_mapping_json).expanduser()
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
