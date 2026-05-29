"""Pure risk-capital leverage replay metrics for CPM fixed-4h research.

This module scales already-computed fixed-window historical observations. It
does not model liquidation, margin, orders, position sizing, execution, or
portfolio accounting.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.cpm_replay_cost_model import CPMReplayCostModel
from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class CPMRiskCapitalDecisionLabel(str, Enum):
    RIGHT_TAIL_CANDIDATE = "right_tail_candidate"
    BOUNDED_RISK_CANDIDATE = "bounded_risk_candidate"
    TOO_THIN_AFTER_COST = "too_thin_after_cost"
    TAIL_LOSS_EXCEEDS_CAMPAIGN = "tail_loss_exceeds_campaign"
    CONTROL_ONLY = "control_only"


class CPMRiskCapitalAssumptions(BaseModel):
    """Owner risk-capital assumptions for research-only replay."""

    model_config = ConfigDict(extra="forbid")

    soft_stop_loss_pct: Decimal = Field(default=Decimal("30"), gt=Decimal("0"))
    hard_stop_loss_pct: Decimal = Field(default=Decimal("50"), gt=Decimal("0"))
    ruin_boundary_pct: Decimal = Field(default=Decimal("100"), gt=Decimal("0"))
    profit_review_thresholds_pct: list[Decimal] = Field(
        default_factory=lambda: [Decimal("30"), Decimal("50"), Decimal("100")]
    )

    @model_validator(mode="after")
    def _validate_stops_and_reject_execution_fields(self) -> "CPMRiskCapitalAssumptions":
        if self.hard_stop_loss_pct < self.soft_stop_loss_pct:
            raise ValueError("hard_stop_loss_pct must be >= soft_stop_loss_pct")
        if self.ruin_boundary_pct < self.hard_stop_loss_pct:
            raise ValueError("ruin_boundary_pct must be >= hard_stop_loss_pct")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_risk_capital_assumptions")
        return self


class CPMRiskCapitalReplayMetrics(BaseModel):
    """Risk-capital replay metrics for a single leverage multiple."""

    model_config = ConfigDict(extra="forbid")

    trades: int = Field(ge=0)
    leverage_multiple: Decimal = Field(gt=Decimal("0"))
    mean_equity_return_pct: Decimal | None = None
    median_equity_return_pct: Decimal | None = None
    win_rate: Decimal | None = None
    average_gain_pct: Decimal | None = None
    average_loss_pct: Decimal | None = None
    payoff_ratio: Decimal | None = None
    expectancy_pct: Decimal | None = None
    p50_equity_adverse_proxy_pct: Decimal | None = None
    p75_equity_adverse_proxy_pct: Decimal | None = None
    p90_equity_adverse_proxy_pct: Decimal | None = None
    p95_equity_adverse_proxy_pct: Decimal | None = None
    p99_equity_adverse_proxy_pct: Decimal | None = None
    max_equity_adverse_proxy_pct: Decimal | None = None
    max_losing_streak: int = Field(default=0, ge=0)
    max_winning_streak: int = Field(default=0, ge=0)
    equity_loss_under_max_losing_streak_pct: Decimal = Decimal("0")
    estimated_trades_to_soft_stop: Decimal | None = None
    estimated_trades_to_hard_stop: Decimal | None = None
    estimated_trades_to_ruin: Decimal | None = None
    p75_gain_pct: Decimal | None = None
    p90_gain_pct: Decimal | None = None
    p95_gain_pct: Decimal | None = None
    right_tail_contribution_pct: Decimal = Decimal("0")
    gain_threshold_counts: dict[str, int] = Field(default_factory=dict)
    gain_threshold_ratios: dict[str, Decimal] = Field(default_factory=dict)
    loss_threshold_counts: dict[str, int] = Field(default_factory=dict)
    loss_threshold_ratios: dict[str, Decimal] = Field(default_factory=dict)
    max_drawdown_proxy_pct: Decimal = Decimal("0")
    decision_label: CPMRiskCapitalDecisionLabel = CPMRiskCapitalDecisionLabel.CONTROL_ONLY

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMRiskCapitalReplayMetrics":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_risk_capital_metrics")
        return self


def equity_return_pct(
    *,
    gross_underlying_return_pct: Decimal,
    cost_model: CPMReplayCostModel,
    leverage_multiple: Decimal,
) -> Decimal:
    """Apply cost drag before leverage and return equity-space percentage."""

    if leverage_multiple <= 0:
        raise ValueError("leverage_multiple must be positive")
    net_underlying_return_pct = cost_model.adjust_return_pct(gross_underlying_return_pct)
    return leverage_multiple * net_underlying_return_pct


def equity_adverse_proxy_pct(
    *,
    underlying_adverse_proxy_pct: Decimal,
    leverage_multiple: Decimal,
) -> Decimal:
    """Scale an underlying adverse proxy into equity-space loss magnitude."""

    if leverage_multiple <= 0:
        raise ValueError("leverage_multiple must be positive")
    return abs(underlying_adverse_proxy_pct) * leverage_multiple


def summarize_risk_capital_replay(
    *,
    gross_underlying_returns_pct: list[Decimal],
    underlying_adverse_proxies_pct: list[Decimal],
    cost_model: CPMReplayCostModel,
    leverage_multiple: Decimal,
    assumptions: CPMRiskCapitalAssumptions | None = None,
) -> CPMRiskCapitalReplayMetrics:
    if len(gross_underlying_returns_pct) != len(underlying_adverse_proxies_pct):
        raise ValueError("gross returns and adverse proxies must have the same length")
    if leverage_multiple <= 0:
        raise ValueError("leverage_multiple must be positive")

    configured_assumptions = assumptions or CPMRiskCapitalAssumptions()
    equity_returns = [
        equity_return_pct(
            gross_underlying_return_pct=value,
            cost_model=cost_model,
            leverage_multiple=leverage_multiple,
        )
        for value in gross_underlying_returns_pct
    ]
    equity_adverse = [
        equity_adverse_proxy_pct(
            underlying_adverse_proxy_pct=value,
            leverage_multiple=leverage_multiple,
        )
        for value in underlying_adverse_proxies_pct
    ]
    return summarize_equity_replay(
        equity_returns_pct=equity_returns,
        equity_adverse_proxies_pct=equity_adverse,
        leverage_multiple=leverage_multiple,
        assumptions=configured_assumptions,
    )


def summarize_equity_replay(
    *,
    equity_returns_pct: list[Decimal],
    equity_adverse_proxies_pct: list[Decimal],
    leverage_multiple: Decimal,
    assumptions: CPMRiskCapitalAssumptions | None = None,
) -> CPMRiskCapitalReplayMetrics:
    if len(equity_returns_pct) != len(equity_adverse_proxies_pct):
        raise ValueError("equity returns and adverse proxies must have the same length")
    configured_assumptions = assumptions or CPMRiskCapitalAssumptions()
    returns = list(equity_returns_pct)
    adverse = list(equity_adverse_proxies_pct)
    if not returns:
        return CPMRiskCapitalReplayMetrics(trades=0, leverage_multiple=leverage_multiple)

    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    average_gain = _mean(wins)
    average_loss = _mean(losses)
    payoff_ratio = (
        average_gain / abs(average_loss)
        if average_gain is not None and average_loss not in (None, Decimal("0"))
        else None
    )
    max_win, max_loss = _streaks(returns)
    _, max_drawdown = _cumulative_and_drawdown(returns)
    worst_streak_loss = _worst_losing_streak_loss(returns)
    threshold_counts, threshold_ratios = _threshold_counts(
        values=returns,
        thresholds=[Decimal("5"), Decimal("10"), Decimal("20")],
        direction="gain",
    )
    loss_counts, loss_ratios = _threshold_counts(
        values=returns,
        thresholds=[Decimal("5"), Decimal("10"), Decimal("20")],
        direction="loss",
    )
    mean_return = _mean(returns)
    win_rate = Decimal(len(wins)) / Decimal(len(returns))
    metrics = CPMRiskCapitalReplayMetrics(
        trades=len(returns),
        leverage_multiple=leverage_multiple,
        mean_equity_return_pct=mean_return,
        median_equity_return_pct=Decimal(str(median(returns))),
        win_rate=win_rate,
        average_gain_pct=average_gain,
        average_loss_pct=average_loss,
        payoff_ratio=payoff_ratio,
        expectancy_pct=mean_return,
        p50_equity_adverse_proxy_pct=_percentile(adverse, Decimal("0.50")),
        p75_equity_adverse_proxy_pct=_percentile(adverse, Decimal("0.75")),
        p90_equity_adverse_proxy_pct=_percentile(adverse, Decimal("0.90")),
        p95_equity_adverse_proxy_pct=_percentile(adverse, Decimal("0.95")),
        p99_equity_adverse_proxy_pct=_percentile(adverse, Decimal("0.99")),
        max_equity_adverse_proxy_pct=max(adverse) if adverse else None,
        max_losing_streak=max_loss,
        max_winning_streak=max_win,
        equity_loss_under_max_losing_streak_pct=worst_streak_loss,
        estimated_trades_to_soft_stop=_trades_to_stop(configured_assumptions.soft_stop_loss_pct, average_loss),
        estimated_trades_to_hard_stop=_trades_to_stop(configured_assumptions.hard_stop_loss_pct, average_loss),
        estimated_trades_to_ruin=_trades_to_stop(configured_assumptions.ruin_boundary_pct, average_loss),
        p75_gain_pct=_percentile(wins, Decimal("0.75")),
        p90_gain_pct=_percentile(wins, Decimal("0.90")),
        p95_gain_pct=_percentile(wins, Decimal("0.95")),
        right_tail_contribution_pct=_right_tail_contribution(wins),
        gain_threshold_counts=threshold_counts,
        gain_threshold_ratios=threshold_ratios,
        loss_threshold_counts=loss_counts,
        loss_threshold_ratios=loss_ratios,
        max_drawdown_proxy_pct=max_drawdown,
        decision_label=CPMRiskCapitalDecisionLabel.CONTROL_ONLY,
    )
    metrics.decision_label = _decision_label(metrics, configured_assumptions)
    return metrics


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    raw_index = (Decimal(len(sorted_values) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP")
    return sorted_values[int(raw_index)]


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


def _worst_losing_streak_loss(returns: list[Decimal]) -> Decimal:
    current_loss = Decimal("0")
    worst_loss = Decimal("0")
    for value in returns:
        if value < 0:
            current_loss += abs(value)
        else:
            current_loss = Decimal("0")
        if current_loss > worst_loss:
            worst_loss = current_loss
    return worst_loss


def _trades_to_stop(stop_loss_pct: Decimal, average_loss_pct: Decimal | None) -> Decimal | None:
    if average_loss_pct is None or average_loss_pct >= 0:
        return None
    return stop_loss_pct / abs(average_loss_pct)


def _threshold_counts(
    *,
    values: list[Decimal],
    thresholds: list[Decimal],
    direction: str,
) -> tuple[dict[str, int], dict[str, Decimal]]:
    counts: dict[str, int] = {}
    ratios: dict[str, Decimal] = {}
    total = Decimal(len(values)) if values else Decimal("1")
    for threshold in thresholds:
        key = f"{_decimal_key(threshold)}pct"
        if direction == "gain":
            count = sum(1 for value in values if value >= threshold)
        else:
            count = sum(1 for value in values if value <= -threshold)
        counts[key] = count
        ratios[key] = Decimal(count) / total
    return counts, ratios


def _decimal_key(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _right_tail_contribution(wins: list[Decimal]) -> Decimal:
    if not wins:
        return Decimal("0")
    threshold = _percentile(wins, Decimal("0.90"))
    if threshold is None:
        return Decimal("0")
    right_tail = [value for value in wins if value >= threshold]
    total_gain = sum(wins, Decimal("0"))
    if total_gain == 0:
        return Decimal("0")
    return sum(right_tail, Decimal("0")) / total_gain * Decimal("100")


def _decision_label(
    metrics: CPMRiskCapitalReplayMetrics,
    assumptions: CPMRiskCapitalAssumptions,
) -> CPMRiskCapitalDecisionLabel:
    if metrics.trades == 0:
        return CPMRiskCapitalDecisionLabel.CONTROL_ONLY
    if (
        metrics.p95_equity_adverse_proxy_pct is not None
        and metrics.p95_equity_adverse_proxy_pct >= assumptions.hard_stop_loss_pct
    ):
        return CPMRiskCapitalDecisionLabel.TAIL_LOSS_EXCEEDS_CAMPAIGN
    if (metrics.expectancy_pct or Decimal("0")) <= 0 or (metrics.win_rate or Decimal("0")) < Decimal("0.45"):
        return CPMRiskCapitalDecisionLabel.TOO_THIN_AFTER_COST
    if (
        metrics.p95_gain_pct is not None
        and metrics.p95_gain_pct >= Decimal("20")
        and metrics.estimated_trades_to_soft_stop is not None
        and metrics.estimated_trades_to_soft_stop >= Decimal("5")
    ):
        return CPMRiskCapitalDecisionLabel.RIGHT_TAIL_CANDIDATE
    return CPMRiskCapitalDecisionLabel.BOUNDED_RISK_CANDIDATE
