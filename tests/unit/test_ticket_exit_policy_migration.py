from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations/versions/2026-07-14-122_add_ticket_exit_policy_core.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_122_ticket_exit_policy_core", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_122_adds_future_only_policy_authority_and_projection():
    migration = _load_migration()
    assert migration.revision == "122"
    assert migration.down_revision == "121"

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    tickets = sa.Table(
        "brc_action_time_tickets",
        metadata,
        sa.Column("ticket_id", sa.String(192), primary_key=True),
    )
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands",
        metadata,
        sa.Column("exchange_command_id", sa.String(192), primary_key=True),
        sa.Column(
            "command_source",
            sa.String(64),
            nullable=False,
            server_default="protected_submit",
        ),
    )
    capabilities = sa.Table(
        "brc_runtime_capabilities_current",
        metadata,
        sa.Column("capability_id", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("certification_ref", sa.String(256), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(tickets.insert().values(ticket_id="legacy-ticket"))
        conn.execute(
            commands.insert().values(
                exchange_command_id="legacy-command",
                command_source="protected_submit",
            )
        )
        previous_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = previous_op

        inspector = sa.inspect(conn)
        policy_columns = {
            item["name"]
            for item in inspector.get_columns("brc_strategy_exit_policies")
        }
        projection_columns = {
            item["name"]
            for item in inspector.get_columns("brc_ticket_exit_policy_current")
        }
        ticket_columns = {
            item["name"]
            for item in inspector.get_columns("brc_action_time_tickets")
        }
        policy_indexes = {
            item["name"]: item
            for item in inspector.get_indexes("brc_strategy_exit_policies")
        }
        legacy = conn.execute(
            sa.text(
                "SELECT exit_policy_id, exit_policy_version, "
                "exit_policy_snapshot, exit_policy_hash "
                "FROM brc_action_time_tickets WHERE ticket_id = 'legacy-ticket'"
            )
        ).mappings().one()
        capability = conn.execute(
            sa.select(capabilities).where(
                capabilities.c.capability_id == "ticket_exit_policy_v1"
            )
        ).mappings().one()
        assert conn.execute(
            sa.text("SELECT count(*) FROM brc_strategy_exit_policies")
        ).scalar_one() == 0

        conn.execute(
            sa.text(
                "INSERT INTO brc_strategy_exit_policies ("
                "exit_policy_id, exit_policy_version, strategy_group_id, "
                "strategy_version, event_spec_id, event_spec_version, side, "
                "policy_family, policy_payload, payload_hash, status, approved_by, "
                "approved_at_ms, created_at_ms"
                ") VALUES ("
                "'p1', '1', 'SOR-001', '1', 'SOR-LONG', '1', 'long', "
                "'right_tail_runner', '{}', 'hash-1', 'current', 'owner', 1, 1)"
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(
                sa.text(
                    "INSERT INTO brc_strategy_exit_policies ("
                    "exit_policy_id, exit_policy_version, strategy_group_id, "
                    "strategy_version, event_spec_id, event_spec_version, side, "
                    "policy_family, policy_payload, payload_hash, status, approved_by, "
                    "approved_at_ms, created_at_ms"
                    ") VALUES ("
                    "'p2', '1', 'SOR-001', '1', 'SOR-LONG', '1', 'long', "
                    "'right_tail_runner', '{}', 'hash-2', 'current', 'owner', 2, 2)"
                )
            )

    assert {
        "exit_policy_id",
        "exit_policy_version",
        "strategy_group_id",
        "strategy_version",
        "event_spec_id",
        "event_spec_version",
        "side",
        "policy_family",
        "policy_payload",
        "payload_hash",
        "status",
        "approved_by",
        "approved_at_ms",
        "created_at_ms",
    } <= policy_columns
    assert {
        "exit_policy_id",
        "exit_policy_version",
        "exit_policy_snapshot",
        "exit_policy_hash",
    } <= ticket_columns
    assert {
        "ticket_id",
        "exit_protection_set_id",
        "exit_policy_id",
        "exit_policy_version",
        "exit_policy_hash",
        "exit_execution_snapshot",
        "exit_execution_hash",
        "actual_r_per_unit",
        "resolved_tp1_price",
        "resolved_tp1_target_qty",
        "tp1_cumulative_filled_qty",
        "tp1_completion_state",
        "remaining_position_qty",
        "runner_break_even_floor",
        "runner_floor_applied_at_ms",
        "last_evaluated_watermark_ms",
        "next_evaluation_not_before_ms",
        "active_runner_generation",
        "pending_generation",
        "updated_at_ms",
    } <= projection_columns
    assert policy_indexes["uq_brc_exit_policy_current_scope"]["unique"] == 1
    assert legacy["exit_policy_id"] == "legacy_unbound"
    assert legacy["exit_policy_version"] == "legacy_unbound"
    snapshot = legacy["exit_policy_snapshot"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    assert snapshot == {
        "binding_kind": "legacy_unbound",
        "historical_semantics_not_synthesized": True,
    }
    assert legacy["exit_policy_hash"] == migration.LEGACY_EXIT_POLICY_HASH
    assert capability["status"] == "disabled"
    assert capability["certification_ref"] == (
        "migration-122:future-only-fail-disabled"
    )


def test_migration_122_extends_the_one_command_source_constraint():
    migration = _load_migration()
    assert "exit_policy_runner" in migration.COMMAND_SOURCES
    assert "exit_policy_close" in migration.COMMAND_SOURCES
    assert "protected_submit" in migration.COMMAND_SOURCES
    assert "orphan_cleanup" in migration.COMMAND_SOURCES
