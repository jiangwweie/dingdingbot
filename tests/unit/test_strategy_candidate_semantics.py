from __future__ import annotations

from decimal import Decimal

import pytest

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


def _candidate_semantics() -> StrategyCandidateSemantics:
    return StrategyCandidateSemantics(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        archetype=StrategyArchetype.BEAR_RALLY_FAILURE,
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        feature_snapshots=[
            StrategyFeatureSnapshot(
                feature_set_id="brf-structure-v0",
                timeframe="1h",
                source="unit_test",
                features={
                    "rally_high_reference": "114",
                    "latest_close": "106",
                },
            )
        ],
        entry=EntrySetupProposal(
            kind=EntrySetupKind.RALLY_FAILURE,
            side="short",
            trigger="bear_rally_failure_confirmed",
            entry_price_reference=Decimal("106"),
            trigger_candle_open_time_ms=1781000000000,
        ),
        protection=ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            stop_price_reference=Decimal("114"),
            invalidation_condition="close_above_rally_high",
            buffer_description="stop outside rally high reference",
        ),
        exit=ExitProposal(
            plan_kind=ExitPlanKind.PARTIAL_TP_PLUS_RUNNER,
            payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
            take_profit_targets=[
                TakeProfitTargetProposal(
                    target_id="tp1",
                    target_kind="rr",
                    rr=Decimal("1"),
                    position_fraction=Decimal("0.5"),
                )
            ],
            runner=RunnerProposal(
                enabled=True,
                trail_kind="atr_or_structure",
                trail_reference="runner trails downside follow-through",
                preserve_right_tail=True,
            ),
            time_stop_bars=6,
            invalidation_conditions=["close_above_rally_high"],
        ),
        quality=CandidateQualityScore(
            score=Decimal("0.72"),
            components=[
                CandidateQualityComponent(
                    component_id="structure_clarity",
                    score=Decimal("0.8"),
                    reason="rally high and rejection close are explicit",
                )
            ],
        ),
    )


def test_strategy_candidate_semantics_are_not_execution_authority() -> None:
    candidate = _candidate_semantics()

    assert candidate.not_order is True
    assert candidate.not_execution_intent is True
    assert candidate.not_execution_authority is True
    assert candidate.payoff_profile == StrategyPayoffProfile.RIGHT_TAIL
    assert candidate.exit.runner is not None
    assert candidate.exit.runner.preserve_right_tail is True


def test_strategy_candidate_semantics_reject_forbidden_execution_fields() -> None:
    with pytest.raises(ValueError, match="notional"):
        StrategyFeatureSnapshot(
            feature_set_id="bad",
            timeframe="1h",
            source="unit_test",
            features={"notional": "10"},
        )


def test_mandatory_protection_requires_stop_reference() -> None:
    with pytest.raises(ValueError, match="stop_price_reference"):
        ProtectionProposal(
            reference_kind=ProtectionReferenceKind.STRUCTURE_EXTREME,
            mandatory=True,
            invalidation_condition="missing_stop",
        )

