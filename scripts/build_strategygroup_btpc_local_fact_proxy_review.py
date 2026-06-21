#!/usr/bin/env python3
"""Build the local BTPC L2 fact-proxy review packet.

This review attaches review-only proxy coverage for BTPC-001 derivatives facts
and a local margin/liquidation shape. It is useful for P0.5 replay and L2
shadow quality review only. It never satisfies live RequiredFacts, never
changes tier policy, never calls FinalGate or Operation Layer, and never places
orders.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BTPC_FACT_QUALITY_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.json"
)
DEFAULT_BTPC_HANDOFF_JSON = (
    REPO_ROOT / "docs/current/strategy-group-handoffs/BTPC-001/handoff.json"
)
DEFAULT_BTPC_REPLAY_CORPUS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-local-fact-proxy-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-local-fact-proxy-review.md"
)


EXPECTED_PROXY_FACTS = {
    "historical_open_interest_window": {
        "source_gap": "historical_open_interest_window_missing",
        "proxy_source_type": "local_derivatives_window_proxy",
        "proxy_coverage_status": "local_proxy_attached",
        "l2_quality_effect": "can_review_crowding_direction_in_replay",
    },
    "historical_global_long_short_ratio_window": {
        "source_gap": "historical_global_long_short_ratio_window_missing",
        "proxy_source_type": "local_derivatives_window_proxy",
        "proxy_coverage_status": "local_proxy_attached",
        "l2_quality_effect": "can_review_positioning_bias_in_replay",
    },
    "top_trader_position_ratio_window": {
        "source_gap": "top_trader_position_ratio_window_missing",
        "proxy_source_type": "local_derivatives_window_proxy",
        "proxy_coverage_status": "local_proxy_attached",
        "l2_quality_effect": "can_review_top_trader_crowding_in_replay",
    },
    "real_exchange_margin_liquidation_model": {
        "source_gap": "real_exchange_margin_liquidation_model_missing",
        "proxy_source_type": "local_margin_liquidation_shape",
        "proxy_coverage_status": "local_review_model_attached",
        "l2_quality_effect": "can_review_research_leverage_bands_without_live_authority",
    },
    "short_squeeze_risk": {
        "source_gap": "short_squeeze_risk_not_runtime_blocking",
        "proxy_source_type": "local_short_squeeze_review_rule",
        "proxy_coverage_status": "local_review_rule_attached",
        "l2_quality_effect": "can_keep_short_squeeze_as_strategy_quality_review_input",
    },
}


def build_btpc_local_fact_proxy_review(
    *,
    btpc_fact_quality_packet: dict[str, Any],
    btpc_handoff: dict[str, Any],
    replay_corpus: dict[str, Any],
) -> dict[str, Any]:
    forbidden_effects = _forbidden_effects(
        btpc_fact_quality_packet,
        btpc_handoff,
        replay_corpus,
    )
    fact_rows = _proxy_rows(btpc_fact_quality_packet)
    replay_summary = _replay_corpus_summary(replay_corpus)
    margin_model = _margin_liquidation_review_model(btpc_handoff)
    handoff_boundary_ok = _btpc_boundary_ok(btpc_handoff)
    fact_quality_ready = (
        btpc_fact_quality_packet.get("status")
        == "btpc_l2_shadow_fact_quality_review_ready"
    )
    proxy_ready = all(
        row.get("proxy_coverage_status")
        in {
            "local_proxy_attached",
            "local_review_model_attached",
            "local_review_rule_attached",
        }
        for row in fact_rows
    )
    replay_boundary_ok = replay_summary["non_executing_boundary_ok"] is True
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif not fact_quality_ready or not handoff_boundary_ok or not replay_boundary_ok:
        status = "btpc_local_fact_proxy_review_incomplete"
    elif proxy_ready:
        status = "btpc_local_fact_proxy_review_ready"
    else:
        status = "btpc_local_fact_proxy_review_missing_proxy"

    live_required_fact_rows = [
        row for row in fact_rows if row["live_required_fact_satisfied"] is False
    ]
    live_order_blocker_rows = [
        row for row in fact_rows if row["blocks_btpc_live_order_eligibility"] is True
    ]
    return {
        "schema": "brc.btpc_local_fact_proxy_review.v1",
        "scope": "btpc_local_fact_proxy_review",
        "status": status,
        "source_status": {
            "btpc_fact_quality_review": btpc_fact_quality_packet.get("status"),
            "btpc_handoff": btpc_handoff.get("status"),
            "replay_corpus": replay_corpus.get("schema_version"),
        },
        "interaction": {
            "level": "L0_local_btpc_fact_proxy_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "expected_proxy_fact_count": len(EXPECTED_PROXY_FACTS),
            "proxy_attached_count": sum(
                1
                for row in fact_rows
                if row.get("proxy_coverage_status")
                in {
                    "local_proxy_attached",
                    "local_review_model_attached",
                    "local_review_rule_attached",
                }
            ),
            "l2_quality_proxy_ready_count": sum(
                1 for row in fact_rows if row.get("l2_quality_proxy_ready") is True
            ),
            "live_required_fact_satisfied_count": 0,
            "live_required_fact_gap_count": len(live_required_fact_rows),
            "btpc_live_order_eligibility_blocker_count": len(live_order_blocker_rows),
            "replay_sample_count": replay_summary["sample_count"],
            "would_enter_replay_count": replay_summary["would_enter_sample_count"],
            "margin_leverage_case_count": len(margin_model["leverage_cases"]),
            "forbidden_effect_count": len(forbidden_effects),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
        },
        "proxy_rows": fact_rows,
        "replay_corpus_summary": replay_summary,
        "margin_liquidation_review_model": margin_model,
        "decision": {
            "l2_shadow_quality_review_can_continue": (
                status == "btpc_local_fact_proxy_review_ready"
            ),
            "local_proxy_can_feed_replay_review": (
                status == "btpc_local_fact_proxy_review_ready"
            ),
            "local_proxy_satisfies_live_required_facts": False,
            "live_required_facts_still_required": True,
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
            "local_btpc_fact_proxy_review_only": True,
            "proxy_is_not_live_required_fact": True,
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
            "does_not_lower_owner_selected_leverage": True,
            "does_not_change_live_profile_or_sizing_defaults": True,
            "source_forbidden_effects": forbidden_effects,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    counts = _as_dict(packet.get("counts"))
    decision = _as_dict(packet.get("decision"))
    lines = [
        "# BTPC Local Fact Proxy Review",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Proxy facts: `{counts.get('proxy_attached_count', 0)}/{counts.get('expected_proxy_fact_count', 0)}`",
        f"- Replay samples: `{counts.get('replay_sample_count', 0)}`",
        f"- Margin leverage cases: `{counts.get('margin_leverage_case_count', 0)}`",
        "- Live RequiredFacts satisfied by proxy: `false`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Proxy Rows",
        "",
        _proxy_table(_dict_rows(packet.get("proxy_rows"))),
        "",
        "## Next",
        "",
        f"- `{decision.get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _proxy_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    source_rows = {
        str(row.get("required_fact") or ""): row
        for row in _dict_rows(packet.get("fact_rows"))
    }
    rows: list[dict[str, Any]] = []
    for required_fact, spec in EXPECTED_PROXY_FACTS.items():
        source = source_rows.get(required_fact, {})
        blocks_live_order = (
            required_fact == "real_exchange_margin_liquidation_model"
            or source.get("boundary_effect") == "blocks_any_btpc_real_order_eligibility"
        )
        rows.append(
            {
                "required_fact": required_fact,
                "source_gap": spec["source_gap"],
                "source_gap_present": source.get("gap") == spec["source_gap"],
                "source_boundary_effect": source.get("boundary_effect"),
                "proxy_source_type": spec["proxy_source_type"],
                "proxy_coverage_status": spec["proxy_coverage_status"],
                "l2_quality_effect": spec["l2_quality_effect"],
                "l2_quality_proxy_ready": True,
                "local_proxy_can_feed_replay_review": True,
                "live_required_fact_satisfied": False,
                "proxy_can_feed_finalgate": False,
                "proxy_can_feed_operation_layer": False,
                "blocks_btpc_live_order_eligibility": blocks_live_order,
                "real_order_authority": False,
                "l4_scope_change_recommended": False,
            }
        )
    return rows


def _replay_corpus_summary(packet: dict[str, Any]) -> dict[str, Any]:
    samples = _dict_rows(packet.get("replay_samples"))
    fixture_cases = [
        str(row.get("fixture_case"))
        for row in samples
        if str(row.get("fixture_case") or "").strip()
    ]
    return {
        "strategy_group_id": packet.get("strategy_group_id"),
        "scope": packet.get("scope"),
        "live_order_eligible": packet.get("live_order_eligible") is True,
        "sample_count": len(samples),
        "would_enter_sample_count": sum(
            1 for row in samples if "would_enter" in str(row.get("signal_status") or "")
        ),
        "missing_derivatives_context_present": (
            "missing_derivatives_context" in fixture_cases
        ),
        "fixture_cases": sorted(fixture_cases),
        "non_executing_boundary_ok": (
            packet.get("live_order_eligible") is not True
            and all(
                row.get("real_order_allowed") is not True
                and row.get("exchange_write_allowed") is not True
                and row.get("operation_layer_submit_allowed") is not True
                and row.get("not_execution_authority") is True
                for row in samples
            )
        ),
    }


def _margin_liquidation_review_model(handoff: dict[str, Any]) -> dict[str, Any]:
    risk_defaults = _as_dict(handoff.get("risk_defaults"))
    leverage_context = [
        str(item) for item in risk_defaults.get("research_leverage_context") or []
    ]
    cases = [
        case
        for case in (_leverage_case(item) for item in leverage_context)
        if case is not None
    ]
    return {
        "status": "local_review_model_attached" if cases else "missing_leverage_context",
        "model_kind": "review_only_initial_margin_envelope",
        "not_exchange_truth": True,
        "live_exchange_maintenance_margin_required": True,
        "does_not_lower_owner_selected_leverage": True,
        "does_not_mutate_live_profile": True,
        "leverage_cases": cases,
    }


def _leverage_case(raw: str) -> dict[str, Any] | None:
    leverage_text = raw.strip().lower().removesuffix("x")
    try:
        leverage = Decimal(leverage_text)
    except (InvalidOperation, ValueError):
        return None
    if leverage <= 0:
        return None
    initial_margin_rate = Decimal("1") / leverage
    return {
        "leverage": raw,
        "initial_margin_rate": _decimal_text(initial_margin_rate),
        "initial_margin_bps": _decimal_text(initial_margin_rate * Decimal("10000")),
        "live_liquidation_price_not_computed": True,
        "requires_exchange_maintenance_margin_for_live": True,
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


def _default_next_step(status: str) -> str:
    if status == "blocked_forbidden_effect":
        return "stop_and_repair_btpc_local_fact_proxy_source_forbidden_effects"
    if status == "btpc_local_fact_proxy_review_incomplete":
        return "repair_btpc_fact_quality_or_replay_proxy_inputs"
    if status == "btpc_local_fact_proxy_review_missing_proxy":
        return "attach_missing_btpc_local_fact_proxy_rows"
    return "run_btpc_l2_shadow_replay_with_local_fact_proxies_and_keep_live_scope_unchanged"


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
    handoff = packets[1] if len(packets) > 1 else {}
    boundary = _as_dict(handoff.get("execution_boundary"))
    if boundary.get("real_submit_authorized") is True:
        effects.append("btpc_handoff.execution_boundary.real_submit_authorized")
    replay = packets[2] if len(packets) > 2 else {}
    if replay.get("live_order_eligible") is True:
        effects.append("btpc_replay_corpus.live_order_eligible")
    for row in _dict_rows(replay.get("replay_samples")):
        fixture = str(row.get("fixture_case") or "unknown")
        if row.get("real_order_allowed") is True:
            effects.append(f"btpc_replay_corpus.{fixture}.real_order_allowed")
        if row.get("exchange_write_allowed") is True:
            effects.append(f"btpc_replay_corpus.{fixture}.exchange_write_allowed")
        if row.get("operation_layer_submit_allowed") is True:
            effects.append(
                f"btpc_replay_corpus.{fixture}.operation_layer_submit_allowed"
            )
    return sorted(set(effects))


def _proxy_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| Fact | Proxy | L2 review | Live fact | Real order |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| Fact | Proxy | L2 review | Live fact | Real order |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("required_fact"),
                row.get("proxy_coverage_status"),
                row.get("l2_quality_effect"),
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


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--btpc-fact-quality-json", default=str(DEFAULT_BTPC_FACT_QUALITY_JSON)
    )
    parser.add_argument("--btpc-handoff-json", default=str(DEFAULT_BTPC_HANDOFF_JSON))
    parser.add_argument(
        "--btpc-replay-corpus-json", default=str(DEFAULT_BTPC_REPLAY_CORPUS_JSON)
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_btpc_local_fact_proxy_review(
        btpc_fact_quality_packet=_load_json_object(
            Path(args.btpc_fact_quality_json).expanduser()
        ),
        btpc_handoff=_load_json_object(Path(args.btpc_handoff_json).expanduser()),
        replay_corpus=_load_json_object(Path(args.btpc_replay_corpus_json).expanduser()),
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
