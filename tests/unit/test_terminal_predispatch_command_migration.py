from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-13-120_reconcile_terminal_predispatch_commands.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_120_predispatch", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_reconciles_only_terminal_never_dispatched_commands() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    attempts = sa.Table(
        "brc_ticket_bound_protected_submit_attempts",
        metadata,
        sa.Column("protected_submit_attempt_id", sa.String, primary_key=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("exchange_write_called", sa.Boolean, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
    )
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        sa.Column("exchange_command_id", sa.String, primary_key=True),
        sa.Column("protected_submit_attempt_id", sa.String, nullable=False),
        sa.Column("command_source", sa.String, nullable=False),
        sa.Column("command_state", sa.String, nullable=False),
        sa.Column("outcome_class", sa.String, nullable=False),
        sa.Column("dispatch_started_at_ms", sa.BigInteger),
        sa.Column("execution_attempt_count", sa.Integer, nullable=False),
        sa.Column("exchange_order_id", sa.String),
        sa.Column("exchange_error_code", sa.String),
        sa.Column("exchange_error_message", sa.String),
        sa.Column("exchange_result", sa.JSON, nullable=False),
        sa.Column("resolved_at_ms", sa.BigInteger),
        sa.Column("updated_at_ms", sa.BigInteger, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            attempts.insert(),
            [
                {"protected_submit_attempt_id": "failed", "status": "submit_failed", "exchange_write_called": False, "updated_at_ms": 200},
                {"protected_submit_attempt_id": "live", "status": "submit_prepared", "exchange_write_called": False, "updated_at_ms": 201},
            ],
        )
        conn.execute(
            commands.insert(),
            [
                {"exchange_command_id": "repair", "protected_submit_attempt_id": "failed", "command_source": "protected_submit", "command_state": "prepared", "outcome_class": "pending", "dispatch_started_at_ms": None, "execution_attempt_count": 0, "exchange_order_id": None, "exchange_result": {}, "updated_at_ms": 100},
                {"exchange_command_id": "keep", "protected_submit_attempt_id": "live", "command_source": "protected_submit", "command_state": "prepared", "outcome_class": "pending", "dispatch_started_at_ms": None, "execution_attempt_count": 0, "exchange_order_id": None, "exchange_result": {}, "updated_at_ms": 101},
            ],
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        rows = {
            row["exchange_command_id"]: row
            for row in conn.execute(sa.select(commands)).mappings()
        }

    assert rows["repair"]["command_state"] == "reconciled_absent"
    assert rows["repair"]["outcome_class"] == "reconciled_absence"
    assert rows["repair"]["exchange_error_code"] == (
        "protected_submit_terminal_before_dispatch"
    )
    assert rows["repair"]["resolved_at_ms"] == 200
    assert rows["repair"]["updated_at_ms"] == 200
    assert rows["keep"]["command_state"] == "prepared"
