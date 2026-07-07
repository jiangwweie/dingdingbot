from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from scripts import materialize_action_time_finalgate_preflight as finalgate
from scripts import materialize_action_time_operation_layer_handoff as handoff
from scripts import materialize_action_time_ticket as ticket_materializer
from scripts import materialize_ticket_bound_runtime_safety_state as safety
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
    migration = _load_module(MIGRATION_PATH, "migration_086_runtime_safety")
    seed = _load_module(SEED_PATH, "seed_runtime_safety")
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
    assert safety.main(["--require-database-url", "--ticket-id", "ticket-1"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert safety.main(["--database-url", "sqlite://"]) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err
    assert not (tmp_path / "runtime-safety.json").exists()


def test_runtime_safety_state_noops_without_operation_layer_handoff(
    pg_control_connection,
):
    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        now_ms=NOW_MS,
    )

    assert payload["status"] == "no_operation_layer_handoff"
    assert payload["submit_allowed"] is False
    assert payload["blockers"] == []
    assert payload["next_action"] == "continue_watcher_observation"
    assert payload["forbidden_effects"] == safety.FORBIDDEN_EFFECTS
    assert _runtime_safety_count(pg_control_connection) == 0


def test_runtime_safety_state_materializes_submit_allowed_snapshot(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_ready"
    assert payload["ticket_id"] == ids["ticket_id"]
    assert payload["finalgate_pass_id"] == ids["finalgate_pass_id"]
    assert payload["operation_layer_handoff_id"] == ids["operation_layer_handoff_id"]
    assert payload["operation_submit_command_id"] == ids["operation_submit_command_id"]
    assert payload["action_time_lane_input_id"] == ids["lane_id"]
    assert payload["strategy_group_id"] == "SOR-001"
    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "long"
    assert payload["submit_allowed"] is True
    assert payload["blockers"] == []
    assert payload["forbidden_effects"] == safety.FORBIDDEN_EFFECTS

    row = pg_control_connection.execute(
        text(
            """
            SELECT runtime_safety_snapshot_id, action_time_lane_input_id,
                   safety_state, submit_allowed, finalgate_ready,
                   operation_layer_ready, protection_ready,
                   active_position_conflict, facts_fresh,
                   trusted_fact_refs_complete, blockers, trusted_fact_refs
            FROM brc_runtime_safety_state_snapshots
            """
        )
    ).mappings().one()
    assert row["action_time_lane_input_id"] == ids["lane_id"]
    assert row["safety_state"] == "live_submit_ready"
    assert row["submit_allowed"] in {True, 1}
    assert row["finalgate_ready"] in {True, 1}
    assert row["operation_layer_ready"] in {True, 1}
    assert row["protection_ready"] in {True, 1}
    assert row["active_position_conflict"] in {False, 0}
    assert row["facts_fresh"] in {True, 1}
    assert row["trusted_fact_refs_complete"] in {True, 1}
    assert _json_value(row["blockers"]) == []

    trusted_refs = _json_value(row["trusted_fact_refs"])
    assert trusted_refs["ticket_id"] == ids["ticket_id"]
    assert trusted_refs["signal_event_id"] == "signal:SOR-001:ETHUSDT:long:unit"
    assert trusted_refs["finalgate_pass_id"] == ids["finalgate_pass_id"]
    assert trusted_refs["operation_layer_handoff_id"] == ids["operation_layer_handoff_id"]
    assert trusted_refs["operation_submit_command_id"] == ids["operation_submit_command_id"]

    lane_snapshot_id = pg_control_connection.execute(
        text(
            """
            SELECT runtime_safety_snapshot_id
            FROM brc_action_time_lane_inputs
            WHERE action_time_lane_input_id = :lane_id
            """
        ),
        {"lane_id": ids["lane_id"]},
    ).scalar_one()
    assert lane_snapshot_id == row["runtime_safety_snapshot_id"]


def test_runtime_safety_state_blocks_ticket_identity_hash_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_action_time_tickets
            SET leverage = 9
            WHERE ticket_id = :ticket_id
            """
        ),
        {"ticket_id": ids["ticket_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert "ticket_hash_mismatch" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["safety_state"] == "blocked_safety"
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_account_position_conflict(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET fact_values = :fact_values
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:account-safe:unit'
            """
        ),
        {
            "fact_values": json.dumps(
                {
                    "account_safe": True,
                    "open_orders_clear": True,
                    "active_position_or_open_order_clear": False,
                },
                sort_keys=True,
            )
        },
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "active_position_or_open_order_conflict" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["active_position_conflict"] in {True, 1}
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_expired_fact_snapshot(pg_control_connection):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_runtime_fact_snapshots
            SET valid_until_ms = :valid_until_ms
            WHERE fact_snapshot_id = 'fact:SOR-001:ETHUSDT:long:action-time:unit'
            """
        ),
        {"valid_until_ms": NOW_MS + 1},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "action_time_fact_snapshot_id_expired" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["facts_fresh"] in {False, 0}
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_non_live_market_signal_source(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET source_kind = 'replay',
                status = 'stale',
                freshness_state = 'stale'
            WHERE signal_event_id = 'signal:SOR-001:ETHUSDT:long:unit'
            """
        )
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert payload["submit_allowed"] is False
    assert "signal_event_not_live_market:replay" in payload["blockers"]
    assert "signal_event_not_fresh:stale" in payload["blockers"]
    row = _runtime_safety_row(pg_control_connection)
    assert row["safety_state"] == "blocked_safety"
    assert row["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_generated_at_signal_time(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    with pytest.raises(IntegrityError):
        pg_control_connection.execute(
            text(
                """
                UPDATE brc_live_signal_events
                SET created_at_ms = event_time_ms
                WHERE signal_event_id = 'signal:SOR-001:ETHUSDT:long:unit'
                """
            )
        )

    assert ids["ticket_id"]
    assert _runtime_safety_count(pg_control_connection) == 0


def test_runtime_safety_state_blocks_finalgate_pass_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_operation_layer_handoffs
            SET finalgate_pass_id = 'finalgate_pass:wrong'
            WHERE operation_layer_handoff_id = :handoff_id
            """
        ),
        {"handoff_id": ids["operation_layer_handoff_id"]},
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert any(
        blocker.startswith("operation_layer_handoff_finalgate_pass_mismatch:")
        for blocker in payload["blockers"]
    )
    assert _runtime_safety_row(pg_control_connection)["submit_allowed"] in {False, 0}


def test_runtime_safety_state_blocks_handoff_command_ticket_mismatch(
    pg_control_connection,
):
    ids = _create_handoff_ready(pg_control_connection)
    command_plan = _json_value(
        pg_control_connection.execute(
            text(
                """
                SELECT command_plan
                FROM brc_operation_layer_handoffs
                WHERE operation_layer_handoff_id = :handoff_id
                """
            ),
            {"handoff_id": ids["operation_layer_handoff_id"]},
        ).scalar_one()
    )
    command_plan["ticket_id"] = "ticket:wrong"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_operation_layer_handoffs
            SET command_plan = :command_plan
            WHERE operation_layer_handoff_id = :handoff_id
            """
        ),
        {
            "handoff_id": ids["operation_layer_handoff_id"],
            "command_plan": json.dumps(command_plan, sort_keys=True),
        },
    )

    payload = safety.materialize_ticket_bound_runtime_safety_state(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_layer_handoff_id=ids["operation_layer_handoff_id"],
        now_ms=NOW_MS + 3000,
    )

    assert payload["status"] == "runtime_safety_state_blocked"
    assert "operation_layer_handoff_command_ticket_mismatch" in payload["blockers"]
    assert _runtime_safety_row(pg_control_connection)["submit_allowed"] in {False, 0}


def test_runtime_safety_selector_fails_closed_on_multiple_current_handoffs():
    selected = safety._select_handoff(
        {
            "action_time_tickets": [
                {
                    "ticket_id": "ticket:current-a",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
                {
                    "ticket_id": "ticket:current-b",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
            ],
            "operation_layer_handoffs": [
                {
                    "operation_layer_handoff_id": "handoff:current-a",
                    "ticket_id": "ticket:current-a",
                    "operation_submit_command_id": "operation-submit:current-a",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:current-b",
                    "ticket_id": "ticket:current-b",
                    "operation_submit_command_id": "operation-submit:current-b",
                    "status": "handoff_ready",
                },
            ],
        },
        ticket_id="",
        operation_layer_handoff_id="",
        now_ms=NOW_MS,
    )

    assert selected["handoff"] == {}
    assert selected["blockers"] == ["multiple_ready_operation_layer_handoffs"]


def test_runtime_safety_selector_ignores_handoffs_without_current_ticket():
    selected = safety._select_handoff(
        {
            "action_time_tickets": [
                {
                    "ticket_id": "ticket:expired",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS - 1,
                },
                {
                    "ticket_id": "ticket:current",
                    "status": "finalgate_ready",
                    "expires_at_ms": NOW_MS + 60_000,
                },
                {
                    "ticket_id": "ticket:closed",
                    "status": "expired",
                    "expires_at_ms": NOW_MS + 60_000,
                },
            ],
            "operation_layer_handoffs": [
                {
                    "operation_layer_handoff_id": "handoff:expired",
                    "ticket_id": "ticket:expired",
                    "operation_submit_command_id": "operation-submit:expired",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:current",
                    "ticket_id": "ticket:current",
                    "operation_submit_command_id": "operation-submit:current",
                    "status": "handoff_ready",
                },
                {
                    "operation_layer_handoff_id": "handoff:closed",
                    "ticket_id": "ticket:closed",
                    "operation_submit_command_id": "operation-submit:closed",
                    "status": "handoff_ready",
                },
            ],
        },
        ticket_id="",
        operation_layer_handoff_id="",
        now_ms=NOW_MS,
    )

    assert selected["blockers"] == []
    assert selected["handoff"]["operation_layer_handoff_id"] == "handoff:current"


def _create_handoff_ready(conn) -> dict[str, str]:
    lane_id = _insert_action_time_lane_graph(conn)
    ticket_payload = ticket_materializer.materialize_action_time_ticket(
        conn,
        now_ms=NOW_MS,
    )
    assert ticket_payload["status"] == "action_time_ticket_created"
    ticket_id = str(ticket_payload["ticket_id"])
    finalgate_payload = finalgate.materialize_action_time_finalgate_preflight(
        conn,
        ticket_id=ticket_id,
        now_ms=NOW_MS + 1000,
    )
    assert finalgate_payload["status"] == "finalgate_ready"
    finalgate_pass_id = str(finalgate_payload["finalgate_pass_id"])
    handoff_payload = handoff.materialize_action_time_operation_layer_handoff(
        conn,
        ticket_id=ticket_id,
        finalgate_pass_id=finalgate_pass_id,
        now_ms=NOW_MS + 2000,
    )
    assert handoff_payload["status"] == "operation_layer_handoff_ready"
    return {
        "lane_id": lane_id,
        "ticket_id": ticket_id,
        "finalgate_pass_id": finalgate_pass_id,
        "operation_layer_handoff_id": str(handoff_payload["operation_layer_handoff_id"]),
        "operation_submit_command_id": str(handoff_payload["operation_submit_command_id"]),
    }


def _runtime_safety_count(conn) -> int:
    return conn.execute(
        text("SELECT COUNT(*) FROM brc_runtime_safety_state_snapshots")
    ).scalar_one()


def _runtime_safety_row(conn):
    return conn.execute(
        text("SELECT * FROM brc_runtime_safety_state_snapshots")
    ).mappings().one()


def _json_value(value):
    if isinstance(value, str):
        return json.loads(value)
    return value
