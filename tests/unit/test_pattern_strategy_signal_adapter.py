from __future__ import annotations

from decimal import Decimal

from src.application.pattern_strategy_signal_adapter import (
    PatternResultToStrategySignalV2Adapter,
)
from src.domain.models import Direction, FilterResult, KlineData, PatternResult
from src.domain.strategy_contract_v2 import (
    EntryPolicyKind,
    LifecycleExitPolicyKind,
    StopPolicyKind,
    StrategyFamily,
    TakeProfitPolicyKind,
)


def _kline() -> KlineData:
    return KlineData(
        symbol="ETH/USDT:USDT",
        timeframe="4h",
        timestamp=1234567890,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("108"),
        volume=Decimal("1000"),
    )


def _pattern(strategy_name: str = "pinbar") -> PatternResult:
    return PatternResult(
        strategy_name=strategy_name,
        direction=Direction.LONG,
        score=Decimal("0.75"),
        details={
            "wick_ratio": 0.7,
            "stop_price_hint": 95,
            "tp_hint": 120,
        },
    )


def test_pinbar_pattern_result_maps_to_strategy_signal_v2():
    signal = PatternResultToStrategySignalV2Adapter().adapt(
        pattern=_pattern("pinbar"),
        kline=_kline(),
        filter_results=[
            ("ema_trend", FilterResult(passed=True, reason="trend_match")),
        ],
        source_context_id="ctx-pinbar",
    )

    assert signal.strategy_id == "pinbar_v1"
    assert signal.strategy_family == StrategyFamily.PATTERN
    assert signal.symbol == "ETH/USDT:USDT"
    assert signal.timeframe == "4h"
    assert signal.direction == Direction.LONG
    assert signal.score == Decimal("0.75")
    assert signal.source_context_id == "ctx-pinbar"
    assert signal.required_history.same_timeframe_bars == 1
    assert signal.metadata["pattern_details"]["wick_ratio"] == 0.7
    assert signal.metadata["filter_results"][0]["name"] == "ema_trend"


def test_engulfing_pattern_result_maps_with_two_bar_history_requirement():
    signal = PatternResultToStrategySignalV2Adapter(adapter_version="v1").adapt(
        pattern=_pattern("engulfing"),
        kline=_kline(),
    )

    assert signal.strategy_id == "engulfing_v1"
    assert signal.required_history.same_timeframe_bars == 2
    assert signal.strategy_family == StrategyFamily.PATTERN


def test_entry_policy_and_lifecycle_policy_are_observe_only_pattern_defaults():
    signal = PatternResultToStrategySignalV2Adapter().adapt(
        pattern=_pattern("pinbar"),
        kline=_kline(),
    )

    assert signal.entry_policy.kind == EntryPolicyKind.MARKET_AFTER_CONFIRMED_CLOSE
    assert signal.entry_policy.trigger == "pattern_confirmed"
    assert signal.lifecycle_exit_policy.kind == LifecycleExitPolicyKind.NONE


def test_diagnostics_are_preserved_but_stop_and_tp_semantics_are_not_derived_from_details():
    signal = PatternResultToStrategySignalV2Adapter().adapt(
        pattern=_pattern("pinbar"),
        kline=_kline(),
    )

    assert signal.metadata["pattern_details"]["stop_price_hint"] == 95
    assert signal.metadata["pattern_details"]["tp_hint"] == 120
    assert signal.stop_policy.kind == StopPolicyKind.NONE
    assert signal.stop_policy.required is False
    assert signal.stop_policy.price is None
    assert signal.take_profit_policy.kind == TakeProfitPolicyKind.MULTI_TP_RR
    assert signal.take_profit_policy.levels == []
    assert signal.metadata["tp_policy_note"].startswith("derived_later")


def test_adapter_does_not_require_runtime_risk_or_execution_dependencies():
    adapter = PatternResultToStrategySignalV2Adapter()

    signal = adapter.adapt(pattern=_pattern("pinbar"), kline=_kline())

    assert signal.strategy_id == "pinbar_v1"
    assert not hasattr(adapter, "_risk_calculator")
    assert not hasattr(adapter, "_execution_orchestrator")
    assert not hasattr(adapter, "_global_kill_switch")


def test_model_dump_is_stable_for_adapter_output():
    signal = PatternResultToStrategySignalV2Adapter(adapter_version="v2").adapt(
        pattern=_pattern("Pinbar"),
        kline=_kline(),
        filter_results=[
            (
                "runtime_direction_policy",
                FilterResult(
                    passed=False,
                    reason="direction_not_allowed_by_runtime_profile",
                    metadata={"actual_direction": "LONG"},
                ),
            )
        ],
        source_context_id="ctx-stable",
    )

    dumped = signal.model_dump(mode="json")

    assert dumped["strategy_id"] == "pinbar_v2"
    assert dumped["strategy_family"] == "pattern"
    assert dumped["entry_policy"]["kind"] == "market_after_confirmed_close"
    assert dumped["entry_policy"]["trigger"] == "pattern_confirmed"
    assert dumped["stop_policy"]["kind"] == "none"
    assert dumped["stop_policy"]["required"] is False
    assert dumped["take_profit_policy"]["kind"] == "multi_tp_rr"
    assert dumped["take_profit_policy"]["levels"] == []
    assert dumped["lifecycle_exit_policy"]["kind"] == "none"
    assert dumped["required_history"]["same_timeframe_bars"] == 1
    assert dumped["created_at_ms"] == 1234567890
    assert dumped["metadata"]["adapter_version"] == "v2"
    assert dumped["metadata"]["filter_results"][0]["result"]["passed"] is False
