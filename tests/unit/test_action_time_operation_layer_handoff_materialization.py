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
from scripts import materialize_action_time_operation_layer_handoff as handoff
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
    migration = _load_module(MIGRATION_PATH, "migration_086_operation_handoff")
    seed = _load_module(SEED_PATH, "seed_operation_handoff")
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
        finally:
            migration.op = old_op
        seed.seed_runtime_control_state_foundation(conn)
    with engine.connect() as conn:
        yield conn
    engine.dispose()


def test_cli_requires_database_url_and_postgres_dsn(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert handoff.main(["--require-database-url", "--ticket-id", "ticket-1"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert handoff.main(["--database-url", "sqlite://"]) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err
    assert not (tmp_path / "handoff.json").exists()


def test_operation_layer_handoff_noops_without_finalgate_ready_ticket(
    pg_control_connection,
):
    payload = handoff.materialize_next_action_time_operation_layer_handoff(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_finalgate_ready_ticket"
    assert payload["ticket_id"] is None
    assert payload["blockers"] == []
    assert payload["next_action"] == "continue_watcher_observation"
    assert payload["forbidden_effects"]["exchange_write_called"] is False


def test_operation_layer_handoff_auto_selector_ignores_expired_finalgate_ticket(
    pg_control_connection,
):
    ticket_id, finalgate_pass_id = _create_finalgate_ready_ticket(pg_control_connection)

    payload = handoff.materialize_next_action_time_operation_layer_handoff(
        pg_control_connection,
        now_ms=NOW_MS + 700_000,
    )

    assert ticket_id
    assert finalgate_pass_id
    assert payload["status"] == "no_finalgate_ready_ticket"
    assert payload["ticket_id"] is None
    assert payload["blockers"] == []


def test_operation_layer_handoff_materializes_from_ticket_and_finalgate_pass(
    pg_control_connection,
):
    ticket_id, finalgate_pass_id = _create_finalgate_ready_ticket(pg_control_connection)

    payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 2000,
    )

    assert payload["status"] == "operation_layer_handoff_ready"
    assert payload["ticket_id"] == ticket_id
    assert payload["finalgate_pass_id"] == finalgate_pass_id
    assert payload["operation_submit_command_id"].startswith(
        "operation_submit_command:"
    )
    assert payload["command_plan"]["ticket_id"] == ticket_id
    assert payload["command_plan"]["finalgate_pass_id"] == finalgate_pass_id
    assert payload["command_plan"]["requires_ticket_bound_protected_submit"] is True
    assert "authorization_id" not in payload["command_plan"]
    assert payload["forbidden_effects"] == handoff.FORBIDDEN_EFFECTS

    row = pg_control_connection.execute(
        text(
            """
            SELECT ticket_id, finalgate_pass_id, status, exchange_write_called,
                   order_created, operation_layer_called
            FROM brc_operation_layer_handoffs
            """
        )
    ).mappings().one()
    assert row["ticket_id"] == ticket_id
    assert row["finalgate_pass_id"] == finalgate_pass_id
    assert row["status"] == "handoff_ready"
    assert row["exchange_write_called"] in {False, 0}
    assert row["order_created"] in {False, 0}
    assert row["operation_layer_called"] in {False, 0}


def test_operation_layer_handoff_is_idempotent(pg_control_connection):
    ticket_id, finalgate_pass_id = _create_finalgate_ready_ticket(pg_control_connection)
    first = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 2000,
    )
    second = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 3000,
    )

    assert first["status"] == "operation_layer_handoff_ready"
    assert second["status"] == "operation_layer_handoff_already_exists"
    assert second["operation_layer_handoff_id"] == first["operation_layer_handoff_id"]
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_operation_layer_handoffs")
    ).scalar_one() == 1


def test_operation_layer_handoff_rejects_mismatched_finalgate_pass(
    pg_control_connection,
):
    ticket_id, _finalgate_pass_id = _create_finalgate_ready_ticket(pg_control_connection)

    payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=ticket_id,
        finalgate_pass_id="finalgate_pass:wrong",
        now_ms=NOW_MS + 2000,
    )

    assert payload["status"] == "blocked"
    assert any(
        blocker.startswith("finalgate_pass_id_mismatch:")
        for blocker in payload["blockers"]
    )
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_operation_layer_handoffs")
    ).scalar_one() == 0


def test_operation_layer_handoff_rejects_ticket_before_finalgate(
    pg_control_connection,
):
    _insert_action_time_lane_graph(pg_control_connection)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=str(ticket_payload["ticket_id"]),
        finalgate_pass_id="finalgate_pass:missing",
        now_ms=NOW_MS + 1000,
    )

    assert payload["status"] == "blocked"
    assert "ticket_status_not_finalgate_ready:created" in payload["blockers"]
    assert "finalgate_pass_id_missing" in payload["blockers"]


def test_operation_layer_handoff_rejects_ticket_identity_hash_mismatch(
    pg_control_connection,
):
    ticket_id, finalgate_pass_id = _create_finalgate_ready_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET leverage = 9
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ticket_id},
    )

    payload = handoff.materialize_action_time_operation_layer_handoff(
        pg_control_connection,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 2000,
    )

    assert payload["status"] == "blocked"
    assert "ticket_hash_mismatch" in payload["blockers"]
    assert pg_control_connection.execute(
        text("SELECT COUNT(*) FROM brc_operation_layer_handoffs")
    ).scalar_one() == 0


def _create_finalgate_ready_ticket(conn) -> tuple[str, str]:
    _insert_action_time_lane_graph(conn)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        conn,
        now_ms=NOW_MS,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=str(ticket_payload["ticket_id"]),
        now_ms=NOW_MS + 1000,
    )
    assert finalgate_payload["status"] == "finalgate_ready"
    return str(ticket_payload["ticket_id"]), str(finalgate_payload["finalgate_pass_id"])
