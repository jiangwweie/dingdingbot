"""Create runtime campaign state transition ledger

Revision ID: 011
Revises: 010
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "runtime_campaign_state_transitions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=False),
        sa.Column("target_status", sa.String(length=32), nullable=False),
        sa.Column("next_status", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("rule_reason_code", sa.String(length=128), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("active_strategy_contract_id", sa.String(length=128), nullable=True),
        sa.Column("active_session_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", _jsonb_type(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "previous_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_previous_status",
        ),
        sa.CheckConstraint(
            "target_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_target_status",
        ),
        sa.CheckConstraint(
            "next_status IN ('observe', 'armed', 'paused', 'profit_protect', "
            "'loss_locked', 'hard_locked', 'closed')",
            name="ck_runtime_campaign_state_transitions_next_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_runtime_campaign_state_transitions_scope_seq",
        "runtime_campaign_state_transitions",
        ["scope_key", "sequence_number"],
        unique=True,
    )
    op.create_index(
        "idx_runtime_campaign_state_transitions_scope_time",
        "runtime_campaign_state_transitions",
        ["scope_key", "occurred_at_ms"],
        unique=False,
    )
    op.create_index(
        "idx_runtime_campaign_state_transitions_trigger",
        "runtime_campaign_state_transitions",
        ["trigger"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_runtime_campaign_state_transitions_trigger",
        table_name="runtime_campaign_state_transitions",
    )
    op.drop_index(
        "idx_runtime_campaign_state_transitions_scope_time",
        table_name="runtime_campaign_state_transitions",
    )
    op.drop_index(
        "uq_runtime_campaign_state_transitions_scope_seq",
        table_name="runtime_campaign_state_transitions",
    )
    op.drop_table("runtime_campaign_state_transitions")
