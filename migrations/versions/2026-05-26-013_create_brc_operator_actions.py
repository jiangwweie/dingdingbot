"""Create BRC operator action ledger

Revision ID: 013
Revises: 012
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "brc_operator_actions",
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=True),
        sa.Column("plan_id", sa.String(length=128), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("draft_action", sa.String(length=64), nullable=False),
        sa.Column("http_method", sa.String(length=16), nullable=False),
        sa.Column("endpoint_path", sa.Text(), nullable=True),
        sa.Column("executable", sa.Boolean(), nullable=False),
        sa.Column("confirmation_phrase_id", sa.String(length=128), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("confirmation_matched", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=True),
        sa.Column("decision_result", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("plan_json", _jsonb_type(), nullable=False),
        sa.Column("result_json", _jsonb_type(), nullable=True),
        sa.Column("result_summary_json", _jsonb_type(), nullable=True),
        sa.Column("mutation_executed", sa.Boolean(), nullable=False),
        sa.Column("withdrawal_executed", sa.Boolean(), nullable=False),
        sa.Column("live_ready", sa.Boolean(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("executed_at_ms", sa.BIGINT(), nullable=True),
        sa.CheckConstraint(
            "draft_action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', 'unknown')",
            name="ck_brc_operator_actions_draft_action",
        ),
        sa.CheckConstraint(
            "decision_result IN ('planned', 'executed', 'blocked')",
            name="ck_brc_operator_actions_decision_result",
        ),
        sa.CheckConstraint("mutation_executed = false", name="ck_brc_operator_actions_no_mutation"),
        sa.CheckConstraint("withdrawal_executed = false", name="ck_brc_operator_actions_no_withdrawal"),
        sa.CheckConstraint("live_ready = false", name="ck_brc_operator_actions_no_live"),
        sa.PrimaryKeyConstraint("action_id"),
    )
    op.create_index(
        "idx_brc_operator_actions_campaign_time",
        "brc_operator_actions",
        ["campaign_id", "created_at_ms"],
        unique=False,
    )
    op.create_index(
        "idx_brc_operator_actions_decision_time",
        "brc_operator_actions",
        ["decision_result", "created_at_ms"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_brc_operator_actions_decision_time", table_name="brc_operator_actions")
    op.drop_index("idx_brc_operator_actions_campaign_time", table_name="brc_operator_actions")
    op.drop_table("brc_operator_actions")
