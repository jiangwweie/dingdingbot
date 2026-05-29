"""Pure fee/slippage cost model for CPM historical replay.

This module adjusts already-computed historical return observations. It does
not simulate orders, position sizing, leverage, funding, matching, routing, or
execution.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class CPMReplayCostModelId(str, Enum):
    ZERO_COST = "zero_cost"
    CPM_FROZEN_COST_MODEL = "cpm_frozen_cost_model"
    STRESS_40BPS_ROUND_TRIP = "stress_40bps_round_trip"


class CPMReplayCostModel(BaseModel):
    """Return-space cost adjustment for research-only CPM replay."""

    model_config = ConfigDict(extra="forbid")

    model_id: CPMReplayCostModelId
    fee_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    entry_slippage_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    exit_slippage_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    fixed_round_trip_drag_pct: Decimal | None = Field(default=None, ge=Decimal("0"))
    notes: str = Field(default="", max_length=1024)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMReplayCostModel":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_replay_cost_model")
        return self

    @property
    def round_trip_drag_pct(self) -> Decimal:
        if self.fixed_round_trip_drag_pct is not None:
            return self.fixed_round_trip_drag_pct
        return Decimal("100") * (
            self.entry_slippage_rate + self.exit_slippage_rate + Decimal("2") * self.fee_rate
        )

    def adjust_return_pct(self, gross_return_pct: Decimal) -> Decimal:
        return gross_return_pct - self.round_trip_drag_pct


class CPMReplayMetrics(BaseModel):
    """Compact replay metrics for a list of net return percentages."""

    model_config = ConfigDict(extra="forbid")

    trades: int = Field(ge=0)
    mean_return_pct: Decimal | None = None
    median_return_pct: Decimal | None = None
    win_rate: Decimal | None = None
    average_gain_pct: Decimal | None = None
    average_loss_pct: Decimal | None = None
    payoff_ratio: Decimal | None = None
    expectancy_pct: Decimal | None = None
    cumulative_return_proxy_pct: Decimal = Decimal("0")
    max_drawdown_proxy_pct: Decimal = Decimal("0")
    max_winning_streak: int = Field(default=0, ge=0)
    max_losing_streak: int = Field(default=0, ge=0)
    advisory_label: str = "not_supported"

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMReplayMetrics":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_replay_metrics")
        return self


def zero_cost_model() -> CPMReplayCostModel:
    return CPMReplayCostModel(
        model_id=CPMReplayCostModelId.ZERO_COST,
        notes="No fee or slippage drag; gross historical observation.",
    )


def cpm_frozen_cost_model() -> CPMReplayCostModel:
    return CPMReplayCostModel(
        model_id=CPMReplayCostModelId.CPM_FROZEN_COST_MODEL,
        fee_rate=Decimal("0.0004"),
        entry_slippage_rate=Decimal("0.001"),
        exit_slippage_rate=Decimal("0.001"),
        notes="CPM frozen research model: fee per side 0.04%, entry/exit slippage 0.1% each.",
    )


def stress_40bps_round_trip_model() -> CPMReplayCostModel:
    return CPMReplayCostModel(
        model_id=CPMReplayCostModelId.STRESS_40BPS_ROUND_TRIP,
        fixed_round_trip_drag_pct=Decimal("0.40"),
        notes="Fixed 40 bps round-trip drag stress model.",
    )


def default_cpm_replay_cost_models() -> list[CPMReplayCostModel]:
    return [zero_cost_model(), cpm_frozen_cost_model(), stress_40bps_round_trip_model()]


def adjust_returns_pct(
    gross_returns_pct: list[Decimal],
    cost_model: CPMReplayCostModel,
) -> list[Decimal]:
    return [cost_model.adjust_return_pct(value) for value in gross_returns_pct]


def summarize_replay_returns(net_returns_pct: list[Decimal]) -> CPMReplayMetrics:
    returns = list(net_returns_pct)
    if not returns:
        return CPMReplayMetrics(trades=0)

    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    average_gain = _mean(wins)
    average_loss = _mean(losses)
    payoff_ratio = (
        average_gain / abs(average_loss)
        if average_gain is not None and average_loss not in (None, Decimal("0"))
        else None
    )
    cumulative, max_drawdown = _cumulative_and_drawdown(returns)
    max_winning_streak, max_losing_streak = _streaks(returns)
    mean_return = _mean(returns)
    win_rate = Decimal(len(wins)) / Decimal(len(returns))
    return CPMReplayMetrics(
        trades=len(returns),
        mean_return_pct=mean_return,
        median_return_pct=Decimal(str(median(returns))),
        win_rate=win_rate,
        average_gain_pct=average_gain,
        average_loss_pct=average_loss,
        payoff_ratio=payoff_ratio,
        expectancy_pct=mean_return,
        cumulative_return_proxy_pct=cumulative,
        max_drawdown_proxy_pct=max_drawdown,
        max_winning_streak=max_winning_streak,
        max_losing_streak=max_losing_streak,
        advisory_label=_advisory_label(
            mean_return=mean_return,
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
        ),
    )


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _cumulative_and_drawdown(returns: list[Decimal]) -> tuple[Decimal, Decimal]:
    total = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for value in returns:
        total += value
        if total > peak:
            peak = total
        drawdown = peak - total
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return total, max_drawdown


def _streaks(returns: list[Decimal]) -> tuple[int, int]:
    max_win = 0
    max_loss = 0
    current_win = 0
    current_loss = 0
    for value in returns:
        if value > 0:
            current_win += 1
            current_loss = 0
        elif value < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = 0
            current_loss = 0
        max_win = max(max_win, current_win)
        max_loss = max(max_loss, current_loss)
    return max_win, max_loss


def _advisory_label(
    *,
    mean_return: Decimal | None,
    win_rate: Decimal | None,
    payoff_ratio: Decimal | None,
) -> str:
    mean_return = mean_return or Decimal("0")
    win_rate = win_rate or Decimal("0")
    payoff_ratio = payoff_ratio or Decimal("0")
    if mean_return > Decimal("0.45") and win_rate >= Decimal("0.58") and payoff_ratio >= Decimal("1.5"):
        return "promising"
    if mean_return > Decimal("0") and win_rate >= Decimal("0.50"):
        return "needs_refinement"
    return "not_supported"
