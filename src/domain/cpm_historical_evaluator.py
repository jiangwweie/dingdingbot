"""CPM-RO-001 historical evaluator.

The evaluator is pure and deterministic. It accepts StrategyFamilySignalInput
and returns StrategyFamilySignalOutput for historical review only. It does not
write databases, create trial-trade-intent evidence, authorize execution, size
risk, route orders, or call live APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1
from typing import Any

from src.domain.strategy_candidate_semantics_builders import (
    build_cpm_long_candidate_semantics,
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


CPM_FAMILY_ID = "CPM-RO-001"


@dataclass(frozen=True)
class CPMHistoricalEvaluatorConfig:
    sma_window: int = 20
    pullback_lookback_bars: int = 20
    min_pullback_pct: Decimal = Decimal("0.5")
    max_pullback_pct: Decimal = Decimal("8.0")


@dataclass(frozen=True)
class _Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class CPMRO001HistoricalEvaluator:
    """Minimal pullback-continuation evaluator for historical replay."""

    def __init__(self, config: CPMHistoricalEvaluatorConfig | None = None) -> None:
        self._config = config or CPMHistoricalEvaluatorConfig()

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != CPM_FAMILY_ID:
            return self._invalid(signal_input, ["cpm_invalid_wrong_family"], "Input is not for CPM-RO-001.")

        windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
        one_hour = _parse_candles(windows.get("1h") or windows.get(signal_input.primary_timeframe) or [])
        four_hour = _parse_candles(windows.get("4h") or [])
        if not one_hour:
            return self._invalid(signal_input, ["cpm_invalid_missing_1h_context"], "Missing 1h candle context.")
        if not four_hour:
            return self._invalid(signal_input, ["cpm_invalid_missing_4h_context"], "Missing 4h candle context.")
        min_needed = self._config.sma_window + 1
        if len(one_hour) < min_needed or len(four_hour) < min_needed:
            return self._invalid(
                signal_input,
                ["cpm_invalid_insufficient_candles"],
                "Insufficient candles for CPM v0 SMA20 and pullback checks.",
                evidence_payload={
                    "one_hour_count": len(one_hour),
                    "four_hour_count": len(four_hour),
                    "min_needed": min_needed,
                },
            )

        evidence = self._evaluate_structure(one_hour=one_hour, four_hour=four_hour)
        if evidence["htf_trend"] == "up":
            if not evidence["long_pullback_depth_normal"]:
                return self._no_action(
                    signal_input,
                    ["cpm_no_action_no_pullback", "cpm_long_htf_trend_intact"],
                    "4h uptrend is present, but 1h pullback depth is outside CPM v0 bounds.",
                    evidence,
                )
            if evidence["long_reclaim_confirmed"]:
                return self._would_enter(
                    signal_input,
                    SignalSide.LONG,
                    [
                        "cpm_long_htf_trend_intact",
                        "cpm_long_pullback_depth_normal",
                        "cpm_long_reclaim_confirmed",
                    ],
                    "CPM v0 long pullback-reclaim structure detected.",
                    evidence,
                )
            return self._no_action(
                signal_input,
                ["cpm_no_action_no_reclaim", "cpm_long_htf_trend_intact"],
                "4h uptrend and normal pullback are present, but 1h reclaim is not confirmed.",
                evidence,
            )

        if evidence["htf_trend"] == "down":
            if not evidence["short_bounce_depth_normal"]:
                return self._no_action(
                    signal_input,
                    ["cpm_no_action_no_pullback", "cpm_short_htf_trend_intact"],
                    "4h downtrend is present, but 1h bounce depth is outside CPM v0 bounds.",
                    evidence,
                )
            if evidence["short_loss_confirmed"]:
                return self._would_enter(
                    signal_input,
                    SignalSide.SHORT,
                    [
                        "cpm_short_htf_trend_intact",
                        "cpm_short_bounce_depth_normal",
                        "cpm_short_loss_confirmed",
                    ],
                    "CPM v0 short bounce-loss structure detected.",
                    evidence,
                )
            return self._no_action(
                signal_input,
                ["cpm_no_action_no_reclaim", "cpm_short_htf_trend_intact"],
                "4h downtrend and normal bounce are present, but 1h structure loss is not confirmed.",
                evidence,
            )

        return self._no_action(
            signal_input,
            ["cpm_no_action_trend_ambiguous"],
            "4h trend is ambiguous under CPM v0.",
            evidence,
        )

    def _evaluate_structure(self, *, one_hour: list[_Candle], four_hour: list[_Candle]) -> dict[str, Any]:
        cfg = self._config
        latest_1h = one_hour[-1]
        previous_1h = one_hour[-2]
        latest_4h = four_hour[-1]
        previous_4h = four_hour[-2]
        sma20_1h = _sma([candle.close for candle in one_hour[-cfg.sma_window :]])
        sma20_4h = _sma([candle.close for candle in four_hour[-cfg.sma_window :]])

        htf_trend = "neutral"
        if latest_4h.close > sma20_4h and latest_4h.close >= previous_4h.close:
            htf_trend = "up"
        elif latest_4h.close < sma20_4h and latest_4h.close <= previous_4h.close:
            htf_trend = "down"

        lookback = one_hour[-(cfg.pullback_lookback_bars + 1) : -1]
        lookback_high = max(candle.high for candle in lookback)
        lookback_low = min(candle.low for candle in lookback)
        pullback_depth_pct = ((lookback_high - lookback_low) / lookback_high) * Decimal("100")
        bounce_depth_pct = ((lookback_high - lookback_low) / lookback_low) * Decimal("100")
        normal_pullback = cfg.min_pullback_pct <= pullback_depth_pct <= cfg.max_pullback_pct
        normal_bounce = cfg.min_pullback_pct <= bounce_depth_pct <= cfg.max_pullback_pct
        long_reclaim = latest_1h.close > sma20_1h and latest_1h.close > previous_1h.high
        short_loss = latest_1h.close < sma20_1h and latest_1h.close < previous_1h.low

        return {
            "regime": "trend" if htf_trend in {"up", "down"} else "transition",
            "trend_alignment": "aligned" if htf_trend in {"up", "down"} else "unknown",
            "entry_pattern": (
                "pullback_reclaim"
                if long_reclaim
                else "bounce_loss"
                if short_loss
                else "none"
            ),
            "htf_trend": htf_trend,
            "primary_trend": "up" if latest_1h.close > sma20_1h else "down" if latest_1h.close < sma20_1h else "neutral",
            "pullback_depth_pct": str(pullback_depth_pct.quantize(Decimal("0.0001"))),
            "bounce_depth_pct": str(bounce_depth_pct.quantize(Decimal("0.0001"))),
            "lookback_high": str(lookback_high),
            "lookback_low": str(lookback_low),
            "sma20_1h": str(sma20_1h),
            "sma20_4h": str(sma20_4h),
            "latest_1h_open_time_ms": latest_1h.open_time_ms,
            "latest_1h_close": str(latest_1h.close),
            "previous_1h_high": str(previous_1h.high),
            "previous_1h_low": str(previous_1h.low),
            "latest_4h_close": str(latest_4h.close),
            "long_pullback_depth_normal": normal_pullback,
            "short_bounce_depth_normal": normal_bounce,
            "long_reclaim_confirmed": long_reclaim,
            "short_loss_confirmed": short_loss,
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
                warnings=list(signal_input.input_quality.warnings),
                notes=["CPM historical evaluator rejected the input as invalid."],
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
        side: SignalSide,
        reason_codes: list[str],
        human_summary: str,
        evidence: dict[str, Any],
    ) -> StrategyFamilySignalOutput:
        semantic_evidence = dict(evidence)
        if side == SignalSide.LONG:
            semantic_evidence["candidate_semantics"] = (
                build_cpm_long_candidate_semantics(
                    strategy_family_version_id=signal_input.strategy_family_version_id,
                    timeframe=signal_input.primary_timeframe,
                    evidence=evidence,
                ).model_dump(mode="json")
            )
        return self._output(
            signal_input,
            signal_type=SignalType.WOULD_ENTER,
            side=side,
            confidence=Decimal("0.70"),
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
            "strategy_family": CPM_FAMILY_ID,
            "logic_version": "cpm-ro-001-historical-v0",
            "context_tags": {
                "regime": evidence_payload.get("regime", "unknown"),
                "trend_alignment": evidence_payload.get("trend_alignment", "unknown"),
                "entry_pattern": evidence_payload.get("entry_pattern", "none"),
                "htf_trend": evidence_payload.get("htf_trend", "unknown"),
                "primary_trend": evidence_payload.get("primary_trend", "unknown"),
            },
        }
        return StrategyFamilySignalOutput(
            signal_id=f"cpm-{_stable_suffix(signal_input.evaluation_id)}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=CPM_FAMILY_ID,
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
            expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
            invalidation_conditions=[
                {"condition_type": "structure_break", "description": "CPM structure invalidates on failed reclaim/loss."},
                {"condition_type": "time_stop", "description": "Review windows are historical evidence only."},
            ],
            signal_snapshot=signal_snapshot,
            evidence_payload={
                "cpm_logic_version": "v0",
                "confidence_notice": "confidence is review sorting only, not win probability or authorization",
                **evidence_payload,
            },
            input_refs=SignalInputRefs(
                market_snapshot_ref=f"historical_ohlcv:{signal_input.symbol}:{signal_input.timestamp_ms}",
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
                    "time_to_MFE",
                    "time_to_MAE",
                    "pain_before_profit",
                    "profit_giveback",
                    "follow_through",
                    "invalidation_hit",
                    "return_time_curve",
                ],
                owner_review_status="historical_review_pending" if review_required else "not_required",
            ),
            not_order=True,
            not_execution_intent=True,
        )


def _parse_candles(raw_candles: list[dict[str, Any]]) -> list[_Candle]:
    candles: list[_Candle] = []
    for raw in raw_candles:
        candles.append(
            _Candle(
                open_time_ms=int(raw["open_time_ms"]),
                open=Decimal(str(raw["open"])),
                high=Decimal(str(raw["high"])),
                low=Decimal(str(raw["low"])),
                close=Decimal(str(raw["close"])),
                volume=Decimal(str(raw.get("volume", "0"))),
            )
        )
    return candles


def _sma(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]
