"""BRF-001 bear-rally-failure price-action evaluator.

The evaluator is pure and deterministic. It accepts StrategyFamilySignalInput
and returns StrategyFamilySignalOutput for B0 strategy semantics review. It
does not size risk, create candidates, create execution intents, create orders,
route orders, or call live APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1
from typing import Any

from src.domain.strategy_candidate_semantics_builders import (
    build_brf_short_candidate_semantics,
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


BRF_FAMILY_ID = "BRF-001"


@dataclass(frozen=True)
class BRFPriceActionEvaluatorConfig:
    min_candles: int = 12
    rally_lookback_bars: int = 8
    min_rally_pct: Decimal = Decimal("2.0")
    min_rejection_upper_wick_ratio: Decimal = Decimal("0.30")
    min_close_reversal_pct: Decimal = Decimal("0.40")
    squeeze_extension_warning_pct: Decimal = Decimal("5.0")
    strong_htf_uptrend_pct: Decimal = Decimal("3.0")


@dataclass(frozen=True)
class _Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class BRF001PriceActionEvaluator:
    """Minimal short-side bear-rally-failure evaluator for B0 review."""

    def __init__(self, config: BRFPriceActionEvaluatorConfig | None = None) -> None:
        self._config = config or BRFPriceActionEvaluatorConfig()

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != BRF_FAMILY_ID:
            return self._invalid(
                signal_input,
                ["brf_invalid_wrong_family"],
                "Input is not for BRF-001.",
            )

        windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
        one_hour = _parse_candles(windows.get("1h") or windows.get(signal_input.primary_timeframe) or [])
        four_hour = _parse_candles(windows.get("4h") or [])
        if not signal_input.market_snapshot.candle_context.get("closed_bar", True):
            return self._invalid(
                signal_input,
                ["brf_invalid_unclosed_bar"],
                "BRF requires explicit closed-candle context.",
            )
        if len(one_hour) < self._config.min_candles:
            return self._invalid(
                signal_input,
                ["brf_invalid_insufficient_1h_candles"],
                "Insufficient 1h closed candles for BRF v0 rally-failure checks.",
                evidence_payload={
                    "one_hour_count": len(one_hour),
                    "min_needed": self._config.min_candles,
                },
            )
        if len(four_hour) < 2:
            return self._invalid(
                signal_input,
                ["brf_invalid_missing_4h_context"],
                "Missing 4h context for BRF v0 short-side review.",
                evidence_payload={"four_hour_count": len(four_hour)},
            )

        evidence = self._evaluate_structure(one_hour=one_hour, four_hour=four_hour)
        if evidence["htf_context"] == "strong_uptrend":
            return self._no_action(
                signal_input,
                ["brf_no_action_htf_uptrend_conflict"],
                "4h context is a strong uptrend; BRF v0 short review stays observe-only/no-action.",
                evidence,
            )
        if not evidence["rally_extension_confirmed"]:
            return self._no_action(
                signal_input,
                ["brf_no_action_no_rally_extension"],
                "No sufficient bear-market rally extension for BRF v0.",
                evidence,
            )
        if not evidence["rejection_confirmed"]:
            return self._no_action(
                signal_input,
                ["brf_no_action_no_rejection_close"],
                "Rally extension exists, but the latest closed candle did not reject the rally high.",
                evidence,
            )

        return self._would_enter(
            signal_input,
            [
                "brf_bear_rally_extended",
                "brf_rally_high_rejected",
                "brf_short_squeeze_risk_reviewed",
            ],
            "BRF v0 bear-rally-failure short structure detected for review.",
            evidence,
        )

    def _evaluate_structure(self, *, one_hour: list[_Candle], four_hour: list[_Candle]) -> dict[str, Any]:
        cfg = self._config
        latest = one_hour[-1]
        previous = one_hour[-2]
        lookback = one_hour[-(cfg.rally_lookback_bars + 1) : -1]
        rally_low = min(candle.low for candle in lookback)
        rally_high = max(candle.high for candle in lookback + [latest])
        rally_pct = _pct(rally_high - rally_low, rally_low)
        latest_range = max(latest.high - latest.low, Decimal("0"))
        upper_wick = max(latest.high - max(latest.open, latest.close), Decimal("0"))
        upper_wick_ratio = (
            upper_wick / latest_range if latest_range > Decimal("0") else Decimal("0")
        )
        close_reversal_pct = _pct(latest.high - latest.close, latest.high)
        htf_net_pct = _pct(four_hour[-1].close - four_hour[0].close, four_hour[0].close)
        htf_context = (
            "strong_uptrend"
            if htf_net_pct >= cfg.strong_htf_uptrend_pct
            else "trend_down"
            if htf_net_pct <= Decimal("-1.0")
            else "mixed"
        )
        market_state = "TREND_DOWN" if htf_context == "trend_down" else "UNCERTAIN"
        rally_extension_confirmed = rally_pct >= cfg.min_rally_pct
        rejection_confirmed = (
            upper_wick_ratio >= cfg.min_rejection_upper_wick_ratio
            and close_reversal_pct >= cfg.min_close_reversal_pct
            and latest.close < latest.open
            and latest.close <= previous.close
        )
        squeeze_warning = rally_pct >= cfg.squeeze_extension_warning_pct

        return {
            "market_state": market_state,
            "htf_context": htf_context,
            "entry_pattern": "bear_rally_failure" if rejection_confirmed else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "rally_extension_confirmed": rally_extension_confirmed,
            "rejection_confirmed": rejection_confirmed,
            "price_action_structure": {
                "bear_rally_failure": rejection_confirmed,
                "closed_bar": True,
                "rally_pct": _s(_q(rally_pct)),
                "rejection_upper_wick_ratio": _s(_q(upper_wick_ratio)),
                "close_reversal_pct": _s(_q(close_reversal_pct)),
                "rally_high_reference": _s(rally_high),
                "rally_low_reference": _s(rally_low),
                "latest_close": _s(latest.close),
                "previous_close": _s(previous.close),
                "invalidation_reference": "rally_high_or_atr_reference",
            },
            "short_squeeze_risk": {
                "status": "reviewed",
                "rally_extension_pct": _s(_q(rally_pct)),
                "squeeze_warning": squeeze_warning,
                "squeeze_risk_level": "elevated" if squeeze_warning else "bounded_review",
                "hard_stop_required": True,
                "runtime_confirmation_mode": "runtime_bounded_auto_attempts",
                "owner_confirm_each_entry_required": False,
                "conservative_short_profile_required": True,
                "runtime_profile_confirmation_required": True,
                "reference": "rally_high_or_atr_reference",
            },
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
                notes=["BRF price-action evaluator rejected the input as invalid."],
            ),
            evidence_payload=evidence_payload or {},
            review_required=False,
        )

    def _no_action(
        self,
        signal_input: StrategyFamilySignalInput,
        reason_codes: list[str],
        human_summary: str,
        evidence: dict[str, Any],
    ) -> StrategyFamilySignalOutput:
        return self._output(
            signal_input,
            signal_type=SignalType.NO_ACTION,
            side=SignalSide.NONE,
            confidence=Decimal("0.25"),
            reason_codes=reason_codes,
            human_summary=human_summary,
            data_quality=signal_input.input_quality,
            evidence_payload=evidence,
            review_required=False,
        )

    def _would_enter(
        self,
        signal_input: StrategyFamilySignalInput,
        reason_codes: list[str],
        human_summary: str,
        evidence: dict[str, Any],
    ) -> StrategyFamilySignalOutput:
        semantic_evidence = dict(evidence)
        semantic_evidence["candidate_semantics"] = (
            build_brf_short_candidate_semantics(
                strategy_family_version_id=signal_input.strategy_family_version_id,
                timeframe=signal_input.primary_timeframe,
                evidence=evidence,
            ).model_dump(mode="json")
        )
        return self._output(
            signal_input,
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.SHORT,
            confidence=Decimal("0.64"),
            reason_codes=reason_codes,
            human_summary=human_summary,
            data_quality=signal_input.input_quality,
            evidence_payload=semantic_evidence,
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
            "strategy_family": BRF_FAMILY_ID,
            "logic_version": "brf-001-price-action-v0",
            "context_tags": {
                "market_state": evidence_payload.get("market_state", "UNCERTAIN"),
                "htf_context": evidence_payload.get("htf_context", "unknown"),
                "entry_pattern": evidence_payload.get("entry_pattern", "none"),
                "short_side_reference": True,
            },
        }
        return StrategyFamilySignalOutput(
            signal_id=f"brf-{_stable_suffix(signal_input.evaluation_id)}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=BRF_FAMILY_ID,
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
            expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
            invalidation_conditions=[
                {
                    "condition_type": "close_above_rally_high",
                    "description": "BRF v0 invalidates if closed price reclaims the rally high reference.",
                },
                {
                    "condition_type": "time_stop",
                    "description": "Failure to follow through should remain review evidence, not repeated attempts.",
                },
            ],
            signal_snapshot=signal_snapshot,
            evidence_payload={
                "brf_logic_version": "v0",
                "confidence_notice": "confidence is review sorting only, not win probability or authorization",
                "semantic_role": "short_bear_rally_failure_reference",
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
                    "short_squeeze_excursion",
                    "rally_failure_follow_through",
                    "pain_before_profit",
                    "profit_giveback",
                    "runner_capped_too_early",
                    "invalidation_hit",
                ],
                owner_review_status="historical_review_pending" if review_required else "not_required",
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


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0"):
        return Decimal("0")
    return (numerator / denominator) * Decimal("100")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _s(value: Decimal) -> str:
    return str(value)


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]
