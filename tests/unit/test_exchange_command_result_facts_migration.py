from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-21-144_add_exchange_command_result_facts.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_144_exchange_command_result_facts",
        MIGRATION_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_144_adds_typed_exchange_result_facts_without_guessing_history() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        sa.Column("exchange_command_id", sa.String, primary_key=True),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("exchange_result", sa.JSON, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            commands.insert().values(
                exchange_command_id="historical-command",
                amount="0.010",
                exchange_result={"filled_qty": "0.005"},
            )
        )
        migration = _load_migration()
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        columns = {
            column["name"]
            for column in sa.inspect(conn).get_columns(
                "brc_ticket_bound_exchange_commands"
            )
        }
        row = conn.execute(
            sa.text(
                "SELECT executed_qty, average_exec_price, result_facts_complete "
                "FROM brc_ticket_bound_exchange_commands "
                "WHERE exchange_command_id = 'historical-command'"
            )
        ).mappings().one()

    assert {
        "exchange_order_status",
        "executed_qty",
        "average_exec_price",
        "exchange_observed_at_ms",
        "result_facts_complete",
    } <= columns
    assert row["executed_qty"] is None
    assert row["average_exec_price"] is None
    assert row["result_facts_complete"] in {False, 0}
