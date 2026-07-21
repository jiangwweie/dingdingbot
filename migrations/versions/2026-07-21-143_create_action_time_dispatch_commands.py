"""Create the durable Action-Time command boundary.

Revision ID: 143
Revises: 142
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "143"
down_revision: Union[str, None] = "142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_action_time_dispatch_commands"


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("dispatch_command_id", sa.String(192), primary_key=True),
        sa.Column("action_time_invocation_id", sa.String(192), nullable=False),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("operation_layer_handoff_id", sa.String(192), nullable=False),
        sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
        sa.Column("runtime_safety_snapshot_id", sa.String(192), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("runtime_profile_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=True),
        sa.Column("first_blocker", sa.Text(), nullable=True),
        sa.Column("claim_owner", sa.String(192), nullable=True),
        sa.Column("claim_token", sa.String(192), nullable=True),
        sa.Column("claim_expires_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_action_time_dispatch_side"),
        sa.CheckConstraint(
            "state IN ('pending', 'claimed', 'submit_prepared', 'blocked')",
            name="ck_brc_action_time_dispatch_state",
        ),
        sa.CheckConstraint(
            "state <> 'claimed' OR (claim_owner IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at_ms IS NOT NULL)",
            name="ck_brc_action_time_dispatch_claim",
        ),
        sa.UniqueConstraint(
            "operation_submit_command_id",
            name="uq_brc_action_time_dispatch_operation_submit",
        ),
    )
    op.create_index(
        "idx_brc_action_time_dispatch_pending",
        TABLE,
        ["state", "created_at_ms"],
    )


def downgrade() -> None:
    # Forward-only runtime audit lineage.
    return
