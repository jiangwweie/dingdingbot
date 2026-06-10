"""Reference price-action evaluators for near-term strategy semantics.

These evaluators are pure, deterministic, and non-executing. They create
StrategyFamilySignalOutput review evidence only; sizing, leverage, venue,
order type, submit permission, and runtime budget authority remain outside the
strategy layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1
from typing import Any

from src.domain.strategy_candidate_semantics_builders import (
    build_btpc_short_candidate_semantics,
    build_lsr_candidate_semantics,
    build_rbr_candidate_semantics,
    build_vcb_candidate_semantics,
)
from src.domain.strategy_family_signal import (
    ExpectedRiskShape,
    SignalDataQuality,
    SignalDataQualityStatus,
    SignalInputRefs,
    SignalReviewPlan,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)


BTPC_FAMILY_ID = "BTPC-001"
LSR_FAMILY_ID = "LSR-001"
RBR_FAMILY_ID = "RBR-001"
VCB_FAMILY_ID = "VCB-001"


@dataclass(frozen=True)
class ReferencePriceActionConfig:
    min_candles: int = 14
    lookback_bars: int = 10
    min_pullback_pct: Decimal = Decimal("1.0")
    boundary_band_pct: Decimal = Decimal("0.35")
    compression_window: int = 6
    compression_ratio: Decimal = Decimal("0.60")


@dataclass(frozen=True)
class _Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class _ReferencePriceActionEvaluator:
    family_id: str
    logic_version: str

    def __init__(self, config: ReferencePriceActionConfig | None = None) -> None:
        self._config = config or ReferencePriceActionConfig()

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != self.family_id:
            return self._invalid(
                signal_input,
                [f"{self.family_id.lower()}_invalid_wrong_family"],
                f"Input is not for {self.family_id}.",
            )
        if not signal_input.market_snapshot.candle_context.get("closed_bar", True):
            return self._invalid(
                signal_input,
                [f"{self.family_id.lower()}_invalid_unclosed_bar"],
                f"{self.family_id} requires explicit closed-candle context.",
            )

        windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
        one_hour = _parse_candles(
            windows.get("1h") or windows.get(signal_input.primary_timeframe) or []
        )
        four_hour = _parse_candles(windows.get("4h") or [])
        if len(one_hour) < self._config.min_candles:
            return self._invalid(
                signal_input,
                [f"{self.family_id.lower()}_invalid_insufficient_1h_candles"],
                f"Insufficient 1h closed candles for {self.family_id} v0.",
                evidence_payload={
                    "one_hour_count": len(one_hour),
                    "min_needed": self._config.min_candles,
                },
            )
        if len(four_hour) < 2:
            return self._invalid(
                signal_input,
                [f"{self.family_id.lower()}_invalid_missing_4h_context"],
                f"Missing 4h context for {self.family_id} v0.",
                evidence_payload={"four_hour_count": len(four_hour)},
            )
        return self._evaluate(signal_input, one_hour=one_hour, four_hour=four_hour)

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        raise NotImplementedError

    def _invalid(
        self,
        signal_input: StrategyFamilySignalInput,
        reason_codes: list[str],
        human_summary: str,
        evidence_payload: dict[str, Any] | None = None,
    ) -> StrategyFamilySignalOutput:
        return self._output(
            signal_input,
            signal_type=SignalType.INVALID,
            side=SignalSide.NONE,
            confidence=Decimal("0"),
            reason_codes=reason_codes,
            human_summary=human_summary,
            data_quality=SignalDataQuality(
                status=SignalDataQualityStatus.INVALID,
                missing_fields=list(signal_input.input_quality.missing_fields),
                stale_fields=list(signal_input.input_quality.stale_fields),
                warnings=list(signal_input.input_quality.warnings),
                notes=[f"{self.family_id} evaluator rejected the input as invalid."],
            ),
            evidence_payload=evidence_payload or {},
            review_required=False,
            expected_risk_shape=ExpectedRiskShape.UNKNOWN,
        )

    def _no_action(
        self,
        signal_input: StrategyFamilySignalInput,
        reason_codes: list[str],
        human_summary: str,
        evidence_payload: dict[str, Any],
        *,
        expected_risk_shape: ExpectedRiskShape | str,
    ) -> StrategyFamilySignalOutput:
        return self._output(
            signal_input,
            signal_type=SignalType.NO_ACTION,
            side=SignalSide.NONE,
            confidence=Decimal("0.25"),
            reason_codes=reason_codes,
            human_summary=human_summary,
            data_quality=signal_input.input_quality,
            evidence_payload=evidence_payload,
            review_required=False,
            expected_risk_shape=expected_risk_shape,
        )

    def _would_enter(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        side: SignalSide,
        confidence: Decimal,
        reason_codes: list[str],
        human_summary: str,
        evidence_payload: dict[str, Any],
        expected_risk_shape: ExpectedRiskShape | str,
    ) -> StrategyFamilySignalOutput:
        return self._output(
            signal_input,
            signal_type=SignalType.WOULD_ENTER,
            side=side,
            confidence=confidence,
            reason_codes=reason_codes,
            human_summary=human_summary,
            data_quality=signal_input.input_quality,
            evidence_payload=evidence_payload,
            review_required=True,
            expected_risk_shape=expected_risk_shape,
        )

    def _output(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        signal_type: SignalType,
        side: SignalSide,
        confidence: Decimal,
        reason_codes: list[str],
        human_summary: str,
        data_quality: SignalDataQuality,
        evidence_payload: dict[str, Any],
        review_required: bool,
        expected_risk_shape: ExpectedRiskShape | str,
    ) -> StrategyFamilySignalOutput:
        signal_snapshot = {
            "strategy_family": self.family_id,
            "logic_version": self.logic_version,
            "context_tags": {
                "market_state": evidence_payload.get("market_state", "UNCERTAIN"),
                "entry_pattern": evidence_payload.get("entry_pattern", "none"),
            },
        }
        return StrategyFamilySignalOutput(
            signal_id=f"{self.family_id.lower()}-{_stable_suffix(signal_input.evaluation_id)}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=self.family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            playbook_id=signal_input.playbook_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=signal_type,
            side=side,
            confidence=confidence,
            reason_codes=reason_codes,
            human_summary=human_summary,
            required_execution_mode="observe_only",
            expected_risk_shape=expected_risk_shape,
            invalidation_conditions=list(evidence_payload.get("invalidation_conditions") or []),
            signal_snapshot=signal_snapshot,
            evidence_payload={
                "logic_version": self.logic_version,
                "confidence_notice": "confidence is review sorting only, not win probability or authorization",
                **evidence_payload,
            },
            input_refs=SignalInputRefs(
                market_snapshot_ref=f"closed_ohlcv:{signal_input.symbol}:{signal_input.timestamp_ms}",
                playbook_snapshot_ref=signal_input.playbook_id,
                evaluation_ref=signal_input.evaluation_id,
            ),
            data_quality=data_quality,
            review_plan=SignalReviewPlan(
                review_required=review_required,
                review_windows=["4h", "24h", "72h", "7d"],
                forward_outcome_metrics=[
                    "MFE",
                    "MAE",
                    "R_multiple",
                    "tail_win_size",
                    "small_loss_count",
                    "winner_hold_time",
                    "runner_capped_too_early",
                    "stop_effectiveness",
                    "attempt_continuation_quality",
                ],
                owner_review_status="strategy_review_pending" if review_required else "not_required",
            ),
            not_order=True,
            not_execution_intent=True,
        )


class BTPC001PriceActionEvaluator(_ReferencePriceActionEvaluator):
    family_id = BTPC_FAMILY_ID
    logic_version = "btpc-001-price-action-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        latest = one_hour[-1]
        previous = one_hour[-2]
        lookback = one_hour[-(self._config.lookback_bars + 1) : -1]
        pullback_low = min(candle.low for candle in lookback)
        pullback_high = max(candle.high for candle in lookback + [latest])
        pullback_pct = _pct(pullback_high - pullback_low, pullback_low)
        htf_net_pct = _pct(four_hour[-1].close - four_hour[0].close, four_hour[0].close)
        trend_down = htf_net_pct <= Decimal("-1.0")
        structure_loss = latest.close < previous.low and latest.close < latest.open
        evidence = {
            "market_state": "TREND_DOWN" if trend_down else "UNCERTAIN",
            "htf_context": "trend_down" if trend_down else "mixed",
            "entry_pattern": "bear_trend_pullback_continuation" if structure_loss else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "price_action_structure": {
                "bear_trend_pullback_continuation": trend_down
                and structure_loss
                and pullback_pct >= self._config.min_pullback_pct,
                "pullback_pct": _s(_q(pullback_pct)),
                "pullback_high_reference": _s(pullback_high),
                "pullback_low_reference": _s(pullback_low),
                "latest_close": _s(latest.close),
                "previous_low": _s(previous.low),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_above_pullback_high",
                    "description": "BTPC invalidates if price closes above pullback high.",
                },
                {
                    "condition_type": "time_stop",
                    "description": "No downside follow-through should stop repeated attempts.",
                },
            ],
        }
        confirmed = evidence["price_action_structure"]["bear_trend_pullback_continuation"]
        if not confirmed:
            return self._no_action(
                signal_input,
                ["btpc_no_action_no_bear_pullback_continuation"],
                "BTPC v0 did not confirm bear-trend pullback continuation.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
            )
        evidence["candidate_semantics"] = build_btpc_short_candidate_semantics(
            strategy_family_version_id=signal_input.strategy_family_version_id,
            timeframe=signal_input.primary_timeframe,
            evidence=evidence,
        ).model_dump(mode="json")
        return self._would_enter(
            signal_input,
            side=SignalSide.SHORT,
            confidence=Decimal("0.62"),
            reason_codes=[
                "btpc_htf_downtrend",
                "btpc_pullback_depth_confirmed",
                "btpc_structure_loss_confirmed",
            ],
            human_summary="BTPC v0 short bear-trend pullback continuation detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
        )


class LSR001PriceActionEvaluator(_ReferencePriceActionEvaluator):
    family_id = LSR_FAMILY_ID
    logic_version = "lsr-001-price-action-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        del four_hour
        latest = one_hour[-1]
        lookback = one_hour[-(self._config.lookback_bars + 1) : -1]
        range_high = max(candle.high for candle in lookback)
        range_low = min(candle.low for candle in lookback)
        range_mid = (range_high + range_low) / Decimal("2")
        swept_low = latest.low < range_low and latest.close > range_low and latest.close > latest.open
        swept_high = latest.high > range_high and latest.close < range_high and latest.close < latest.open
        side = SignalSide.LONG if swept_low else SignalSide.SHORT if swept_high else SignalSide.NONE
        sweep_extreme = latest.low if side == SignalSide.LONG else latest.high
        evidence = {
            "market_state": "RANGE",
            "entry_pattern": "liquidity_sweep_reversal" if side != SignalSide.NONE else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "range_structure": {
                "range_high_reference": _s(range_high),
                "range_low_reference": _s(range_low),
                "range_mid_reference": _s(range_mid),
            },
            "price_action_structure": {
                "liquidity_sweep_reversal": side != SignalSide.NONE,
                "sweep_direction": "down" if side == SignalSide.LONG else "up" if side == SignalSide.SHORT else "none",
                "sweep_extreme_reference": _s(sweep_extreme),
                "range_mid_reference": _s(range_mid),
                "latest_close": _s(latest.close),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_beyond_sweep_extreme",
                    "description": "LSR invalidates if price closes beyond the sweep extreme.",
                },
                {
                    "condition_type": "time_stop",
                    "description": "Mean-reversion failure should time out quickly.",
                },
            ],
        }
        if side == SignalSide.NONE:
            return self._no_action(
                signal_input,
                ["lsr_no_action_no_sweep_reclaim"],
                "LSR v0 did not confirm a liquidity sweep and reclaim/rejection.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        evidence["candidate_semantics"] = build_lsr_candidate_semantics(
            strategy_family_version_id=signal_input.strategy_family_version_id,
            timeframe=signal_input.primary_timeframe,
            side=side.value,
            evidence=evidence,
        ).model_dump(mode="json")
        return self._would_enter(
            signal_input,
            side=side,
            confidence=Decimal("0.58"),
            reason_codes=["lsr_sweep_extreme", "lsr_reclaim_or_rejection_confirmed"],
            human_summary="LSR v0 liquidity sweep reversal detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.UNKNOWN,
        )


class RBR001PriceActionEvaluator(_ReferencePriceActionEvaluator):
    family_id = RBR_FAMILY_ID
    logic_version = "rbr-001-price-action-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        del four_hour
        latest = one_hour[-1]
        lookback = one_hour[-(self._config.lookback_bars + 1) : -1]
        range_high = max(candle.high for candle in lookback)
        range_low = min(candle.low for candle in lookback)
        range_width = range_high - range_low
        band = max(range_width * (self._config.boundary_band_pct / Decimal("100")), Decimal("0.0001"))
        near_low = latest.low <= range_low + band and latest.close > latest.open
        near_high = latest.high >= range_high - band and latest.close < latest.open
        side = SignalSide.LONG if near_low else SignalSide.SHORT if near_high else SignalSide.NONE
        stop_reference = range_low if side == SignalSide.LONG else range_high
        target_reference = range_high if side == SignalSide.LONG else range_low
        evidence = {
            "market_state": "RANGE",
            "entry_pattern": "range_boundary_reversion" if side != SignalSide.NONE else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "range_structure": {
                "range_high_reference": _s(range_high),
                "range_low_reference": _s(range_low),
                "range_width": _s(range_width),
                "boundary_band": _s(_q(band)),
            },
            "volatility_state": {
                "state": "bounded_range",
                "compression_confirmed": False,
            },
            "price_action_structure": {
                "range_boundary_reversion": side != SignalSide.NONE,
                "range_boundary": "lower" if side == SignalSide.LONG else "upper" if side == SignalSide.SHORT else "none",
                "boundary_stop_reference": _s(stop_reference),
                "opposite_range_target_reference": _s(target_reference),
                "latest_close": _s(latest.close),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_outside_range_boundary",
                    "description": "RBR invalidates if price closes outside rejected range boundary.",
                },
                {
                    "condition_type": "time_stop",
                    "description": "Range-boundary reversion should not consume attempts indefinitely.",
                },
            ],
        }
        if side == SignalSide.NONE:
            return self._no_action(
                signal_input,
                ["rbr_no_action_not_at_range_boundary"],
                "RBR v0 did not confirm range-boundary rejection.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        evidence["candidate_semantics"] = build_rbr_candidate_semantics(
            strategy_family_version_id=signal_input.strategy_family_version_id,
            timeframe=signal_input.primary_timeframe,
            side=side.value,
            evidence=evidence,
        ).model_dump(mode="json")
        return self._would_enter(
            signal_input,
            side=side,
            confidence=Decimal("0.57"),
            reason_codes=["rbr_range_context", "rbr_boundary_rejection_confirmed"],
            human_summary="RBR v0 range-boundary reversion detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.UNKNOWN,
        )


class VCB001PriceActionEvaluator(_ReferencePriceActionEvaluator):
    family_id = VCB_FAMILY_ID
    logic_version = "vcb-001-price-action-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        del four_hour
        cfg = self._config
        latest = one_hour[-1]
        compression_window = one_hour[-(cfg.compression_window + 1) : -1]
        prior_window = one_hour[-(cfg.compression_window * 2 + 1) : -(cfg.compression_window + 1)]
        compression_high = max(candle.high for candle in compression_window)
        compression_low = min(candle.low for candle in compression_window)
        compression_range = compression_high - compression_low
        prior_avg_range = _avg_range(prior_window)
        recent_avg_range = _avg_range(compression_window)
        compression_confirmed = (
            prior_avg_range > Decimal("0")
            and recent_avg_range <= prior_avg_range * cfg.compression_ratio
        )
        breakout_up = compression_confirmed and latest.close > compression_high and latest.close > latest.open
        breakout_down = compression_confirmed and latest.close < compression_low and latest.close < latest.open
        side = SignalSide.LONG if breakout_up else SignalSide.SHORT if breakout_down else SignalSide.NONE
        stop_reference = compression_low if side == SignalSide.LONG else compression_high
        breakout_boundary = compression_high if side == SignalSide.LONG else compression_low
        evidence = {
            "market_state": "UNCERTAIN",
            "entry_pattern": "volatility_compression_breakout" if side != SignalSide.NONE else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "volatility_state": {
                "compression_confirmed": compression_confirmed,
                "recent_avg_range": _s(_q(recent_avg_range)),
                "prior_avg_range": _s(_q(prior_avg_range)),
                "compression_range_pct": _s(_q(_pct(compression_range, compression_low))),
            },
            "price_action_structure": {
                "volatility_compression_breakout": side != SignalSide.NONE,
                "breakout_direction": side.value,
                "breakout_boundary_reference": _s(breakout_boundary),
                "compression_opposite_boundary_reference": _s(stop_reference),
                "compression_range_pct": _s(_q(_pct(compression_range, compression_low))),
                "latest_close": _s(latest.close),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_back_inside_compression_range",
                    "description": "VCB invalidates if price closes back inside compression range.",
                },
                {
                    "condition_type": "time_stop",
                    "description": "Failed volatility expansion should stop quickly.",
                },
            ],
        }
        if side == SignalSide.NONE:
            return self._no_action(
                signal_input,
                ["vcb_no_action_no_compression_breakout"],
                "VCB v0 did not confirm volatility compression breakout.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
            )
        evidence["candidate_semantics"] = build_vcb_candidate_semantics(
            strategy_family_version_id=signal_input.strategy_family_version_id,
            timeframe=signal_input.primary_timeframe,
            side=side.value,
            evidence=evidence,
        ).model_dump(mode="json")
        return self._would_enter(
            signal_input,
            side=side,
            confidence=Decimal("0.60"),
            reason_codes=["vcb_compression_confirmed", "vcb_breakout_close_confirmed"],
            human_summary="VCB v0 volatility compression breakout detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
        )


def _parse_candles(raw_candles: list[dict[str, Any]]) -> list[_Candle]:
    candles: list[_Candle] = []
    for raw in raw_candles:
        candle = _Candle(
            open_time_ms=int(raw["open_time_ms"]),
            open=Decimal(str(raw["open"])),
            high=Decimal(str(raw["high"])),
            low=Decimal(str(raw["low"])),
            close=Decimal(str(raw["close"])),
            volume=Decimal(str(raw.get("volume", "0"))),
        )
        _validate_ohlc(candle)
        candles.append(candle)
    return sorted(candles, key=lambda candle: candle.open_time_ms)


def _validate_ohlc(candle: _Candle) -> None:
    if candle.high < max(candle.open, candle.close):
        raise ValueError("high must be >= open and close")
    if candle.low > min(candle.open, candle.close):
        raise ValueError("low must be <= open and close")
    if min(candle.open, candle.high, candle.low, candle.close) <= Decimal("0"):
        raise ValueError("OHLC values must be positive")


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _avg_range(candles: list[_Candle]) -> Decimal:
    if not candles:
        return Decimal("0")
    return sum((candle.high - candle.low for candle in candles), Decimal("0")) / Decimal(
        len(candles)
    )


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _s(value: Decimal) -> str:
    return str(value.normalize())


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]
