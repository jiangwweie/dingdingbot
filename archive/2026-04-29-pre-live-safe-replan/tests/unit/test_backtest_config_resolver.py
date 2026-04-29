"""
Unit tests for the backtest config abstraction layer.

These tests do not touch exchange, PG, or historical data. They only verify the
profile/request/runtime override contract.
"""

from decimal import Decimal

import pytest

from src.application.backtest_config import (
    BACKTEST_ETH_BASELINE_PROFILE,
    BACKTEST_INJECTABLE_PARAMS,
    BacktestConfigResolver,
    BacktestExecutionProfile,
    BacktestRiskProfile,
    DEFAULT_BACKTEST_PROFILE_PROVIDER,
    StaticBacktestProfileProvider,
    list_backtest_injectable_params,
)
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides, Direction, OrderStrategy, RiskConfig
from src.domain.validators import stable_config_hash


@pytest.mark.asyncio
async def test_backtest_eth_baseline_resolves_profile_defaults():
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)

    resolved = await resolver.resolve("backtest_eth_baseline")

    assert resolved.profile_name == "backtest_eth_baseline"
    assert resolved.symbol == "ETH/USDT:USDT"
    assert resolved.timeframe == "1h"
    assert resolved.params.mtf_mapping == {"1h": "4h"}
    assert resolved.params.allowed_directions == ["LONG"]
    assert resolved.params.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
    assert resolved.params.tp_targets == [Decimal("1.0"), Decimal("3.5")]
    assert resolved.risk_config.max_loss_percent == Decimal("0.01")
    assert resolved.order_strategy.initial_stop_loss_rr == Decimal("-1.0")


@pytest.mark.asyncio
async def test_request_overrides_market_risk_costs_and_order_strategy():
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)
    request = BacktestRequest(
        symbol="BTC/USDT:USDT",
        timeframe="4h",
        limit=500,
        initial_balance=Decimal("20000"),
        slippage_rate=Decimal("0.002"),
        risk_overrides=RiskConfig(
            max_loss_percent=Decimal("0.02"),
            max_leverage=10,
            max_total_exposure=Decimal("0.5"),
        ),
        order_strategy=OrderStrategy(
            id="request_order",
            name="Request Order",
            tp_levels=2,
            tp_ratios=[Decimal("0.7"), Decimal("0.3")],
            tp_targets=[Decimal("1.0"), Decimal("2.0")],
            initial_stop_loss_rr=Decimal("-1.2"),
        ),
    )

    resolved = await resolver.resolve("backtest_eth_baseline", request=request)

    assert resolved.symbol == "BTC/USDT:USDT"
    assert resolved.timeframe == "4h"
    assert resolved.limit == 500
    assert resolved.params.initial_balance == Decimal("20000")
    assert resolved.params.slippage_rate == Decimal("0.002")
    assert resolved.risk_config.max_loss_percent == Decimal("0.02")
    assert resolved.order_strategy.id == "request_order"
    assert resolved.order_strategy.tp_ratios == [Decimal("0.7"), Decimal("0.3")]


@pytest.mark.asyncio
async def test_runtime_overrides_take_priority_over_request_and_profile():
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)
    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        order_strategy=OrderStrategy(
            id="request_order",
            name="Request Order",
            tp_levels=2,
            tp_ratios=[Decimal("0.7"), Decimal("0.3")],
            tp_targets=[Decimal("1.0"), Decimal("2.0")],
        ),
    )
    overrides = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.25"), Decimal("0.75")],
        tp_targets=[Decimal("1.5"), Decimal("4.0")],
        allowed_directions=["SHORT"],
    )

    resolved = await resolver.resolve("backtest_eth_baseline", request=request, runtime_overrides=overrides)

    assert resolved.params.tp_ratios == [Decimal("0.25"), Decimal("0.75")]
    assert resolved.params.tp_targets == [Decimal("1.5"), Decimal("4.0")]
    assert resolved.params.allowed_directions == ["SHORT"]
    assert resolved.order_strategy.id == "backtest_eth_baseline_execution"
    assert resolved.order_strategy.tp_targets == [Decimal("1.5"), Decimal("4.0")]


@pytest.mark.asyncio
async def test_resolved_config_builds_backtest_request_without_mutating_source_request():
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)
    request = BacktestRequest(symbol="SOL/USDT:USDT", timeframe="1h", limit=300)

    resolved = await resolver.resolve("backtest_eth_baseline", request=request)
    materialized = resolved.to_backtest_request(request)

    assert request.strategies is None
    assert request.order_strategy is None
    assert materialized.symbol == "SOL/USDT:USDT"
    assert materialized.strategies is not None
    assert materialized.risk_overrides is not None
    assert materialized.order_strategy is not None


def test_execution_profile_rejects_invalid_tp_ratio_sum():
    with pytest.raises(ValueError, match="tp_ratios must sum to 1.0"):
        BacktestExecutionProfile(
            tp_levels=2,
            tp_ratios=[Decimal("0.4"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.0")],
        )


def test_risk_profile_converts_decimal_strings():
    risk = BacktestRiskProfile(
        max_loss_percent="0.01",
        max_leverage=20,
        max_total_exposure="1.0",
    )

    assert risk.max_loss_percent == Decimal("0.01")
    assert risk.max_total_exposure == Decimal("1.0")


@pytest.mark.asyncio
async def test_static_provider_returns_deep_copy():
    provider = StaticBacktestProfileProvider({BACKTEST_ETH_BASELINE_PROFILE.name: BACKTEST_ETH_BASELINE_PROFILE})

    first = await provider.get_backtest_profile("backtest_eth_baseline")
    second = await provider.get_backtest_profile("backtest_eth_baseline")

    assert first is not None
    assert second is not None
    first.execution.tp_ratios[0] = Decimal("0.9")
    assert second.execution.tp_ratios[0] == Decimal("0.5")


@pytest.mark.asyncio
async def test_unknown_profile_raises_clear_error():
    resolver = BacktestConfigResolver(DEFAULT_BACKTEST_PROFILE_PROVIDER)

    with pytest.raises(ValueError, match="backtest profile not found"):
        await resolver.resolve("missing_profile")


def test_injectable_param_contract_contains_core_override_keys():
    keys = {param.key for param in BACKTEST_INJECTABLE_PARAMS}

    assert "strategy.ema.min_distance_pct" in keys
    assert "strategy.ema.period" in keys
    assert "system.mtf_ema_period" in keys
    assert "execution.tp_ratios" in keys
    assert "execution.tp_targets" in keys
    assert "risk_overrides" in keys
    assert "order_strategy" in keys
    assert "backtest.allowed_directions" in keys


def test_injectable_param_contract_can_filter_optimizer_safe_params():
    optimizer_params = list_backtest_injectable_params(optimizer_safe=True)

    assert optimizer_params
    assert all(param.optimizer_safe for param in optimizer_params)
    assert "symbol" not in {param.key for param in optimizer_params}
    assert "execution.tp_targets" in {param.key for param in optimizer_params}


def test_runtime_override_injectable_keys_align_with_backtest_runtime_overrides_model():
    key_to_field = {
        "strategy.atr.max_atr_ratio": "max_atr_ratio",
        "strategy.ema.min_distance_pct": "min_distance_pct",
        "strategy.ema.period": "ema_period",
        "system.mtf_ema_period": "mtf_ema_period",
        "system.mtf_mapping": "mtf_mapping",
        "execution.tp_ratios": "tp_ratios",
        "execution.tp_targets": "tp_targets",
        "backtest.breakeven_enabled": "breakeven_enabled",
        "backtest.allowed_directions": "allowed_directions",
        "backtest.same_bar_policy": "same_bar_policy",
        "backtest.same_bar_tp_first_prob": "same_bar_tp_first_prob",
        "backtest.random_seed": "random_seed",
    }
    runtime_override_keys = {
        param.key
        for param in BACKTEST_INJECTABLE_PARAMS
        if "runtime_overrides" in param.sources
    }

    assert runtime_override_keys == set(key_to_field)
    assert set(key_to_field.values()).issubset(set(BacktestRuntimeOverrides.model_fields))


def test_backtest_profile_hash_is_stable_across_key_order_and_unicode_payloads():
    payload_a = {"profile_name": "回测ETH", "profile": {"b": 2, "a": "中文"}}
    payload_b = {"profile": {"a": "中文", "b": 2}, "profile_name": "回测ETH"}

    assert stable_config_hash(payload_a) == stable_config_hash(payload_b)
