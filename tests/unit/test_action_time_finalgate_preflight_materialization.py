from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from scripts import materialize_action_time_finalgate_preflight as finalgate
from scripts import materialize_action_time_ticket as ticket_materializer
from tests.unit.test_action_time_ticket_materialization import (
    NOW_MS,
    _insert_action_time_lane_graph,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
RISK_RESERVATION_MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-09-103_add_budget_risk_at_stop_reservation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def pg_control_connection():
    migration = _load_module(MIGRATION_PATH, "migration_086_action_time_finalgate")
    risk_reservation_migration = _load_module(
        RISK_RESERVATION_MIGRATION_PATH,
        "migration_103_action_time_finalgate",
    )
    seed = _load_module(SEED_PATH, "seed_action_time_finalgate")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
            old_risk_op = risk_reservation_migration.op
            risk_reservation_migration.op = migration.op
            try:
                risk_reservation_migration.upgrade()
            finally:
                risk_reservation_migration.op = old_risk_op
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_cli_requires_database_url_and_postgres_dsn(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert finalgate.main(["--require-database-url", "--ticket-id", "ticket-1"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert finalgate.main(["--database-url", "sqlite://"]) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err
    assert not (tmp_path / "finalgate.json").exists()


def test_finalgate_preflight_noops_without_action_time_ticket(pg_control_connection):
    payload = finalgate.materialize_next_action_time_finalgate_preflight(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_action_time_ticket"
    assert payload["ticket_id"] is None
    assert payload["blockers"] == []
    assert payload["next_action"] == "continue_watcher_observation"
    assert payload["forbidden_effects"]["exchange_write_called"] is False


def test_finalgate_preflight_selects_single_eligible_ticket(pg_control_connection):
    ticket_id = _create_ticket(pg_control_connection)

    payload = finalgate.materialize_next_action_time_finalgate_preflight(
        pg_control_connection,
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "finalgate_ready"
    assert payload["ticket_id"] == ticket_id


def test_finalgate_preflight_auto_selector_ignores_expired_ticket(
    pg_control_connection,
):
    ticket_id = _create_ticket(pg_control_connection)

    payload = finalgate.materialize_next_action_time_finalgate_preflight(
        pg_control_connection,
        now_ms=NOW_MS + 700_000,
    )

    assert ticket_id
    assert payload["status"] == "no_action_time_ticket"
    assert payload["ticket_id"] is None
    assert payload["blockers"] == []


def test_finalgate_preflight_requires_existing_ticket(pg_control_connection):
    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id="ticket:missing",
        now_ms=NOW_MS,
    )

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["action_time_ticket_missing"]
    assert payload["forbidden_effects"]["exchange_write_called"] is False


def test_finalgate_preflight_updates_ticket_to_finalgate_ready(pg_control_connection):
    ticket_id = _create_ticket(pg_control_connection)

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "finalgate_ready"
    assert payload["ticket_id"] == ticket_id
    assert payload["finalgate_pass_id"] == f"finalgate_pass:{ticket_id}:{NOW_MS + 1000}"
    assert payload["next_action"] == "prepare_official_operation_layer_handoff"
    assert payload["forbidden_effects"] == finalgate.FORBIDDEN_EFFECTS

    status = pg_control_connection.execute(
        text("SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).scalar_one()
    assert status == "finalgate_ready"

    transitions = pg_control_connection.execute(
        text(
            """
            SELECT from_status, to_status
            FROM brc_action_time_ticket_events
            WHERE ticket_id = :ticket_id
            ORDER BY occurred_at_ms, ticket_event_id
            """
        ),
        {"ticket_id": ticket_id},
    ).all()
    assert (None, "created") in transitions
    assert ("created", "preflight_pending") in transitions
    assert ("preflight_pending", "finalgate_ready") in transitions


def test_finalgate_preflight_is_idempotent_after_pass(pg_control_connection):
    ticket_id = _create_ticket(pg_control_connection)
    first = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )
    second = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 2000,
    )

    assert first["status"] == "finalgate_ready"
    assert second["status"] == "finalgate_already_ready"
    assert second["finalgate_pass_id"] == first["finalgate_pass_id"]
    assert pg_control_connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM brc_action_time_ticket_events
            WHERE ticket_id = :ticket_id
              AND to_status = 'finalgate_ready'
            """
        ),
        {"ticket_id": ticket_id},
    ).scalar_one() == 1


def test_finalgate_preflight_rejects_expired_ticket(pg_control_connection):
    ticket_id = _create_ticket(pg_control_connection)

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 700_000,
    )

    assert payload["status"] == "blocked"
    assert "ticket_expired" in payload["blockers"]
    assert "signal_event_expired" in payload["blockers"]
    status = pg_control_connection.execute(
        text("SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).scalar_one()
    assert status == "finalgate_rejected"


def test_finalgate_preflight_rejects_account_conflict(pg_control_connection):
    ticket_id = _create_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:account-safe:unit'
            """
        ),
        {
            "fact_values": (
                '{"account_safe": true, "open_orders_clear": true, '
                '"active_position_or_open_order_clear": false}'
            )
        },
    )

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "blocked"
    assert "active_position_or_open_order_conflict" in payload["blockers"]
    assert pg_control_connection.execute(
        text("SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).scalar_one() == "finalgate_rejected"


def test_finalgate_preflight_rejects_missing_stop_risk_reservation(
    pg_control_connection,
):
    ticket_id = _create_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_budget_reservations
            SET risk_at_stop = NULL
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    )

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "blocked"
    assert "risk_at_stop_invalid" in payload["blockers"]


def test_finalgate_preflight_rejects_ticket_identity_hash_mismatch(
    pg_control_connection,
):
    ticket_id = _create_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET target_notional = 999
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    )

    payload = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "blocked"
    assert "ticket_hash_mismatch" in payload["blockers"]
    assert pg_control_connection.execute(
        text("SELECT status FROM brc_action_time_tickets WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id},
    ).scalar_one() == "finalgate_rejected"


def test_finalgate_preflight_already_ready_still_checks_ticket_hash(
    pg_control_connection,
):
    ticket_id = _create_ticket(pg_control_connection)
    first = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )
    assert first["status"] == "finalgate_ready"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET target_notional = 999
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    )

    second = finalgate.materialize_action_time_finalgate_preflight(
        pg_control_connection,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 2000,
    )

    assert second["status"] == "blocked"
    assert "ticket_hash_mismatch" in second["blockers"]
    assert second["finalgate_pass_id"] == first["finalgate_pass_id"]


def _create_ticket(conn) -> str:
    _insert_action_time_lane_graph(conn)
    payload = ticket_materializer.materialize_action_time_ticket(conn, now_ms=NOW_MS)
    assert payload["status"] == "action_time_ticket_created"
    ticket_id = str(payload["ticket_id"])
    assert ticket_id
    return ticket_id
