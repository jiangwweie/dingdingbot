"""Create BRC campaign tables

Revision ID: 012
Revises: 011
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "brc_campaigns",
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_playbook_id", sa.String(length=128), nullable=False),
        sa.Column("bucket", _jsonb_type(), nullable=False),
        sa.Column("risk_envelope", _jsonb_type(), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(36, 18), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("attempts", _jsonb_type(), nullable=False),
        sa.Column("outcome", sa.String(length=128), nullable=True),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("finalized_at_ms", sa.BIGINT(), nullable=True),
        sa.CheckConstraint(
            "status IN ('observe', 'active', 'profit_protect', 'loss_locked', 'ended')",
            name="ck_brc_campaigns_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_brc_campaigns_attempt_count_nonnegative"),
        sa.PrimaryKeyConstraint("campaign_id"),
    )
    op.create_index(
        "idx_brc_campaigns_status_updated",
        "brc_campaigns",
        ["status", "updated_at_ms"],
        unique=False,
    )

    op.create_table(
        "brc_playbook_switch_decisions",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("switch_id", sa.String(length=128), nullable=False),
        sa.Column("previous_playbook_id", sa.String(length=128), nullable=False),
        sa.Column("new_playbook_id", sa.String(length=128), nullable=False),
        sa.Column("decision_result", sa.String(length=32), nullable=False),
        sa.Column("reason_category", sa.String(length=128), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("evidence_refs", _jsonb_type(), nullable=False),
        sa.Column("risk_change_direction", sa.String(length=32), nullable=False),
        sa.Column("campaign_pnl_at_switch", sa.Numeric(36, 18), nullable=False),
        sa.Column("attempt_count_at_switch", sa.Integer(), nullable=False),
        sa.Column("campaign_status_at_switch", sa.String(length=32), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("inferred_fields", _jsonb_type(), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=False),
        sa.Column("switched_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "decision_result IN ('allowed', 'blocked', 'review_required')",
            name="ck_brc_switch_decisions_result",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("switch_id", name="uq_brc_playbook_switch_decisions_switch_id"),
    )
    op.create_index(
        "uq_brc_switch_decisions_campaign_seq",
        "brc_playbook_switch_decisions",
        ["campaign_id", "sequence_number"],
        unique=True,
    )
    op.create_index(
        "idx_brc_switch_decisions_campaign_time",
        "brc_playbook_switch_decisions",
        ["campaign_id", "switched_at_ms"],
        unique=False,
    )

    op.create_table(
        "brc_campaign_events",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("attempt_id", sa.String(length=128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", _jsonb_type(), nullable=False),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_brc_campaign_events_campaign_seq",
        "brc_campaign_events",
        ["campaign_id", "sequence_number"],
        unique=True,
    )
    op.create_index(
        "idx_brc_campaign_events_campaign_time",
        "brc_campaign_events",
        ["campaign_id", "occurred_at_ms"],
        unique=False,
    )
    op.create_index("idx_brc_campaign_events_type", "brc_campaign_events", ["event_type"], unique=False)

    op.create_table(
        "brc_mock_pnl_events",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("campaign_id", sa.String(length=128), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("cumulative_pnl", sa.Numeric(36, 18), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triggered_state", sa.String(length=32), nullable=True),
        sa.Column("occurred_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint("source IN ('testnet_mock')", name="ck_brc_mock_pnl_events_source"),
        sa.CheckConstraint("amount != 0", name="ck_brc_mock_pnl_events_amount_nonzero"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_brc_mock_pnl_events_event_id"),
    )
    op.create_index(
        "uq_brc_mock_pnl_events_campaign_seq",
        "brc_mock_pnl_events",
        ["campaign_id", "sequence_number"],
        unique=True,
    )
    op.create_index(
        "idx_brc_mock_pnl_events_campaign_time",
        "brc_mock_pnl_events",
        ["campaign_id", "occurred_at_ms"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_brc_mock_pnl_events_campaign_time", table_name="brc_mock_pnl_events")
    op.drop_index("uq_brc_mock_pnl_events_campaign_seq", table_name="brc_mock_pnl_events")
    op.drop_table("brc_mock_pnl_events")

    op.drop_index("idx_brc_campaign_events_type", table_name="brc_campaign_events")
    op.drop_index("idx_brc_campaign_events_campaign_time", table_name="brc_campaign_events")
    op.drop_index("uq_brc_campaign_events_campaign_seq", table_name="brc_campaign_events")
    op.drop_table("brc_campaign_events")

    op.drop_index("idx_brc_switch_decisions_campaign_time", table_name="brc_playbook_switch_decisions")
    op.drop_index("uq_brc_switch_decisions_campaign_seq", table_name="brc_playbook_switch_decisions")
    op.drop_table("brc_playbook_switch_decisions")

    op.drop_index("idx_brc_campaigns_status_updated", table_name="brc_campaigns")
    op.drop_table("brc_campaigns")
