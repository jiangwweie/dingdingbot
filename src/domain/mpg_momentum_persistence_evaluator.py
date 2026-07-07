"""MPG-001 momentum-persistence reference evaluator.

This evaluator is pure, deterministic, and non-executing. It turns closed
candle context into StrategyFamilySignalOutput review evidence only. It does
not size risk, select venue, create candidates, create intents, call
OrderLifecycle, or call exchange APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1
from typing import Any

from src.domain.strategy_candidate_semantics_builders import (
    build_mpg_long_candidate_semantics,
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


MPG_FAMILY_ID = "MPG-001"


@dataclass(frozen=True)
class MPGMomentumPersistenceConfig:
    min_1h_candles: int = 16
    min_4h_candles: int = 4
    lookback_bars: int = 8
    floor_lookback_bars: int = 5
    min_1h_net_pct: Decimal = Decimal("1.0")
    min_4h_net_pct: Decimal = Decimal("0.8")
    min_higher_closes: int = 3


@dataclass(frozen=True)
class _Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class MPG001MomentumPersistenceEvaluator:
    """Minimal long-only reference evaluator for StrategyGroup MPG-001."""

    def __init__(self, config: MPGMomentumPersistenceConfig | None = None) -> None:
        self._config = config or MPGMomentumPersistenceConfig()

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != MPG_FAMILY_ID:
            return self._invalid(
                signal_input,
                ["mpg_invalid_wrong_family"],
                "Input is not for MPG-001.",
            )
        if not signal_input.market_snapshot.candle_context.get("closed_bar", True):
            return self._invalid(
                signal_input,
                ["mpg_invalid_unclosed_bar"],
                "MPG-001 requires closed-candle context.",
            )

        windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
        one_hour = _parse_candles(
            windows.get("1h")
            or windows.get(signal_input.primary_timeframe)
            or []
        )
        four_hour = _parse_candles(windows.get("4h") or [])
        if len(one_hour) < self._config.min_1h_candles:
            return self._invalid(
                signal_input,
                ["mpg_invalid_insufficient_1h_candles"],
                "Insufficient 1h closed candles for MPG-001 v0.",
                evidence_payload={
                    "one_hour_count": len(one_hour),
                    "min_needed": self._config.min_1h_candles,
                },
            )
        if len(four_hour) < self._config.min_4h_candles:
            return self._invalid(
                signal_input,
                ["mpg_invalid_insufficient_4h_candles"],
                "Insufficient 4h closed candles for MPG-001 v0.",
                evidence_payload={
                    "four_hour_count": len(four_hour),
                    "min_needed": self._config.min_4h_candles,
                },
            )

        evidence = self._evaluate_structure(
            one_hour=one_hour,
            four_hour=four_hour,
        )
        confirmed = evidence["price_action_structure"]["momentum_persistence"]
        if not confirmed:
            return self._no_action(
                signal_input,
                ["mpg_no_action_momentum_persistence_not_confirmed"],
                "MPG-001 v0 did not confirm long momentum persistence.",
                evidence,
            )

        evidence["candidate_semantics"] = (
            build_mpg_long_candidate_semantics(
                strategy_family_version_id=(
                    signal_input.strategy_family_version_id
                ),
                timeframe=signal_input.primary_timeframe,
                evidence=evidence,
            ).model_dump(mode="json")
        )
        return self._would_enter(
            signal_input,
            side=SignalSide.LONG,
            confidence=Decimal("0.61"),
            reason_codes=[
                "mpg_htf_trend_up",
                "mpg_1h_momentum_positive",
                "mpg_breakout_close_confirmed",
            ],
            human_summary=(
                "MPG-001 v0 long momentum persistence detected for review."
            ),
            evidence_payload=evidence,
        )

    def _evaluate_structure(
        self,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> dict[str, Any]:
        cfg = self._config
        latest = one_hour[-1]
        lookback = one_hour[-(cfg.lookback_bars + 1) : -1]
        floor_lookback = one_hour[-(cfg.floor_lookback_bars + 1) : -1]
        one_hour_net_pct = _pct(
            latest.close - lookback[0].close,
            lookback[0].close,
        )
        four_hour_net_pct = _pct(
            four_hour[-1].close - four_hour[0].close,
            four_hour[0].close,
        )
        previous_range_high = max(candle.high for candle in lookback)
        momentum_floor = min(candle.low for candle in floor_lookback)
        higher_closes = _count_higher_closes(one_hour[-(cfg.min_higher_closes + 2) :])
        htf_up = four_hour_net_pct >= cfg.min_4h_net_pct
        primary_positive = one_hour_net_pct >= cfg.min_1h_net_pct
        breakout_close = latest.close > previous_range_high and latest.close > latest.open
        confirmed = htf_up and primary_positive and breakout_close and (
            higher_closes >= cfg.min_higher_closes
        )
        return {
            "market_state": "TREND_UP" if htf_up else "UNCERTAIN",
            "htf_context": "trend_up" if htf_up else "mixed",
            "entry_pattern": (
                "momentum_persistence_continuation" if breakout_close else "none"
            ),
            "latest_1h_open_time_ms": latest.open_time_ms,
            "momentum_state": {
                "one_hour_net_pct": _s(_q(one_hour_net_pct)),
                "four_hour_net_pct": _s(_q(four_hour_net_pct)),
                "consecutive_higher_closes": higher_closes,
            },
            "price_action_structure": {
                "momentum_persistence": confirmed,
                "latest_close": _s(latest.close),
                "previous_range_high": _s(previous_range_high),
                "momentum_floor_reference": _s(momentum_floor),
                "one_hour_net_pct": _s(_q(one_hour_net_pct)),
                "four_hour_net_pct": _s(_q(four_hour_net_pct)),
                "consecutive_higher_closes": higher_closes,
                "breakout_close": breakout_close,
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_below_recent_momentum_floor",
                    "description": (
                        "MPG invalidates when price closes below the recent "
                        "momentum floor reference."
                    ),
                },
                {
                    "condition_type": "time_stop",
                    "description": (
                        "No continuation after signal should stop repeated "
                        "attempts."
                    ),
                },
            ],
        }

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
                notes=["MPG-001 evaluator rejected the input as invalid."],
            ),
            evidence_payload=evidence_payload or {},
            review_required=False,
        )

    def _no_action(
        self,
        signal_input: StrategyFamilySignalInput,
        reason_codes: list[str],
        human_summary: str,
        evidence_payload: dict[str, Any],
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
    ) -> StrategyFamilySignalOutput:
        signal_snapshot = {
            "strategy_family": MPG_FAMILY_ID,
            "logic_version": "mpg-001-momentum-persistence-v0",
            "context_tags": {
                "market_state": evidence_payload.get("market_state", "UNKNOWN"),
                "htf_context": evidence_payload.get("htf_context", "unknown"),
                "entry_pattern": evidence_payload.get("entry_pattern", "none"),
            },
        }
        return StrategyFamilySignalOutput(
            signal_id=f"mpg-{_stable_suffix(signal_input.evaluation_id)}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=MPG_FAMILY_ID,
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
            required_execution_mode="observe_only",
            expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
            invalidation_conditions=list(
                evidence_payload.get("invalidation_conditions") or []
            ),
            signal_snapshot=signal_snapshot,
            evidence_payload={
                "logic_version": "mpg-001-momentum-persistence-v0",
                "confidence_notice": (
                    "confidence is review sorting only, not win probability "
                    "or authorization"
                ),
                **evidence_payload,
            },
            input_refs=SignalInputRefs(
                market_snapshot_ref=(
                    f"closed_ohlcv:{signal_input.symbol}:"
                    f"{signal_input.timestamp_ms}"
                ),
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
                    "runner_giveback",
                    "momentum_follow_through",
                    "stop_effectiveness",
                ],
                owner_review_status=(
                    "strategy_review_pending" if review_required else "not_required"
                ),
            ),
            not_order=True,
            not_execution_intent=True,
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


def _count_higher_closes(candles: list[_Candle]) -> int:
    return sum(
        1
        for previous, current in zip(candles, candles[1:])
        if current.close > previous.close
    )


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _s(value: Decimal) -> str:
    return str(value.normalize())


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]
