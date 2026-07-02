"""Create runtime campaign state table

Revision ID: 010
Revises: 009
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_campaign_state",
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("active_strategy_contract_id", sa.String(length=128), nullable=True),
        sa.Column("active_session_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_status",
        ),
        sa.PrimaryKeyConstraint("scope_key"),
    )
    op.create_index(
        "idx_runtime_campaign_state_updated_at",
        "runtime_campaign_state",
        ["updated_at_ms"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_runtime_campaign_state_updated_at",
        table_name="runtime_campaign_state",
    )
    op.drop_table("runtime_campaign_state")
