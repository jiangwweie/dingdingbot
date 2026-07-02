"""Create BRC review decision ledger

Revision ID: 014
Revises: 013
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "brc_review_decisions",
        sa.Column("review_id", sa.String(length=128), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("source_action_id", sa.String(length=128), nullable=True),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("next_recommended_task", sa.String(length=256), nullable=False),
        sa.Column("testnet_only", sa.Boolean(), nullable=False),
        sa.Column("real_live_authorized", sa.Boolean(), nullable=False),
        sa.Column("withdrawal_authorized", sa.Boolean(), nullable=False),
        sa.Column("strategy_execution_authorized", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("metadata", _jsonb_type(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('accepted', 'needs_followup', 'next_campaign_blocked', 'testnet_rehearsal_authorized')",
            name="ck_brc_review_decisions_decision",
        ),
        sa.CheckConstraint("testnet_only = true", name="ck_brc_review_decisions_testnet_only"),
        sa.CheckConstraint("real_live_authorized = false", name="ck_brc_review_decisions_no_live"),
        sa.CheckConstraint("withdrawal_authorized = false", name="ck_brc_review_decisions_no_withdrawal"),
        sa.CheckConstraint(
            "strategy_execution_authorized = false",
            name="ck_brc_review_decisions_no_strategy_execution",
        ),
        sa.PrimaryKeyConstraint("review_id"),
    )
    op.create_index(
        "idx_brc_review_decisions_campaign_time",
        "brc_review_decisions",
        ["campaign_id", "created_at_ms"],
        unique=False,
    )
    op.create_index(
        "idx_brc_review_decisions_decision_time",
        "brc_review_decisions",
        ["decision", "created_at_ms"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_brc_review_decisions_decision_time", table_name="brc_review_decisions")
    op.drop_index("idx_brc_review_decisions_campaign_time", table_name="brc_review_decisions")
    op.drop_table("brc_review_decisions")
