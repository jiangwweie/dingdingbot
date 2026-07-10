"""Pure SOR-001 15m session opening-range evaluator.

The evaluator emits strategy facts only.  It does not authorize execution,
size an order, or call any runtime or exchange surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade
from src.domain.strategy_family_signal import (
    ExpectedRiskShape,
    SignalInputRefs,
    SignalReviewPlan,
    SignalSide,
    SignalType,
    StrategyFactObservation,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)


SOR_FAMILY_ID = "SOR-001"
SOR_PRIMARY_TIMEFRAME = "15m"
SOR_OPENING_RANGE_BARS = 4
SOR_EVENT_VALIDITY_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class _Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class SOR001SessionRangeEvaluator:
    """Evaluate both sides of the canonical four-bar 15m opening range."""

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != SOR_FAMILY_ID:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                reason_codes=["sor_invalid_wrong_family"],
                human_summary="Input is not for SOR-001.",
                review_required=False,
            )
        if signal_input.primary_timeframe != SOR_PRIMARY_TIMEFRAME:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                reason_codes=["sor_invalid_primary_timeframe"],
                human_summary="SOR-001 requires the PG event-spec 15m timeframe.",
                review_required=False,
            )
        if not signal_input.market_snapshot.candle_context.get("closed_bar", True):
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                reason_codes=["sor_invalid_unclosed_bar"],
                human_summary="SOR-001 requires closed 15m candles.",
                review_required=False,
            )

        windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
        try:
            candles = _parse_candles(windows.get(SOR_PRIMARY_TIMEFRAME) or [])
        except (KeyError, TypeError, ValueError):
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                reason_codes=["sor_invalid_candle_payload"],
                human_summary="SOR-001 received an invalid closed-candle payload.",
                review_required=False,
            )
        minimum = SOR_OPENING_RANGE_BARS + 1
        if len(candles) < minimum:
            return self._output(
                signal_input,
                signal_type=SignalType.INVALID,
                side=SignalSide.NONE,
                reason_codes=["sor_invalid_insufficient_15m_candles"],
                human_summary="SOR-001 requires four opening-range bars and one trigger bar.",
                evidence_payload={"candle_count": len(candles), "min_needed": minimum},
                review_required=False,
            )

        opening_range = candles[:SOR_OPENING_RANGE_BARS]
        latest = candles[-1]
        previous = candles[-2]
        range_high = max(candle.high for candle in opening_range)
        range_low = min(candle.low for candle in opening_range)
        breakout = latest.close > range_high and latest.close >= previous.close
        breakdown = latest.close < range_low and latest.close <= previous.close
        evidence = {
            "logic_version": "sor-session-range-v2",
            "opening_range_bars": SOR_OPENING_RANGE_BARS,
            "opening_range_high": str(range_high),
            "opening_range_low": str(range_low),
            "latest_close": str(latest.close),
            "breakout_confirmed": breakout,
            "breakdown_confirmed": breakdown,
        }

        if not breakout and not breakdown:
            return self._output(
                signal_input,
                signal_type=SignalType.NO_ACTION,
                side=SignalSide.NONE,
                confidence=Decimal("0.20"),
                reason_codes=["sor_no_action_opening_range_intact"],
                human_summary="SOR-001 opening range remains intact.",
                evidence_payload=evidence,
                review_required=False,
            )

        side = SignalSide.LONG if breakout else SignalSide.SHORT
        event_fact = "breakout_confirmed" if breakout else "breakdown_confirmed"
        protection_fact = (
            "opening_range_low_reference"
            if breakout
            else "opening_range_high_reference"
        )
        protection_value = range_low if breakout else range_high
        trigger_ms = int(signal_input.trigger_candle_close_time_ms or 0)
        valid_until_ms = trigger_ms + SOR_EVENT_VALIDITY_MS
        source_ref = f"closed_ohlcv:{signal_input.symbol}:{trigger_ms}:sor-v2"
        fact_observations = [
            StrategyFactObservation(
                fact_key="opening_range_defined",
                observed_value=True,
                observed_at_ms=trigger_ms,
                valid_until_ms=valid_until_ms,
                source_ref=source_ref,
            ),
            StrategyFactObservation(
                fact_key=event_fact,
                observed_value=True,
                observed_at_ms=trigger_ms,
                valid_until_ms=valid_until_ms,
                source_ref=source_ref,
            ),
            StrategyFactObservation(
                fact_key=protection_fact,
                observed_value=protection_value,
                observed_at_ms=trigger_ms,
                valid_until_ms=valid_until_ms,
                source_ref=source_ref,
            ),
        ]
        return self._output(
            signal_input,
            signal_type=SignalType.WOULD_ENTER,
            side=side,
            confidence=Decimal("0.60"),
            reason_codes=[f"sor_opening_range_{'breakout' if breakout else 'breakdown'}"],
            human_summary=f"SOR-001 15m opening-range {side.value} event detected.",
            evidence_payload=evidence,
            fact_observations=fact_observations,
            review_required=True,
            signal_grade=SignalGrade.TRIAL_GRADE_SIGNAL,
            required_execution_mode=RequiredExecutionMode.TRIAL_LIVE,
        )

    def _output(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        signal_type: SignalType,
        side: SignalSide,
        reason_codes: list[str],
        human_summary: str,
        review_required: bool,
        confidence: Decimal = Decimal("0"),
        evidence_payload: dict[str, Any] | None = None,
        fact_observations: list[StrategyFactObservation] | None = None,
        signal_grade: SignalGrade = SignalGrade.OBSERVE_ONLY_SIGNAL,
        required_execution_mode: RequiredExecutionMode = RequiredExecutionMode.OBSERVE_ONLY,
    ) -> StrategyFamilySignalOutput:
        return StrategyFamilySignalOutput(
            signal_id=f"sor-session-range-{signal_input.evaluation_id}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            playbook_id=signal_input.playbook_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=signal_type,
            side=side,
            confidence=confidence,
            reason_codes=reason_codes,
            human_summary=human_summary,
            signal_grade=signal_grade,
            required_execution_mode=required_execution_mode,
            expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
            signal_snapshot={
                "strategy_family": SOR_FAMILY_ID,
                "logic_version": "sor-session-range-v2",
            },
            evidence_payload=evidence_payload or {},
            fact_observations=fact_observations or [],
            input_refs=SignalInputRefs(
                market_snapshot_ref=(
                    f"closed_ohlcv:{signal_input.symbol}:{signal_input.timestamp_ms}"
                ),
                playbook_snapshot_ref=signal_input.playbook_id,
                evaluation_ref=signal_input.evaluation_id,
            ),
            data_quality=signal_input.input_quality,
            review_plan=SignalReviewPlan(
                review_required=review_required,
                review_windows=["1h", "4h", "24h"],
                forward_outcome_metrics=["MFE", "MAE", "false_breakout", "follow_through"],
                owner_review_status=(
                    "strategy_review_pending" if review_required else "not_required"
                ),
            ),
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
        if candle.high < max(candle.open, candle.close):
            raise ValueError("high must be >= open and close")
        if candle.low > min(candle.open, candle.close):
            raise ValueError("low must be <= open and close")
        if min(candle.open, candle.high, candle.low, candle.close) <= Decimal("0"):
            raise ValueError("OHLC values must be positive")
        candles.append(candle)
    return sorted(candles, key=lambda candle: candle.open_time_ms)
