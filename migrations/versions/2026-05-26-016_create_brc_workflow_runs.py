"""Create BRC operator workflow run ledger

Revision ID: 016
Revises: 015
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "brc_workflow_runs",
        sa.Column("workflow_run_id", sa.String(length=128), nullable=False),
        sa.Column("llm_intent_id", sa.String(length=128), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confirmation_phrase_id", sa.String(length=128), nullable=False),
        sa.Column("confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("confirmation_matched", sa.Boolean(), nullable=False),
        sa.Column("confirmed_by", sa.String(length=128), nullable=True),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("result_json", _jsonb_type(), nullable=True),
        sa.Column("result_summary_json", _jsonb_type(), nullable=True),
        sa.Column("workflow_state_json", _jsonb_type(), nullable=False),
        sa.Column("langgraph_checkpoint_ref", sa.String(length=256), nullable=True),
        sa.Column("mutation_executed", sa.Boolean(), nullable=False),
        sa.Column("withdrawal_executed", sa.Boolean(), nullable=False),
        sa.Column("live_ready", sa.Boolean(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("completed_at_ms", sa.BIGINT(), nullable=True),
        sa.CheckConstraint(
            "action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', "
            "'request_testnet_rehearsal', 'unknown')",
            name="ck_brc_workflow_runs_action",
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_confirmation', 'running', 'completed', 'blocked', 'failed')",
            name="ck_brc_workflow_runs_status",
        ),
        sa.CheckConstraint("withdrawal_executed = false", name="ck_brc_workflow_runs_no_withdrawal"),
        sa.CheckConstraint("live_ready = false", name="ck_brc_workflow_runs_no_live"),
        sa.PrimaryKeyConstraint("workflow_run_id"),
    )
    op.create_index(
        "idx_brc_workflow_runs_status_time",
        "brc_workflow_runs",
        ["status", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_workflow_runs_action_time",
        "brc_workflow_runs",
        ["action", "created_at_ms"],
    )


def downgrade() -> None:
    op.drop_index("idx_brc_workflow_runs_action_time", table_name="brc_workflow_runs")
    op.drop_index("idx_brc_workflow_runs_status_time", table_name="brc_workflow_runs")
    op.drop_table("brc_workflow_runs")
