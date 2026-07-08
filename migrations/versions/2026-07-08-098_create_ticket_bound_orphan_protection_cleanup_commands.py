"""Create ticket-bound orphan protection cleanup commands.

Revision ID: 098
Revises: 097
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "098"
down_revision: Union[str, None] = "097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "brc_ticket_bound_orphan_protection_cleanup_commands"


def upgrade() -> None:
    if _has_table(TABLE):
        return
    json_t = _json_type()
    op.create_table(
        TABLE,
        sa.Column("orphan_protection_cleanup_command_id", sa.String(192), primary_key=True),
        sa.Column("exit_protection_set_id", sa.String(192), nullable=False),
        sa.Column("lifecycle_run_id", sa.String(192), nullable=False),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("cleanup_action", sa.String(96), nullable=False),
        sa.Column("first_blocker", sa.String(160), nullable=True),
        sa.Column("blockers", json_t, nullable=False, server_default="[]"),
        sa.Column("command_plan", json_t, nullable=False),
        sa.Column("result_payload", json_t, nullable=False, server_default="{}"),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_orphan_cleanup_side"),
        sa.CheckConstraint(
            "status IN ('prepared', 'result_recorded', 'blocked', 'failed')",
            name="ck_brc_orphan_cleanup_status",
        ),
        sa.CheckConstraint(
            "cleanup_action IN ('cancel_flat_position_live_protection')",
            name="ck_brc_orphan_cleanup_action",
        ),
        sa.CheckConstraint(
            "status <> 'blocked' OR first_blocker IS NOT NULL",
            name="ck_brc_orphan_cleanup_blocked_has_blocker",
        ),
        sa.UniqueConstraint(
            "exit_protection_set_id",
            name="uq_brc_orphan_cleanup_exit_protection_set",
        ),
    )
    op.create_index(
        "idx_brc_orphan_cleanup_ticket_status",
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
