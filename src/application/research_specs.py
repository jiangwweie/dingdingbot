"""
Research specs (StudySpec / JobSpec) for backtest + optuna scripts.

Design goal:
- Stop scripts from hand-assembling conflicting parameter semantics.
- Make "what this run means" explicit and serializable.
- Keep runtime profiles read-only: research outputs are candidate-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    OptimizationObjective,
    OptimizationRequest,
    ParameterSpace,
)


class TimeWindowMs(BaseModel):
    start_time_ms: int = Field(..., ge=0)
    end_time_ms: int = Field(..., ge=0)

    @model_validator(mode="after")
    def validate_window(self) -> "TimeWindowMs":
        if self.end_time_ms <= self.start_time_ms:
            raise ValueError("end_time_ms must be greater than start_time_ms")
        return self


class EngineCostSpec(BaseModel):
    initial_balance: Decimal = Decimal("10000")
    slippage_rate: Decimal = Decimal("0.001")
    tp_slippage_rate: Decimal = Decimal("0.0005")
    fee_rate: Decimal = Decimal("0.0004")


class BacktestJobSpec(BaseModel):
    """
    Spec for a single backtest run.

    This spec is intended to be used by "pure backtest entry scripts", such as
    scripts/run_eth_backtest.py, to keep the run definition consistent.
    """

    name: str
    profile_name: str = "backtest_eth_baseline"
    symbol: str = "ETH/USDT:USDT"
    timeframe: str = "1h"
    window: TimeWindowMs
    limit: int = Field(default=9000, ge=10, le=30000)
    mode: str = "v3_pms"
    costs: EngineCostSpec = Field(default_factory=EngineCostSpec)

    # Highest-priority runtime overrides (candidate-only, never written to runtime DB)
    runtime_overrides: Optional[BacktestRuntimeOverrides] = None

    def to_backtest_request(self) -> BacktestRequest:
        return BacktestRequest(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_time=self.window.start_time_ms,
            end_time=self.window.end_time_ms,
            limit=self.limit,
            mode=self.mode,
            initial_balance=self.costs.initial_balance,
            slippage_rate=self.costs.slippage_rate,
            tp_slippage_rate=self.costs.tp_slippage_rate,
            fee_rate=self.costs.fee_rate,
        )


class OptunaStudySpec(BaseModel):
    """
    Spec for an Optuna study.

    Scripts should build OptimizationRequest from this spec, rather than
    scattering fixed params and cost semantics across files.
    """

    study_name: str
    job: BacktestJobSpec
    objective: OptimizationObjective = OptimizationObjective.SHARPE
    n_trials: int = Field(default=30, ge=1, le=100000)
    parameter_space: ParameterSpace
    fixed_params: dict[str, Any] = Field(default_factory=dict)

    def to_optimization_request(self) -> OptimizationRequest:
        return OptimizationRequest(
            symbol=self.job.symbol,
            timeframe=self.job.timeframe,
            start_time=self.job.window.start_time_ms,
            end_time=self.job.window.end_time_ms,
            objective=self.objective,
            n_trials=self.n_trials,
            parameter_space=self.parameter_space,
            initial_balance=self.job.costs.initial_balance,
            slippage_rate=self.job.costs.slippage_rate,
            tp_slippage_rate=self.job.costs.tp_slippage_rate,
            fee_rate=self.job.costs.fee_rate,
            fixed_params=self.fixed_params,
        )

