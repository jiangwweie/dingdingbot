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
                    "coverage_state": "covered",
                    "liveness_state": "healthy",
                    "is_current": True,
                    "created_at_ms": 900,
                    "last_tick_at_ms": 9_900,
                    "valid_until_ms": 10_100,
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
    assert result.forbidden_effects["calls_exchange_write"] is False
