"""Add future-only Ticket exit-policy authority and current projection.

Revision ID: 122
Revises: 121
Create Date: 2026-07-14
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "122"
down_revision: Union[str, None] = "121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POLICY_TABLE = "brc_strategy_exit_policies"
TICKET_TABLE = "brc_action_time_tickets"
CURRENT_TABLE = "brc_ticket_exit_policy_current"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
CAPABILITY_TABLE = "brc_runtime_capabilities_current"
CURRENT_SCOPE_INDEX = "uq_brc_exit_policy_current_scope"
COMMAND_SOURCE_CHECK = "ck_brc_exchange_command_source"
COMMAND_SOURCES = (
    "protected_submit",
    "protection_recovery",
    "runner_mutation",
    "orphan_cleanup",
    "exit_policy_runner",
    "exit_policy_close",
)
LEGACY_EXIT_POLICY_SNAPSHOT = {
    "binding_kind": "legacy_unbound",
    "historical_semantics_not_synthesized": True,
}
_LEGACY_CANONICAL = json.dumps(
    LEGACY_EXIT_POLICY_SNAPSHOT,
    sort_keys=True,
    separators=(",", ":"),
)
LEGACY_EXIT_POLICY_HASH = sha256(_LEGACY_CANONICAL.encode("utf-8")).hexdigest()


def upgrade() -> None:
    _create_policy_table()
    _extend_ticket_table()
    _create_current_projection()
    _ensure_command_source_constraint()
    _seed_disabled_capability_if_supported()


def downgrade() -> None:
    _drop_command_source_constraint()
    if _has_table(CURRENT_TABLE):
        op.drop_table(CURRENT_TABLE)
    if _has_table(TICKET_TABLE):
        for name in (
            "exit_policy_hash",
            "exit_policy_snapshot",
            "exit_policy_version",
            "exit_policy_id",
        ):
            _drop_column_if_present(TICKET_TABLE, name)
    if _has_table(POLICY_TABLE):
        op.drop_table(POLICY_TABLE)


def _create_policy_table() -> None:
    if _has_table(POLICY_TABLE):
        return
    op.create_table(
        POLICY_TABLE,
        sa.Column("exit_policy_id", sa.String(192), primary_key=True),
        sa.Column("exit_policy_version", sa.String(96), primary_key=True),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("strategy_version", sa.String(160), nullable=False),
        sa.Column("event_spec_id", sa.String(160), nullable=False),
        sa.Column("event_spec_version", sa.String(160), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("policy_family", sa.String(64), nullable=False),
        sa.Column("policy_payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "side IN ('long', 'short')",
            name="ck_brc_exit_policy_side",
        ),
        sa.CheckConstraint(
            "policy_family IN ('right_tail_runner', 'fixed_targets', "
            "'lifecycle_only')",
            name="ck_brc_exit_policy_family",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'certified_disabled', 'current', 'retired')",
            name="ck_brc_exit_policy_status",
        ),
        sa.CheckConstraint(
            "(status <> 'current' AND status <> 'retired') OR "
            "(approved_by IS NOT NULL AND approved_at_ms IS NOT NULL)",
            name="ck_brc_exit_policy_approval",
        ),
        sa.UniqueConstraint("payload_hash", name="uq_brc_exit_policy_payload_hash"),
    )
    op.create_index(
        CURRENT_SCOPE_INDEX,
        POLICY_TABLE,
        [
            "strategy_group_id",
            "strategy_version",
            "event_spec_id",
            "event_spec_version",
            "side",
        ],
        unique=True,
        postgresql_where=sa.text("status = 'current'"),
        sqlite_where=sa.text("status = 'current'"),
    )


def _extend_ticket_table() -> None:
    if not _has_table(TICKET_TABLE):
        return
    additions = (
        sa.Column(
            "exit_policy_id",
            sa.String(192),
            nullable=True,
        ),
        sa.Column(
            "exit_policy_version",
            sa.String(96),
            nullable=True,
        ),
        sa.Column(
            "exit_policy_snapshot",
            sa.JSON(),
            nullable=True,
        ),
        sa.Column(
            "exit_policy_hash",
            sa.String(64),
            nullable=True,
        ),
    )
    for column in additions:
        _add_column_if_missing(TICKET_TABLE, column)
    tickets = sa.Table(TICKET_TABLE, sa.MetaData(), autoload_with=op.get_bind())
    op.get_bind().execute(
        tickets.update()
        .where(tickets.c.exit_policy_id.is_(None))
        .values(
            exit_policy_id="legacy_unbound",
            exit_policy_version="legacy_unbound",
            exit_policy_snapshot=LEGACY_EXIT_POLICY_SNAPSHOT,
            exit_policy_hash=LEGACY_EXIT_POLICY_HASH,
        )
    )
    if op.get_bind().dialect.name != "sqlite":
        snapshot_json = json.dumps(
            LEGACY_EXIT_POLICY_SNAPSHOT,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        defaults = {
            "exit_policy_id": "legacy_unbound",
            "exit_policy_version": "legacy_unbound",
            "exit_policy_snapshot": snapshot_json,
            "exit_policy_hash": LEGACY_EXIT_POLICY_HASH,
        }
        for column in additions:
            op.alter_column(
                TICKET_TABLE,
                str(column.name),
                existing_type=column.type,
                nullable=False,
                server_default=defaults[str(column.name)],
            )


def _create_current_projection() -> None:
    if _has_table(CURRENT_TABLE):
        return
    op.create_table(
        CURRENT_TABLE,
        sa.Column("ticket_id", sa.String(192), primary_key=True),
        sa.Column("exit_protection_set_id", sa.String(192), nullable=True),
        sa.Column("exit_policy_id", sa.String(192), nullable=False),
        sa.Column("exit_policy_version", sa.String(96), nullable=False),
        sa.Column("exit_policy_hash", sa.String(64), nullable=False),
        sa.Column("exit_execution_snapshot", sa.JSON(), nullable=True),
        sa.Column("exit_execution_hash", sa.String(64), nullable=True),
        sa.Column("actual_r_per_unit", sa.Numeric(36, 18), nullable=True),
        sa.Column("resolved_tp1_price", sa.Numeric(36, 18), nullable=True),
        sa.Column("resolved_tp1_target_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column(
            "tp1_cumulative_filled_qty",
            sa.Numeric(36, 18),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "tp1_completion_state",
            sa.String(32),
            nullable=False,
            server_default="unfilled",
        ),
        sa.Column("remaining_position_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("state", sa.String(64), nullable=False, server_default="bound"),
        sa.Column("last_evaluated_watermark_ms", sa.BIGINT(), nullable=True),
        sa.Column("next_evaluation_not_before_ms", sa.BIGINT(), nullable=True),
        sa.Column("last_decision_kind", sa.String(64), nullable=True),
        sa.Column("last_reason_code", sa.String(192), nullable=True),
        sa.Column("active_runner_order_id", sa.String(192), nullable=True),
        sa.Column("active_runner_generation", sa.Integer(), nullable=True),
        sa.Column("active_runner_stop", sa.Numeric(36, 18), nullable=True),
        sa.Column("runner_break_even_floor", sa.Numeric(36, 18), nullable=True),
        sa.Column("runner_floor_applied_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("pending_runner_order_id", sa.String(192), nullable=True),
        sa.Column("pending_generation", sa.Integer(), nullable=True),
        sa.Column("replaced_runner_order_id", sa.String(192), nullable=True),
        sa.Column("first_blocker", sa.String(256), nullable=True),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "tp1_completion_state IN ('unfilled', 'partial', 'complete', "
            "'contradictory')",
            name="ck_brc_ticket_exit_tp1_completion",
        ),
        sa.CheckConstraint(
            "active_runner_generation IS NULL OR active_runner_generation > 0",
            name="ck_brc_ticket_exit_active_generation",
        ),
        sa.CheckConstraint(
            "pending_generation IS NULL OR pending_generation > 0",
            name="ck_brc_ticket_exit_pending_generation",
        ),
    )
    op.create_index(
        "idx_brc_ticket_exit_policy_due",
        CURRENT_TABLE,
        ["state", "next_evaluation_not_before_ms", "updated_at_ms"],
    )


def _ensure_command_source_constraint() -> None:
    if not _has_table(COMMAND_TABLE) or not _has_column(COMMAND_TABLE, "command_source"):
        return
    if COMMAND_SOURCE_CHECK in _check_constraint_names(COMMAND_TABLE):
        return
    condition = "command_source IN (" + ", ".join(
        repr(source) for source in COMMAND_SOURCES
    ) + ")"
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(COMMAND_TABLE, recreate="always") as batch_op:
            batch_op.create_check_constraint(COMMAND_SOURCE_CHECK, condition)
    else:
        op.create_check_constraint(
            COMMAND_SOURCE_CHECK,
            COMMAND_TABLE,
            condition,
        )


def _seed_disabled_capability_if_supported() -> None:
    if not _has_table(CAPABILITY_TABLE):
        return
    capabilities = sa.Table(
        CAPABILITY_TABLE,
        sa.MetaData(),
        autoload_with=op.get_bind(),
    )
    existing = op.get_bind().execute(
        sa.select(capabilities.c.capability_id).where(
            capabilities.c.capability_id == "ticket_exit_policy_v1"
        )
    ).first()
    if existing:
        return
    op.get_bind().execute(
        capabilities.insert().values(
            capability_id="ticket_exit_policy_v1",
            status="disabled",
            certification_ref="migration-122:future-only-fail-disabled",
            updated_at_ms=0,
        )
    )


def _drop_command_source_constraint() -> None:
    if not _has_table(COMMAND_TABLE):
        return
    if COMMAND_SOURCE_CHECK not in _check_constraint_names(COMMAND_TABLE):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(COMMAND_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(COMMAND_SOURCE_CHECK, type_="check")
    else:
        op.drop_constraint(COMMAND_SOURCE_CHECK, COMMAND_TABLE, type_="check")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _check_constraint_names(table_name: str) -> set[str]:
    return {
        str(item.get("name") or "")
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, str(column.name)):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if not _has_column(table_name, column_name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_column(column_name)
    else:
        op.drop_column(table_name, column_name)
