#!/usr/bin/env python3
"""Build StrategyGroup live-facts readiness from intake and read-only facts.

The packet separates observe readiness from armed candidate-preparation
readiness. Missing account, open-order, budget, protection, or next-gate facts
must block candidate preparation, but they do not erase the StrategyGroup
handoff or authorize any execution.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_strategy_group_handoff_intake_packet import (
    DEFAULT_HANDOFF_DIR,
    build_packet as build_handoff_intake_packet,
)


PASS_VALUES = {
    "available",
    "clear",
    "flat",
    "fresh",
    "no_active_position",
    "no_open_orders",
    "none",
    "pass",
    "present",
    "ready",
    "trading",
    "valid",
    "waiting_for_fresh_strategy_signal",
    "ready_for_strategy_signal",
}
UNKNOWN_VALUES = {"", "missing", "not_available", "unknown", "unavailable"}
UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}


def _read_json(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _status(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("status", "state", "readiness", "value"):
            if value.get(key) is not None:
                return str(value.get(key)).strip().lower()
        return "present"
    if value is None:
        return "missing"
    return str(value).strip().lower()


def _is_pass(value: Any) -> bool:
    return _status(value) in PASS_VALUES


def _is_unknown(value: Any) -> bool:
    return _status(value) in UNKNOWN_VALUES


def _fact(live_facts: dict[str, Any], key: str) -> Any:
    value = live_facts.get(key)
    if value is not None:
        return value
    facts = live_facts.get("facts")
    if isinstance(facts, dict):
        return facts.get(key)
    return None


def _symbols_exchange_ready(
    *,
    group: dict[str, Any],
    live_facts: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    symbols = [str(item) for item in group.get("supported_symbols") or []]
    rules = _fact(live_facts, "exchange_rules")
    if not isinstance(rules, dict):
        return False, [], symbols
    symbol_rules = rules.get("symbols") if isinstance(rules.get("symbols"), dict) else rules
    ready: list[str] = []
    blocked: list[str] = []
    for symbol in symbols:
        status = _status(symbol_rules.get(symbol) if isinstance(symbol_rules, dict) else None)
        if status in {"trading", "ready", "available", "pass"}:
            ready.append(symbol)
        else:
            blocked.append(symbol)
    return not blocked and bool(symbols), ready, blocked


def _candidate_fact_checks(live_facts: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [
        ("account", "account", "block_candidate_prepare"),
        ("same_symbol_position_state", "active_position", "block_candidate_prepare"),
        ("open_order_same_symbol_state", "open_orders", "block_candidate_prepare"),
        ("protection_plan_state", "protection", "block_candidate_prepare"),
        ("budget_state", "budget", "block_candidate_prepare"),
        ("next_attempt_gate_state", "next_attempt_gate", "block_candidate_prepare"),
    ]
    rows: list[dict[str, Any]] = []
    for fact_key, live_key, missing_behavior in checks:
        value = _fact(live_facts, live_key)
        rows.append(
            {
                "fact_key": fact_key,
                "live_fact_key": live_key,
                "status": _status(value),
                "ready": _is_pass(value),
                "missing": _is_unknown(value),
                "missing_behavior": missing_behavior,
            }
        )
    return rows


def _group_readiness(
    *,
    group: dict[str, Any],
    live_facts: dict[str, Any],
) -> dict[str, Any]:
    exchange_ready, ready_symbols, blocked_symbols = _symbols_exchange_ready(
        group=group,
        live_facts=live_facts,
    )
    candidate_checks = _candidate_fact_checks(live_facts)
    candidate_blockers = [
        f"{item['live_fact_key']}:{item['status']}"
        for item in candidate_checks
        if not item["ready"]
    ]
    if blocked_symbols:
        candidate_blockers.append("exchange_rules_not_ready_for_all_symbols")
    observe_ready = exchange_ready
    default_mode = str((group.get("picker") or {}).get("default_mode") or "")
    if not observe_ready:
        readiness_status = "blocked_observation_exchange_rules"
    elif default_mode == "observe_only":
        readiness_status = "observe_only_ready_candidate_blocked"
    elif candidate_blockers:
        readiness_status = "observe_ready_armed_candidate_blocked"
    else:
        readiness_status = "armed_observation_live_facts_ready"
    return {
        "strategy_group_id": group.get("strategy_group_id"),
        "default_mode": default_mode,
        "readiness_status": readiness_status,
        "observe_ready": observe_ready,
        "armed_candidate_prepare_ready": (
            readiness_status == "armed_observation_live_facts_ready"
        ),
        "supported_symbol_count": group.get("supported_symbol_count"),
        "exchange_rules": {
            "ready": exchange_ready,
            "ready_symbols": ready_symbols,
            "blocked_symbols": blocked_symbols,
        },
        "candidate_fact_checks": candidate_checks,
        "blockers": candidate_blockers,
        "warnings": list(group.get("warnings") or []),
    }


def build_packet(
    *,
    intake_packet: dict[str, Any],
    live_facts: dict[str, Any],
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = generated_at_ms or int(time.time() * 1000)
    groups = [
        item for item in intake_packet.get("strategy_picker") or []
        if isinstance(item, dict)
    ]
    rows = [_group_readiness(group=group, live_facts=live_facts) for group in groups]
    blocked = [row for row in rows if row["blockers"]]
    observe_ready_count = sum(1 for row in rows if row["observe_ready"])
    armed_ready_count = sum(1 for row in rows if row["armed_candidate_prepare_ready"])
    if not rows:
        status = "blocked_no_strategy_group_intake"
    elif armed_ready_count:
        status = "strategy_group_live_facts_ready_for_armed_observation"
    elif observe_ready_count:
        status = "strategy_group_observe_ready_armed_blocked"
    else:
        status = "strategy_group_live_facts_blocked"
    return {
        "scope": "strategy_group_live_facts_readiness",
        "status": status,
        "generated_at_ms": generated_at_ms,
        "source_anchor": intake_packet.get("source_anchor") or {},
        "counts": {
            "strategy_groups": len(rows),
            "observe_ready": observe_ready_count,
            "armed_candidate_prepare_ready": armed_ready_count,
            "blocked_for_candidate_prepare": len(blocked),
        },
        "readiness": rows,
        "operator_path": {
            "can_continue_observation": observe_ready_count > 0,
            "can_prepare_fresh_candidate": armed_ready_count > 0,
            "next_gate": (
                "wait_for_or_generate_fresh_strategy_signal"
                if observe_ready_count > 0 and armed_ready_count == 0
                else "review_ready_groups_before_fresh_candidate_prepare"
                if armed_ready_count > 0
                else "resolve_live_fact_blockers"
            ),
            "requires_action_time_final_gate_before_submit": True,
            "requires_official_operation_layer": True,
        },
        "safety_invariants": {
            **{name: False for name in sorted(UNSAFE_FLAGS)},
            "reads_live_facts_only": True,
            "registers_runtime": False,
            "creates_candidate": False,
            "authorizes_execution": False,
            "places_order": False,
            "mutates_pg": False,
        },
        "blockers": sorted(
            {
                f"{row['strategy_group_id']}:{blocker}"
                for row in rows
                for blocker in row.get("blockers") or []
            }
        ),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build StrategyGroup live-facts readiness from intake and facts.",
    )
    parser.add_argument("--intake-json")
    parser.add_argument("--handoff-dir")
    parser.add_argument("--live-facts-json")
    parser.add_argument("--output-json", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.intake_json:
        intake = _read_json(args.intake_json)
    else:
        intake = build_handoff_intake_packet(
            handoff_dir=Path(args.handoff_dir).expanduser()
            if args.handoff_dir
            else DEFAULT_HANDOFF_DIR
        )
    live_facts = _read_json(args.live_facts_json)
    packet = build_packet(intake_packet=intake, live_facts=live_facts)
    _write_json(args.output_json, packet)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if packet["operator_path"]["can_continue_observation"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
