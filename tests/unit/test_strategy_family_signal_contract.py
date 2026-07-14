from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    ExpectedRiskShape,
    MarketSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    SignalInputRefs,
    SignalReviewPlan,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.execution_eligibility import (
    RequiredExecutionMode,
    SignalGrade,
    resolve_execution_eligibility,
)


def _market_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000000,
        source="exchange_live_market",
        freshness="fresh",
        last_price=Decimal("68000.5"),
        mark_price=Decimal("68001.2"),
        index_price=Decimal("67995.8"),
        bid=Decimal("68000.0"),
        ask=Decimal("68001.0"),
        bid_ask_spread=Decimal("1.0"),
        volume=Decimal("1234.56"),
        quote_volume=Decimal("83950000.00"),
        funding_rate=Decimal("0.0001"),
        next_funding_time_ms=1770003600000,
        volatility=Decimal("0.42"),
        atr=Decimal("950.25"),
        timeframe="4h",
        candle_context={
            "closed_bar": True,
            "open": "67000",
            "high": "68400",
            "low": "66850",
            "close": "68000",
        },
        source_latency_ms=250,
        missing_fields=[],
    )


def _account_facts_snapshot() -> AccountFactsSnapshot:
    return AccountFactsSnapshot(
        source="exchange_live",
        truth_level="exchange_read",
        timestamp_ms=1770000000100,
        freshness="fresh",
        account_status="normal",
        available_balance=Decimal("1000.25"),
        positions=[{"symbol": "BTC/USDT:USDT", "side": "none", "status": "flat"}],
        open_orders=[],
        position_count=0,
        open_order_count=0,
        unknown_unmanaged_counts={"orders": 0, "positions": 0},
        reconciliation_status={"status": "clean"},
        read_only_provider="exchange_gateway_read_only_snapshot_provider",
        limitations=[],
    )


def _signal_input() -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id="eval-001",
        strategy_family_id="tf",
        strategy_family_version_id="tf-v1",
        playbook_id="TF-001",
        campaign_id="brc-campaign-001",
        binding_id="bind-001",
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000200,
        trigger_candle_close_time_ms=1770000000200,
        primary_timeframe="4h",
        context_timeframes=["1d", "1h"],
        market_snapshot=_market_snapshot(),
        account_facts_snapshot=_account_facts_snapshot(),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "observe", "live_ready": False},
        execution_permission_resolution={
            "requested_permission": "intent_recording",
            "final_permission": "intent_recording",
            "downgrade_reason": None,
        },
        trial_constraints_snapshot={
            "max_loss_budget": "10",
            "max_attempts": 1,
            "allowed_symbols": ["BTC/USDT:USDT"],
        },
        playbook_snapshot={"playbook_id": "TF-001", "version": "readonly-v0"},
        strategy_family_metadata={"family_key": "trend_following", "status": "intake"},
        source="unit_test",
        freshness="fresh",
        input_quality=SignalDataQuality(status=SignalDataQualityStatus.OK),
    )


def _input_refs() -> SignalInputRefs:
    return SignalInputRefs(
        market_snapshot_ref="market:eval-001",
        account_facts_snapshot_ref="account:eval-001",
        permission_resolution_ref="permission:eval-001",
        trial_constraints_snapshot_ref="constraints:eval-001",
        playbook_snapshot_ref="playbook:TF-001",
        runtime_safety_snapshot_ref="runtime:eval-001",
        evaluation_ref="eval-001",
    )


def test_can_construct_valid_strategy_family_signal_input():
    signal_input = _signal_input()

    assert signal_input.contract_version == "brc-strategy-family-signal-v1"
    assert signal_input.market_snapshot.mark_price == Decimal("68001.2")
    assert signal_input.account_facts_snapshot.source == "exchange_live"
    assert signal_input.execution_permission_resolution["final_permission"] == "intent_recording"
    assert signal_input.runtime_safety_snapshot["live_ready"] is False


def test_can_construct_no_action_signal_output():
    output = StrategyFamilySignalOutput(
        signal_id="sig-no-action-001",
        evaluation_id="eval-001",
        strategy_family_id="tf",
        strategy_family_version_id="tf-v1",
        playbook_id="TF-001",
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000300,
        timeframe="4h",
        signal_type=SignalType.NO_ACTION,
        side=SignalSide.NONE,
        confidence=Decimal("0.99"),
        reason_codes=["trend_context_absent"],
        human_summary="No actionable read-only signal.",
        input_refs=_input_refs(),
        review_plan=SignalReviewPlan(review_required=False, owner_review_status="not_required"),
    )

    assert output.signal_type == SignalType.NO_ACTION
    assert output.side == SignalSide.NONE
    assert output.not_order is True
    assert output.not_execution_intent is True


def test_can_construct_would_enter_signal_output():
    output = StrategyFamilySignalOutput(
        signal_id="sig-enter-001",
        evaluation_id="eval-001",
        strategy_family_id="tf",
        strategy_family_version_id="tf-v1",
        playbook_id="TF-001",
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000400,
        trigger_candle_close_time_ms=1770000000400,
        timeframe="4h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.72"),
        reason_codes=["trend_follow_through", "atr_context_available"],
        human_summary="Trend-following family would enter long for review evidence.",
        required_execution_mode="observe_only",
        expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
        invalidation_conditions=[
            {"kind": "structure_break", "description": "Close back under breakout range"}
        ],
        signal_snapshot={"trigger": "closed_bar_context", "timeframe": "4h"},
        evidence_payload={"review_only": True, "contract": "strategy_family_signal"},
        input_refs=_input_refs(),
        data_quality=SignalDataQuality(status=SignalDataQualityStatus.OK),
        review_plan=SignalReviewPlan(
            review_required=True,
            review_windows=["4h", "24h", "72h", "7d"],
            forward_outcome_metrics=["MFE", "MAE", "invalidation_hit", "follow_through"],
            owner_review_status="pending",
        ),
    )

    assert output.signal_type == SignalType.WOULD_ENTER
    assert output.side == SignalSide.LONG
    assert output.reason_codes == ["trend_follow_through", "atr_context_available"]
    assert output.input_refs.evaluation_ref == "eval-001"
    assert output.time_authority == "trigger_candle_close_time_ms"
    assert output.trigger_candle_close_time_ms == 1770000000400
    assert output.model_dump(mode="json")["trigger_candle_close_time_ms"] == 1770000000400
    assert output.review_plan.review_required is True
    assert output.not_order is True
    assert output.not_execution_intent is True


def test_signal_output_accepts_typed_fact_observations():
    output = StrategyFamilySignalOutput(
        signal_id="sig-facts-001",
        evaluation_id="eval-001",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        timestamp_ms=1770000000400,
        trigger_candle_close_time_ms=1770000000400,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        fact_observations=[
            {
                "fact_key": "htf_trend_intact",
                "observed_value": True,
                "observed_at_ms": 1770000000400,
                "valid_until_ms": 1770003600400,
                "source_ref": "evaluator:cpm-ro-001-historical-v0:htf_trend",
            }
        ],
        input_refs=_input_refs(),
    )

    assert output.fact_observations[0].fact_key == "htf_trend_intact"
    assert output.fact_observations[0].observed_value is True


def test_observe_only_signal_is_never_execution_eligible():
    envelope = resolve_execution_eligibility(
        declared_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
        declared_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
        execution_eligibility_enabled=False,
        evaluator_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
        evaluator_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
        authority_source_ref="event-spec:SOR-LONG-v1",
    )

    assert envelope.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL
    assert envelope.required_execution_mode == RequiredExecutionMode.OBSERVE_ONLY
    assert envelope.execution_eligible is False


def test_evaluator_cannot_upgrade_event_spec_authority():
    with pytest.raises(ValueError, match="exceeds declared event-spec authority"):
        resolve_execution_eligibility(
            declared_signal_grade=SignalGrade.OBSERVE_ONLY_SIGNAL,
            declared_required_execution_mode=RequiredExecutionMode.OBSERVE_ONLY,
            execution_eligibility_enabled=False,
            evaluator_signal_grade=SignalGrade.TRIAL_GRADE_SIGNAL,
            evaluator_required_execution_mode=RequiredExecutionMode.TRIAL_LIVE,
            authority_source_ref="event-spec:SOR-LONG-v1",
        )


def test_signal_output_defaults_to_typed_observe_only_authority():
    output = StrategyFamilySignalOutput(
        signal_id="sig-observe-only-001",
        evaluation_id="eval-001",
        strategy_family_id="tf",
        strategy_family_version_id="tf-v1",
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000400,
        trigger_candle_close_time_ms=1770000000400,
        timeframe="4h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        input_refs=_input_refs(),
    )

    assert output.signal_grade == SignalGrade.OBSERVE_ONLY_SIGNAL
    assert output.required_execution_mode == RequiredExecutionMode.OBSERVE_ONLY


def test_would_enter_signal_output_requires_trigger_candle_close_time():
    with pytest.raises(ValueError, match="trigger_candle_close_time_ms"):
        StrategyFamilySignalOutput(
            signal_id="sig-enter-missing-time",
            evaluation_id="eval-001",
            strategy_family_id="tf",
            strategy_family_version_id="tf-v1",
            symbol="BTC/USDT:USDT",
            timestamp_ms=1770000000450,
            timeframe="4h",
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.LONG,
            reason_codes=["missing_time_authority"],
            input_refs=_input_refs(),
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    ],
)
def test_signal_output_rejects_forbidden_execution_order_fields(field_name: str):
    with pytest.raises(ValueError, match="forbidden execution/order field"):
        StrategyFamilySignalOutput(
            signal_id="sig-bad-001",
            evaluation_id="eval-001",
            strategy_family_id="tf",
            strategy_family_version_id="tf-v1",
            symbol="BTC/USDT:USDT",
            timestamp_ms=1770000000500,
            trigger_candle_close_time_ms=1770000000500,
            timeframe="4h",
            signal_type=SignalType.WOULD_ENTER,
            side=SignalSide.LONG,
            reason_codes=["bad_payload"],
            input_refs=_input_refs(),
            evidence_payload={field_name: "must_not_exist"},
        )


def test_high_confidence_does_not_authorize_execution():
    output = StrategyFamilySignalOutput(
        signal_id="sig-confidence-001",
        evaluation_id="eval-001",
        strategy_family_id="tf",
        strategy_family_version_id="tf-v1",
        symbol="BTC/USDT:USDT",
        timestamp_ms=1770000000600,
        trigger_candle_close_time_ms=1770000000600,
        timeframe="4h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.SHORT,
        confidence=Decimal("1.0"),
        reason_codes=["review_sort_high"],
        input_refs=_input_refs(),
    )
    dumped = output.model_dump(mode="json")

    assert output.not_order is True
    assert output.not_execution_intent is True
    assert "authorization" in output.confidence_semantics
    assert "final_permission" not in dumped
    assert "permission_upgrade" not in dumped


@pytest.mark.parametrize("field_name", ["quantity", "notional", "leverage", "order_type", "venue"])
def test_strategy_family_signal_input_rejects_forbidden_execution_order_fields(field_name: str):
    payload = _signal_input().model_dump(mode="python")
    payload["playbook_snapshot"][field_name] = "must_not_exist"

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        StrategyFamilySignalInput.model_validate(payload)


def test_market_and_account_snapshots_reject_execution_order_instructions():
    with pytest.raises(ValueError, match="forbidden execution/order field"):
        MarketSnapshot(
            symbol="BTC/USDT:USDT",
            timestamp_ms=1770000000700,
            source="exchange_live_market",
            freshness="fresh",
            candle_context={"order_type": "market"},
        )

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        AccountFactsSnapshot(
            source="exchange_live",
            truth_level="exchange_read",
            timestamp_ms=1770000000800,
            freshness="fresh",
            positions=[{"symbol": "BTC/USDT:USDT", "quantity": "1"}],
            open_orders=[],
            reconciliation_status={"status": "clean"},
        )


def test_signal_output_serialization_round_trip_preserves_non_execution_flags():
    output = StrategyFamilySignalOutput(
        signal_id="sig-roundtrip-001",
        evaluation_id="eval-001",
        strategy_family_id="vb",
        strategy_family_version_id="vb-v1",
        playbook_id="VB-001",
        symbol="ETH/USDT:USDT",
        timestamp_ms=1770000000900,
        trigger_candle_close_time_ms=1770000000900,
        timeframe="1h",
        signal_type=SignalType.WOULD_REDUCE,
        side=SignalSide.LONG,
        confidence=Decimal("0.61"),
        reason_codes=["volatility_expansion_faded"],
        required_execution_mode="observe_only",
        expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
        input_refs=_input_refs(),
    )

    dumped = output.model_dump(mode="json")
    restored = StrategyFamilySignalOutput.model_validate(dumped)

    assert restored == output
    assert dumped["not_order"] is True
    assert dumped["not_execution_intent"] is True
    assert dumped["signal_type"] == "would_reduce"
    assert dumped["side"] == "long"
