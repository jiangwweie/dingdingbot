from __future__ import annotations

from src.application.owner_notification import (
    OwnerNotificationKind,
    project_owner_notification_intents,
)


NOW_MS = 1_800_000_000_000


def _signal(
    *,
    status: str = "facts_validated",
    freshness: str = "fresh",
    execution_eligible: bool = True,
) -> dict:
    return {
        "signal_event_id": "signal-001",
        "strategy_group_id": "SOR-001",
        "symbol": "SOLUSDT",
        "side": "long",
        "source_kind": "live_market",
        "status": status,
        "freshness_state": freshness,
        "execution_eligible": execution_eligible,
        "required_execution_mode": (
            "trial_live" if execution_eligible else "observe_only"
        ),
        "event_time_ms": NOW_MS - 60_000,
        "observed_at_ms": NOW_MS - 50_000,
        "expires_at_ms": NOW_MS + 60_000 if freshness == "fresh" else NOW_MS - 1,
    }


def _ticket(*, status: str = "submitted") -> dict:
    return {
        "ticket_id": "ticket-001",
        "signal_event_id": "signal-001",
        "strategy_group_id": "SOR-001",
        "symbol": "SOLUSDT",
        "side": "long",
        "status": status,
        "created_at_ms": NOW_MS - 40_000,
    }


def _lifecycle(status: str, *, blocker: str | None = None) -> dict:
    return {
        "lifecycle_run_id": "lifecycle-001",
        "ticket_id": "ticket-001",
        "strategy_group_id": "SOR-001",
        "symbol": "SOLUSDT",
        "side": "long",
        "status": status,
        "first_blocker": blocker,
        "entry_filled_qty": "2.5",
        "entry_avg_price": "140.25",
        "updated_at_ms": NOW_MS - 10_000,
    }


def test_one_fresh_signal_emits_one_opportunity_despite_candidate_lane_and_ticket() -> None:
    state = {
        "live_signal_events": [_signal()],
        "promotion_candidates": [
            {
                "promotion_candidate_id": "promotion-001",
                "signal_event_id": "signal-001",
                "status": "eligible",
            }
        ],
        "action_time_lane_inputs": [
            {
                "action_time_lane_input_id": "lane-001",
                "signal_event_id": "signal-001",
                "status": "active",
            }
        ],
        "action_time_tickets": [_ticket(status="created")],
    }

    intents = project_owner_notification_intents(state, now_ms=NOW_MS)

    assert [item.notification_kind for item in intents] == [
        OwnerNotificationKind.OPPORTUNITY_DETECTED
    ]
    assert intents[0].correlation_id == "signal:signal-001"


def test_observe_only_fresh_signal_does_not_emit_trading_opportunity() -> None:
    intents = project_owner_notification_intents(
        {"live_signal_events": [_signal(execution_eligible=False)]},
        now_ms=NOW_MS,
    )

    assert intents == []


def test_prefixed_production_signal_identity_is_not_double_prefixed() -> None:
    signal = _signal()
    signal["signal_event_id"] = "signal:signal-001"

    intents = project_owner_notification_intents(
        {"live_signal_events": [signal]},
        now_ms=NOW_MS,
    )

    assert intents[0].correlation_id == "signal:signal-001"


def test_previously_sent_signal_terminal_without_submit_emits_not_executed() -> None:
    state = {
        "live_signal_events": [_signal(status="stale", freshness="stale")],
        "action_time_tickets": [_ticket(status="expired")],
        "server_monitor_notifications": [
            {
                "notification_kind": "opportunity_detected",
                "correlation_id": "signal:signal-001",
                "notification_state": "sent",
            }
        ],
    }

    intents = project_owner_notification_intents(state, now_ms=NOW_MS)

    assert [item.notification_kind for item in intents] == [
        OwnerNotificationKind.OPPORTUNITY_NOT_EXECUTED
    ]
    assert intents[0].owner_action_required is False
    assert "没有下单" in intents[0].result_summary


def test_ticket_emits_only_latest_material_lifecycle_stage() -> None:
    for status, expected in (
        ("entry_submit_sent", OwnerNotificationKind.TRADE_SUBMITTED),
        ("position_protected", OwnerNotificationKind.POSITION_PROTECTED),
        ("runner_protected", OwnerNotificationKind.TP1_RUNNER_ACTIVE),
        ("lifecycle_closed", OwnerNotificationKind.TRADE_CLOSED),
    ):
        state = {
            "live_signal_events": [_signal()],
            "action_time_tickets": [_ticket()],
            "ticket_bound_order_lifecycle_runs": [_lifecycle(status)],
            "live_outcome_ledger": [
                {
                    "ticket_id": "ticket-001",
                    "net_pnl": "12.40",
                    "r_multiple": "1.75",
                }
            ],
        }

        intents = project_owner_notification_intents(state, now_ms=NOW_MS)

        assert [item.notification_kind for item in intents] == [expected]
        assert intents[0].correlation_id == "ticket:ticket-001"


def test_unprotected_and_unknown_exchange_outcome_are_critical() -> None:
    unprotected = project_owner_notification_intents(
        {
            "action_time_tickets": [_ticket()],
            "ticket_bound_order_lifecycle_runs": [
                _lifecycle("protection_missing", blocker="protection_missing")
            ],
        },
        now_ms=NOW_MS,
    )
    unknown = project_owner_notification_intents(
        {
            "action_time_tickets": [_ticket()],
            "ticket_bound_exchange_commands": [
                {
                    "exchange_command_id": "command-001",
                    "ticket_id": "ticket-001",
                    "strategy_group_id": "SOR-001",
                    "symbol": "SOLUSDT",
                    "side": "long",
                    "command_state": "outcome_unknown",
                    "updated_at_ms": NOW_MS - 120_000,
                }
            ],
        },
        now_ms=NOW_MS,
    )

    for intents in (unprotected, unknown):
        assert len(intents) == 1
        assert intents[0].notification_kind is OwnerNotificationKind.INTERVENTION_REQUIRED
        assert intents[0].owner_action_required is True


def test_sent_incident_emits_one_recovery_when_no_longer_current() -> None:
    state = {
        "server_monitor_notifications": [
            {
                "notification_kind": "intervention_required",
                "correlation_id": "incident:exchange:command-001",
                "notification_state": "sent",
                "strategy_group_id": "SOR-001",
                "symbol": "SOLUSDT",
                "severity": "critical",
                "owner_action_required": True,
                "occurred_at_ms": NOW_MS - 600_000,
            }
        ],
        "ticket_bound_exchange_commands": [
            {
                "exchange_command_id": "command-001",
                "ticket_id": "ticket-001",
                "command_state": "reconciled_submitted",
                "updated_at_ms": NOW_MS - 10_000,
            }
        ],
    }

    intents = project_owner_notification_intents(state, now_ms=NOW_MS)

    assert [item.notification_kind for item in intents] == [
        OwnerNotificationKind.INCIDENT_RECOVERED
    ]
    assert intents[0].owner_action_required is False
