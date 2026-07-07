"""Create ticket-bound order lifecycle and exit protection tables.

Revision ID: 091
Revises: 090
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "091"
down_revision: Union[str, None] = "090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LIFECYCLE_TABLE = "brc_ticket_bound_order_lifecycle_runs"
SET_TABLE = "brc_ticket_bound_exit_protection_sets"
ORDER_TABLE = "brc_ticket_bound_exit_protection_orders"
EVENT_TABLE = "brc_ticket_bound_lifecycle_events"


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    json_t = _json_type()

    if not _has_table(LIFECYCLE_TABLE):
        op.create_table(
            LIFECYCLE_TABLE,
            sa.Column("lifecycle_run_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("runtime_profile_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(96), nullable=False),
            sa.Column("entry_local_order_id", sa.String(192), nullable=True),
            sa.Column("entry_exchange_order_id", sa.String(192), nullable=True),
            sa.Column("entry_fill_confirmed", sa.Boolean(), nullable=False),
            sa.Column("entry_filled_qty", sa.Numeric(36, 18), nullable=True),
            sa.Column("entry_avg_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("exit_protection_set_id", sa.String(192), nullable=True),
            sa.Column("first_blocker", sa.String(160), nullable=True),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("warnings", json_t, nullable=False, server_default="[]"),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_lifecycle_side"),
            sa.CheckConstraint(
                "status IN ('entry_submit_sent', 'entry_fill_pending', "
                "'entry_filled', 'exit_protection_submitted', "
                "'position_protected', 'blocked')",
                name="ck_brc_lifecycle_status",
            ),
            sa.CheckConstraint(
                "status <> 'position_protected' OR "
                "(entry_fill_confirmed = true "
                "AND exit_protection_set_id IS NOT NULL "
                "AND first_blocker IS NULL)",
                name="ck_brc_lifecycle_position_protected_truth",
            ),
            sa.CheckConstraint(
                "status <> 'blocked' OR first_blocker IS NOT NULL",
                name="ck_brc_lifecycle_blocked_has_blocker",
            ),
            sa.UniqueConstraint("ticket_id", name="uq_brc_lifecycle_ticket"),
        )
        op.create_index(
            "idx_brc_lifecycle_attempt",
            LIFECYCLE_TABLE,
            ["protected_submit_attempt_id", "status"],
        )
        op.create_index(
            "idx_brc_lifecycle_scope_status",
            LIFECYCLE_TABLE,
            ["strategy_group_id", "symbol", "side", "status"],
        )

    if not _has_table(SET_TABLE):
        op.create_table(
            SET_TABLE,
            sa.Column("exit_protection_set_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
            sa.Column("entry_local_order_id", sa.String(192), nullable=False),
            sa.Column("entry_exchange_order_id", sa.String(192), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("entry_filled_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("entry_avg_price", sa.Numeric(36, 18), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("sl_order_id", sa.String(192), nullable=True),
            sa.Column("tp1_order_id", sa.String(192), nullable=True),
            sa.Column("runner_qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("protection_complete", sa.Boolean(), nullable=False),
            sa.Column("reconciled_with_exchange", sa.Boolean(), nullable=False),
            sa.Column("first_blocker", sa.String(160), nullable=True),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("warnings", json_t, nullable=False, server_default="[]"),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_exit_set_side"),
            sa.CheckConstraint(
                "status IN ('pending', 'materializing', 'submitted', "
                "'reconciled', 'failed', 'closed')",
                name="ck_brc_exit_set_status",
            ),
            sa.CheckConstraint(
                "protection_complete = false OR "
                "(sl_order_id IS NOT NULL AND tp1_order_id IS NOT NULL)",
                name="ck_brc_exit_set_complete_refs",
            ),
            sa.CheckConstraint(
                "status NOT IN ('submitted', 'reconciled') OR protection_complete = true",
                name="ck_brc_exit_set_submitted_complete",
            ),
            sa.UniqueConstraint("ticket_id", name="uq_brc_exit_set_ticket"),
        )
        op.create_index(
            "idx_brc_exit_set_attempt",
            SET_TABLE,
            ["protected_submit_attempt_id", "status"],
        )

    if not _has_table(ORDER_TABLE):
        op.create_table(
            ORDER_TABLE,
            sa.Column("exit_protection_order_id", sa.String(192), primary_key=True),
            sa.Column("exit_protection_set_id", sa.String(192), nullable=False),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("role", sa.String(64), nullable=False),
            sa.Column("local_order_id", sa.String(192), nullable=False),
            sa.Column("exchange_order_id", sa.String(192), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("order_type", sa.String(64), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("qty", sa.Numeric(36, 18), nullable=False),
            sa.Column("price", sa.Numeric(36, 18), nullable=True),
            sa.Column("trigger_price", sa.Numeric(36, 18), nullable=True),
            sa.Column("reduce_only", sa.Boolean(), nullable=False),
            sa.Column("replaces_exit_protection_order_id", sa.String(192), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "role IN ('SL', 'TP1', 'SL_ADJUSTMENT', 'RUNNER_SL')",
                name="ck_brc_exit_order_role",
            ),
            sa.CheckConstraint(
                "status IN ('planned', 'submitted', 'open', 'partially_filled', "
                "'filled', 'cancel_pending', 'cancelled', 'replace_pending', "
                "'replaced', 'failed')",
                name="ck_brc_exit_order_status",
            ),
            sa.CheckConstraint(
                "side IN ('buy', 'sell')",
                name="ck_brc_exit_order_side",
            ),
            sa.CheckConstraint(
                "reduce_only = true",
                name="ck_brc_exit_order_reduce_only",
            ),
            sa.CheckConstraint(
                "role <> 'TP1' OR price IS NOT NULL",
                name="ck_brc_exit_order_tp1_price",
            ),
            sa.CheckConstraint(
                "role NOT IN ('SL', 'SL_ADJUSTMENT', 'RUNNER_SL') "
                "OR trigger_price IS NOT NULL",
                name="ck_brc_exit_order_sl_trigger",
            ),
            sa.UniqueConstraint(
                "exit_protection_set_id",
                "role",
                "local_order_id",
                name="uq_brc_exit_order_set_role_local",
            ),
        )
        op.create_index(
            "idx_brc_exit_order_set",
            ORDER_TABLE,
            ["exit_protection_set_id", "role", "status"],
        )
        op.create_index(
            "idx_brc_exit_order_ticket",
            ORDER_TABLE,
            ["ticket_id", "status"],
        )

    if not _has_table(EVENT_TABLE):
        op.create_table(
            EVENT_TABLE,
            sa.Column("lifecycle_event_id", sa.String(192), primary_key=True),
            sa.Column("lifecycle_run_id", sa.String(192), nullable=False),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
            sa.Column("event_type", sa.String(96), nullable=False),
            sa.Column("event_payload", json_t, nullable=False, server_default="{}"),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "event_type IN ('entry_submitted', 'entry_filled', "
                "'exit_protection_materialization_started', 'sl_submitted', "
                "'tp1_submitted', 'exit_protection_reconciled', 'hard_stopped')",
                name="ck_brc_lifecycle_event_type",
            ),
        )
        op.create_index(
            "idx_brc_lifecycle_event_run",
            EVENT_TABLE,
            ["lifecycle_run_id", "created_at_ms"],
        )


def downgrade() -> None:
    for table_name in (EVENT_TABLE, ORDER_TABLE, SET_TABLE, LIFECYCLE_TABLE):
        if _has_table(table_name):
            op.drop_table(table_name)
