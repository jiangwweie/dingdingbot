from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.application.runtime_signal_forensics import (
    RuntimeSignalForensicsQuery,
    reduce_runtime_signal_forensics,
)


def _query() -> RuntimeSignalForensicsQuery:
    return RuntimeSignalForensicsQuery(start_ms=1_000, end_ms=10_000)


def _signal(**overrides) -> dict:
    row = {
        "signal_event_id": "signal-1",
        "strategy_group_id": "SOR-001",
        "symbol": "BTCUSDT",
        "side": "long",
        "observed_at_ms": 2_000,
        "expires_at_ms": 9_000,
        "status": "facts_validated",
        "freshness_state": "fresh",
    }
    row.update(overrides)
    return row


def test_query_rejects_reversed_window_and_limit_above_1000() -> None:
    with pytest.raises(ValidationError):
        RuntimeSignalForensicsQuery(start_ms=10, end_ms=1)
    with pytest.raises(ValidationError):
        RuntimeSignalForensicsQuery(start_ms=1, end_ms=10, limit=1001)


def test_no_signal_is_only_market_absence_when_window_coverage_is_proven() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [],
            "watcher_runtime_coverage": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "coverage_state": "covered",
                    "liveness_state": "healthy",
                    "is_current": True,
                    "created_at_ms": 900,
                    "last_tick_at_ms": 9_900,
                    "valid_until_ms": 10_100,
                }
            ],
            "strategy_group_candidate_scope": [
                {
                    "strategy_group_id": "SOR-001",
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "status": "active",
                    "created_at_ms": 900,
                }
            ],
            "server_monitor_runs": [
                {"finished_at_ms": 1_100, "status": "quiet"},
                {"finished_at_ms": 9_900, "status": "quiet"},
            ],
        },
    )
    assert result.conclusion_code == "no_detected_signal_with_coverage"
    assert result.market_absence_proven is True


def test_no_signal_without_coverage_is_runtime_data_gap() -> None:
    result = reduce_runtime_signal_forensics(_query(), {"live_signal_events": []})
    assert result.conclusion_code == "runtime_data_gap"
    assert result.market_absence_proven is False


@pytest.mark.parametrize(
    ("process_state", "expected_classification"),
    [
        ("business_blocked", "runtime_business_blocked"),
        ("retryable_failure", "engineering_runtime_failure"),
        ("hard_failure", "runtime_safety_or_identity_failure"),
    ],
)
def test_missing_promotion_uses_invocation_process_blocker_before_handoff_gap(
    process_state: str, expected_classification: str
) -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "action_time_invocations": [
                {
                    "action_time_invocation_id": "invocation-1",
                    "signal_event_id": "signal-1",
                    "lane_identity_key": "lane-1",
                    "source_watermark": "watermark-1",
                }
            ],
            "runtime_process_outcomes": [
                {
                    "action_time_invocation_id": "invocation-1",
                    "process_name": "action_time_fact_snapshots",
                    "process_state": process_state,
                    "first_blocker": "active_position_clear",
                    "completed_at_ms": 3_000,
                }
            ],
        },
    )

    finding = result.findings[0]
    assert result.schema_name == "brc.runtime_signal_forensics.v2"
    assert finding.classification == expected_classification
    assert finding.first_blocker == "active_position_clear"
    assert finding.action_time_invocation_id == "invocation-1"
    assert finding.process_name == "action_time_fact_snapshots"
    assert finding.process_state == process_state


def test_successful_invocation_without_promotion_is_true_handoff_gap() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "action_time_invocations": [
                {"action_time_invocation_id": "invocation-1", "signal_event_id": "signal-1"}
            ],
            "runtime_process_outcomes": [
                {
                    "action_time_invocation_id": "invocation-1",
                    "process_name": "action_time_fact_snapshots",
                    "process_state": "succeeded",
                }
            ],
        },
    )

    finding = result.findings[0]
    assert finding.classification == "engineering_handoff_gap"
    assert finding.first_blocker == (
        "promotion_candidate_missing_after_successful_invocation"
    )
    assert finding.action_time_invocation_id == "invocation-1"


def test_missing_invocation_is_not_reported_as_promotion_gap() -> None:
    result = reduce_runtime_signal_forensics(
        _query(), {"live_signal_events": [_signal()]}
    )

    finding = result.findings[0]
    assert finding.chain_stage == "action_time_invocation"
    assert finding.first_blocker == "action_time_invocation_missing"


def test_signal_chain_reports_first_missing_machine_object() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {"signal_event_id": "signal-1", "promotion_candidate_id": "p-1"}
            ],
            "action_time_lane_inputs": [],
        },
    )
    finding = result.findings[0]
    assert finding.chain_stage == "promotion_candidate"
    assert finding.first_blocker == "action_time_lane_missing"
    assert finding.classification == "engineering_handoff_gap"


def test_arbitration_loser_is_not_reported_as_engineering_gap() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {
                    "signal_event_id": "signal-1",
                    "promotion_candidate_id": "p-1",
                    "status": "arbitration_lost",
                    "blockers": [],
                }
            ],
        },
    )
    finding = result.findings[0]
    assert finding.classification == "not_selected_by_arbitration"
    assert finding.first_blocker == "arbitration_lost"


def test_blocked_promotion_preserves_exact_business_blocker() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {
                    "signal_event_id": "signal-1",
                    "promotion_candidate_id": "p-1",
                    "status": "blocked",
                    "blockers": [
                        "risk_reservation_rounded_notional_below_exchange_minimum"
                    ],
                }
            ],
        },
    )
    finding = result.findings[0]
    assert finding.classification == "runtime_safety_or_exchange_constraint"
    assert finding.first_blocker == (
        "risk_reservation_rounded_notional_below_exchange_minimum"
    )


def test_expired_ticket_is_terminal_before_submit_not_missing_exchange_command() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {"signal_event_id": "signal-1", "promotion_candidate_id": "p-1"}
            ],
            "action_time_lane_inputs": [
                {"signal_event_id": "signal-1", "action_time_lane_input_id": "lane-1"}
            ],
            "action_time_tickets": [
                {
                    "signal_event_id": "signal-1",
                    "ticket_id": "ticket-1",
                    "status": "expired",
                }
            ],
        },
    )
    finding = result.findings[0]
    assert finding.classification == "opportunity_expired_before_submit"
    assert finding.first_blocker == "ticket_expired_before_submit"


def test_failed_submit_without_exchange_write_overrides_prepared_command_presence() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {"signal_event_id": "signal-1", "promotion_candidate_id": "p-1"}
            ],
            "action_time_lane_inputs": [
                {"signal_event_id": "signal-1", "action_time_lane_input_id": "lane-1"}
            ],
            "action_time_tickets": [
                {
                    "signal_event_id": "signal-1",
                    "ticket_id": "ticket-1",
                    "status": "expired",
                }
            ],
            "ticket_bound_protected_submit_attempts": [
                {
                    "ticket_id": "ticket-1",
                    "status": "submit_failed",
                    "exchange_write_called": False,
                    "blockers": ["brc_runtime_exchange_account_id_missing"],
                    "updated_at_ms": 4_000,
                }
            ],
            "ticket_bound_exchange_commands": [
                {
                    "ticket_id": "ticket-1",
                    "exchange_command_id": "command-1",
                    "command_state": "prepared",
                    "execution_attempt_count": 0,
                    "dispatch_started_at_ms": None,
                }
            ],
        },
    )

    finding = result.findings[0]
    assert finding.chain_stage == "operation_layer"
    assert finding.classification == "operation_blocked"
    assert finding.first_blocker == "brc_runtime_exchange_account_id_missing"
    assert "没有调用交易所" in finding.explanation


def test_closed_ticket_reports_trade_result_and_notification_state() -> None:
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [_signal()],
            "promotion_candidates": [
                {"signal_event_id": "signal-1", "promotion_candidate_id": "p-1"}
            ],
            "action_time_lane_inputs": [
                {"signal_event_id": "signal-1", "lane_input_id": "lane-1"}
            ],
            "action_time_tickets": [
                {"signal_event_id": "signal-1", "ticket_id": "ticket-1", "status": "closed"}
            ],
            "ticket_bound_exchange_commands": [
                {"ticket_id": "ticket-1", "exchange_command_id": "cmd-1", "command_state": "acknowledged"}
            ],
            "ticket_bound_order_lifecycle_runs": [
                {"ticket_id": "ticket-1", "status": "lifecycle_closed"}
            ],
            "live_outcome_ledger": [
                {"ticket_id": "ticket-1", "net_pnl": "12.50", "r_multiple": "2.1"}
            ],
            "server_monitor_notifications": [
                {"correlation_id": "ticket:ticket-1", "notification_kind": "trade_closed", "notification_state": "sent"}
            ],
        },
    )
    finding = result.findings[0]
    assert finding.chain_stage == "closed"
    assert finding.classification == "trade_completed"
    assert finding.notification_state == "sent"
    assert finding.net_pnl == "12.50"
    assert finding.promotion_candidate_id == "p-1"
    assert finding.action_time_lane_input_id == "lane-1"
    assert result.forbidden_effects["calls_exchange_write"] is False


def test_prefixed_production_signal_id_matches_raw_notification_correlation() -> None:
    signal = _signal(signal_event_id="signal:production-id")
    result = reduce_runtime_signal_forensics(
        _query(),
        {
            "live_signal_events": [signal],
            "promotion_candidates": [
                {
                    "signal_event_id": "signal:production-id",
                    "promotion_candidate_id": "p-1",
                }
            ],
            "action_time_lane_inputs": [],
            "server_monitor_notifications": [
                {
                    "correlation_id": "signal:production-id",
                    "notification_state": "sent",
                    "updated_at_ms": 3_000,
                }
            ],
        },
    )

    assert result.findings[0].notification_state == "sent"
