from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.strategy_evaluation_context_builder import (
    build_strategy_evaluation_context,
)
from src.domain.reference_price_action_evaluators import (
    BTPC001PriceActionEvaluator,
    LSR001PriceActionEvaluator,
    RBR001PriceActionEvaluator,
    VCB001PriceActionEvaluator,
)
from src.domain.strategy_candidate_semantics import (
    ExitPlanKind,
    StrategyArchetype,
    StrategyCandidateSemantics,
    StrategyPayoffProfile,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    FORBIDDEN_EXECUTION_FIELDS,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.domain.strategy_semantics import (
    StrategyFactCheckStatus,
    initial_strategy_semantics_catalog,
)


NOW_MS = 1781000000000


def _candle(
    index: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    *,
    volume: str = "100",
) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (30 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _down_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _mixed_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "100", "103", "98", "101"),
        _candle(1, "101", "104", "99", "102"),
        _candle(2, "102", "105", "100", "101"),
        _candle(3, "101", "104", "99", "102"),
    ]


def _up_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "100", "102", "99", "100"),
        _candle(1, "100", "104", "99", "102"),
        _candle(2, "102", "106", "101", "104"),
        _candle(3, "104", "109", "103", "108"),
    ]


def _btpc_1h() -> list[dict[str, Any]]:
    return [
        _candle(0, "110", "111", "108", "109"),
        _candle(1, "109", "110", "107", "108"),
        _candle(2, "108", "109", "106", "107"),
        _candle(3, "107", "108", "105", "106"),
        _candle(4, "106", "107", "104", "105"),
        _candle(5, "105", "106", "103", "104"),
        _candle(6, "104", "105", "102", "103"),
        _candle(7, "103", "104", "101", "102"),
        _candle(8, "102", "104", "100", "103"),
        _candle(9, "103", "105", "101", "104"),
        _candle(10, "104", "106", "102", "105"),
        _candle(11, "105", "106", "100", "101"),
        _candle(12, "101", "102", "99", "100"),
        _candle(13, "100", "101", "95", "96"),
    ]


def _lsr_long_1h() -> list[dict[str, Any]]:
    candles = [
        _candle(index, "104", "110", "100", "105")
        for index in range(13)
    ]
    candles.append(_candle(13, "101", "106", "98", "103"))
    return candles


def _lsr_short_revival_1h() -> list[dict[str, Any]]:
    candles = [
        _candle(index, "104", "110", "100", "105")
        for index in range(13)
    ]
    candles.append(_candle(13, "109", "112", "104", "108"))
    return candles


def _rbr_short_1h() -> list[dict[str, Any]]:
    candles = [
        _candle(index, "105", "110", "100", "106")
        for index in range(13)
    ]
    candles.append(_candle(13, "109", "110.2", "106", "108"))
    return candles


def _vcb_long_1h() -> list[dict[str, Any]]:
    return [
        _candle(0, "100", "103", "99", "102"),
        _candle(1, "101", "105", "99", "103"),
        _candle(2, "102", "106", "100", "104"),
        _candle(3, "103", "107", "101", "105"),
        _candle(4, "104", "108", "102", "106"),
        _candle(5, "105", "109", "103", "107"),
        _candle(6, "106", "110", "104", "108"),
        _candle(7, "107.0", "107.8", "106.8", "107.2"),
        _candle(8, "107.2", "108.0", "107.0", "107.4"),
        _candle(9, "107.4", "108.2", "107.2", "107.6"),
        _candle(10, "107.6", "108.4", "107.4", "107.8"),
        _candle(11, "107.8", "108.5", "107.5", "108.0"),
        _candle(12, "108.0", "108.6", "107.6", "108.2"),
        _candle(13, "108.4", "111", "108.2", "110", volume="180"),
    ]


def _vcb_false_breakout_1h() -> list[dict[str, Any]]:
    candles = _vcb_long_1h()
    candles[-1] = _candle(13, "108.4", "111", "107.9", "108.3", volume="180")
    return candles


def _vcb_missing_volume_expansion_1h() -> list[dict[str, Any]]:
    candles = _vcb_long_1h()
    candles[-1] = _candle(13, "108.4", "111", "108.2", "110", volume="100")
    return candles


def _signal_input(
    *,
    family_id: str,
    version_id: str,
    one_hour: list[dict[str, Any]],
    four_hour: list[dict[str, Any]],
    freshness: str = "fresh",
) -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id=f"eval-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS,
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
            candle_context={
                "windows": {"1h": one_hour, "4h": four_hour},
                "closed_bar": True,
            },
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
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "10",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
        },
        source="unit_test",
        freshness=freshness,
    )


def _runtime(family_id: str, version_id: str, side: str) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=f"runtime-{family_id}",
        trial_binding_id=f"trial-{family_id}",
        admission_decision_id=f"admission-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("30"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


@pytest.mark.parametrize(
    (
        "family_id",
        "version_id",
        "evaluator",
        "one_hour",
        "four_hour",
        "expected_side",
        "expected_archetype",
        "expected_payoff",
        "expected_exit",
    ),
    [
        (
            "BTPC-001",
            "BTPC-001-v0",
            BTPC001PriceActionEvaluator(),
            _btpc_1h(),
            _down_context_4h(),
            SignalSide.SHORT,
            StrategyArchetype.BEAR_TREND_PULLBACK_CONTINUATION,
            StrategyPayoffProfile.RIGHT_TAIL,
            ExitPlanKind.PARTIAL_TP_PLUS_RUNNER,
        ),
        (
            "LSR-001",
            "LSR-001-v0",
            LSR001PriceActionEvaluator(),
            _lsr_short_revival_1h(),
            _mixed_context_4h(),
            SignalSide.SHORT,
            StrategyArchetype.LIQUIDITY_SWEEP_REVERSAL,
            StrategyPayoffProfile.MEAN_REVERSION,
            ExitPlanKind.FIXED_RR_OR_RANGE_TARGETS,
        ),
        (
            "RBR-001",
            "RBR-001-v0",
            RBR001PriceActionEvaluator(),
            _rbr_short_1h(),
            _mixed_context_4h(),
            SignalSide.SHORT,
            StrategyArchetype.RANGE_BOUNDARY_REVERSION,
            StrategyPayoffProfile.MEAN_REVERSION,
            ExitPlanKind.FIXED_RR_OR_RANGE_TARGETS,
        ),
        (
            "VCB-001",
            "VCB-001-v0",
            VCB001PriceActionEvaluator(),
            _vcb_long_1h(),
            _mixed_context_4h(),
            SignalSide.LONG,
            StrategyArchetype.VOLATILITY_COMPRESSION_BREAKOUT,
            StrategyPayoffProfile.RIGHT_TAIL,
            ExitPlanKind.PARTIAL_TP_PLUS_RUNNER,
        ),
    ],
)
def test_reference_price_action_evaluator_candidate_semantics_and_fact_check(
    family_id,
    version_id,
    evaluator,
    one_hour,
    four_hour,
    expected_side,
    expected_archetype,
    expected_payoff,
    expected_exit,
):
    signal_input = _signal_input(
        family_id=family_id,
        version_id=version_id,
        one_hour=one_hour,
        four_hour=four_hour,
    )

    output = evaluator.evaluate(signal_input)

    assert output.signal_type == SignalType.WOULD_ENTER
    assert output.side == expected_side
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert not _contains_forbidden_key(output.model_dump(mode="json"))

    semantics = StrategyCandidateSemantics.model_validate(
        output.evidence_payload["candidate_semantics"]
    )
    assert semantics.archetype == expected_archetype
    assert semantics.payoff_profile == expected_payoff
    assert semantics.entry.side == expected_side.value
    assert semantics.protection.stop_price_reference is not None
    assert semantics.exit.plan_kind == expected_exit

    context = build_strategy_evaluation_context(
        signal_input,
        output=output,
        runtime=_runtime(family_id, version_id, expected_side.value),
    )
    binding = initial_strategy_semantics_catalog().get_binding(
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
    )
    assert binding.fact_check(context).status == StrategyFactCheckStatus.PASS

    route = RuntimeStrategySignalEvaluationService().evaluate(signal_input)
    assert route.status == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    assert route.can_call_semantic_binding is True
    assert route.output is not None
    assert route.output.signal_type == SignalType.WOULD_ENTER
    assert route.order_candidate_created is False
    assert route.execution_intent_created is False
    assert route.exchange_called is False


def test_btpc001_revision_disables_strong_uptrend_and_stale_signal() -> None:
    strong_uptrend_input = _signal_input(
        family_id="BTPC-001",
        version_id="BTPC-001-v0",
        one_hour=_btpc_1h(),
        four_hour=_up_context_4h(),
    )
    stale_input = _signal_input(
        family_id="BTPC-001",
        version_id="BTPC-001-v0",
        one_hour=_btpc_1h(),
        four_hour=_down_context_4h(),
        freshness="stale",
    )

    strong_uptrend = BTPC001PriceActionEvaluator().evaluate(strong_uptrend_input)
    stale = BTPC001PriceActionEvaluator().evaluate(stale_input)

    assert strong_uptrend.signal_type == SignalType.NO_ACTION
    assert strong_uptrend.reason_codes == ["btpc_disable_strong_uptrend_conflict"]
    assert strong_uptrend.evidence_payload["logic_version"] == (
        "btpc-001-price-action-v1"
    )
    assert strong_uptrend.evidence_payload["classifier_revision"] == {
        "status": "local_classifier_revision_executed",
        "target_classifier": "btpc_strong_uptrend_and_freshness_disable_rule",
        "blocks_l2_promotion": True,
        "not_execution_authority": True,
        "not_l2_promotion_authority": True,
        "not_l4_scope_change": True,
    }
    assert strong_uptrend.evidence_payload["disable_states"][
        "strong_uptrend_disable_state"
    ] is True
    assert strong_uptrend.evidence_payload["disable_states"]["stale_signal"] is False
    assert strong_uptrend.not_order is True
    assert strong_uptrend.not_execution_intent is True

    assert stale.signal_type == SignalType.NO_ACTION
    assert stale.reason_codes == ["btpc_disable_stale_signal_before_l2_review"]
    assert stale.evidence_payload["logic_version"] == "btpc-001-price-action-v1"
    assert stale.evidence_payload["disable_states"]["stale_signal"] is True
    assert stale.evidence_payload["entry_states"]["pullback_structure_loss"] is True
    assert stale.not_order is True
    assert stale.not_execution_intent is True
    assert not _contains_forbidden_key(strong_uptrend.model_dump(mode="json"))
    assert not _contains_forbidden_key(stale.model_dump(mode="json"))


def test_lsr001_revision_disables_old_long_preview_conflict() -> None:
    signal_input = _signal_input(
        family_id="LSR-001",
        version_id="LSR-001-v0",
        one_hour=_lsr_long_1h(),
        four_hour=_mixed_context_4h(),
    )

    output = LSR001PriceActionEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.NO_ACTION
    assert output.side == SignalSide.NONE
    assert output.reason_codes == [
        "lsr_disable_long_preview_conflicts_with_short_revival_lead"
    ]
    assert output.evidence_payload["logic_version"] == "lsr-001-price-action-v1"
    assert output.evidence_payload["classifier_revision"] == {
        "status": "local_classifier_revision_executed",
        "target_classifier": "side_specific_short_revival_classifier",
        "blocks_l2_promotion": True,
        "not_execution_authority": True,
        "not_l2_promotion_authority": True,
        "not_l4_scope_change": True,
    }
    assert output.evidence_payload["disable_states"][
        "current_broader_preview_side_long_conflicts_with_short_revival_lead"
    ] is True
    assert output.evidence_payload["entry_states"][
        "short_revival_confirmation_present"
    ] is False
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert not _contains_forbidden_key(output.model_dump(mode="json"))


def test_vcb001_revision_disables_false_breakout_and_requires_volume() -> None:
    false_breakout_input = _signal_input(
        family_id="VCB-001",
        version_id="VCB-001-v0",
        one_hour=_vcb_false_breakout_1h(),
        four_hour=_mixed_context_4h(),
    )
    missing_volume_input = _signal_input(
        family_id="VCB-001",
        version_id="VCB-001-v0",
        one_hour=_vcb_missing_volume_expansion_1h(),
        four_hour=_mixed_context_4h(),
    )

    false_breakout = VCB001PriceActionEvaluator().evaluate(false_breakout_input)
    missing_volume = VCB001PriceActionEvaluator().evaluate(missing_volume_input)

    assert false_breakout.signal_type == SignalType.NO_ACTION
    assert false_breakout.reason_codes == [
        "vcb_disable_false_breakout_reversal_detected"
    ]
    assert false_breakout.evidence_payload["logic_version"] == (
        "vcb-001-price-action-v1"
    )
    assert false_breakout.evidence_payload["classifier_revision"] == {
        "status": "local_classifier_revision_executed",
        "target_classifier": "true_breakout_pre_entry_classifier",
        "blocks_l2_promotion": True,
        "not_execution_authority": True,
        "not_l2_promotion_authority": True,
        "not_l4_scope_change": True,
    }
    assert false_breakout.evidence_payload["disable_states"][
        "false_breakout_reversal_detected"
    ] is True
    assert false_breakout.not_order is True
    assert false_breakout.not_execution_intent is True

    assert missing_volume.signal_type == SignalType.NO_ACTION
    assert missing_volume.reason_codes == ["vcb_no_action_volume_expansion_missing"]
    assert missing_volume.evidence_payload["entry_states"][
        "compression_window_present"
    ] is True
    assert missing_volume.evidence_payload["entry_states"][
        "volume_expansion_confirmed"
    ] is False
    assert missing_volume.evidence_payload["disable_states"][
        "false_breakout_reversal_detected"
    ] is False
    assert not _contains_forbidden_key(false_breakout.model_dump(mode="json"))
    assert not _contains_forbidden_key(missing_volume.model_dump(mode="json"))


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).strip().lower() in FORBIDDEN_EXECUTION_FIELDS
            or _contains_forbidden_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False
