from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATHS = {
    "086": REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py",
    "091": REPO_ROOT
    / "migrations/versions/2026-07-08-091_create_ticket_bound_order_lifecycle.py",
    "092": REPO_ROOT
    / "migrations/versions/2026-07-08-092_extend_ticket_bound_runner_statuses.py",
    "093": REPO_ROOT
    / "migrations/versions/2026-07-08-093_extend_ticket_bound_lifecycle_closure.py",
    "094": REPO_ROOT
    / "migrations/versions/2026-07-08-094_extend_ticket_bound_lifecycle_safety_core_statuses.py",
    "095": REPO_ROOT
    / "migrations/versions/2026-07-08-095_create_ticket_bound_runner_mutation_commands.py",
    "096": REPO_ROOT
    / "migrations/versions/2026-07-08-096_create_ticket_bound_protection_recovery_commands.py",
    "097": REPO_ROOT
    / "migrations/versions/2026-07-08-097_repair_temp_094_lifecycle_safety.py",
}


def test_097_repairs_lifecycle_constraints_when_official_094_was_skipped():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        _run_migrations(conn, ["086", "091", "092", "093", "095", "096"])
        _expect_integrity_error(conn, _insert_lifecycle_sql(), {"status": "protection_missing"})
        _expect_integrity_error(conn, _insert_exit_set_sql(), {"status": "protection_missing"})
        _expect_integrity_error(
            conn,
            _insert_lifecycle_event_sql(),
            {"event_type": "runner_mutation_failed"},
        )

        _run_migrations(conn, ["097"])

        conn.execute(text(_insert_lifecycle_sql()), {"status": "protection_missing"})
        conn.execute(text(_insert_exit_set_sql()), {"status": "protection_missing"})
        conn.execute(
            text(_insert_lifecycle_event_sql()),
            {"event_type": "runner_mutation_failed"},
        )
        _expect_integrity_error(
            conn,
            _insert_attempt_sql(),
            {"id": "attempt-temp-after-097", "submit_mode": "temp_tiny_live_protected_submit"},
        )
    engine.dispose()


def test_097_fails_closed_when_temp_submit_attempt_rows_exist():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        _run_migrations(conn, ["086", "091", "092", "093", "095", "096"])
        conn.execute(text("PRAGMA ignore_check_constraints = ON"))
        conn.execute(
            text(_insert_attempt_sql()),
            {
                "id": "attempt-existing-temp",
                "submit_mode": "temp_tiny_live_protected_submit",
            },
        )
        conn.execute(text("PRAGMA ignore_check_constraints = OFF"))

        with pytest.raises(RuntimeError, match="temp_tiny_live_protected_submit rows exist"):
            _run_migrations(conn, ["097"])
    engine.dispose()


def _run_migrations(conn, revisions: list[str]) -> None:
    for revision in revisions:
        migration = _load_migration(
            MIGRATION_PATHS[revision],
            f"migration_{revision}_temp_094_repair",
        )
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op


def _load_migration(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expect_integrity_error(conn, statement: str, params: dict[str, object]) -> None:
    savepoint = conn.begin_nested()
    try:
        with pytest.raises(IntegrityError):
            conn.execute(text(statement), params)
    finally:
        savepoint.rollback()


def _insert_attempt_sql() -> str:
    return """
        INSERT INTO brc_ticket_bound_protected_submit_attempts (
            protected_submit_attempt_id, ticket_id, finalgate_pass_id,
            operation_layer_handoff_id, operation_submit_command_id,
            runtime_safety_snapshot_id, action_time_lane_input_id,
            strategy_group_id, symbol, side, runtime_profile_id, submit_mode,
            status, submit_allowed, blockers, warnings, trusted_fact_refs,
            submit_request, submit_result, identity_evidence,
            official_operation_layer_submit_called, exchange_write_called,
            order_created, order_lifecycle_called, withdrawal_or_transfer_created,
            live_profile_changed, order_sizing_changed, authority_boundary,
            created_at_ms, updated_at_ms
        ) VALUES (
            :id, 'ticket-1', 'finalgate-pass-1', 'handoff-1', 'submit-command-1',
            'safety-1', 'lane-1', 'SOR-001', 'ETHUSDT', 'long', 'runtime-profile-1',
            :submit_mode, 'blocked', false, '[]', '[]', '{}', '{}', '{}', '{}',
            false, false, false, false, false, false, false,
            'ticket_bound_protected_submit_attempt', 1770000000000, 1770000000000
        )
    """


def _insert_lifecycle_sql() -> str:
    return """
        INSERT INTO brc_ticket_bound_order_lifecycle_runs (
            lifecycle_run_id, ticket_id, protected_submit_attempt_id,
            strategy_group_id, symbol, side, runtime_profile_id, status,
            entry_fill_confirmed, first_blocker, blockers, warnings,
            authority_boundary, created_at_ms, updated_at_ms
        ) VALUES (
            'lifecycle-1', 'ticket-1', 'attempt-1', 'SOR-001', 'ETHUSDT',
            'long', 'runtime-profile-1', :status, false,
            'open_position_without_valid_sl', '["open_position_without_valid_sl"]',
            '[]', 'ticket_bound_lifecycle', 1770000000000, 1770000000000
        )
    """


def _insert_exit_set_sql() -> str:
    return """
        INSERT INTO brc_ticket_bound_exit_protection_sets (
            exit_protection_set_id, ticket_id, protected_submit_attempt_id,
            entry_local_order_id, entry_exchange_order_id, strategy_group_id,
            symbol, side, entry_filled_qty, entry_avg_price, status,
            runner_qty, protection_complete, reconciled_with_exchange,
            first_blocker, blockers, warnings, authority_boundary,
            created_at_ms, updated_at_ms
        ) VALUES (
            'exit-set-1', 'ticket-1', 'attempt-1', 'entry-local-1',
            'entry-exchange-1', 'SOR-001', 'ETHUSDT', 'long', 1, 100,
            :status, 0.5, false, false, 'open_position_without_valid_sl',
            '["open_position_without_valid_sl"]', '[]',
            'ticket_bound_exit_protection', 1770000000000, 1770000000000
        )
    """


def _insert_lifecycle_event_sql() -> str:
    return """
        INSERT INTO brc_ticket_bound_lifecycle_events (
            lifecycle_event_id, lifecycle_run_id, ticket_id,
            protected_submit_attempt_id, event_type, event_payload, created_at_ms
        ) VALUES (
            'event-1', 'lifecycle-1', 'ticket-1', 'attempt-1',
            :event_type, '{}', 1770000000000
        )
    """
