from __future__ import annotations

from scripts.ops import check_tokyo_runtime_ops_health_once as health


def test_ops_health_includes_lifecycle_unit_checks():
    commands = {name: command for name, command in health.COMMANDS}

    assert commands["lifecycle_timer_status"] == (
        "systemctl",
        "is-active",
        "brc-ticket-lifecycle-maintenance.timer",
    )
    assert commands["lifecycle_service_enabled"] == (
        "systemctl",
        "is-enabled",
        "brc-ticket-lifecycle-maintenance.service",
    )


def test_unknown_exchange_command_is_critical_not_false_green():
    summary = health.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 100,
            "since_ms": 0,
            "goal": {},
            "monitor": {},
            "open_counts": {},
            "exchange_command_critical_rows": [
                {
                    "exchange_command_id": "command-1",
                    "command_state": "outcome_unknown",
                }
            ],
        }
    )

    assert summary["status"] == "critical"
    assert "ticket_bound_exchange_command_critical_state" in summary["issues"]
    assert summary["exchange_command_critical_count"] == 1


def test_closed_lifecycle_without_live_outcome_is_critical():
    summary = health.summarize_l2_l7_chain_snapshot(
        {
            "now_ms": 100,
            "since_ms": 0,
            "goal": {},
            "monitor": {},
            "open_counts": {},
            "lifecycle_closed_without_live_outcome": [{"ticket_id": "ticket-1"}],
        }
    )

    assert summary["status"] == "critical"
    assert "lifecycle_closed_without_live_outcome" in summary["issues"]
    assert summary["lifecycle_closed_without_live_outcome_count"] == 1
