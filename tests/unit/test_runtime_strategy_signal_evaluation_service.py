from __future__ import annotations

from decimal import Decimal
from typing import Any

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


def _signal_input(
    *,
    family_id: str = "BRF-001",
    version_id: str = "BRF-001-v0",
    one_hour: list[dict[str, Any]] | None = None,
    four_hour: list[dict[str, Any]] | None = None,
) -> StrategyFamilySignalInput:
    windows: dict[str, list[dict[str, Any]]] = {}
    if one_hour is not None:
        windows["1h"] = one_hour
    if four_hour is not None:
        windows["4h"] = four_hour
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-runtime-evaluator-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
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
            timeframe="1h",
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


def test_mpg_momentum_persistence_route_ready_for_semantic_binding():
    result = RuntimeStrategySignalEvaluationService().evaluate(
        _signal_input(
            family_id="MPG-001",
            version_id="MPG-001-v0",
            one_hour=_mpg_long_1h(),
            four_hour=_cpm_up_context_4h(),
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
