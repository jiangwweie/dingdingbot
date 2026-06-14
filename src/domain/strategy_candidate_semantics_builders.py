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


def build_mpg_long_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    latest_close = _decimal(structure.get("latest_close"))
    stop_reference = _decimal(structure.get("momentum_floor_reference"))
    trigger_open_time_ms = _optional_int(evidence.get("latest_1h_open_time_ms"))
    quality = _quality_score(
        structure=(
            Decimal("0.78")
            if structure.get("momentum_persistence")
            else Decimal("0.35")
        ),
        context=(
            Decimal("0.76")
            if evidence.get("market_state") == "TREND_UP"
            else Decimal("0.45")
        ),
        protection=Decimal("0.70") if stop_reference is not None else Decimal("0.20"),
        labels={
            "structure_clarity": "momentum continuation and recent floor are explicit",
            "context_alignment": "higher-timeframe context supports long momentum",
            "protection_clarity": "recent momentum floor can anchor a hard stop",
        },
        warnings=["reference_semantics_not_alpha_proof"],
    )
    return StrategyCandidateSemantics(
        strategy_family_id="MPG-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.MOMENTUM_PERSISTENCE,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="mpg-momentum-persistence-v0",
                timeframe=timeframe,
                source="mpg_momentum_persistence_evaluator",
                features={
                    "market_state": evidence.get("market_state"),
                    "htf_context": evidence.get("htf_context"),
                    "entry_pattern": evidence.get("entry_pattern"),
                    "momentum_state": evidence.get("momentum_state"),
                    "price_action_structure": structure,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.MOMENTUM_CONTINUATION,
            side="long",
            trigger="mpg_momentum_persistence_confirmed",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=trigger_open_time_ms,
            valid_timeframe=timeframe,
            evidence={
                "latest_close": structure.get("latest_close"),
                "previous_range_high": structure.get("previous_range_high"),
                "consecutive_higher_closes": structure.get(
                    "consecutive_higher_closes"
                ),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            stop_price_reference=stop_reference,
            invalidation_condition="close_below_recent_momentum_floor",
            buffer_description="hard stop anchored below recent momentum floor",
            evidence={
                "momentum_floor_reference": structure.get(
                    "momentum_floor_reference"
                )
            },
        ),
        exit=_right_tail_exit(
            invalidation_condition="close_below_recent_momentum_floor",
            runner_note=(
                "runner trails momentum continuation after TP1 so rare right-tail "
                "moves are not capped early"
            ),
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


def build_btpc_short_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    latest_close = _decimal(structure.get("latest_close"))
    stop_reference = _decimal(structure.get("pullback_high_reference"))
    return StrategyCandidateSemantics(
        strategy_family_id="BTPC-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.BEAR_TREND_PULLBACK_CONTINUATION,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="btpc-bear-trend-pullback-continuation-v0",
                timeframe=timeframe,
                source="reference_price_action_evaluators",
                features={
                    "market_state": evidence.get("market_state"),
                    "htf_context": evidence.get("htf_context"),
                    "price_action_structure": structure,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.TREND_PULLBACK_LOSS,
            side="short",
            trigger="btpc_bear_trend_pullback_loss_confirmed",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=_optional_int(evidence.get("latest_1h_open_time_ms")),
            valid_timeframe=timeframe,
            evidence={
                "pullback_high_reference": structure.get("pullback_high_reference"),
                "latest_close": structure.get("latest_close"),
                "previous_low": structure.get("previous_low"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            stop_price_reference=stop_reference,
            invalidation_condition="close_above_pullback_high",
            buffer_description="hard stop anchored above bear-trend pullback high",
            evidence={"pullback_high_reference": structure.get("pullback_high_reference")},
        ),
        exit=_right_tail_exit(
            invalidation_condition="close_above_pullback_high",
            runner_note="downside runner preserves bear-trend continuation payoff after TP1",
        ),
        quality=_quality_score(
            structure=Decimal("0.78") if structure.get("bear_trend_pullback_continuation") else Decimal("0.35"),
            context=Decimal("0.78") if evidence.get("market_state") == "TREND_DOWN" else Decimal("0.45"),
            protection=Decimal("0.72") if stop_reference is not None else Decimal("0.20"),
            labels={
                "structure_clarity": "pullback high and continuation loss are explicit",
                "context_alignment": "higher-timeframe context supports bear-trend continuation",
                "protection_clarity": "pullback high can anchor a mandatory hard stop",
            },
            warnings=["short_side_conservative_profile_required"],
        ),
    )


def build_lsr_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    side: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    latest_close = _decimal(structure.get("latest_close"))
    sweep_extreme = _decimal(structure.get("sweep_extreme_reference"))
    range_target = _decimal(structure.get("range_mid_reference"))
    return StrategyCandidateSemantics(
        strategy_family_id="LSR-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.LIQUIDITY_SWEEP_REVERSAL,
        payoff_profile=StrategyPayoffProfile.MEAN_REVERSION,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="lsr-liquidity-sweep-reversal-v0",
                timeframe=timeframe,
                source="reference_price_action_evaluators",
                features={
                    "market_state": evidence.get("market_state"),
                    "range_structure": evidence.get("range_structure"),
                    "price_action_structure": structure,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.LIQUIDITY_SWEEP_RECLAIM,
            side=side,  # type: ignore[arg-type]
            trigger=f"lsr_{side}_sweep_reclaim_confirmed",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=_optional_int(evidence.get("latest_1h_open_time_ms")),
            valid_timeframe=timeframe,
            evidence={
                "sweep_extreme_reference": structure.get("sweep_extreme_reference"),
                "range_mid_reference": structure.get("range_mid_reference"),
                "sweep_direction": structure.get("sweep_direction"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.RANGE_BOUNDARY_BUFFER,
            stop_price_reference=sweep_extreme,
            invalidation_condition="close_beyond_sweep_extreme",
            buffer_description="hard stop beyond liquidity sweep extreme",
            evidence={"sweep_extreme_reference": structure.get("sweep_extreme_reference")},
        ),
        exit=_mean_reversion_exit(
            price_reference=range_target,
            invalidation_condition="close_beyond_sweep_extreme",
            note="liquidity sweep reversal exits at fixed RR or range-mid target; no mandatory runner",
        ),
        quality=_quality_score(
            structure=Decimal("0.78") if structure.get("liquidity_sweep_reversal") else Decimal("0.35"),
            context=Decimal("0.68"),
            protection=Decimal("0.72") if sweep_extreme is not None else Decimal("0.20"),
            labels={
                "structure_clarity": "sweep, reclaim, and range midpoint are explicit",
                "context_alignment": "mean-reversion setup does not require trend continuation",
                "protection_clarity": "sweep extreme can anchor a bounded hard stop",
            },
        ),
    )


def build_rbr_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    side: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    boundary_stop = _decimal(structure.get("boundary_stop_reference"))
    target = _decimal(structure.get("opposite_range_target_reference"))
    latest_close = _decimal(structure.get("latest_close"))
    return StrategyCandidateSemantics(
        strategy_family_id="RBR-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.RANGE_BOUNDARY_REVERSION,
        payoff_profile=StrategyPayoffProfile.MEAN_REVERSION,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="rbr-range-boundary-reversion-v0",
                timeframe=timeframe,
                source="reference_price_action_evaluators",
                features={
                    "market_state": evidence.get("market_state"),
                    "range_structure": evidence.get("range_structure"),
                    "volatility_state": evidence.get("volatility_state"),
                    "price_action_structure": structure,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.RANGE_BOUNDARY_REJECTION,
            side=side,  # type: ignore[arg-type]
            trigger=f"rbr_{side}_range_boundary_rejection",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=_optional_int(evidence.get("latest_1h_open_time_ms")),
            valid_timeframe=timeframe,
            evidence={
                "range_boundary": structure.get("range_boundary"),
                "boundary_stop_reference": structure.get("boundary_stop_reference"),
                "opposite_range_target_reference": structure.get("opposite_range_target_reference"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.RANGE_BOUNDARY_BUFFER,
            stop_price_reference=boundary_stop,
            invalidation_condition="close_outside_range_boundary",
            buffer_description="hard stop outside rejected range boundary",
            evidence={"boundary_stop_reference": structure.get("boundary_stop_reference")},
        ),
        exit=_mean_reversion_exit(
            price_reference=target,
            invalidation_condition="close_outside_range_boundary",
            note="range-boundary reversion exits at opposite range or fixed RR target",
        ),
        quality=_quality_score(
            structure=Decimal("0.76") if structure.get("range_boundary_reversion") else Decimal("0.35"),
            context=Decimal("0.78") if evidence.get("market_state") in {"RANGE", "CHOP"} else Decimal("0.45"),
            protection=Decimal("0.72") if boundary_stop is not None else Decimal("0.20"),
            labels={
                "structure_clarity": "range boundary rejection and target boundary are explicit",
                "context_alignment": "range/chop context supports mean reversion",
                "protection_clarity": "range boundary can anchor a bounded hard stop",
            },
        ),
    )


def build_vcb_candidate_semantics(
    *,
    strategy_family_version_id: str,
    timeframe: str,
    side: str,
    evidence: dict[str, Any],
) -> StrategyCandidateSemantics:
    structure = dict(evidence.get("price_action_structure") or {})
    latest_close = _decimal(structure.get("latest_close"))
    stop_reference = _decimal(structure.get("compression_opposite_boundary_reference"))
    return StrategyCandidateSemantics(
        strategy_family_id="VCB-001",
        strategy_family_version_id=strategy_family_version_id,
        archetype=StrategyArchetype.VOLATILITY_COMPRESSION_BREAKOUT,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="vcb-volatility-compression-breakout-v0",
                timeframe=timeframe,
                source="reference_price_action_evaluators",
                features={
                    "market_state": evidence.get("market_state"),
                    "volatility_state": evidence.get("volatility_state"),
                    "price_action_structure": structure,
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.COMPRESSION_BREAKOUT,
            side=side,  # type: ignore[arg-type]
            trigger=f"vcb_{side}_compression_breakout",
            entry_price_reference=latest_close,
            trigger_candle_open_time_ms=_optional_int(evidence.get("latest_1h_open_time_ms")),
            valid_timeframe=timeframe,
            evidence={
                "breakout_boundary_reference": structure.get("breakout_boundary_reference"),
                "compression_range_pct": structure.get("compression_range_pct"),
            },
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.COMPRESSION_BOUNDARY_BUFFER,
            stop_price_reference=stop_reference,
            invalidation_condition="close_back_inside_compression_range",
            buffer_description="hard stop beyond opposite compression boundary",
            evidence={
                "compression_opposite_boundary_reference": structure.get(
                    "compression_opposite_boundary_reference"
                )
            },
        ),
        exit=_right_tail_exit(
            invalidation_condition="close_back_inside_compression_range",
            runner_note="breakout runner preserves rare volatility expansion payoff after TP1",
        ),
        quality=_quality_score(
            structure=Decimal("0.78") if structure.get("volatility_compression_breakout") else Decimal("0.35"),
            context=Decimal("0.70") if evidence.get("volatility_state", {}).get("compression_confirmed") else Decimal("0.45"),
            protection=Decimal("0.70") if stop_reference is not None else Decimal("0.20"),
            labels={
                "structure_clarity": "compression boundary and breakout close are explicit",
                "context_alignment": "volatility compression supports breakout payoff",
                "protection_clarity": "opposite compression boundary can anchor hard stop",
            },
        ),
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


def _mean_reversion_exit(
    *,
    price_reference: Decimal | None,
    invalidation_condition: str,
    note: str,
) -> ExitProposal:
    return ExitProposal(
        plan_kind=ExitPlanKind.FIXED_RR_OR_RANGE_TARGETS,
        payoff_profile=StrategyPayoffProfile.MEAN_REVERSION,
        take_profit_targets=[
            TakeProfitTargetProposal(
                target_id="tp1",
                target_kind="rr",
                rr=Decimal("1"),
                position_fraction=Decimal("0.5"),
                notes=["first fixed-RR realization for bounded mean-reversion attempt"],
            ),
            TakeProfitTargetProposal(
                target_id="range_target",
                target_kind="range_reference",
                price_reference=price_reference,
                position_fraction=Decimal("0.5"),
                notes=["mean-reversion target; no mandatory right-tail runner"],
            ),
        ],
        runner=RunnerProposal(
            enabled=False,
            trail_kind="none",
            preserve_right_tail=False,
        ),
        time_stop_bars=6,
        invalidation_conditions=[invalidation_condition],
        notes=[note],
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
