from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
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


def test_domain_hold_health_query_uses_migration_113_columns_only():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE brc_ticket_bound_scope_freezes (
                  scope_freeze_id TEXT PRIMARY KEY,
                  strategy_group_id TEXT,
                  symbol TEXT,
                  side TEXT,
                  status TEXT,
                  source_kind TEXT,
                  source_id TEXT,
                  source_ticket_id TEXT,
                  netting_domain_key TEXT,
                  first_blocker TEXT,
                  blockers TEXT,
                  updated_at_ms INTEGER
                )
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO brc_ticket_bound_scope_freezes (
                  scope_freeze_id, strategy_group_id, symbol, side, status,
                  source_kind, source_id, source_ticket_id,
                  netting_domain_key, first_blocker, blockers, updated_at_ms
                ) VALUES (
                  'hold-1', 'SOR-001', 'ETH/USDT:USDT', 'long', 'active',
                  'exchange_command', 'command-1', 'ticket-1',
                  'domain-1', 'exchange_command_outcome_unknown', '[]', 90
                )
                """
            )
        )

        rows = health._read_active_domain_holds(conn)

    assert len(rows) == 1
    assert rows[0]["source_ticket_id"] == "ticket-1"
    assert rows[0]["first_blocker"] == "exchange_command_outcome_unknown"


def test_ops_l2_l7_query_executes_against_migration_head(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_path = tmp_path / "ops-health-head.db"
    config = Config()
    config.set_main_option("script_location", str(Path("migrations").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(config, "106")

    from scripts.seed_runtime_control_state_foundation import (
        seed_runtime_control_state_foundation,
    )

    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        seed_runtime_control_state_foundation(
            conn,
            migration_baseline_revision="106",
        )
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    command_columns = {
        item["name"]
        for item in inspector.get_columns("brc_ticket_bound_exchange_commands")
    }
    hold_columns = {
        item["name"]
        for item in inspector.get_columns("brc_ticket_bound_scope_freezes")
    }
    engine.dispose()

    assert set(health.EXCHANGE_COMMAND_HEALTH_COLUMNS) <= command_columns
    assert set(health.DOMAIN_HOLD_HEALTH_COLUMNS) <= hold_columns
