from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade
from src.domain.comparative_strength import (
    ComparativeStrengthMember,
    ComparativeStrengthSnapshot,
)
from src.domain.strategy_candidate_semantics import (
    StrategyArchetype,
    StrategyCandidateSemantics,
)


NOW_MS = 1781000000000


def _candle(index: int, open_: str, high: str, low: str, close: str) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (20 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": "100",
    }


def _bear_rally_failure_1h() -> list[dict[str, Any]]:
    return [
        _candle(0, "101", "102", "99", "100"),
        _candle(1, "100", "103", "99", "102"),
        _candle(2, "102", "105", "101", "104"),
        _candle(3, "104", "106", "103", "105"),
        _candle(4, "105", "108", "104", "107"),
        _candle(5, "107", "109", "106", "108"),
        _candle(6, "108", "110", "107", "109"),
        _candle(7, "109", "111", "108", "110"),
        _candle(8, "110", "112", "109", "111"),
        _candle(9, "111", "113", "110", "112"),
        _candle(10, "112", "113", "109", "111"),
        _candle(11, "111", "114", "105", "106"),
    ]


def _down_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _cpm_long_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(20):
        close = Decimal("100") + Decimal(index) * Decimal("0.2")
        candles.append(
            _candle(
                index,
                str(close),
                str(close + Decimal("0.2")),
                str(close - Decimal("0.2")),
                str(close),
            )
        )
    candles.append(_candle(20, "103.5", "105.2", "102", "105"))
    return candles


def _cpm_up_context_4h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(21):
        close = Decimal("100") + Decimal(index) * Decimal("0.3")
        candles.append(
            _candle(
                index,
                str(close),
                str(close + Decimal("0.2")),
                str(close - Decimal("0.2")),
                str(close),
            )
        )
    return candles


def _mpg_long_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(16):
        close = Decimal("100") + Decimal(index) * Decimal("0.35")
        candles.append(
            _candle(
                index,
                str(close),
                str(close + Decimal("0.3")),
                str(close - Decimal("0.3")),
                str(close),
            )
        )
    candles.append(_candle(16, "105.4", "107.2", "105", "107"))
    return candles


def _mpg_flat_1h() -> list[dict[str, Any]]:
    return [
        _candle(index, "100", "101", "99", "100")
        for index in range(17)
    ]


def _mi_impulse_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(14):
        close = Decimal("100") + Decimal(index) * Decimal("0.45")
        candles.append(
            _candle(
                index,
                str(close),
                str(close + Decimal("0.4")),
                str(close - Decimal("0.3")),
                str(close),
            )
        )
    return candles


def _signal_input(
    *,
    family_id: str = "BRF-001",
    version_id: str = "BRF-001-v0",
    one_hour: list[dict[str, Any]] | None = None,
    four_hour: list[dict[str, Any]] | None = None,
    comparative_strength_snapshot: ComparativeStrengthSnapshot | None = None,
    primary_timeframe: str = "1h",
) -> StrategyFamilySignalInput:
    windows: dict[str, list[dict[str, Any]]] = {}
    if one_hour is not None:
        windows[primary_timeframe] = one_hour
    if four_hour is not None:
        windows["4h"] = four_hour
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-runtime-evaluator-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
        primary_timeframe=primary_timeframe,
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="unit_market_read_only",
            freshness="fresh",
            last_price=Decimal("106"),
            mark_price=Decimal("106"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.18"),
            atr=Decimal("4"),
            timeframe=primary_timeframe,
            candle_context={"windows": windows, "closed_bar": True},
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="unit_account_read_only",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="normal",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "clean"},
            read_only_provider="unit_test_read_only",
            limitations=[],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "shadow", "live_ready": False},
        source="unit_test",
        freshness="fresh",
        comparative_strength_snapshot=comparative_strength_snapshot,
    )


def _sor_session_15m(*, side: str) -> list[dict[str, Any]]:
    opening = [
        _candle(0, "100", "101", "99", "100"),
        _candle(1, "100", "102", "99", "101"),
        _candle(2, "101", "102", "98", "100"),
        _candle(3, "100", "101", "98", "100"),
    ]
    if side == "long":
        return opening + [_candle(4, "101", "104", "100", "103")]
    return opening + [_candle(4, "99", "100", "96", "97")]


def _comparative_snapshot(
    *,
    candidate_rank: int = 1,
    candidate_return_pct: str = "8",
) -> ComparativeStrengthSnapshot:
    peer_rank = 2 if candidate_rank == 1 else 1
    return ComparativeStrengthSnapshot(
        strategy_group_id="MPG-001",
        timeframe="1h",
        lookback_bars=8,
        trigger_candle_close_time_ms=NOW_MS,
        universe_symbols=("ETHUSDT", "SOLUSDT"),
        members=(
            ComparativeStrengthMember(
                symbol="ETHUSDT",
                start_close=Decimal("100"),
                end_close=Decimal("108"),
                return_pct=Decimal(candidate_return_pct),
                rank=candidate_rank,
            ),
            ComparativeStrengthMember(
                symbol="SOLUSDT",
                start_close=Decimal("100"),
                end_close=Decimal("106"),
                return_pct=Decimal("6"),
                rank=peer_rank,
            ),
        ),
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 3_600_000,
        source_ref="pg:strategy_comparative:unit",
    )


def _mi_comparative_snapshot(
    *,
    candidate_rank: int = 1,
    candidate_return_pct: Decimal | None = None,
) -> ComparativeStrengthSnapshot:
    candles = _mi_impulse_1h()
    start = Decimal(str(candles[-13]["close"]))
    end = Decimal(str(candles[-1]["close"]))
    actual_return = ((end - start) / start) * Decimal("100")
    candidate_return = (
        actual_return
        if candidate_return_pct is None
        else candidate_return_pct
    )
    return ComparativeStrengthSnapshot(
        strategy_group_id="MI-001",
        timeframe="1h",
        lookback_bars=12,
        trigger_candle_close_time_ms=NOW_MS,
        universe_symbols=("ETHUSDT", "SOLUSDT"),
        members=(
            ComparativeStrengthMember(
                symbol="ETHUSDT",
                start_close=start,
                end_close=end,
                return_pct=candidate_return,
                rank=candidate_rank,
            ),
            ComparativeStrengthMember(
                symbol="SOLUSDT",
                start_close=Decimal("100"),
                end_close=Decimal("102"),
                return_pct=Decimal("2"),
                rank=2 if candidate_rank == 1 else 1,
            ),
        ),
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 3_600_000,
        source_ref="pg:strategy_comparative:mi-unit",
    )


class _FakeShortEvaluator:
    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        return StrategyFamilySignalOutput(
            signal_id=f"fake-short-{signal_input.evaluation_id}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.SHORT,
            confidence=Decimal("0.6"),
            reason_codes=["unit_fake_short"],
            human_summary="Fake short output for semantic side gate.",
            required_execution_mode="observe_only",
            evidence_payload={"unit": "semantic_side_gate"},
        )


def test_brf_evaluator_route_ready_for_semantic_binding():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            one_hour=_bear_rally_failure_1h(),
            four_hour=_down_context_4h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert result.blockers == []
    assert result.can_call_semantic_binding is True
    assert result.output is not None
    assert result.output.signal_type == SignalType.WOULD_ENTER
    assert result.output.side == SignalSide.SHORT
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert (
        result.output.evidence_payload["short_squeeze_risk"][
            "runtime_confirmation_mode"
        ]
        == "runtime_bounded_auto_attempts"
    )
    assert (
        result.output.evidence_payload["short_squeeze_risk"][
            "owner_confirm_each_entry_required"
        ]
        is False
    )
    assert result.signal_evaluation_created is False
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False


def test_cpm_short_output_blocks_before_semantic_binding():
    result = RuntimeStrategySignalEvaluationService(
        evaluators={
            ("CPM-RO-001", "CPM-RO-001-v0"): _FakeShortEvaluator(),
        }
    ).evaluate(
        _signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert "strategy_output_side_not_supported_by_semantics" in result.blockers
    assert result.can_call_semantic_binding is False
    assert result.output is not None
    assert result.output.side == SignalSide.SHORT
    assert result.strategy_candidate_mode == "shadow_order_candidate_allowed"
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.exchange_called is False


def test_cpm_live_reference_route_ready_for_semantic_binding():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="CPM-001",
            version_id="CPM-001-v0",
            one_hour=_cpm_long_1h(),
            four_hour=_cpm_up_context_4h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert result.blockers == []
    assert result.evaluator_called is True
    assert result.evaluator_id == "_CPM001LiveReferenceEvaluator"
    assert result.output is not None
    assert result.output.strategy_family_id == "CPM-001"
    assert result.output.strategy_family_version_id == "CPM-001-v0"
    assert result.output.signal_type == SignalType.WOULD_ENTER
    assert result.output.side == SignalSide.LONG
    assert (
        result.output.evidence_payload["candidate_semantics"]["strategy_family_id"]
        == "CPM-001"
    )
    assert (
        result.output.evidence_payload["candidate_semantics"][
            "strategy_family_version_id"
        ]
        == "CPM-001-v0"
    )
    assert result.can_call_semantic_binding is True
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.exchange_called is False


def test_cpm_ro_long_emits_trial_grade_observed_facts():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            one_hour=_cpm_long_1h(),
            four_hour=_cpm_up_context_4h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert result.output is not None
    assert result.output.signal_type == SignalType.WOULD_ENTER
    assert result.output.side == SignalSide.LONG
    assert result.output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert result.output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    facts = {
        item.fact_key: item.observed_value
        for item in result.output.fact_observations
    }
    assert facts["htf_trend_intact"] is True
    assert facts["reclaim_confirmed"] is True
    assert Decimal(str(facts["pullback_low_reference"])) > 0


def test_mpg_momentum_persistence_route_ready_for_semantic_binding():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
            comparative_strength_snapshot=_comparative_snapshot(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert result.blockers == []
    assert result.evaluator_called is True
    assert result.evaluator_id == "MPG001MomentumPersistenceEvaluator"
    assert result.can_call_semantic_binding is True
    assert result.output is not None
    assert result.output.signal_type == SignalType.WOULD_ENTER
    assert result.output.side == SignalSide.LONG
    assert result.output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert result.output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    observed_facts = {
        item.fact_key: item.observed_value
        for item in result.output.fact_observations
    }
    assert observed_facts["momentum_persistence_confirmed"] is True
    assert observed_facts["leader_strength_confirmed"] is True
    assert Decimal(str(observed_facts["momentum_floor_reference"])) > 0
    semantics = StrategyCandidateSemantics.model_validate(
        result.output.evidence_payload["candidate_semantics"]
    )
    assert semantics.strategy_family_id == "MPG-001"
    assert semantics.strategy_family_version_id == "MPG-001-v0"
    assert semantics.archetype == StrategyArchetype.MOMENTUM_PERSISTENCE
    assert semantics.not_order is True
    assert semantics.not_execution_intent is True
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False
    assert result.order_created is False
    assert result.order_lifecycle_called is False
    assert result.exchange_called is False


def test_mpg_missing_comparative_snapshot_is_invalid_engineering_input():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.output is not None
    assert result.output.signal_type == SignalType.INVALID
    assert "mpg_invalid_comparative_strength_missing" in result.output.reason_codes
    assert result.output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL
    assert result.output.required_execution_mode == RequiredExecutionMode.OBSERVE_ONLY


def test_mpg_computed_non_leader_is_market_no_action_not_missing_input():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
            comparative_strength_snapshot=_comparative_snapshot(candidate_rank=2),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
    assert result.output is not None
    assert result.output.signal_type == SignalType.NO_ACTION
    assert "mpg_no_action_leader_strength_not_confirmed" in result.output.reason_codes
    assert result.output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL


def test_mpg_rank_one_with_non_positive_return_is_market_no_action():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
            comparative_strength_snapshot=_comparative_snapshot(
                candidate_rank=1,
                candidate_return_pct="0",
            ),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
    assert result.output is not None
    assert result.output.signal_type == SignalType.NO_ACTION
    assert "mpg_no_action_leader_return_not_positive" in result.output.reason_codes
    assert result.output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL


def test_mpg_momentum_persistence_no_action_stays_observe_only():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_flat_1h(),
            four_hour=_cpm_up_context_4h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
    assert "strategy_signal_not_would_enter" in result.blockers
    assert result.output is not None
    assert result.output.signal_type == SignalType.NO_ACTION
    assert result.output.side == SignalSide.NONE
    assert result.can_call_semantic_binding is False
    assert result.order_candidate_created is False
    assert result.exchange_called is False


def test_strategygroup_pilot_reference_routes_are_configured_and_non_executing():
    service = RuntimeStrategySignalEvaluationService()

    for family_id, version_id in [
        ("TEQ-001", "TEQ-001-v0"),
        ("FBS-001", "FBS-001-v0"),
        ("PMR-001", "PMR-001-v0"),
        ("SOR-001", "SOR-001-v0"),
    ]:
        assert service.route_configured(
            strategy_family_id=family_id,
            strategy_family_version_id=version_id,
        )
        result = service.evaluate(
            _signal_input(family_id=family_id, version_id=version_id)
        )

        assert result.semantics_binding_found is True
        assert result.evaluator_called is True
        assert result.order_candidate_created is False
        assert result.execution_intent_created is False
        assert result.order_created is False
        assert result.order_lifecycle_called is False
        assert result.exchange_called is False


@pytest.mark.parametrize(
    ("side", "event_fact", "protection_fact"),
    [
        ("long", "breakout_confirmed", "opening_range_low_reference"),
        ("short", "breakdown_confirmed", "opening_range_high_reference"),
    ],
)
def test_sor_runtime_evaluator_emits_side_specific_trial_event_facts(
    side,
    event_fact,
    protection_fact,
):
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="SOR-001",
            version_id="SOR-001-v0",
            one_hour=_sor_session_15m(side=side),
            four_hour=None,
            primary_timeframe="15m",
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert result.blockers == []
    assert result.output is not None
    assert result.output.signal_type == SignalType.WOULD_ENTER
    assert result.output.side.value == side
    assert result.output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert result.output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    facts = {item.fact_key: item.observed_value for item in result.output.fact_observations}
    assert facts["opening_range_defined"] is True
    assert facts[event_fact] is True
    assert Decimal(str(facts[protection_fact])) > 0


def test_mainline_mi_and_brf2_routes_are_configured_and_non_executing():
    service = RuntimeStrategySignalEvaluationService()

    mi = service.evaluate(
        _signal_input(
            family_id="MI-001",
            version_id="MI-001-v0",
            one_hour=_mi_impulse_1h(),
            comparative_strength_snapshot=_mi_comparative_snapshot(),
        )
    )
    brf2 = service.evaluate(
        _signal_input(
            family_id="BRF2-001",
            version_id="BRF2-001-v0",
            one_hour=_bear_rally_failure_1h(),
            four_hour=_down_context_4h(),
        )
    )

    assert mi.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert mi.blockers == []
    assert mi.evaluator_called is True
    assert mi.evaluator_id == "_MI001RuntimeReferenceEvaluator"
    assert mi.output is not None
    assert mi.output.strategy_family_id == "MI-001"
    assert mi.output.strategy_family_version_id == "MI-001-v0"
    assert mi.output.signal_type == SignalType.WOULD_ENTER
    assert mi.output.side == SignalSide.LONG
    assert mi.output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert mi.output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    mi_facts = {
        item.fact_key: item.observed_value
        for item in mi.output.fact_observations
    }
    assert mi_facts["impulse_confirmed"] is True
    assert mi_facts["relative_strength_confirmed"] is True
    assert Decimal(str(mi_facts["impulse_invalidation_reference"])) > 0
    assert mi.order_candidate_created is False
    assert mi.execution_intent_created is False
    assert mi.exchange_called is False

    assert brf2.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert brf2.blockers == []
    assert brf2.evaluator_called is True
    assert brf2.evaluator_id == "_BRF2LiveReferenceEvaluator"
    assert brf2.output is not None
    assert brf2.output.strategy_family_id == "BRF2-001"
    assert brf2.output.strategy_family_version_id == "BRF2-001-v0"
    assert brf2.output.signal_type == SignalType.WOULD_ENTER
    assert brf2.output.side == SignalSide.SHORT
    assert brf2.output.signal_grade == SignalGrade.TRIAL_GRADE_SIGNAL
    assert brf2.output.required_execution_mode == RequiredExecutionMode.TRIAL_LIVE
    assert brf2.output.signal_snapshot["reference_strategy_family"] == "BRF-001"
    brf2_facts = {
        item.fact_key: item.observed_value
        for item in brf2.output.fact_observations
    }
    assert brf2_facts["rally_failure_confirmed"] is True
    assert brf2_facts["short_side_not_disabled"] is True
    assert brf2_facts["strong_uptrend_disable"] is False
    assert Decimal(str(brf2_facts["rally_high_reference"])) > 0
    assert brf2.order_candidate_created is False
    assert brf2.execution_intent_created is False
    assert brf2.exchange_called is False


def test_mi_missing_comparative_snapshot_is_invalid_engineering_input():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MI-001",
            version_id="MI-001-v0",
            one_hour=_mi_impulse_1h(),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.output is not None
    assert result.output.signal_type == SignalType.INVALID
    assert "mi001_invalid_comparative_strength_missing" in result.output.reason_codes
    assert result.output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL


def test_mi_computed_non_leader_is_market_no_action():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MI-001",
            version_id="MI-001-v0",
            one_hour=_mi_impulse_1h(),
            comparative_strength_snapshot=_mi_comparative_snapshot(
                candidate_rank=2
            ),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
    assert result.output is not None
    assert result.output.signal_type == SignalType.NO_ACTION
    assert "mi001_no_action_relative_strength_not_confirmed" in result.output.reason_codes
    assert result.output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL


def test_mi_rejects_comparative_return_mismatch_as_invalid_input():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MI-001",
            version_id="MI-001-v0",
            one_hour=_mi_impulse_1h(),
            comparative_strength_snapshot=_mi_comparative_snapshot(
                candidate_return_pct=Decimal("99")
            ),
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.output is not None
    assert result.output.signal_type == SignalType.INVALID
    assert "mi001_invalid_comparative_return_mismatch" in result.output.reason_codes


def test_rmr_classifier_binding_observe_only_without_evaluator_call():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(family_id="RMR-001", version_id="RMR-001-v0")
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
    assert result.evaluator_called is False
    assert result.output is None
    assert result.strategy_candidate_mode == "regime_classifier_only"
    assert result.runtime_confirmation_mode == "observe_only"
    assert (
        "strategy_candidate_mode_not_runtime_candidate:regime_classifier_only"
        in result.blockers
    )
    assert result.order_candidate_created is False
    assert result.exchange_called is False


def test_data_backlog_binding_blocks_without_evaluator_call():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(family_id="FCO-001", version_id="FCO-001-v0")
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.evaluator_called is False
    assert result.strategy_candidate_mode == "data_backlog_only"
    assert result.runtime_confirmation_mode == "data_backlog_only"
    assert "strategy_candidate_mode_not_runtime_candidate:data_backlog_only" in result.blockers
    assert result.output is None
    assert result.order_candidate_created is False
    assert result.exchange_called is False


def test_cpm_live_reference_short_output_blocks_before_semantic_binding():
    result = RuntimeStrategySignalEvaluationService(
        evaluators={
            ("CPM-001", "CPM-001-v0"): _FakeShortEvaluator(),
        }
    ).evaluate(
        _signal_input(
            family_id="CPM-001",
            version_id="CPM-001-v0",
        )
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.evaluator_called is True
    assert result.semantics_binding_found is True
    assert result.strategy_candidate_mode == "shadow_order_candidate_allowed"
    assert result.runtime_confirmation_mode == "runtime_bounded_auto_attempts"
    assert "strategy_output_side_not_supported_by_semantics" in result.blockers
    assert result.output is not None
    assert result.output.side == SignalSide.SHORT
    assert result.order_candidate_created is False
    assert result.execution_intent_created is False


def test_unknown_strategy_binding_blocks_without_evaluator_call():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(family_id="UNKNOWN-001", version_id="UNKNOWN-001-v0")
    )

    assert result.status == RuntimeStrategySignalEvaluationStatus.BLOCKED
    assert result.evaluator_called is False
    assert result.semantics_binding_found is False
    assert "strategy_semantics_binding_missing" in result.blockers
    assert result.output is None
    assert result.order_candidate_created is False
    assert result.exchange_called is False
