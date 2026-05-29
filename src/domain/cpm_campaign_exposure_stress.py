"""Pure CPM-SOL campaign exposure stress review.

This module consumes already-persisted fixed-4h historical outcome
observations. It does not model orders, fills, margin, liquidation, routing,
portfolio accounting, live execution, or strategy evaluation.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from statistics import median

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.cpm_campaign_replay import CPMCampaignReplayConfig, CPMCampaignRiskModel
from src.domain.strategy_family_signal import reject_forbidden_execution_fields


DAY_MS = 86_400_000


class CPMCampaignStressMode(str, Enum):
    SINGLE_CHRONOLOGICAL_CAMPAIGN = "single_chronological_campaign"
    NON_OVERLAPPING_WINDOW_CAMPAIGN = "non_overlapping_window_campaign"


class CPMCampaignStressDecisionLabel(str, Enum):
    RIGHT_TAIL_AMPLIFIES_WITH_CONTROLLED_LEFT_TAIL = "right_tail_amplifies_with_controlled_left_tail"
    RIGHT_TAIL_EXISTS_BUT_LEFT_TAIL_EXPANDS_TOO_FAST = "right_tail_exists_but_left_tail_expands_too_fast"
    NOT_SUPPORTED_UNDER_EXPOSURE = "not_supported_under_exposure"
    INSUFFICIENT_PATH_DATA = "insufficient_path_data"


class CPMCampaignStressObservation(BaseModel):
    """One fixed-4h CPM would-enter observation."""

    model_config = ConfigDict(extra="forbid")

    timestamp_ms: int = Field(ge=0)
    gross_return_pct: Decimal
    adverse_proxy_pct: Decimal | None = None

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMCampaignStressObservation":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_stress_observation")
        return self


class CPMCampaignStressRun(BaseModel):
    """One campaign path over a selected observation window."""

    model_config = ConfigDict(extra="forbid")

    mode: CPMCampaignStressMode
    window_days: int | None = Field(default=None, ge=1)
    exposure_multiplier: Decimal = Field(gt=Decimal("0"))
    cost_drag_pct: Decimal = Field(ge=Decimal("0"))
    start_time_ms: int | None = Field(default=None, ge=0)
    end_time_ms: int | None = Field(default=None, ge=0)
    trades: int = Field(ge=0)
    final_multiple: Decimal
    max_drawdown_pct: Decimal = Decimal("0")
    intrabar_stressed_max_drawdown_pct: Decimal | None = None
    largest_single_trade_loss_pct: Decimal = Decimal("0")
    max_losing_streak: int = Field(default=0, ge=0)
    ruined: bool = False
    below_1x: bool = False

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMCampaignStressRun":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_stress_run")
        return self


class CPMCampaignExposureStressSummary(BaseModel):
    """Distribution and path-risk summary for one exposure/campaign mode."""

    model_config = ConfigDict(extra="forbid")

    mode: CPMCampaignStressMode
    window_days: int | None = Field(default=None, ge=1)
    exposure_multiplier: Decimal = Field(gt=Decimal("0"))
    cost_drag_pct: Decimal = Field(ge=Decimal("0"))
    campaigns: int = Field(ge=0)
    trades: int = Field(ge=0)
    final_multiple: Decimal | None = None
    mean_campaign_multiple: Decimal | None = None
    median_campaign_multiple: Decimal | None = None
    top_10pct_campaign_multiple: Decimal | None = None
    top_5pct_campaign_multiple: Decimal | None = None
    max_campaign_multiple: Decimal | None = None
    worst_10pct_campaign_multiple: Decimal | None = None
    worst_5pct_campaign_multiple: Decimal | None = None
    ruin_rate: Decimal = Decimal("0")
    below_1x_rate: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    intrabar_stressed_max_drawdown_pct: Decimal | None = None
    largest_single_trade_loss_pct: Decimal = Decimal("0")
    max_losing_streak: int = Field(default=0, ge=0)
    liquidation_proxy_breach_counts: dict[str, int] = Field(default_factory=dict)
    liquidation_proxy_breach_rates: dict[str, Decimal] = Field(default_factory=dict)
    outcome_distribution: dict[str, int] = Field(default_factory=dict)
    decision_label: CPMCampaignStressDecisionLabel = CPMCampaignStressDecisionLabel.INSUFFICIENT_PATH_DATA

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "CPMCampaignExposureStressSummary":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="cpm_campaign_exposure_stress_summary")
        return self


def build_non_overlapping_campaign_windows(
    observations: list[CPMCampaignStressObservation],
    *,
    window_days: int,
) -> list[list[CPMCampaignStressObservation]]:
    """Build deterministic non-overlapping observation windows."""

    if window_days <= 0:
        raise ValueError("window_days must be positive")
    ordered = sorted(observations, key=lambda item: item.timestamp_ms)
    if not ordered:
        return []

    windows: list[list[CPMCampaignStressObservation]] = []
    current: list[CPMCampaignStressObservation] = []
    window_start = ordered[0].timestamp_ms
    window_end = window_start + window_days * DAY_MS
    for observation in ordered:
        while observation.timestamp_ms >= window_end and current:
            windows.append(current)
            current = []
            window_start = window_end
            window_end = window_start + window_days * DAY_MS
        while observation.timestamp_ms >= window_end:
            window_start = window_end
            window_end = window_start + window_days * DAY_MS
        current.append(observation)
    if current:
        windows.append(current)
    return windows


def summarize_campaign_exposure_stress(
    *,
    observations: list[CPMCampaignStressObservation],
    config: CPMCampaignReplayConfig,
    exposure_multiplier: Decimal,
    cost_drag_pct: Decimal,
    mode: CPMCampaignStressMode,
    window_days: int | None = None,
    liquidation_proxy_thresholds_pct: list[Decimal] | None = None,
) -> CPMCampaignExposureStressSummary:
    if exposure_multiplier <= 0:
        raise ValueError("exposure_multiplier must be positive")
    if cost_drag_pct < 0:
        raise ValueError("cost_drag_pct must be non-negative")
    if mode == CPMCampaignStressMode.NON_OVERLAPPING_WINDOW_CAMPAIGN and window_days is None:
        raise ValueError("window_days is required for non-overlapping window campaign mode")

    ordered = sorted(observations, key=lambda item: item.timestamp_ms)
    if mode == CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN:
        windows = [ordered] if ordered else []
    else:
        assert window_days is not None
        windows = build_non_overlapping_campaign_windows(ordered, window_days=window_days)

    runs = [
        _run_stress_campaign(
            observations=window,
            config=config,
            exposure_multiplier=exposure_multiplier,
            cost_drag_pct=cost_drag_pct,
            mode=mode,
            window_days=window_days,
        )
        for window in windows
        if window
    ]
    return summarize_campaign_stress_runs(
        runs=runs,
        all_observations=ordered,
        exposure_multiplier=exposure_multiplier,
        cost_drag_pct=cost_drag_pct,
        mode=mode,
        window_days=window_days,
        liquidation_proxy_thresholds_pct=liquidation_proxy_thresholds_pct,
    )


def summarize_campaign_stress_runs(
    *,
    runs: list[CPMCampaignStressRun],
    all_observations: list[CPMCampaignStressObservation],
    exposure_multiplier: Decimal,
    cost_drag_pct: Decimal,
    mode: CPMCampaignStressMode,
    window_days: int | None = None,
    liquidation_proxy_thresholds_pct: list[Decimal] | None = None,
) -> CPMCampaignExposureStressSummary:
    thresholds = liquidation_proxy_thresholds_pct or [
        Decimal("3"),
        Decimal("5"),
        Decimal("10"),
        Decimal("15"),
        Decimal("20"),
    ]
    if not runs:
        return CPMCampaignExposureStressSummary(
            mode=mode,
            window_days=window_days,
            exposure_multiplier=exposure_multiplier,
            cost_drag_pct=cost_drag_pct,
            campaigns=0,
            trades=0,
        )

    multiples = [run.final_multiple for run in runs]
    campaign_count = Decimal(len(runs))
    breach_counts, breach_rates = _liquidation_proxy_breaches(
        observations=all_observations,
        exposure_multiplier=exposure_multiplier,
        thresholds=thresholds,
    )
    intrabar_values = [
        run.intrabar_stressed_max_drawdown_pct
        for run in runs
        if run.intrabar_stressed_max_drawdown_pct is not None
    ]
    outcome_distribution = _outcome_distribution(multiples, runs)
    summary = CPMCampaignExposureStressSummary(
        mode=mode,
        window_days=window_days,
        exposure_multiplier=exposure_multiplier,
        cost_drag_pct=cost_drag_pct,
        campaigns=len(runs),
        trades=sum(run.trades for run in runs),
        final_multiple=multiples[-1] if mode == CPMCampaignStressMode.SINGLE_CHRONOLOGICAL_CAMPAIGN else None,
        mean_campaign_multiple=sum(multiples, Decimal("0")) / campaign_count,
        median_campaign_multiple=Decimal(str(median(multiples))),
        top_10pct_campaign_multiple=_percentile(multiples, Decimal("0.90")),
        top_5pct_campaign_multiple=_percentile(multiples, Decimal("0.95")),
        max_campaign_multiple=max(multiples),
        worst_10pct_campaign_multiple=_percentile(multiples, Decimal("0.10")),
        worst_5pct_campaign_multiple=_percentile(multiples, Decimal("0.05")),
        ruin_rate=Decimal(sum(1 for run in runs if run.ruined)) / campaign_count,
        below_1x_rate=Decimal(sum(1 for run in runs if run.below_1x)) / campaign_count,
        max_drawdown_pct=max((run.max_drawdown_pct for run in runs), default=Decimal("0")),
        intrabar_stressed_max_drawdown_pct=max(intrabar_values) if intrabar_values else None,
        largest_single_trade_loss_pct=min((run.largest_single_trade_loss_pct for run in runs), default=Decimal("0")),
        max_losing_streak=max((run.max_losing_streak for run in runs), default=0),
        liquidation_proxy_breach_counts=breach_counts,
        liquidation_proxy_breach_rates=breach_rates,
        outcome_distribution=outcome_distribution,
        decision_label=CPMCampaignStressDecisionLabel.INSUFFICIENT_PATH_DATA,
    )
    summary.decision_label = _decision_label(summary)
    return summary


def _run_stress_campaign(
    *,
    observations: list[CPMCampaignStressObservation],
    config: CPMCampaignReplayConfig,
    exposure_multiplier: Decimal,
    cost_drag_pct: Decimal,
    mode: CPMCampaignStressMode,
    window_days: int | None,
) -> CPMCampaignStressRun:
    equity = config.initial_capital
    retained = Decimal("0")
    peak = equity
    max_drawdown = Decimal("0")
    intrabar_max_drawdown: Decimal | None = None
    largest_loss_pct = Decimal("0")
    max_losing_streak = 0
    current_losing_streak = 0
    target = config.initial_capital * config.target_multiple
    start_time_ms = observations[0].timestamp_ms if observations else None
    end_time_ms = observations[-1].timestamp_ms if observations else None

    for observation in observations:
        risk_unit = _risk_unit(config, equity)
        if observation.adverse_proxy_pct is not None:
            adverse_delta = -risk_unit * exposure_multiplier * abs(observation.adverse_proxy_pct) / Decimal("100")
            intrabar_equity = equity + adverse_delta
            if peak > 0:
                drawdown = (peak - intrabar_equity) / peak * Decimal("100")
                intrabar_max_drawdown = max(intrabar_max_drawdown or Decimal("0"), drawdown)

        net_return_pct = observation.gross_return_pct - cost_drag_pct
        close_delta = risk_unit * exposure_multiplier * net_return_pct / Decimal("100")
        equity += close_delta
        largest_loss_pct = min(largest_loss_pct, close_delta / config.initial_capital * Decimal("100"))
        if close_delta < 0:
            current_losing_streak += 1
        else:
            current_losing_streak = 0
        max_losing_streak = max(max_losing_streak, current_losing_streak)

        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * Decimal("100"))

        if equity >= config.initial_capital * Decimal("2") and config.withdraw_initial_at_2x:
            withdraw = min(config.initial_capital, equity)
            equity -= withdraw
            retained += withdraw
        if equity + retained >= target or equity <= 0:
            break

    final_total = max(Decimal("0"), equity + retained)
    return CPMCampaignStressRun(
        mode=mode,
        window_days=window_days,
        exposure_multiplier=exposure_multiplier,
        cost_drag_pct=cost_drag_pct,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        trades=len(observations),
        final_multiple=final_total / config.initial_capital,
        max_drawdown_pct=max_drawdown,
        intrabar_stressed_max_drawdown_pct=intrabar_max_drawdown,
        largest_single_trade_loss_pct=largest_loss_pct,
        max_losing_streak=max_losing_streak,
        ruined=equity <= 0,
        below_1x=final_total < config.initial_capital,
    )


def _risk_unit(config: CPMCampaignReplayConfig, equity: Decimal) -> Decimal:
    if config.risk_model == CPMCampaignRiskModel.FIXED_FRACTIONAL:
        assert config.risk_per_trade_pct is not None
        return max(Decimal("0"), equity * config.risk_per_trade_pct / Decimal("100"))
    assert config.fixed_risk_unit is not None
    return min(config.fixed_risk_unit, max(Decimal("0"), equity))


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    raw_index = (Decimal(len(sorted_values) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP")
    return sorted_values[int(raw_index)]


def _liquidation_proxy_breaches(
    *,
    observations: list[CPMCampaignStressObservation],
    exposure_multiplier: Decimal,
    thresholds: list[Decimal],
) -> tuple[dict[str, int], dict[str, Decimal]]:
    adverse_values = [
        abs(observation.adverse_proxy_pct) * exposure_multiplier
        for observation in observations
        if observation.adverse_proxy_pct is not None
    ]
    denominator = Decimal(len(adverse_values) or 1)
    counts = {
        f"{threshold}%": sum(1 for value in adverse_values if value >= threshold)
        for threshold in thresholds
    }
    rates = {key: Decimal(value) / denominator for key, value in counts.items()}
    return counts, rates


def _outcome_distribution(
    multiples: list[Decimal],
    runs: list[CPMCampaignStressRun],
) -> dict[str, int]:
    distribution = {
        "ruined": 0,
        "below_1x": 0,
        "1x_to_1.25x": 0,
        "1.25x_to_1.5x": 0,
        "1.5x_to_2x": 0,
        "2x_to_3x": 0,
        "above_3x": 0,
    }
    for multiple, run in zip(multiples, runs):
        if run.ruined:
            distribution["ruined"] += 1
        elif multiple < Decimal("1"):
            distribution["below_1x"] += 1
        elif multiple < Decimal("1.25"):
            distribution["1x_to_1.25x"] += 1
        elif multiple < Decimal("1.5"):
            distribution["1.25x_to_1.5x"] += 1
        elif multiple < Decimal("2"):
            distribution["1.5x_to_2x"] += 1
        elif multiple < Decimal("3"):
            distribution["2x_to_3x"] += 1
        else:
            distribution["above_3x"] += 1
    return distribution


def _decision_label(summary: CPMCampaignExposureStressSummary) -> CPMCampaignStressDecisionLabel:
    if summary.campaigns == 0 or summary.intrabar_stressed_max_drawdown_pct is None:
        return CPMCampaignStressDecisionLabel.INSUFFICIENT_PATH_DATA
    median_multiple = summary.median_campaign_multiple or Decimal("0")
    worst_5pct = summary.worst_5pct_campaign_multiple or Decimal("0")
    top_10pct = summary.top_10pct_campaign_multiple or Decimal("0")
    if median_multiple < Decimal("1") or summary.ruin_rate > Decimal("0.30"):
        return CPMCampaignStressDecisionLabel.NOT_SUPPORTED_UNDER_EXPOSURE
    if (
        top_10pct >= Decimal("1.5")
        and worst_5pct >= Decimal("0.85")
        and summary.intrabar_stressed_max_drawdown_pct <= Decimal("35")
    ):
        return CPMCampaignStressDecisionLabel.RIGHT_TAIL_AMPLIFIES_WITH_CONTROLLED_LEFT_TAIL
    if top_10pct > Decimal("1.25") and median_multiple >= Decimal("1"):
        return CPMCampaignStressDecisionLabel.RIGHT_TAIL_EXISTS_BUT_LEFT_TAIL_EXPANDS_TOO_FAST
    return CPMCampaignStressDecisionLabel.NOT_SUPPORTED_UNDER_EXPOSURE
