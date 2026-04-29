"""
Unit tests for research specs (StudySpec / JobSpec).

These specs are the SSOT entrypoint for research scripts to build consistent
OptimizationRequest / BacktestRequest objects.
"""

from decimal import Decimal

import pytest

from src.application.research_specs import (
    BacktestJobSpec,
    EngineCostSpec,
    OptunaStudySpec,
    TimeWindowMs,
)
from src.domain.models import (
    OptimizationObjective,
    ParameterDefinition,
    ParameterSpace,
    ParameterType,
)


def test_backtest_job_spec_to_backtest_request_maps_fields():
    window = TimeWindowMs(start_time_ms=1, end_time_ms=2)
    costs = EngineCostSpec(
        initial_balance=Decimal("123"),
        slippage_rate=Decimal("0"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0"),
    )
    spec = BacktestJobSpec(
        name="t",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=999,
        mode="v3_pms",
        costs=costs,
    )

    request = spec.to_backtest_request()
    assert request.symbol == "ETH/USDT:USDT"
    assert request.timeframe == "1h"
    assert request.start_time == 1
    assert request.end_time == 2
    assert request.limit == 999
    assert request.mode == "v3_pms"
    assert request.initial_balance == Decimal("123")
    assert request.slippage_rate == Decimal("0")
    assert request.fee_rate == Decimal("0")
    assert request.tp_slippage_rate == Decimal("0.0005")


def test_optuna_study_spec_to_optimization_request_maps_fields():
    window = TimeWindowMs(start_time_ms=10, end_time_ms=20)
    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )
    job = BacktestJobSpec(
        name="job",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
    )
    parameter_space = ParameterSpace(
        parameters=[
            ParameterDefinition(
                name="ema_period",
                type=ParameterType.INT,
                low=40,
                high=80,
            )
        ]
    )
    spec = OptunaStudySpec(
        study_name="study",
        job=job,
        objective=OptimizationObjective.SHARPE,
        n_trials=10,
        parameter_space=parameter_space,
        fixed_params={"breakeven_enabled": False},
    )

    request = spec.to_optimization_request()
    assert request.symbol == "ETH/USDT:USDT"
    assert request.timeframe == "1h"
    assert request.start_time == 10
    assert request.end_time == 20
    assert request.objective == OptimizationObjective.SHARPE
    assert request.n_trials == 10
    assert request.initial_balance == Decimal("10000")
    assert request.slippage_rate == Decimal("0.001")
    assert request.tp_slippage_rate == Decimal("0.0005")
    assert request.fee_rate == Decimal("0.0004")
    assert request.fixed_params == {"breakeven_enabled": False}


def test_time_window_requires_end_after_start():
    with pytest.raises(ValueError):
        TimeWindowMs(start_time_ms=5, end_time_ms=5)
