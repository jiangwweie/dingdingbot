from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.models import Direction
from src.domain.strategy_contract_v2 import (
    EntryPolicy,
    EntryPolicyKind,
    ExitSignalRef,
    LifecycleAppliesTo,
    LifecycleExitPolicy,
    LifecycleExitPolicyKind,
    RequiredHistory,
    StopPolicy,
    StopPolicyKind,
    StrategyFamily,
    StrategyPermissionKey,
    StrategyPermissionState,
    StrategySignalV2,
    TakeProfitLevel,
    TakeProfitPolicy,
    TakeProfitPolicyKind,
)


def _direction_a_signal() -> StrategySignalV2:
    return StrategySignalV2(
        strategy_id="direction_a_donchian20_ema60_v0",
        strategy_family=StrategyFamily.LIFECYCLE_BREAKOUT,
        symbol="ETH/USDT:USDT",
        timeframe="4h",
        direction=Direction.LONG,
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_OPEN,
            trigger="donchian20_breakout",
            parameters={"lookback_bars": 20, "breakout_side": "high"},
        ),
        stop_policy=StopPolicy(
            kind=StopPolicyKind.STRUCTURE_REFERENCE,
            required=True,
            reference={"name": "frozen_direction_a_protective_stop"},
            risk_notes=(
                "Protective SL is a capital-protection boundary, not the EMA60 "
                "payoff-engine lifecycle exit."
            ),
        ),
        take_profit_policy=TakeProfitPolicy(
            kind=TakeProfitPolicyKind.LIFECYCLE_ONLY,
            levels=[],
        ),
        lifecycle_exit_policy=LifecycleExitPolicy(
            kind=LifecycleExitPolicyKind.EMA_CLOSE_BREAK,
            timeframe="4h",
            parameters={"ema_period": 60, "exit_timing": "after_close_break"},
        ),
        required_history=RequiredHistory(
            same_timeframe_bars=80,
            indicator_warmup={"donchian20": 20, "ema60": 60},
        ),
        score=None,
        metadata={"evidence_state": "design_only"},
        created_at_ms=1234567890,
        source_context_id="ctx-direction-a",
    )


def test_can_construct_direction_a_style_strategy_signal_v2():
    signal = _direction_a_signal()

    assert signal.strategy_family == StrategyFamily.LIFECYCLE_BREAKOUT
    assert signal.entry_policy.trigger == "donchian20_breakout"
    assert signal.entry_policy.parameters["lookback_bars"] == 20
    assert signal.take_profit_policy.kind == TakeProfitPolicyKind.LIFECYCLE_ONLY
    assert signal.take_profit_policy.levels == []
    assert signal.lifecycle_exit_policy.kind == LifecycleExitPolicyKind.EMA_CLOSE_BREAK
    assert signal.lifecycle_exit_policy.applies_to == LifecycleAppliesTo.EXISTING_POSITION_ONLY
    assert signal.lifecycle_exit_policy.emits == ExitSignalRef.EXIT_SIGNAL
    assert signal.stop_policy.required is True


def test_can_construct_pattern_strategy_style_strategy_signal_v2():
    signal = StrategySignalV2(
        strategy_id="pinbar_v1",
        strategy_family=StrategyFamily.PATTERN,
        symbol="BTC/USDT:USDT",
        timeframe="4h",
        direction=Direction.SHORT,
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_AFTER_CONFIRMED_CLOSE,
            trigger="pinbar_confirmed",
            parameters={"adapter": "pattern_result_v1"},
        ),
        stop_policy=StopPolicy(
            kind=StopPolicyKind.FIXED_PRICE,
            required=True,
            price=Decimal("101000"),
        ),
        take_profit_policy=TakeProfitPolicy(
            kind=TakeProfitPolicyKind.MULTI_TP_RR,
            levels=[
                TakeProfitLevel(rr=Decimal("1.5"), position_ratio=Decimal("0.5")),
                TakeProfitLevel(rr=Decimal("3.0"), position_ratio=Decimal("0.5")),
            ],
        ),
        lifecycle_exit_policy=LifecycleExitPolicy(kind=LifecycleExitPolicyKind.NONE),
        required_history=RequiredHistory(same_timeframe_bars=1),
        score=Decimal("0.82"),
        metadata={"pattern_details": {"wick_ratio": 0.72}},
        created_at_ms=123,
    )

    assert signal.strategy_family == StrategyFamily.PATTERN
    assert signal.take_profit_policy.kind == TakeProfitPolicyKind.MULTI_TP_RR
    assert len(signal.take_profit_policy.levels) == 2
    assert signal.lifecycle_exit_policy.kind == LifecycleExitPolicyKind.NONE


def test_stop_policy_carries_formal_stop_semantics_outside_metadata():
    signal = _direction_a_signal()

    assert signal.stop_policy.required is True
    assert signal.stop_policy.kind == StopPolicyKind.STRUCTURE_REFERENCE
    assert signal.stop_policy.reference == {"name": "frozen_direction_a_protective_stop"}
    assert "stop" not in signal.metadata


def test_strategy_permission_key_is_strategy_symbol_timeframe():
    key = StrategyPermissionKey(
        strategy_id="direction_a_donchian20_ema60_v0",
        symbol="ETH/USDT:USDT",
        timeframe="4h",
    )

    assert key.value == "direction_a_donchian20_ema60_v0:ETH/USDT:USDT:4h"
    assert key.model_dump() == {
        "strategy_id": "direction_a_donchian20_ema60_v0",
        "symbol": "ETH/USDT:USDT",
        "timeframe": "4h",
    }


def test_strategy_permission_states_are_eligibility_only_enums():
    assert StrategyPermissionState.OBSERVE_ONLY.value == "OBSERVE_ONLY"
    assert StrategyPermissionState.PAPER_ALLOWED.value == "PAPER_ALLOWED"
    assert StrategyPermissionState.LIVE_ALLOWED.value == "LIVE_ALLOWED"
    assert not hasattr(StrategyPermissionState.OBSERVE_ONLY, "can_execute")


def test_strategy_signal_v2_model_dump_and_validate_are_stable():
    signal = _direction_a_signal()
    dumped = signal.model_dump(mode="json")

    assert dumped["direction"] == "LONG"
    assert dumped["entry_policy"]["kind"] == "market_next_open"
    assert dumped["take_profit_policy"]["kind"] == "lifecycle_only"
    assert dumped["lifecycle_exit_policy"]["kind"] == "ema_close_break"
    assert dumped["required_history"]["indicator_warmup"] == {
        "donchian20": 20,
        "ema60": 60,
    }

    restored = StrategySignalV2.model_validate(dumped)
    assert restored == signal


def test_lifecycle_only_policy_rejects_fixed_tp_levels():
    with pytest.raises(ValueError, match="lifecycle_only must not define fixed TP levels"):
        TakeProfitPolicy(
            kind=TakeProfitPolicyKind.LIFECYCLE_ONLY,
            levels=[TakeProfitLevel(rr=Decimal("2"), position_ratio=Decimal("1"))],
        )
