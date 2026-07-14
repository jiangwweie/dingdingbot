from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-14-121_add_exit_execution_safety.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_121_exit_execution_safety", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_121_adds_durable_exit_execution_truth_with_safe_defaults():
    migration = _load_migration()
    assert migration.revision == "121"
    assert migration.down_revision == "120"

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    orders = sa.Table(
        "brc_ticket_bound_exit_protection_orders",
        metadata,
        sa.Column("exit_protection_order_id", sa.String, primary_key=True),
        sa.Column("exit_protection_set_id", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
    )
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        sa.Column("exchange_command_id", sa.String, primary_key=True),
    )
    outcomes = sa.Table(
        "brc_live_outcome_ledger",
        metadata,
        sa.Column("live_outcome_id", sa.String, primary_key=True),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            orders.insert().values(
                exit_protection_order_id="legacy-order",
                exit_protection_set_id="set-1",
                role="TP1",
                status="open",
            )
        )
        conn.execute(commands.insert().values(exchange_command_id="legacy-command"))
        conn.execute(outcomes.insert().values(live_outcome_id="legacy-outcome"))
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op

        inspector = sa.inspect(conn)
        order_columns = {
            item["name"]: item
            for item in inspector.get_columns(
                "brc_ticket_bound_exit_protection_orders"
            )
        }
        command_columns = {
            item["name"]: item
            for item in inspector.get_columns("brc_ticket_bound_exchange_commands")
        }
        outcome_columns = {
            item["name"]: item
            for item in inspector.get_columns("brc_live_outcome_ledger")
        }
        legacy_order = conn.execute(
            sa.text(
                "SELECT generation FROM brc_ticket_bound_exit_protection_orders "
                "WHERE exit_protection_order_id = 'legacy-order'"
            )
        ).mappings().one()
        legacy_command = conn.execute(
            sa.text(
                "SELECT execution_style, time_in_force, post_only, "
                "market_fallback_allowed FROM brc_ticket_bound_exchange_commands "
                "WHERE exchange_command_id = 'legacy-command'"
            )
        ).mappings().one()
        indexes = {
            item["name"]
            for item in inspector.get_indexes(
                "brc_ticket_bound_exit_protection_orders"
            )
        }

    assert order_columns["generation"]["nullable"] is False
    assert isinstance(order_columns["generation"]["type"], sa.Integer)
    assert {
        "execution_style",
        "time_in_force",
        "post_only",
        "market_fallback_allowed",
    } <= command_columns.keys()
    assert command_columns["execution_style"]["nullable"] is True
    assert command_columns["time_in_force"]["nullable"] is True
    assert command_columns["post_only"]["nullable"] is False
    assert command_columns["market_fallback_allowed"]["nullable"] is False
    assert {
        "tp1_liquidity_role",
        "tp1_fee",
        "tp1_fee_asset",
        "exchange_configured_initial_leverage",
        "effective_account_exposure_leverage",
    } <= outcome_columns.keys()
    assert legacy_order["generation"] == 1
    assert legacy_command == {
        "execution_style": None,
        "time_in_force": None,
        "post_only": 0,
        "market_fallback_allowed": 0,
    }
    assert "idx_brc_exit_order_active_generation" in indexes

