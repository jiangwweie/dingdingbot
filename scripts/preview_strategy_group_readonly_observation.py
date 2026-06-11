#!/usr/bin/env python3
"""Preview strategy-group read-only signals without recording observations.

This command is intentionally lighter than
``run_strategy_group_readonly_observation_once.py``: it does not connect to PG,
does not write observation rows, does not resolve runtimes, and does not create
shadow candidates. It is a safe operator probe for checking whether the broader
strategy shelf has any current would-enter signals while ACTIVE runtime
observation is waiting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SourceName = Literal["sample", "local_sqlite_fallback", "live_market"]


def build_preview_packet(*, source_name: SourceName) -> dict[str, Any]:
    from src.application.strategy_group_live_readonly_observation import (
        SampleStrategyGroupMarketBarSource,
        build_strategy_group_live_readonly_observation_v1,
    )

    if source_name == "sample":
        source = SampleStrategyGroupMarketBarSource()
    else:
        from src.application.strategy_group_readonly_observation_scheduler import (
            build_observation_market_source,
        )

        source = build_observation_market_source(source_name)

    preview = build_strategy_group_live_readonly_observation_v1(market_source=source)
    payload = preview.model_dump(mode="json")
    signals = payload.get("current_signals") or []
    would_enter = [
        _signal_summary(row)
        for row in signals
        if isinstance(row, dict) and row.get("signal_type") == "would_enter"
    ]
    no_action = [
        _signal_summary(row)
        for row in signals
        if isinstance(row, dict) and row.get("signal_type") == "no_action"
    ]
    invalid = [
        _signal_summary(row)
        for row in signals
        if isinstance(row, dict) and row.get("signal_type") == "invalid"
    ]
    return {
        "scope": "strategy_group_readonly_observation_preview",
        "status": "preview_built",
        "source_requested": source_name,
        "market_source": getattr(source, "source_id", "unknown_market_source"),
        "checks": {
            "candidate_count": len(payload.get("candidates") or []),
            "current_signal_count": len(signals),
            "would_enter_signal_count": len(would_enter),
            "no_action_signal_count": len(no_action),
            "invalid_signal_count": len(invalid),
            "forbidden_effects": [],
        },
        "would_enter_signals": would_enter,
        "no_action_signals": no_action,
        "invalid_signals": invalid,
        "preview": payload,
        "operator_command_plan": {
            "not_executed": True,
            "records_observation": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "withdrawal_or_transfer_requested": False,
            "next_step": (
                "review_strategy_group_would_enter_signals_without_execution"
                if would_enter
                else "continue_runtime_observation_or_review_strategy_coverage"
            ),
        },
        "safety_invariants": {
            "preview_only": True,
            "database_connected": False,
            "pg_observation_written": False,
            "runtime_resolver_called": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_started": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _signal_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "strategy_group_id": row.get("strategy_group_id"),
        "strategy_family_version_id": row.get("strategy_family_version_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "signal_type": row.get("signal_type"),
        "confidence": row.get("confidence"),
        "reason_codes": row.get("reason_codes") or [],
        "human_summary": row.get("human_summary"),
        "market_bar_timestamp_ms": row.get("market_bar_timestamp_ms"),
        "market_bar_close": row.get("market_bar_close"),
        "not_order": row.get("not_order"),
        "not_execution_intent": row.get("not_execution_intent"),
        "no_execution_permission": row.get("no_execution_permission"),
        "no_order_permission": row.get("no_order_permission"),
        "no_runtime_start": row.get("no_runtime_start"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="local_sqlite_fallback",
        help="Read-only closed-candle source.",
    )
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)

    packet = build_preview_packet(source_name=args.source)
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
