"""Pure CPM fixed-4h campaign feasibility replay.

This module consumes already-computed cost-adjusted historical return
observations. It does not model orders, fills, margin, liquidation, funding,
portfolio accounting, live routing, or execution.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class CPMCampaignRiskModel(str, Enum):
    FIXED_FRACTIONAL = "fixed_fractional"
    FIXED_UNIT = "fixed_unit"


class CPMCampaignStatus(str, Enum):
    ACTIVE = "active"
    RUINED = "ruined"
    TARGET_HIT = "target_hit"
    COMPLETED = "completed"


class CPMCampaignDecisionLabel(str, Enum):
    CAMPAIGN_PROMISING = "campaign_promising"
    NEEDS_REFINEMENT = "needs_refinement"
    NOT_SUPPORTED = "not_supported"
    INSUFFICIENT_DATA = "insufficient_data"


class CPMCampaignOutcomeBucket(str, Enum):
    RUINED = "ruined"
    BELOW_1X = "below_1x"
    ONE_TO_2X = "1x_to_2x"
    TWO_TO_3X = "2x_to_3x"
    THREE_TO_5X = "3x_to_5x"
    ABOVE_5X = "above_5x"


class CPMCampaignReplayConfig(BaseModel):
    """Research-only campaign configuration."""

    model_config = ConfigDict(extra="forbid")

    config_id: str = Field(min_length=1, max_length=128)
    initial_capital: Decimal = Field(default=Decimal("100"), gt=Decimal("0"))
    risk_model: CPMCampaignRiskModel
    risk_per_trade_pct: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("100"))
    fixed_risk_unit: Decimal | None = Field(default=None, gt=Decimal("0"))
    target_multiple: Decimal = Field(default=Decimal("2"), gt=Decimal("1"))
    withdraw_initial_at_2x: bool = False
    withdraw_pct_at_3x: Decimal | None = Field(default=None, gt=Decimal("0"), lt=Decimal("100"))
    complete_at_5x: bool = False

    @model_validator(mode="after")
    def _validate_model_and_reject_execution_fields(self) -> "CPMCampaignReplayConfig":
        if self.risk_model == CPMCampaignRiskModel.FIXED_FRACTIONAL and self.risk_per_trade_pct is None:
            raise ValueError("risk_per_trade_pct is required for fixed_fractional")
        if self.risk_model == CPMCampaignRiskModel.FIXED_UNIT and self.fixed_risk_unit is None:
            raise ValueError("fixed_risk_unit is required for fixed_unit")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_config")
        return self


class CPMCampaignRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str = Field(min_length=1, max_length=128)
    config_id: str = Field(min_length=1, max_length=128)
    status: CPMCampaignStatus
    initial_capital: Decimal
    final_equity: Decimal
    retained_capital: Decimal = Decimal("0")
    trades_consumed: int = Field(ge=0)
    final_multiple: Decimal
    peak_multiple: Decimal
    target_multiple: Decimal
    target_hit_2x: bool = False
    target_hit_3x: bool = False
    target_hit_5x: bool = False
    max_drawdown_pct: Decimal = Decimal("0")
    largest_trade_gain: Decimal = Decimal("0")
    largest_trade_loss: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMCampaignRun":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_run")
        return self


class CPMCampaignReplaySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_id: str = Field(min_length=1, max_length=128)
    exposure_multiplier: Decimal = Field(gt=Decimal("0"))
    campaigns_simulated: int = Field(ge=0)
    total_trades_consumed: int = Field(ge=0)
    average_trades_per_campaign: Decimal | None = None
    median_trades_per_campaign: Decimal | None = None
    ruin_rate: Decimal = Decimal("0")
    hit_rate_2x: Decimal = Decimal("0")
    hit_rate_3x: Decimal = Decimal("0")
    hit_rate_5x: Decimal = Decimal("0")
    median_final_multiple: Decimal | None = None
    mean_final_multiple: Decimal | None = None
    max_final_multiple: Decimal | None = None
    median_campaign_duration_trades: Decimal | None = None
    max_consecutive_ruined_campaigns: int = Field(default=0, ge=0)
    max_drawdown_within_campaign_pct: Decimal = Decimal("0")
    withdrawal_adjusted_total_retained_capital: Decimal = Decimal("0")
    largest_winner_contribution: Decimal = Decimal("0")
    outcome_distribution: dict[str, int] = Field(default_factory=dict)
    decision_label: CPMCampaignDecisionLabel = CPMCampaignDecisionLabel.INSUFFICIENT_DATA

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMCampaignReplaySummary":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_summary")
        return self


def replay_campaigns(
    *,
    net_returns_pct: list[Decimal],
    config: CPMCampaignReplayConfig,
    exposure_multiplier: Decimal,
) -> list[CPMCampaignRun]:
    if exposure_multiplier <= 0:
        raise ValueError("exposure_multiplier must be positive")
    runs: list[CPMCampaignRun] = []
    index = 0
    campaign_index = 0
    while index < len(net_returns_pct):
        run, consumed = _run_one_campaign(
            returns=net_returns_pct[index:],
            config=config,
            exposure_multiplier=exposure_multiplier,
            campaign_index=campaign_index,
        )
        runs.append(run)
        index += max(1, consumed)
        campaign_index += 1
    return runs


def summarize_campaign_runs(
    *,
    runs: list[CPMCampaignRun],
    config_id: str,
    exposure_multiplier: Decimal,
) -> CPMCampaignReplaySummary:
    if not runs:
        return CPMCampaignReplaySummary(
            config_id=config_id,
            exposure_multiplier=exposure_multiplier,
            campaigns_simulated=0,
            total_trades_consumed=0,
        )
    campaign_count = Decimal(len(runs))
    trades = [run.trades_consumed for run in runs]
    final_multiples = [run.final_multiple for run in runs]
    distribution = {bucket.value: 0 for bucket in CPMCampaignOutcomeBucket}
    for run in runs:
        distribution[_outcome_bucket(run).value] += 1
    summary = CPMCampaignReplaySummary(
        config_id=config_id,
        exposure_multiplier=exposure_multiplier,
        campaigns_simulated=len(runs),
        total_trades_consumed=sum(trades),
        average_trades_per_campaign=Decimal(sum(trades)) / campaign_count,
        median_trades_per_campaign=Decimal(str(median(trades))),
        ruin_rate=Decimal(sum(1 for run in runs if run.status == CPMCampaignStatus.RUINED)) / campaign_count,
        hit_rate_2x=Decimal(sum(1 for run in runs if run.target_hit_2x)) / campaign_count,
        hit_rate_3x=Decimal(sum(1 for run in runs if run.target_hit_3x)) / campaign_count,
        hit_rate_5x=Decimal(sum(1 for run in runs if run.target_hit_5x)) / campaign_count,
        median_final_multiple=Decimal(str(median(final_multiples))),
        mean_final_multiple=sum(final_multiples, Decimal("0")) / campaign_count,
        max_final_multiple=max(final_multiples),
        median_campaign_duration_trades=Decimal(str(median(trades))),
        max_consecutive_ruined_campaigns=_max_consecutive_ruined(runs),
        max_drawdown_within_campaign_pct=max((run.max_drawdown_pct for run in runs), default=Decimal("0")),
        withdrawal_adjusted_total_retained_capital=sum((run.retained_capital for run in runs), Decimal("0")),
        largest_winner_contribution=max((run.largest_trade_gain for run in runs), default=Decimal("0")),
        outcome_distribution=distribution,
        decision_label=CPMCampaignDecisionLabel.INSUFFICIENT_DATA,
    )
    summary.decision_label = _decision_label(summary)
    return summary


def replay_and_summarize_campaigns(
    *,
    net_returns_pct: list[Decimal],
    config: CPMCampaignReplayConfig,
    exposure_multiplier: Decimal,
) -> CPMCampaignReplaySummary:
    return summarize_campaign_runs(
        runs=replay_campaigns(
            net_returns_pct=net_returns_pct,
            config=config,
            exposure_multiplier=exposure_multiplier,
        ),
        config_id=config.config_id,
        exposure_multiplier=exposure_multiplier,
    )


def default_campaign_configs() -> list[CPMCampaignReplayConfig]:
    configs: list[CPMCampaignReplayConfig] = []
    for target in [Decimal("2"), Decimal("3"), Decimal("5")]:
        configs.append(
            CPMCampaignReplayConfig(
                config_id=f"conservative_fixed_fraction_{target}x",
                risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
                risk_per_trade_pct=Decimal("10"),
                target_multiple=target,
            )
        )
        configs.append(
            CPMCampaignReplayConfig(
                config_id=f"aggressive_fixed_fraction_{target}x",
                risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
                risk_per_trade_pct=Decimal("20"),
                target_multiple=target,
            )
        )
    configs.append(
        CPMCampaignReplayConfig(
            config_id="fixed_fraction_with_withdrawal_5x",
            risk_model=CPMCampaignRiskModel.FIXED_FRACTIONAL,
            risk_per_trade_pct=Decimal("20"),
            target_multiple=Decimal("5"),
            withdraw_initial_at_2x=True,
            withdraw_pct_at_3x=Decimal("30"),
            complete_at_5x=True,
        )
    )
    for target in [Decimal("2"), Decimal("3"), Decimal("5")]:
        configs.append(
            CPMCampaignReplayConfig(
                config_id=f"fixed_unit_risk_{target}x",
                risk_model=CPMCampaignRiskModel.FIXED_UNIT,
                fixed_risk_unit=Decimal("10"),
                target_multiple=target,
            )
        )
    return configs


def _run_one_campaign(
    *,
    returns: list[Decimal],
    config: CPMCampaignReplayConfig,
    exposure_multiplier: Decimal,
    campaign_index: int,
) -> tuple[CPMCampaignRun, int]:
    equity = config.initial_capital
    peak = equity
    retained = Decimal("0")
    target = config.initial_capital * config.target_multiple
    hit_2x = False
    hit_3x = False
    hit_5x = False
    withdrew_initial = False
    withdrew_3x = False
    max_drawdown = Decimal("0")
    largest_gain = Decimal("0")
    largest_loss = Decimal("0")
    status = CPMCampaignStatus.COMPLETED
    consumed = 0
    for value in returns:
        consumed += 1
        risk_unit = _risk_unit(config, equity)
        equity_delta = risk_unit * exposure_multiplier * value / Decimal("100")
        equity += equity_delta
        largest_gain = max(largest_gain, equity_delta)
        largest_loss = min(largest_loss, equity_delta)
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * Decimal("100"))
        if equity >= config.initial_capital * Decimal("2"):
            hit_2x = True
            if config.withdraw_initial_at_2x and not withdrew_initial:
                withdraw = min(config.initial_capital, equity)
                equity -= withdraw
                retained += withdraw
                withdrew_initial = True
                peak = max(peak, equity)
        if equity + retained >= config.initial_capital * Decimal("3"):
            hit_3x = True
            if config.withdraw_pct_at_3x is not None and not withdrew_3x:
                withdraw = equity * config.withdraw_pct_at_3x / Decimal("100")
                equity -= withdraw
                retained += withdraw
                withdrew_3x = True
        if equity + retained >= config.initial_capital * Decimal("5"):
            hit_5x = True
        if equity <= 0:
            equity = Decimal("0")
            status = CPMCampaignStatus.RUINED
            break
        if equity + retained >= target or (config.complete_at_5x and hit_5x):
            status = CPMCampaignStatus.TARGET_HIT
            break
    final_total = equity + retained
    return (
        CPMCampaignRun(
            campaign_id=f"{config.config_id}:{campaign_index}",
            config_id=config.config_id,
            status=status,
            initial_capital=config.initial_capital,
            final_equity=equity,
            retained_capital=retained,
            trades_consumed=consumed,
            final_multiple=final_total / config.initial_capital,
            peak_multiple=max(peak + retained, final_total) / config.initial_capital,
            target_multiple=config.target_multiple,
            target_hit_2x=hit_2x,
            target_hit_3x=hit_3x,
            target_hit_5x=hit_5x,
            max_drawdown_pct=max_drawdown,
            largest_trade_gain=largest_gain,
            largest_trade_loss=largest_loss,
        ),
        consumed,
    )


def _risk_unit(config: CPMCampaignReplayConfig, equity: Decimal) -> Decimal:
    if config.risk_model == CPMCampaignRiskModel.FIXED_FRACTIONAL:
        assert config.risk_per_trade_pct is not None
        return max(Decimal("0"), equity * config.risk_per_trade_pct / Decimal("100"))
    assert config.fixed_risk_unit is not None
    return min(config.fixed_risk_unit, max(Decimal("0"), equity))


def _outcome_bucket(run: CPMCampaignRun) -> CPMCampaignOutcomeBucket:
    if run.status == CPMCampaignStatus.RUINED:
        return CPMCampaignOutcomeBucket.RUINED
    if run.final_multiple < Decimal("1"):
        return CPMCampaignOutcomeBucket.BELOW_1X
    if run.final_multiple < Decimal("2"):
        return CPMCampaignOutcomeBucket.ONE_TO_2X
    if run.final_multiple < Decimal("3"):
        return CPMCampaignOutcomeBucket.TWO_TO_3X
    if run.final_multiple < Decimal("5"):
        return CPMCampaignOutcomeBucket.THREE_TO_5X
    return CPMCampaignOutcomeBucket.ABOVE_5X


def _max_consecutive_ruined(runs: list[CPMCampaignRun]) -> int:
    max_count = 0
    current = 0
    for run in runs:
        if run.status == CPMCampaignStatus.RUINED:
            current += 1
        else:
            current = 0
        max_count = max(max_count, current)
    return max_count


def _decision_label(summary: CPMCampaignReplaySummary) -> CPMCampaignDecisionLabel:
    if summary.total_trades_consumed < 30 or summary.campaigns_simulated == 0:
        return CPMCampaignDecisionLabel.INSUFFICIENT_DATA
    if summary.ruin_rate >= Decimal("0.5") and summary.hit_rate_2x < Decimal("0.1"):
        return CPMCampaignDecisionLabel.NOT_SUPPORTED
    if (
        summary.hit_rate_2x >= Decimal("0.2")
        and summary.hit_rate_3x >= Decimal("0.05")
        and summary.max_consecutive_ruined_campaigns <= 3
    ):
        return CPMCampaignDecisionLabel.CAMPAIGN_PROMISING
    if summary.hit_rate_2x > 0 or (summary.mean_final_multiple or Decimal("0")) > Decimal("1"):
        return CPMCampaignDecisionLabel.NEEDS_REFINEMENT
    return CPMCampaignDecisionLabel.NOT_SUPPORTED
