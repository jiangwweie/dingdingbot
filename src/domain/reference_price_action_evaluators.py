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
TEQ_FAMILY_ID = "TEQ-001"
FBS_FAMILY_ID = "FBS-001"
PMR_FAMILY_ID = "PMR-001"
SOR_FAMILY_ID = "SOR-001"


@dataclass(frozen=True)
class ReferencePriceActionConfig:
    min_candles: int = 14
    lookback_bars: int = 10
    min_pullback_pct: Decimal = Decimal("1.0")
    boundary_band_pct: Decimal = Decimal("0.35")
    compression_window: int = 6
    compression_ratio: Decimal = Decimal("0.60")
    volume_expansion_ratio: Decimal = Decimal("1.20")


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
            trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
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
    logic_version = "btpc-001-price-action-v1"

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
        strong_uptrend = htf_net_pct >= Decimal("1.0")
        structure_loss = latest.close < previous.low and latest.close < latest.open
        entry_states = {
            "bear_trend_context": trend_down,
            "weak_rally_or_pullback_depth": pullback_pct >= self._config.min_pullback_pct,
            "pullback_structure_loss": structure_loss,
            "regime_trend_down_state": trend_down,
        }
        disable_states = {
            "strong_uptrend_disable_state": strong_uptrend,
            "short_squeeze_disable_state": False,
            "stale_signal": signal_input.freshness != "fresh",
        }
        evidence = {
            "market_state": "TREND_DOWN" if trend_down else "UNCERTAIN",
            "htf_context": "trend_down" if trend_down else "mixed",
            "entry_pattern": "bear_trend_pullback_continuation" if structure_loss else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "classifier_revision": {
                "status": "local_classifier_revision_executed",
                "target_classifier": "btpc_strong_uptrend_and_freshness_disable_rule",
                "blocks_l2_promotion": True,
                "not_execution_authority": True,
                "not_l2_promotion_authority": True,
                "not_l4_scope_change": True,
            },
            "entry_states": entry_states,
            "disable_states": disable_states,
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
        if disable_states["stale_signal"]:
            return self._no_action(
                signal_input,
                ["btpc_disable_stale_signal_before_l2_review"],
                "BTPC v1 rejects stale shadow signals before any L2 promotion review.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
            )
        if disable_states["strong_uptrend_disable_state"]:
            return self._no_action(
                signal_input,
                ["btpc_disable_strong_uptrend_conflict"],
                "BTPC v1 disables short continuation review during strong-uptrend conflict.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
            )
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
    logic_version = "lsr-001-price-action-v1"

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
        short_revival_confirmed = swept_high
        sweep_extreme = latest.high if short_revival_confirmed else latest.low
        disable_states = {
            "current_broader_preview_side_long_conflicts_with_short_revival_lead": swept_low,
            "range_context_missing": False,
            "sweep_reclaim_missing": not short_revival_confirmed,
            "stale_signal": signal_input.freshness != "fresh",
        }
        entry_states = {
            "upper_range_liquidity_sweep_detected": swept_high,
            "reclaim_failure_or_rejection_confirmed": (
                latest.close < range_high and latest.close < latest.open
            ),
            "short_revival_confirmation_present": short_revival_confirmed,
            "lookahead_proxy_absent": True,
        }
        evidence = {
            "market_state": "RANGE",
            "entry_pattern": (
                "side_specific_short_revival"
                if short_revival_confirmed
                else "none"
            ),
            "latest_1h_open_time_ms": latest.open_time_ms,
            "classifier_revision": {
                "status": "local_classifier_revision_executed",
                "target_classifier": "side_specific_short_revival_classifier",
                "blocks_l2_promotion": True,
                "not_execution_authority": True,
                "not_l2_promotion_authority": True,
                "not_l4_scope_change": True,
            },
            "range_structure": {
                "range_high_reference": _s(range_high),
                "range_low_reference": _s(range_low),
                "range_mid_reference": _s(range_mid),
            },
            "price_action_structure": {
                "liquidity_sweep_reversal": short_revival_confirmed,
                "sweep_direction": "up" if short_revival_confirmed else "none",
                "sweep_extreme_reference": _s(sweep_extreme),
                "range_mid_reference": _s(range_mid),
                "latest_close": _s(latest.close),
            },
            "entry_states": entry_states,
            "disable_states": disable_states,
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
        if swept_low:
            return self._no_action(
                signal_input,
                ["lsr_disable_long_preview_conflicts_with_short_revival_lead"],
                "LSR v1 disables the old long sweep preview until the short-revival rewrite passes review.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        if not short_revival_confirmed:
            return self._no_action(
                signal_input,
                ["lsr_no_action_short_revival_not_confirmed"],
                "LSR v1 did not confirm a side-specific upper-range short revival.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        evidence["candidate_semantics"] = build_lsr_candidate_semantics(
            strategy_family_version_id=signal_input.strategy_family_version_id,
            timeframe=signal_input.primary_timeframe,
            side=SignalSide.SHORT.value,
            evidence=evidence,
        ).model_dump(mode="json")
        return self._would_enter(
            signal_input,
            side=SignalSide.SHORT,
            confidence=Decimal("0.61"),
            reason_codes=[
                "lsr_upper_range_liquidity_sweep_detected",
                "lsr_short_revival_confirmation_present",
                "lsr_lookahead_proxy_absent",
            ],
            human_summary="LSR v1 side-specific short revival detected for review.",
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
    logic_version = "vcb-001-price-action-v1"

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
        compression_avg_volume = _avg_volume(compression_window)
        compression_confirmed = (
            prior_avg_range > Decimal("0")
            and recent_avg_range <= prior_avg_range * cfg.compression_ratio
        )
        volume_expansion_confirmed = (
            compression_avg_volume > Decimal("0")
            and latest.volume >= compression_avg_volume * cfg.volume_expansion_ratio
        )
        wick_breakout_up = compression_confirmed and latest.high > compression_high
        wick_breakout_down = compression_confirmed and latest.low < compression_low
        false_breakout_reversal_detected = (
            (wick_breakout_up and latest.close <= compression_high)
            or (wick_breakout_down and latest.close >= compression_low)
        )
        breakout_up = (
            compression_confirmed
            and volume_expansion_confirmed
            and latest.close > compression_high
            and latest.close > latest.open
        )
        breakout_down = (
            compression_confirmed
            and volume_expansion_confirmed
            and latest.close < compression_low
            and latest.close < latest.open
        )
        side = SignalSide.LONG if breakout_up else SignalSide.SHORT if breakout_down else SignalSide.NONE
        stop_reference = compression_low if side == SignalSide.LONG else compression_high
        breakout_boundary = compression_high if side == SignalSide.LONG else compression_low
        entry_states = {
            "compression_window_present": compression_confirmed,
            "breakout_close_confirmed": side != SignalSide.NONE,
            "volume_expansion_confirmed": volume_expansion_confirmed,
            "post_entry_edge_proxy_reproducible_without_lookahead": side != SignalSide.NONE
            and not false_breakout_reversal_detected,
        }
        disable_states = {
            "false_breakout_reversal_detected": false_breakout_reversal_detected,
            "compression_context_missing": not compression_confirmed,
            "slot_m2m_ruin_state_triggered": False,
            "stale_signal": signal_input.freshness != "fresh",
        }
        evidence = {
            "market_state": "UNCERTAIN",
            "entry_pattern": "volatility_compression_breakout" if side != SignalSide.NONE else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "classifier_revision": {
                "status": "local_classifier_revision_executed",
                "target_classifier": "true_breakout_pre_entry_classifier",
                "blocks_l2_promotion": True,
                "not_execution_authority": True,
                "not_l2_promotion_authority": True,
                "not_l4_scope_change": True,
            },
            "volatility_state": {
                "compression_confirmed": compression_confirmed,
                "recent_avg_range": _s(_q(recent_avg_range)),
                "prior_avg_range": _s(_q(prior_avg_range)),
                "compression_range_pct": _s(_q(_pct(compression_range, compression_low))),
                "compression_avg_volume": _s(_q(compression_avg_volume)),
                "latest_volume": _s(_q(latest.volume)),
                "volume_expansion_confirmed": volume_expansion_confirmed,
            },
            "price_action_structure": {
                "volatility_compression_breakout": side != SignalSide.NONE,
                "breakout_direction": side.value,
                "breakout_boundary_reference": _s(breakout_boundary),
                "compression_opposite_boundary_reference": _s(stop_reference),
                "compression_range_pct": _s(_q(_pct(compression_range, compression_low))),
                "latest_close": _s(latest.close),
            },
            "entry_states": entry_states,
            "disable_states": disable_states,
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
        if false_breakout_reversal_detected:
            return self._no_action(
                signal_input,
                ["vcb_disable_false_breakout_reversal_detected"],
                "VCB v1 disables wick-only compression breakouts before L2 review.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
            )
        if compression_confirmed and not volume_expansion_confirmed:
            return self._no_action(
                signal_input,
                ["vcb_no_action_volume_expansion_missing"],
                "VCB v1 requires volume expansion before true-breakout review.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
            )
        if side == SignalSide.NONE:
            return self._no_action(
                signal_input,
                ["vcb_no_action_no_compression_breakout"],
                "VCB v1 did not confirm volatility compression breakout.",
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
            reason_codes=[
                "vcb_compression_window_present",
                "vcb_breakout_close_confirmed",
                "vcb_volume_expansion_confirmed",
                "vcb_post_entry_edge_proxy_without_lookahead",
            ],
            human_summary="VCB v1 true compression breakout detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
        )


class TEQ001PilotReferenceEvaluator(_ReferencePriceActionEvaluator):
    family_id = TEQ_FAMILY_ID
    logic_version = "teq-001-pilot-reference-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        latest = one_hour[-1]
        lookback = one_hour[-(self._config.lookback_bars + 1) : -1]
        previous_high = max(candle.high for candle in lookback)
        one_hour_net_pct = _pct(latest.close - lookback[0].close, lookback[0].close)
        four_hour_net_pct = _pct(four_hour[-1].close - four_hour[0].close, four_hour[0].close)
        breakout = latest.close > previous_high and latest.close > latest.open
        theme_momentum = (
            breakout
            and one_hour_net_pct >= Decimal("1.2")
            and four_hour_net_pct >= Decimal("0.6")
        )
        evidence = {
            "market_state": "TREND_UP" if four_hour_net_pct >= Decimal("0.6") else "UNCERTAIN",
            "entry_pattern": "equity_like_momentum_breakout" if breakout else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "price_action_structure": {
                "theme_momentum": theme_momentum,
                "latest_close": _s(latest.close),
                "previous_high": _s(previous_high),
                "one_hour_net_pct": _s(_q(one_hour_net_pct)),
                "four_hour_net_pct": _s(_q(four_hour_net_pct)),
                "breakout_close": breakout,
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_back_below_breakout_reference",
                    "description": "TEQ invalidates if price closes back below the breakout reference.",
                },
                {
                    "condition_type": "post_burst_overextension",
                    "description": "Post-burst extension or concentration warnings should downshift the candidate.",
                },
            ],
        }
        if not theme_momentum:
            return self._no_action(
                signal_input,
                ["teq_no_action_theme_momentum_not_confirmed"],
                "TEQ-001 v0 did not confirm equity-like long momentum.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
            )
        return self._would_enter(
            signal_input,
            side=SignalSide.LONG,
            confidence=Decimal("0.62"),
            reason_codes=[
                "teq_theme_momentum_state",
                "teq_breakout_close_confirmed",
                "teq_htf_context_positive",
            ],
            human_summary="TEQ-001 v0 equity-like long momentum detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
        )


class FBS001PilotReferenceEvaluator(_ReferencePriceActionEvaluator):
    family_id = FBS_FAMILY_ID
    logic_version = "fbs-001-pilot-reference-v0"

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
        funding_rate = signal_input.market_snapshot.funding_rate
        one_hour_net_pct = _pct(latest.close - lookback[0].close, lookback[0].close)
        negative_funding = (
            funding_rate is not None and funding_rate <= Decimal("-0.0002")
        )
        squeeze_followthrough = latest.close > latest.open and one_hour_net_pct >= Decimal("0.5")
        confirmed = negative_funding and squeeze_followthrough
        evidence = {
            "market_state": "FUNDING_STRESS" if negative_funding else "UNCERTAIN",
            "entry_pattern": "negative_funding_squeeze_followthrough" if confirmed else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "funding_state": {
                "funding_rate": str(funding_rate) if funding_rate is not None else None,
                "negative_funding": negative_funding,
            },
            "price_action_structure": {
                "squeeze_followthrough": squeeze_followthrough,
                "one_hour_net_pct": _s(_q(one_hour_net_pct)),
                "latest_close": _s(latest.close),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "funding_stress_disappears",
                    "description": "FBS invalidates if negative funding stress disappears before candidate preparation.",
                },
                {
                    "condition_type": "mark_deviation_spike",
                    "description": "Abnormal mark deviation should block armed observation.",
                },
            ],
        }
        if funding_rate is None:
            return self._no_action(
                signal_input,
                ["fbs_no_action_funding_rate_missing"],
                "FBS-001 v0 requires funding facts before funding-stress observation.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        if not confirmed:
            return self._no_action(
                signal_input,
                ["fbs_no_action_funding_stress_not_confirmed"],
                "FBS-001 v0 did not confirm negative-funding squeeze follow-through.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.UNKNOWN,
            )
        return self._would_enter(
            signal_input,
            side=SignalSide.LONG,
            confidence=Decimal("0.60"),
            reason_codes=[
                "fbs_negative_funding_stress",
                "fbs_squeeze_followthrough_confirmed",
            ],
            human_summary="FBS-001 v0 negative-funding long squeeze detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.UNKNOWN,
        )


class PMR001PilotReferenceEvaluator(_ReferencePriceActionEvaluator):
    family_id = PMR_FAMILY_ID
    logic_version = "pmr-001-pilot-reference-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        latest = one_hour[-1]
        lookback = one_hour[-(self._config.lookback_bars + 1) : -1]
        previous_low = min(candle.low for candle in lookback)
        one_hour_net_pct = _pct(latest.close - lookback[0].close, lookback[0].close)
        four_hour_net_pct = _pct(four_hour[-1].close - four_hour[0].close, four_hour[0].close)
        breakdown = latest.close < previous_low and latest.close < latest.open
        metal_breakdown = (
            breakdown
            and one_hour_net_pct <= Decimal("-0.8")
            and four_hour_net_pct <= Decimal("-0.4")
        )
        evidence = {
            "market_state": "TREND_DOWN" if four_hour_net_pct <= Decimal("-0.4") else "UNCERTAIN",
            "entry_pattern": "metal_role_breakdown_short" if breakdown else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "price_action_structure": {
                "metal_breakdown": metal_breakdown,
                "latest_close": _s(latest.close),
                "previous_low": _s(previous_low),
                "one_hour_net_pct": _s(_q(one_hour_net_pct)),
                "four_hour_net_pct": _s(_q(four_hour_net_pct)),
                "breakdown_close": breakdown,
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_back_above_breakdown_reference",
                    "description": "PMR invalidates if price closes back above the breakdown reference.",
                },
                {
                    "condition_type": "role_conflict",
                    "description": "Mixed metal role or session context should keep PMR observe-only.",
                },
            ],
        }
        if not metal_breakdown:
            return self._no_action(
                signal_input,
                ["pmr_no_action_metal_breakdown_not_confirmed"],
                "PMR-001 v0 did not confirm precious-metal short breakdown.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
            )
        return self._would_enter(
            signal_input,
            side=SignalSide.SHORT,
            confidence=Decimal("0.59"),
            reason_codes=[
                "pmr_metal_breakdown_state",
                "pmr_short_followthrough_confirmed",
            ],
            human_summary="PMR-001 v0 precious-metal short breakdown detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
        )


class SOR001PilotReferenceEvaluator(_ReferencePriceActionEvaluator):
    family_id = SOR_FAMILY_ID
    logic_version = "sor-001-pilot-reference-v0"

    def _evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        one_hour: list[_Candle],
        four_hour: list[_Candle],
    ) -> StrategyFamilySignalOutput:
        del four_hour
        latest = one_hour[-1]
        opening_range = one_hour[-5:-1]
        range_high = max(candle.high for candle in opening_range)
        range_low = min(candle.low for candle in opening_range)
        short_break = latest.close < range_low and latest.close < latest.open
        evidence = {
            "market_state": "SESSION_BREAKOUT" if short_break else "UNCERTAIN",
            "entry_pattern": "session_opening_range_breakdown" if short_break else "none",
            "latest_1h_open_time_ms": latest.open_time_ms,
            "session_structure": {
                "range_high_reference": _s(range_high),
                "range_low_reference": _s(range_low),
                "reference_window_bars": len(opening_range),
            },
            "price_action_structure": {
                "session_opening_range_breakdown": short_break,
                "latest_close": _s(latest.close),
                "range_low_reference": _s(range_low),
            },
            "invalidation_conditions": [
                {
                    "condition_type": "close_back_inside_opening_range",
                    "description": "SOR invalidates if price closes back inside the opening range.",
                },
                {
                    "condition_type": "session_mapping_missing",
                    "description": "Missing session mapping blocks candidate preparation.",
                },
            ],
        }
        if not short_break:
            return self._no_action(
                signal_input,
                ["sor_no_action_session_breakout_not_confirmed"],
                "SOR-001 v0 did not confirm a session opening-range breakdown.",
                evidence,
                expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
            )
        return self._would_enter(
            signal_input,
            side=SignalSide.SHORT,
            confidence=Decimal("0.58"),
            reason_codes=[
                "sor_opening_range_breakdown",
                "sor_closed_trigger_confirmed",
            ],
            human_summary="SOR-001 v0 session opening-range short breakdown detected for review.",
            evidence_payload=evidence,
            expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
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


def _avg_volume(candles: list[_Candle]) -> Decimal:
    if not candles:
        return Decimal("0")
    return sum((candle.volume for candle in candles), Decimal("0")) / Decimal(
        len(candles)
    )


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _s(value: Decimal) -> str:
    return str(value.normalize())


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]
