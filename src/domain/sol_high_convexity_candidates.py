"""Pure SOL high-convexity candidate comparison helpers.

These helpers evaluate deterministic historical research signals from OHLCV
bars. They do not implement live trading, order simulation, execution intents,
trial-trade-intent evidence, live routing, or strategy scheduling.
"""

from __future__ import annotations

import random
from collections import Counter
from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.cpm_campaign_exposure_stress import (
    CPMCampaignStressMode,
    CPMCampaignStressObservation,
    summarize_campaign_exposure_stress,
)
from src.domain.cpm_campaign_replay import CPMCampaignReplayConfig
from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class SOLCandidateId(str, Enum):
    VOL_EXPANSION_BREAKOUT = "sol_volatility_expansion_breakout_v0"
    DONCHIAN_20_BREAKOUT = "sol_donchian_20_breakout_v0"
    DONCHIAN_55_BREAKOUT = "sol_donchian_55_breakout_v0"
    DONCHIAN_20_BTC_FILTERED = "sol_donchian_20_btc_regime_filtered_v0"
    VOL_EXPANSION_BTC_FILTERED = "sol_volatility_expansion_btc_regime_filtered_v0"


class SOLResearchSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class SOLCandidateVerdict(str, Enum):
    PARK = "park"
    NEEDS_REFINEMENT = "needs_refinement"
    RIGHT_TAIL_CANDIDATE = "right_tail_candidate"
    CAMPAIGN_CANDIDATE = "campaign_candidate"
    OBSERVATION_CANDIDATE = "observation_candidate"


class BTCRegime(str, Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class SOLResearchCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp_ms: int = Field(ge=0)
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: Decimal = Field(ge=Decimal("0"))

    @model_validator(mode="after")
    def _validate_and_reject_execution_fields(self) -> "SOLResearchCandle":
        if self.high < self.low:
            raise ValueError("high must be >= low")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="sol_research_candle")
        return self


class SOLCandidateSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: SOLCandidateId
    timestamp_ms: int = Field(ge=0)
    side: SOLResearchSide
    entry_close: Decimal = Field(gt=Decimal("0"))
    reason_codes: list[str] = Field(default_factory=list)
    context: dict[str, str | Decimal | int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "SOLCandidateSignal":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="sol_candidate_signal")
        return self


class SOLForwardOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: SOLCandidateId
    timestamp_ms: int = Field(ge=0)
    side: SOLResearchSide
    exit_window_hours: int = Field(gt=0)
    gross_return_pct: Decimal
    mfe_pct: Decimal
    mae_pct: Decimal
    follow_through: bool
    invalidation_hit: bool

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "SOLForwardOutcome":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="sol_forward_outcome")
        return self


class SOLReplayMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_count: int = Field(ge=0)
    exit_window_hours: int = Field(gt=0)
    cost_drag_pct: Decimal = Field(ge=Decimal("0"))
    gross_mean_pct: Decimal | None = None
    gross_median_pct: Decimal | None = None
    net_mean_pct: Decimal | None = None
    net_median_pct: Decimal | None = None
    win_rate: Decimal | None = None
    average_gain_pct: Decimal | None = None
    average_loss_pct: Decimal | None = None
    payoff_ratio: Decimal | None = None
    mean_mfe_pct: Decimal | None = None
    mean_mae_pct: Decimal | None = None
    mfe_mae_ratio: Decimal | None = None
    follow_through_rate: Decimal | None = None
    invalidation_hit_rate: Decimal | None = None

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "SOLReplayMetrics":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="sol_replay_metrics")
        return self


class SOLRandomBaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seeds: int = Field(ge=1)
    candidate_mean_pct: Decimal | None = None
    baseline_mean_of_means_pct: Decimal | None = None
    baseline_p95_mean_pct: Decimal | None = None
    percentile_rank: Decimal | None = None

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "SOLRandomBaselineResult":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="sol_random_baseline_result")
        return self


def detect_volatility_expansion_breakouts(
    candles: list[SOLResearchCandle],
    *,
    candidate_id: SOLCandidateId = SOLCandidateId.VOL_EXPANSION_BREAKOUT,
    compression_bars: int = 12,
    prior_bars: int = 48,
    compression_threshold: Decimal = Decimal("0.45"),
    min_breakout_pct: Decimal = Decimal("0.10"),
) -> list[SOLCandidateSignal]:
    ordered = sorted(candles, key=lambda item: item.timestamp_ms)
    signals: list[SOLCandidateSignal] = []
    for index in range(prior_bars, len(ordered)):
        current = ordered[index]
        recent = ordered[index - compression_bars : index]
        prior = ordered[index - prior_bars : index]
        recent_high = max(candle.high for candle in recent)
        recent_low = min(candle.low for candle in recent)
        prior_high = max(candle.high for candle in prior)
        prior_low = min(candle.low for candle in prior)
        prior_range = prior_high - prior_low
        if prior_range <= 0:
            continue
        compression_ratio = (recent_high - recent_low) / prior_range
        if compression_ratio > compression_threshold:
            continue
        min_breakout = min_breakout_pct / Decimal("100")
        if current.close > recent_high * (Decimal("1") + min_breakout):
            signals.append(
                SOLCandidateSignal(
                    candidate_id=candidate_id,
                    timestamp_ms=current.timestamp_ms,
                    side=SOLResearchSide.LONG,
                    entry_close=current.close,
                    reason_codes=["vol_compression", "range_high_breakout"],
                    context={"compression_ratio": compression_ratio, "recent_high": recent_high},
                )
            )
        elif current.close < recent_low * (Decimal("1") - min_breakout):
            signals.append(
                SOLCandidateSignal(
                    candidate_id=candidate_id,
                    timestamp_ms=current.timestamp_ms,
                    side=SOLResearchSide.SHORT,
                    entry_close=current.close,
                    reason_codes=["vol_compression", "range_low_breakout"],
                    context={"compression_ratio": compression_ratio, "recent_low": recent_low},
                )
            )
    return _dedupe_signals(signals)


def detect_donchian_breakouts(
    candles: list[SOLResearchCandle],
    *,
    lookback_bars: int,
    candidate_id: SOLCandidateId,
) -> list[SOLCandidateSignal]:
    ordered = sorted(candles, key=lambda item: item.timestamp_ms)
    signals: list[SOLCandidateSignal] = []
    for index in range(lookback_bars, len(ordered)):
        current = ordered[index]
        previous = ordered[index - 1]
        lookback = ordered[index - lookback_bars : index]
        channel_high = max(candle.high for candle in lookback)
        channel_low = min(candle.low for candle in lookback)
        previous_lookback = ordered[index - lookback_bars - 1 : index - 1] if index > lookback_bars else []
        previous_high = max((candle.high for candle in previous_lookback), default=channel_high)
        previous_low = min((candle.low for candle in previous_lookback), default=channel_low)
        if current.close > channel_high and previous.close <= previous_high:
            signals.append(
                SOLCandidateSignal(
                    candidate_id=candidate_id,
                    timestamp_ms=current.timestamp_ms,
                    side=SOLResearchSide.LONG,
                    entry_close=current.close,
                    reason_codes=[f"donchian_{lookback_bars}_high_break"],
                    context={"channel_high": channel_high, "lookback_bars": lookback_bars},
                )
            )
        elif current.close < channel_low and previous.close >= previous_low:
            signals.append(
                SOLCandidateSignal(
                    candidate_id=candidate_id,
                    timestamp_ms=current.timestamp_ms,
                    side=SOLResearchSide.SHORT,
                    entry_close=current.close,
                    reason_codes=[f"donchian_{lookback_bars}_low_break"],
                    context={"channel_low": channel_low, "lookback_bars": lookback_bars},
                )
            )
    return _dedupe_signals(signals)


def btc_regime_by_timestamp(
    btc_context_candles: list[SOLResearchCandle],
    *,
    sma_bars: int = 20,
) -> dict[int, BTCRegime]:
    ordered = sorted(btc_context_candles, key=lambda item: item.timestamp_ms)
    regimes: dict[int, BTCRegime] = {}
    for index in range(len(ordered)):
        if index + 1 < sma_bars:
            regimes[ordered[index].timestamp_ms] = BTCRegime.UNKNOWN
            continue
        window = ordered[index + 1 - sma_bars : index + 1]
        sma = sum((candle.close for candle in window), Decimal("0")) / Decimal(sma_bars)
        close = ordered[index].close
        if close > sma * Decimal("1.005"):
            regimes[ordered[index].timestamp_ms] = BTCRegime.UP
        elif close < sma * Decimal("0.995"):
            regimes[ordered[index].timestamp_ms] = BTCRegime.DOWN
        else:
            regimes[ordered[index].timestamp_ms] = BTCRegime.NEUTRAL
    return regimes


def apply_btc_regime_filter(
    signals: list[SOLCandidateSignal],
    btc_regimes: dict[int, BTCRegime],
    *,
    filtered_candidate_id: SOLCandidateId,
) -> list[SOLCandidateSignal]:
    if not btc_regimes:
        return []
    regime_timestamps = sorted(btc_regimes)
    filtered: list[SOLCandidateSignal] = []
    for signal in signals:
        regime = _latest_regime_at_or_before(signal.timestamp_ms, regime_timestamps, btc_regimes)
        allowed = (
            regime in {BTCRegime.UP, BTCRegime.NEUTRAL}
            if signal.side == SOLResearchSide.LONG
            else regime in {BTCRegime.DOWN, BTCRegime.NEUTRAL}
        )
        if not allowed:
            continue
        filtered.append(
            signal.model_copy(
                update={
                    "candidate_id": filtered_candidate_id,
                    "reason_codes": [*signal.reason_codes, f"btc_regime_{regime.value}"],
                    "context": {**signal.context, "btc_regime": regime.value},
                }
            )
        )
    return filtered


def compute_forward_outcomes(
    *,
    candles: list[SOLResearchCandle],
    signals: list[SOLCandidateSignal],
    exit_windows_hours: list[int],
) -> list[SOLForwardOutcome]:
    ordered = sorted(candles, key=lambda item: item.timestamp_ms)
    by_timestamp = {candle.timestamp_ms: index for index, candle in enumerate(ordered)}
    outcomes: list[SOLForwardOutcome] = []
    for signal in sorted(signals, key=lambda item: item.timestamp_ms):
        index = by_timestamp.get(signal.timestamp_ms)
        if index is None:
            continue
        entry = signal.entry_close
        for window in exit_windows_hours:
            future = ordered[index + 1 : index + 1 + window]
            if len(future) < window:
                continue
            exit_close = future[-1].close
            if signal.side == SOLResearchSide.LONG:
                gross_return = (exit_close - entry) / entry * Decimal("100")
                mfe = (max(candle.high for candle in future) - entry) / entry * Decimal("100")
                mae = (min(candle.low for candle in future) - entry) / entry * Decimal("100")
            else:
                gross_return = (entry - exit_close) / entry * Decimal("100")
                mfe = (entry - min(candle.low for candle in future)) / entry * Decimal("100")
                mae = (entry - max(candle.high for candle in future)) / entry * Decimal("100")
            outcomes.append(
                SOLForwardOutcome(
                    candidate_id=signal.candidate_id,
                    timestamp_ms=signal.timestamp_ms,
                    side=signal.side,
                    exit_window_hours=window,
                    gross_return_pct=gross_return,
                    mfe_pct=mfe,
                    mae_pct=mae,
                    follow_through=gross_return > Decimal("0"),
                    invalidation_hit=mae <= Decimal("-2"),
                )
            )
    return outcomes


def summarize_forward_outcomes(
    outcomes: list[SOLForwardOutcome],
    *,
    exit_window_hours: int,
    cost_drag_pct: Decimal,
) -> SOLReplayMetrics:
    selected = [item for item in outcomes if item.exit_window_hours == exit_window_hours]
    if not selected:
        return SOLReplayMetrics(signal_count=0, exit_window_hours=exit_window_hours, cost_drag_pct=cost_drag_pct)
    gross = [item.gross_return_pct for item in selected]
    net = [item.gross_return_pct - cost_drag_pct for item in selected]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    mean_mfe = _mean([item.mfe_pct for item in selected])
    mean_abs_mae = _mean([abs(item.mae_pct) for item in selected])
    return SOLReplayMetrics(
        signal_count=len(selected),
        exit_window_hours=exit_window_hours,
        cost_drag_pct=cost_drag_pct,
        gross_mean_pct=_mean(gross),
        gross_median_pct=Decimal(str(median(gross))),
        net_mean_pct=_mean(net),
        net_median_pct=Decimal(str(median(net))),
        win_rate=Decimal(len(wins)) / Decimal(len(selected)),
        average_gain_pct=_mean(wins),
        average_loss_pct=_mean(losses),
        payoff_ratio=_payoff(wins, losses),
        mean_mfe_pct=mean_mfe,
        mean_mae_pct=mean_abs_mae,
        mfe_mae_ratio=mean_mfe / mean_abs_mae if mean_mfe is not None and mean_abs_mae not in (None, Decimal("0")) else None,
        follow_through_rate=Decimal(sum(1 for item in selected if item.follow_through)) / Decimal(len(selected)),
        invalidation_hit_rate=Decimal(sum(1 for item in selected if item.invalidation_hit)) / Decimal(len(selected)),
    )


def random_same_frequency_baseline(
    *,
    eligible_candles: list[SOLResearchCandle],
    candidate_signals: list[SOLCandidateSignal],
    exit_window_hours: int,
    cost_drag_pct: Decimal,
    seeds: int = 100,
    base_seed: int = 1701,
) -> SOLRandomBaselineResult:
    signal_count = len(candidate_signals)
    if signal_count == 0:
        return SOLRandomBaselineResult(seeds=seeds)
    side_counts = Counter(signal.side for signal in candidate_signals)
    side_sequence = [side for side, count in sorted(side_counts.items(), key=lambda item: item[0].value) for _ in range(count)]
    eligible = eligible_candles[:-exit_window_hours] if exit_window_hours < len(eligible_candles) else []
    if len(eligible) < signal_count:
        return SOLRandomBaselineResult(seeds=seeds)

    candidate_mean = _mean([outcome.gross_return_pct - cost_drag_pct for outcome in compute_forward_outcomes(
        candles=eligible_candles,
        signals=candidate_signals,
        exit_windows_hours=[exit_window_hours],
    )])
    baseline_means: list[Decimal] = []
    for seed in range(seeds):
        rng = random.Random(base_seed + seed)
        sampled = rng.sample(eligible, signal_count)
        signals = [
            SOLCandidateSignal(
                candidate_id=SOLCandidateId.VOL_EXPANSION_BREAKOUT,
                timestamp_ms=candle.timestamp_ms,
                side=side_sequence[index % len(side_sequence)],
                entry_close=candle.close,
                reason_codes=["random_same_frequency"],
            )
            for index, candle in enumerate(sampled)
        ]
        outcomes = compute_forward_outcomes(
            candles=eligible_candles,
            signals=signals,
            exit_windows_hours=[exit_window_hours],
        )
        mean_return = _mean([outcome.gross_return_pct - cost_drag_pct for outcome in outcomes])
        if mean_return is not None:
            baseline_means.append(mean_return)
    if not baseline_means:
        return SOLRandomBaselineResult(seeds=seeds, candidate_mean_pct=candidate_mean)
    rank = (
        Decimal(sum(1 for value in baseline_means if candidate_mean is not None and value <= candidate_mean))
        / Decimal(len(baseline_means))
        if candidate_mean is not None
        else None
    )
    return SOLRandomBaselineResult(
        seeds=seeds,
        candidate_mean_pct=candidate_mean,
        baseline_mean_of_means_pct=_mean(baseline_means),
        baseline_p95_mean_pct=_percentile(baseline_means, Decimal("0.95")),
        percentile_rank=rank,
    )


def campaign_observations_from_outcomes(
    outcomes: list[SOLForwardOutcome],
    *,
    exit_window_hours: int,
) -> list[CPMCampaignStressObservation]:
    return [
        CPMCampaignStressObservation(
            timestamp_ms=outcome.timestamp_ms,
            gross_return_pct=outcome.gross_return_pct,
            adverse_proxy_pct=abs(outcome.mae_pct),
        )
        for outcome in sorted(outcomes, key=lambda item: item.timestamp_ms)
        if outcome.exit_window_hours == exit_window_hours
    ]


def summarize_campaign_candidate(
    *,
    outcomes: list[SOLForwardOutcome],
    exit_window_hours: int,
    cost_drag_pct: Decimal,
    exposure_multiplier: Decimal,
    campaign_config: CPMCampaignReplayConfig,
    mode: CPMCampaignStressMode,
    window_days: Optional[int] = None,
):
    return summarize_campaign_exposure_stress(
        observations=campaign_observations_from_outcomes(outcomes, exit_window_hours=exit_window_hours),
        config=campaign_config,
        exposure_multiplier=exposure_multiplier,
        cost_drag_pct=cost_drag_pct,
        mode=mode,
        window_days=window_days,
    )


def choose_candidate_verdict(
    *,
    best_metrics: SOLReplayMetrics,
    baseline: SOLRandomBaselineResult | None,
    top_campaign_multiple: Decimal | None,
    worst_campaign_multiple: Decimal | None,
    cpm_top_campaign_multiple: Decimal | None,
) -> SOLCandidateVerdict:
    net_mean = best_metrics.net_mean_pct or Decimal("0")
    net_median = best_metrics.net_median_pct or Decimal("0")
    win_rate = best_metrics.win_rate or Decimal("0")
    baseline_rank = baseline.percentile_rank if baseline is not None else None
    if best_metrics.signal_count < 20:
        return SOLCandidateVerdict.PARK
    if net_mean <= 0 or win_rate < Decimal("0.45"):
        return SOLCandidateVerdict.PARK
    if baseline_rank is not None and baseline_rank < Decimal("0.80"):
        return SOLCandidateVerdict.NEEDS_REFINEMENT
    if (
        top_campaign_multiple is not None
        and worst_campaign_multiple is not None
        and cpm_top_campaign_multiple is not None
        and top_campaign_multiple > cpm_top_campaign_multiple
        and worst_campaign_multiple >= Decimal("0.95")
    ):
        return SOLCandidateVerdict.CAMPAIGN_CANDIDATE
    if net_mean > 0 and net_median > 0 and win_rate >= Decimal("0.50"):
        return SOLCandidateVerdict.RIGHT_TAIL_CANDIDATE
    return SOLCandidateVerdict.NEEDS_REFINEMENT


def _dedupe_signals(signals: list[SOLCandidateSignal]) -> list[SOLCandidateSignal]:
    deduped: list[SOLCandidateSignal] = []
    previous_key: tuple[int, SOLResearchSide] | None = None
    for signal in sorted(signals, key=lambda item: item.timestamp_ms):
        key = (signal.timestamp_ms, signal.side)
        if key == previous_key:
            continue
        deduped.append(signal)
        previous_key = key
    return deduped


def _latest_regime_at_or_before(
    timestamp_ms: int,
    regime_timestamps: list[int],
    btc_regimes: dict[int, BTCRegime],
) -> BTCRegime:
    latest: int | None = None
    for value in regime_timestamps:
        if value <= timestamp_ms:
            latest = value
        else:
            break
    return btc_regimes.get(latest, BTCRegime.UNKNOWN) if latest is not None else BTCRegime.UNKNOWN


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _payoff(wins: list[Decimal], losses: list[Decimal]) -> Decimal | None:
    average_gain = _mean(wins)
    average_loss = _mean(losses)
    if average_gain is None or average_loss in (None, Decimal("0")):
        return None
    return average_gain / abs(average_loss)


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    raw_index = (Decimal(len(sorted_values) - 1) * percentile).to_integral_value(rounding="ROUND_HALF_UP")
    return sorted_values[int(raw_index)]
