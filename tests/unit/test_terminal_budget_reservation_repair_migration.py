from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/2026-07-14-123_repair_terminal_budget_reservations.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("migration_123_budget_repair", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migration_123_budget_repair"] = module
    spec.loader.exec_module(module)
    return module


def _tables(conn: sa.Connection) -> None:
    for statement in (
        "CREATE TABLE brc_budget_reservations (budget_reservation_id TEXT PRIMARY KEY, ticket_id TEXT, status TEXT, release_reason TEXT)",
        "CREATE TABLE brc_action_time_tickets (ticket_id TEXT PRIMARY KEY, status TEXT)",
        "CREATE TABLE brc_ticket_bound_protected_submit_attempts (ticket_id TEXT, exchange_write_called BOOLEAN)",
        "CREATE TABLE brc_ticket_bound_exchange_commands (ticket_id TEXT, command_state TEXT, dispatch_started_at_ms BIGINT, exchange_order_id TEXT)",
        "CREATE TABLE brc_account_exposure_current (owner_ticket_id TEXT, position_slot_claimed BOOLEAN)",
        "CREATE TABLE brc_budget_reservation_events (budget_reservation_event_id TEXT PRIMARY KEY, budget_reservation_id TEXT, from_status TEXT, to_status TEXT, reason TEXT, evidence_ref TEXT, created_at_ms BIGINT)",
    ):
        conn.execute(sa.text(statement))


def test_migration_123_releases_only_terminal_pre_dispatch_reservations() -> None:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        _tables(conn)
        conn.execute(sa.text("INSERT INTO brc_action_time_tickets VALUES ('safe', 'expired'), ('written', 'expired'), ('unknown-command', 'expired')"))
        conn.execute(sa.text("INSERT INTO brc_budget_reservations VALUES ('safe-budget', 'safe', 'consumed', NULL), ('written-budget', 'written', 'consumed', NULL), ('unknown-command-budget', 'unknown-command', 'consumed', NULL)"))
        conn.execute(sa.text("INSERT INTO brc_ticket_bound_protected_submit_attempts VALUES ('written', true)"))
        conn.execute(sa.text("INSERT INTO brc_ticket_bound_exchange_commands VALUES ('unknown-command', 'dispatching', 1, NULL)"))
        module = _load()
        old_op = module.op
        module.op = Operations(MigrationContext.configure(conn))
        try:
            module.upgrade()
        finally:
            module.op = old_op

        statuses = dict(
            conn.execute(
                sa.text("SELECT budget_reservation_id, status FROM brc_budget_reservations")
            ).all()
        )
        events = conn.execute(sa.text("SELECT budget_reservation_id, to_status FROM brc_budget_reservation_events")).all()

    assert statuses == {
        "safe-budget": "released",
        "written-budget": "consumed",
        "unknown-command-budget": "consumed",
    }
    assert events == [("safe-budget", "released")]
