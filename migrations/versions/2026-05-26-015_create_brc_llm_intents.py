"""Create BRC LLM intent ledger

Revision ID: 015
Revises: 014
Create Date: 2026-05-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "brc_llm_intents",
        sa.Column("intent_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=128), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Numeric(8, 6), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("provider_name", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("raw_response_summary", _jsonb_type(), nullable=False),
        sa.Column("decision_result", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("live_ready", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "action IN ('read_review_packet', 'read_next_eligibility', 'read_evidence', "
            "'request_testnet_rehearsal', 'unknown')",
            name="ck_brc_llm_intents_action",
        ),
        sa.CheckConstraint(
            "decision_result IN ('planned', 'executed', 'blocked')",
            name="ck_brc_llm_intents_decision_result",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_brc_llm_intents_confidence"),
        sa.CheckConstraint("live_ready = false", name="ck_brc_llm_intents_no_live"),
        sa.PrimaryKeyConstraint("intent_id"),
    )
    op.create_index("idx_brc_llm_intents_workflow", "brc_llm_intents", ["workflow_run_id"])
    op.create_index(
        "idx_brc_llm_intents_action_time",
        "brc_llm_intents",
        ["action", "created_at_ms"],
    )


def downgrade() -> None:
    op.drop_index("idx_brc_llm_intents_action_time", table_name="brc_llm_intents")
    op.drop_index("idx_brc_llm_intents_workflow", table_name="brc_llm_intents")
    op.drop_table("brc_llm_intents")
