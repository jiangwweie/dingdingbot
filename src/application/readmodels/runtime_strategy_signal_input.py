#!/usr/bin/env python3
"""Build a read-only strategy signal input artifact for one runtime."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


async def _load_runtime(runtime_instance_id: str) -> Any:
    from src.infrastructure.connection_pool import close_all_connections
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    repository = PgStrategyRuntimeRepository()
    await repository.initialize()
    try:
        runtime = await repository.get(runtime_instance_id)
        if runtime is None:
            raise RuntimeError(f"strategy runtime not found: {runtime_instance_id}")
        return runtime
    finally:
        await close_all_connections()


def market_source(args: argparse.Namespace) -> Any:
    if args.source == "sample":
        from src.application.strategy_group_live_readonly_observation import (
            SampleStrategyGroupMarketBarSource,
        )

        return SampleStrategyGroupMarketBarSource()
    from src.infrastructure.binance_public_kline_market_source import (
        BinancePublicKlineMarketSource,
    )

    return BinancePublicKlineMarketSource(timeout_seconds=args.timeout_seconds)


def _candle_json(candle: Any) -> dict[str, Any]:
    return {
        "open_time_ms": int(candle.open_time_ms),
        "close_time_ms": (
            int(candle.close_time_ms) if getattr(candle, "close_time_ms", None) is not None else None
        ),
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(getattr(candle, "volume", Decimal("0"))),
    }


def _atr(candles: list[Any], *, window: int = 14) -> Decimal | None:
    if not candles:
        return None
    sample = candles[-window:]
    if not sample:
        return None
    total = sum((Decimal(str(item.high)) - Decimal(str(item.low))) for item in sample)
    return (total / Decimal(len(sample))).quantize(Decimal("0.00000001"))


def _account_placeholder(*, runtime: Any, now_ms: int) -> Any:
    from src.domain.strategy_family_signal import AccountFactsSnapshot

    return AccountFactsSnapshot(
        source="runtime_signal_input_builder_placeholder",
        truth_level="placeholder_replaced_by_trusted_runtime_overlay",
        timestamp_ms=now_ms,
        freshness="placeholder",
        account_status="unknown",
        positions=[],
        open_orders=[],
        position_count=0,
        open_order_count=0,
        unknown_unmanaged_counts={"positions": 0, "orders": 0},
        reconciliation_status={
            "status": "placeholder",
            "trusted_overlay_required_before_candidate_planning": True,
        },
        read_only_provider="none",
        limitations=[
            "not_trusted_for_candidate_planning",
            "must_be_replaced_by_trusted_runtime_fact_overlay",
        ],
    )


def _trial_constraints(runtime: Any) -> dict[str, Any]:
    boundary = runtime.boundary
    return {
        "runtime_instance_id": runtime.runtime_instance_id,
        "max_attempts": boundary.max_attempts,
        "attempts_used": boundary.attempts_used,
        "attempts_remaining": boundary.attempts_remaining,
        "max_loss_budget": str(boundary.total_budget or ""),
        "budget_reserved": str(boundary.budget_reserved),
        "budget_remaining": str(boundary.budget_remaining or ""),
        "max_notional_per_attempt": str(boundary.max_notional_per_attempt or ""),
        "max_active_positions": boundary.max_active_positions,
        "max_leverage": str(boundary.max_leverage or ""),
        "allowed_symbols": list(boundary.allowed_symbols),
        "allowed_sides": list(boundary.allowed_sides),
        "requires_protection": boundary.requires_protection,
        "requires_review": boundary.requires_review,
    }


def build_signal_input(
    *,
    runtime: Any,
    one_hour: list[Any],
    four_hour: list[Any],
    source_id: str,
    source_type: str,
    evaluation_id: str | None,
    playbook_id: str | None,
    now_ms: int,
) -> Any:
    from src.domain.strategy_family_signal import (
        MarketSnapshot,
        SignalDataQuality,
        StrategyFamilySignalInput,
    )

    latest = one_hour[-1]
    trigger_candle_close_time_ms = getattr(latest, "close_time_ms", None)
    if trigger_candle_close_time_ms is None or int(trigger_candle_close_time_ms) <= int(latest.open_time_ms):
        raise RuntimeError("latest closed candle is missing authoritative close_time_ms")
    trigger_candle_close_time_ms = int(trigger_candle_close_time_ms)
    atr = _atr(one_hour)
    resolved_evaluation_id = evaluation_id or (
        f"runtime-signal-input:{runtime.runtime_instance_id}:"
        f"{runtime.strategy_family_id}:{trigger_candle_close_time_ms}"
    )
    return StrategyFamilySignalInput(
        evaluation_id=resolved_evaluation_id,
        strategy_family_id=runtime.strategy_family_id,
        strategy_family_version_id=runtime.strategy_family_version_id,
        playbook_id=playbook_id or runtime.policy_snapshot.playbook_id,
        binding_id=runtime.trial_binding_id,
        symbol=runtime.symbol,
        timestamp_ms=trigger_candle_close_time_ms,
        trigger_candle_close_time_ms=trigger_candle_close_time_ms,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol=runtime.symbol,
            timestamp_ms=trigger_candle_close_time_ms,
            source=source_id,
            freshness="latest_closed_public_kline"
            if source_type == "live_market_read_only"
            else "sample_rehearsal",
            last_price=Decimal(str(latest.close)),
            mark_price=Decimal(str(latest.close)),
            atr=atr,
            timeframe="1h",
            candle_context={
                "windows": {
                    "1h": [_candle_json(item) for item in one_hour],
                    "4h": [_candle_json(item) for item in four_hour],
                },
                "closed_bar": True,
                "source_type": source_type,
            },
        ),
        account_facts_snapshot=_account_placeholder(runtime=runtime, now_ms=now_ms),
        position_open_order_summary={
            "source": "placeholder_replaced_by_trusted_runtime_overlay",
            "position_count": 0,
            "open_order_count": 0,
        },
        reconciliation_status={
            "status": "placeholder",
            "trusted_overlay_required_before_candidate_planning": True,
        },
        runtime_safety_snapshot={
            "runtime_instance_id": runtime.runtime_instance_id,
            "runtime_state": runtime.status.value,
            "execution_enabled": runtime.execution_enabled,
            "shadow_mode": runtime.shadow_mode,
            "trusted_overlay_required_before_candidate_planning": True,
        },
        trial_constraints_snapshot=_trial_constraints(runtime),
        source="runtime_strategy_signal_input_builder",
        freshness="fresh_read_only_market_context",
        input_quality=SignalDataQuality(
            notes=[
                "market_context_from_read_only_closed_candles",
                "account_facts_placeholder_requires_trusted_overlay_before_candidate_planning",
            ]
        ),
    )


async def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    from src.application.runtime_strategy_signal_evaluation_service import (
        RuntimeStrategySignalEvaluationService,
        RuntimeStrategySignalEvaluationStatus,
    )

    runtime = await _load_runtime(args.runtime_instance_id)
    source = market_source(args)
    one_hour = source.latest_closed_candles(
        symbol=args.symbol or runtime.symbol,
        timeframe="1h",
        limit=args.one_hour_limit,
    )
    four_hour = source.latest_closed_candles(
        symbol=args.symbol or runtime.symbol,
        timeframe="4h",
        limit=args.four_hour_limit,
    )
    if args.symbol and args.symbol != runtime.symbol:
        raise RuntimeError("signal symbol override must match runtime symbol")
    now_ms = int(time.time() * 1000)
    signal_input = build_signal_input(
        runtime=runtime,
        one_hour=one_hour,
        four_hour=four_hour,
        source_id=getattr(source, "source_id", "unknown_read_only_market_source"),
        source_type=getattr(source, "source_type", "read_only_market_source"),
        evaluation_id=args.evaluation_id,
        playbook_id=args.playbook_id,
        now_ms=now_ms,
    )
    evaluation = RuntimeStrategySignalEvaluationService().evaluate(signal_input)
    ready = (
        evaluation.status
        == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    )
    return {
        "scope": "runtime_strategy_signal_input_artifact",
        "status": "ready_for_shadow_candidate_prepare" if ready else evaluation.status.value,
        "runtime_instance_id": runtime.runtime_instance_id,
        "strategy_family_id": runtime.strategy_family_id,
        "strategy_family_version_id": runtime.strategy_family_version_id,
        "symbol": runtime.symbol,
        "side": runtime.side,
        "source": getattr(source, "source_id", "unknown_read_only_market_source"),
        "source_type": getattr(source, "source_type", "read_only_market_source"),
        "signal_input": _json_value(signal_input),
        "evaluation_result": _json_value(evaluation),
        "signal_input_artifact_plan": {
            "scope": "runtime_strategy_signal_input_artifact_plan",
            "next_step": (
                "materialize_pg_promotion_action_time_lane"
                if ready
                else "observe_only_or_wait_for_next_closed_bar"
            ),
            "pg_materialization_steps": (
                [
                    "materialize_pg_promotion_action_time_lane",
                    "materialize_action_time_ticket",
                ]
                if ready
                else []
            ),
            "not_executed": True,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "signal_observation_artifact_only": True,
            "market_data_read_only": True,
            "account_facts_placeholder_not_trusted": True,
            "trusted_runtime_overlay_required_before_candidate_planning": True,
            "signal_evaluation_created": False,
            "order_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a read-only strategy signal input artifact for one runtime.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--source", choices=["live_market", "sample"], default="live_market")
    parser.add_argument("--symbol")
    parser.add_argument("--evaluation-id")
    parser.add_argument("--playbook-id")
    parser.add_argument("--one-hour-limit", type=int, default=25)
    parser.add_argument("--four-hour-limit", type=int, default=25)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        payload = asyncio.run(build_artifact(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if payload["status"] == "ready_for_shadow_candidate_prepare" else 2


if __name__ == "__main__":
    raise SystemExit(main())
