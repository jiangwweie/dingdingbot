"""Create ticket-bound runner mutation commands.

Revision ID: 095
Revises: 094
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "095"
down_revision: Union[str, None] = "094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "brc_ticket_bound_runner_mutation_commands"


def upgrade() -> None:
    if _has_table(TABLE):
        return
    json_t = _json_type()
    op.create_table(
        TABLE,
        sa.Column("runner_mutation_command_id", sa.String(192), primary_key=True),
        sa.Column("exit_protection_set_id", sa.String(192), nullable=False),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("old_sl_order_id", sa.String(192), nullable=False),
        sa.Column("old_sl_exchange_order_id", sa.String(192), nullable=False),
        sa.Column("tp1_order_id", sa.String(192), nullable=False),
        sa.Column("tp1_exchange_order_id", sa.String(192), nullable=False),
        sa.Column("runner_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("first_blocker", sa.String(160), nullable=True),
        sa.Column("blockers", json_t, nullable=False, server_default="[]"),
        sa.Column("command_plan", json_t, nullable=False),
        sa.Column("result_payload", json_t, nullable=False, server_default="{}"),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_runner_cmd_side"),
        sa.CheckConstraint(
            "status IN ('prepared', 'result_recorded', 'blocked', 'failed')",
            name="ck_brc_runner_cmd_status",
        ),
        sa.CheckConstraint("runner_qty > 0", name="ck_brc_runner_cmd_qty_positive"),
        sa.CheckConstraint(
            "status <> 'blocked' OR first_blocker IS NOT NULL",
            name="ck_brc_runner_cmd_blocked_has_blocker",
        ),
        sa.UniqueConstraint(
            "exit_protection_set_id",
            name="uq_brc_runner_cmd_exit_protection_set",
        ),
    )
    op.create_index(
        "idx_brc_runner_cmd_ticket_status",
        TABLE,
        ["ticket_id", "status"],
    )


def downgrade() -> None:
    op.drop_table(TABLE)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.dialects.postgresql.JSONB()
    return sa.JSON()


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()
