from __future__ import annotations

from src.application.strategy_group_live_readonly_observation import (
    InMemoryStrategyGroupObservationSink,
    MI001MomentumImpulseReadOnlyEvaluator,
    SampleStrategyGroupMarketBarSource,
    build_strategy_group_live_readonly_observation_v1,
    run_strategy_group_live_readonly_observation_once,
    _market_snapshot,
    _sample_mi_candles,
    _sample_signal_input,
)
from src.domain.strategy_family_signal import SignalSide, SignalType


def test_live_readonly_observation_v1_exposes_mi_and_cpm_without_execution_fields():
    payload = build_strategy_group_live_readonly_observation_v1()

    candidate_ids = {item.candidate_id for item in payload.candidates}
    assert {"MI-001-SOL-LONG", "MI-001-BNB-LONG", "CPM-RO-001"} <= candidate_ids
    assert payload.runner_mapping["strategy_specific_signal_evaluator_glue_wired"] is True
    assert payload.live_observation_active is False
    assert payload.live_ready is False
    assert len(payload.current_signals) == 3
    assert payload.sink_summary["pg_observation_sink"] == "blocked_schema_gap_no_live_observation_table_found"
    assert payload.input_source_summary["external_exchange_write"] is False
    assert payload.review_hook_summary["review_hook_status"] == "records_include_pending_forward_outcome_windows"
    assert payload.non_permissions["no_execution_intent"] is True
    assert payload.non_permissions["no_order_permission"] is True

    raw = payload.model_dump(mode="json")
    text = str(raw)
    assert "execution_permission_granted" not in text
    assert "order_permission_granted" not in text
    assert "trial_started" not in text


def test_run_once_records_observe_only_signal_history_without_runtime_effect():
    sink = InMemoryStrategyGroupObservationSink()
    payload = run_strategy_group_live_readonly_observation_once(
        market_source=SampleStrategyGroupMarketBarSource(),
        sink=sink,
    )

    assert len(payload.current_signals) == 3
    assert len(payload.signal_history) == 3
    assert payload.sink_summary["sink_status"] == "process_local_sink_recording_enabled"
    assert payload.sink_summary["writes_execution_or_order_tables"] is False
    assert all(record.not_order is True for record in payload.signal_history)
    assert all(record.not_execution_intent is True for record in payload.signal_history)
    assert all(record.no_runtime_start is True for record in payload.signal_history)


def test_mi001_readonly_evaluator_returns_would_enter_for_impulse_preview():
    market_snapshot = _market_snapshot(
        symbol="SOL/USDT:USDT",
        candles=_sample_mi_candles(),
        timestamp_ms=1770000000000,
    )
    signal_input = _sample_signal_input(
        family_id="MI-001",
        version_id="MI-001-smoke-v0",
        playbook_id="MI-001-SOL-LONG-BT-001",
        symbol="SOL/USDT:USDT",
        side=SignalSide.LONG,
        market_snapshot=market_snapshot,
    )

    output = MI001MomentumImpulseReadOnlyEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.WOULD_ENTER
    assert output.side == SignalSide.LONG
    assert output.required_execution_mode == "observe_only"
    assert output.not_order is True
    assert output.not_execution_intent is True
    assert "impulse_return_pct" in output.evidence_payload


def test_mi001_readonly_evaluator_returns_invalid_for_missing_context():
    market_snapshot = _market_snapshot(
        symbol="SOL/USDT:USDT",
        candles=_sample_mi_candles()[:2],
        timestamp_ms=1770000000000,
    )
    signal_input = _sample_signal_input(
        family_id="MI-001",
        version_id="MI-001-smoke-v0",
        playbook_id="MI-001-SOL-LONG-BT-001",
        symbol="SOL/USDT:USDT",
        side=SignalSide.LONG,
        market_snapshot=market_snapshot,
    )

    output = MI001MomentumImpulseReadOnlyEvaluator().evaluate(signal_input)

    assert output.signal_type == SignalType.INVALID
    assert "mi001_invalid_insufficient_candles" in output.reason_codes
    assert output.not_order is True
    assert output.not_execution_intent is True
