"""Builders for strategy candidate semantic snapshots.

These helpers keep strategy-specific entry/protection/exit semantics near the
strategy evaluators while preserving the boundary that they are not executable
order instructions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.domain.strategy_candidate_semantics import (
    CandidateQualityComponent,
    CandidateQualityScore,
    EntrySetupKind,
    EntrySetupProposal,
    ExitPlanKind,
    ExitProposal,
    ProtectionProposal,
    ProtectionReferenceKind,
    RunnerProposal,
    StrategyArchetype,
    StrategyCandidateSemantics,
    StrategyFeatureSnapshot,
    StrategyPayoffProfile,
    TakeProfitTargetProposal,
)


def build_cpm_long_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    latest_close = _decimal_from_evidence(evidence, "latest_1h_close")
    stop_reference = _decimal_from_evidence(evidence, "lookback_low")
    trigger_open_time_ms = _optional_int(evidence.get("latest_1h_open_time_ms"))
    quality = _quality_score(
        structure=Decimal("0.80") if evidence.get("long_reclaim_confirmed") else Decimal("0.35"),
        context=Decimal("0.75") if evidence.get("htf_trend") == "up" else Decimal("0.40"),
        protection=Decimal("0.70") if stop_reference is not None else Decimal("0.20"),
        labels={
            "structure_clarity": "pullback depth and reclaim close are explicit",
            "context_alignment": "4h trend supports long continuation",
            "protection_clarity": "lookback low can anchor a hard stop",
        },
    )
    return StrategyCandidateSemantics(
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.LONG_PULLBACK_CONTINUATION,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="cpm-long-pullback-reclaim-v0",
                timeframe=timeframe,
                source="cpm_historical_evaluator",
                features={
                    "htf_trend": evidence.get("htf_trend"),
                    "primary_trend": evidence.get("primary_trend"),
                    "pullback_depth_pct": evidence.get("pullback_depth_pct"),
                    "lookback_high": evidence.get("lookback_high"),
                    "lookback_low": evidence.get("lookback_low"),
                    "latest_1h_close": evidence.get("latest_1h_close"),
                    "previous_1h_high": evidence.get("previous_1h_high"),
                    "long_reclaim_confirmed": evidence.get("long_reclaim_confirmed"),
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.PULLBACK_RECLAIM,
            side="long",
            trigger="cpm_long_pullback_reclaim_confirmed",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=trigger_open_time_ms,
            valid_timeframe=timeframe,
            evidence={
                "entry_pattern": evidence.get("entry_pattern"),
                "previous_1h_high": evidence.get("previous_1h_high"),
                "sma20_1h": evidence.get("sma20_1h"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            stop_price_reference=stop_reference,
            invalidation_condition="close_below_pullback_low_or_failed_reclaim",
            buffer_description="hard stop anchored beyond pullback low reference",
            evidence={"lookback_low": evidence.get("lookback_low")},
        ),
        exit=_right_tail_exit(
            invalidation_condition="close_below_pullback_low_or_failed_reclaim",
            runner_note="runner trails continuation after TP1 so rare trend wins are not capped early",
        ),
        quality=quality,
    )


def build_brf_short_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    squeeze = dict(evidence.get("short_squeeze_risk") or {})
    latest_close = _decimal(structure.get("latest_close"))
    stop_reference = _decimal(structure.get("rally_high_reference"))
    trigger_open_time_ms = _optional_int(evidence.get("latest_1h_open_time_ms"))
    quality = _quality_score(
        structure=Decimal("0.80") if structure.get("bear_rally_failure") else Decimal("0.35"),
        context=Decimal("0.70") if evidence.get("market_state") == "TREND_DOWN" else Decimal("0.50"),
        protection=Decimal("0.75") if stop_reference is not None else Decimal("0.20"),
        labels={
            "structure_clarity": "rally high and rejection close are explicit",
            "context_alignment": "4h context is not strong uptrend conflict",
            "protection_clarity": "rally high can anchor a mandatory hard stop",
        },
        warnings=[
            "short_side_conservative_profile_required"
            if squeeze.get("conservative_short_profile_required")
            else ""
        ],
    )
    return StrategyCandidateSemantics(
        strategy_family_id="BRF-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.BEAR_RALLY_FAILURE,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="brf-bear-rally-failure-v0",
                timeframe=timeframe,
                source="brf_price_action_evaluator",
                features={
                    "market_state": evidence.get("market_state"),
                    "htf_context": evidence.get("htf_context"),
                    "entry_pattern": evidence.get("entry_pattern"),
                    "price_action_structure": structure,
                    "short_squeeze_risk": squeeze,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.RALLY_FAILURE,
            side="short",
            trigger="brf_bear_rally_failure_confirmed",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=trigger_open_time_ms,
            valid_timeframe=timeframe,
            evidence={
                "rally_high_reference": structure.get("rally_high_reference"),
                "close_reversal_pct": structure.get("close_reversal_pct"),
                "rejection_upper_wick_ratio": structure.get("rejection_upper_wick_ratio"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            stop_price_reference=stop_reference,
            invalidation_condition="close_above_rally_high",
            buffer_description="hard stop anchored beyond rejected rally high reference",
            evidence={
                "rally_high_reference": structure.get("rally_high_reference"),
                "squeeze_risk_level": squeeze.get("squeeze_risk_level"),
            },
        ),
        exit=_right_tail_exit(
            invalidation_condition="close_above_rally_high",
            runner_note="downside runner trails bear-market follow-through after TP1",
        ),
        quality=quality,
    )


def _right_tail_exit(
    *,
    invalidation_condition: str,
    runner_note: str,
) -> ExitProposal:
    return ExitProposal(
        plan_kind=ExitPlanKind.PARTIAL_TP_PLUS_RUNNER,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        take_profit_targets=[
            TakeProfitTargetProposal(
                target_id="tp1",
                target_kind="rr",
                rr=Decimal("1"),
                position_fraction=Decimal("0.5"),
                notes=["realize partial profit without closing the right-tail path"],
            )
        ],
        runner=RunnerProposal(
            enabled=True,
            trail_kind="structure_or_atr",
            trail_reference="trail after TP1 using structure invalidation or ATR-backed stop",
            preserve_right_tail=True,
        ),
        time_stop_bars=12,
        invalidation_conditions=[invalidation_condition],
        notes=[runner_note],
    )


def _quality_score(
    *,
    structure: Decimal,
    context: Decimal,
    protection: Decimal,
    labels: dict[str, str],
    warnings: list[str] | None = None,
) -> CandidateQualityScore:
    score = ((structure + context + protection) / Decimal("3")).quantize(Decimal("0.0001"))
    return CandidateQualityScore(
        score=score,
        components=[
            CandidateQualityComponent(
                component_id="structure_clarity",
                score=structure,
                reason=labels["structure_clarity"],
            ),
            CandidateQualityComponent(
                component_id="context_alignment",
                score=context,
                reason=labels["context_alignment"],
            ),
            CandidateQualityComponent(
                component_id="protection_clarity",
                score=protection,
                reason=labels["protection_clarity"],
            ),
        ],
        warnings=[warning for warning in warnings or [] if warning],
    )


def _decimal_from_evidence(evidence: dict[str, Any], key: str) -> Decimal | None:
    return _decimal(evidence.get(key))


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    decimal = Decimal(str(value))
    if abs(decimal.as_tuple().exponent) > 8:
        decimal = decimal.quantize(Decimal("0.00000001"))
    return decimal.normalize()


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
