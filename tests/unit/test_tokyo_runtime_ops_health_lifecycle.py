from __future__ import annotations

import sqlalchemy as sa

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


def test_exchange_command_health_query_uses_migration_114_columns_only():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_ticket_bound_exchange_commands (
                  exchange_command_id TEXT PRIMARY KEY,
                  ticket_id TEXT,
                  command_kind TEXT,
                  command_source TEXT,
                  command_state TEXT,
                  outcome_class TEXT,
                  exchange_result TEXT,
                  netting_domain_key TEXT,
                  claim_owner TEXT,
                  claim_expires_at_ms INTEGER,
                  updated_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_ticket_bound_exchange_commands (
                  exchange_command_id, ticket_id, command_kind,
                  command_source, command_state, outcome_class,
                  exchange_result, netting_domain_key, updated_at_ms
                ) VALUES (
                  'command-1', 'ticket-1', 'place_order',
                  'runner_mutation', 'outcome_unknown', 'network_ambiguous',
                  '{"error_code":"exchange_timeout"}', 'domain-1', 90
                )
                """
            )
        )

        rows = health._read_exchange_command_critical_rows(conn, now_ms=100)

    assert len(rows) == 1
    assert rows[0]["first_blocker"] == "exchange_timeout"
    assert rows[0]["outcome_class"] == "network_ambiguous"
