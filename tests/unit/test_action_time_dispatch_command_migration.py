from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-21-143_create_action_time_dispatch_commands.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_143_action_time_dispatch", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_143_creates_durable_dispatch_claim_boundary() -> None:
    migration = _load_migration()
    assert migration.revision == "143"
    assert migration.down_revision == "142"
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = previous_op
        table = sa.Table(
            "brc_action_time_dispatch_commands", sa.MetaData(), autoload_with=conn
        )
        assert {
            "dispatch_command_id",
            "operation_submit_command_id",
            "runtime_safety_snapshot_id",
            "state",
            "claim_token",
            "claim_expires_at_ms",
            "protected_submit_attempt_id",
        } <= set(table.c.keys())
        row = _row()
        conn.execute(table.insert().values(**row))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(table.insert().values(**{**row, "dispatch_command_id": "dispatch:two"}))
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(table.insert().values(**{**row, "dispatch_command_id": "dispatch:three", "operation_submit_command_id": "submit:three", "state": "invalid"}))


def _row() -> dict[str, object]:
    return {
        "dispatch_command_id": "dispatch:one",
        "action_time_invocation_id": "invocation:one",
        "ticket_id": "ticket:one",
        "operation_layer_handoff_id": "handoff:one",
        "operation_submit_command_id": "submit:one",
        "runtime_safety_snapshot_id": "safety:one",
        "strategy_group_id": "SOR-001",
        "symbol": "ETHUSDT",
        "side": "long",
        "runtime_profile_id": "profile:one",
        "state": "pending",
        "protected_submit_attempt_id": None,
        "first_blocker": None,
        "claim_owner": None,
        "claim_token": None,
        "claim_expires_at_ms": None,
        "created_at_ms": 1,
        "updated_at_ms": 1,
    }
