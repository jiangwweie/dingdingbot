"""Create ticket-bound post-submit closures.

Revision ID: 089
Revises: 088
Create Date: 2026-07-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "089"
down_revision: Union[str, None] = "088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_ticket_bound_post_submit_closures"


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def upgrade() -> None:
    if _has_table():
        return
    json_t = _json_type()
    op.create_table(
        TABLE_NAME,
        sa.Column("post_submit_closure_id", sa.String(192), primary_key=True),
        sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
        sa.Column("ticket_id", sa.String(192), nullable=False),
        sa.Column("finalgate_pass_id", sa.String(256), nullable=False),
        sa.Column("operation_layer_handoff_id", sa.String(192), nullable=False),
        sa.Column("operation_submit_command_id", sa.String(192), nullable=False),
        sa.Column("runtime_safety_snapshot_id", sa.String(192), nullable=False),
        sa.Column("action_time_lane_input_id", sa.String(192), nullable=False),
        sa.Column("strategy_group_id", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("protection_state", sa.String(64), nullable=False),
        sa.Column("reconciliation_state", sa.String(64), nullable=False),
        sa.Column("settlement_state", sa.String(64), nullable=False),
        sa.Column("review_state", sa.String(64), nullable=False),
        sa.Column("first_blocker", sa.String(160), nullable=True),
        sa.Column("blockers", json_t, nullable=False, server_default="[]"),
        sa.Column("warnings", json_t, nullable=False, server_default="[]"),
        sa.Column("submitted_order_refs", json_t, nullable=False, server_default="[]"),
        sa.Column("reconciliation_evidence", json_t, nullable=False, server_default="{}"),
        sa.Column("settlement_evidence", json_t, nullable=False, server_default="{}"),
        sa.Column("review_evidence", json_t, nullable=False, server_default="{}"),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("finalgate_called", sa.Boolean(), nullable=False),
        sa.Column("operation_layer_called", sa.Boolean(), nullable=False),
        sa.Column("exchange_write_called", sa.Boolean(), nullable=False),
        sa.Column("order_created", sa.Boolean(), nullable=False),
        sa.Column("order_lifecycle_called", sa.Boolean(), nullable=False),
        sa.Column("withdrawal_or_transfer_created", sa.Boolean(), nullable=False),
        sa.Column("live_profile_changed", sa.Boolean(), nullable=False),
        sa.Column("order_sizing_changed", sa.Boolean(), nullable=False),
        sa.Column("runtime_budget_mutated", sa.Boolean(), nullable=False),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
        sa.CheckConstraint(
            "side IN ('long', 'short')",
            name="ck_brc_ticket_post_submit_side",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'reconciliation_pending', "
            "'reconciliation_matched', 'settlement_ready', 'review_ready', "
            "'closed')",
            name="ck_brc_ticket_post_submit_status",
        ),
        sa.CheckConstraint(
            "protection_state IN ('submitted', 'missing', 'failed', 'unknown')",
            name="ck_brc_ticket_post_submit_protection",
        ),
        sa.CheckConstraint(
            "reconciliation_state IN ('not_checked', 'matched', 'mismatch', "
            "'blocked')",
            name="ck_brc_ticket_post_submit_reconciliation",
        ),
        sa.CheckConstraint(
            "settlement_state IN ('not_started', 'held_until_position_resolved', "
            "'released', 'blocked')",
            name="ck_brc_ticket_post_submit_settlement",
        ),
        sa.CheckConstraint(
            "review_state IN ('not_recorded', 'recorded', 'blocked')",
            name="ck_brc_ticket_post_submit_review",
        ),
        sa.CheckConstraint(
            "finalgate_called = false "
            "AND operation_layer_called = false "
            "AND exchange_write_called = false "
            "AND order_created = false "
            "AND order_lifecycle_called = false "
            "AND withdrawal_or_transfer_created = false "
            "AND live_profile_changed = false "
            "AND order_sizing_changed = false "
            "AND runtime_budget_mutated = false",
            name="ck_brc_ticket_post_submit_no_effects",
        ),
        sa.CheckConstraint(
            "status <> 'closed' OR "
            "(protection_state = 'submitted' "
            "AND reconciliation_state = 'matched' "
            "AND settlement_state = 'released' "
            "AND review_state = 'recorded' "
            "AND first_blocker IS NULL)",
            name="ck_brc_ticket_post_submit_closed_truth",
        ),
        sa.UniqueConstraint(
            "protected_submit_attempt_id",
            name="uq_brc_ticket_post_submit_attempt",
        ),
    )
    op.create_index(
        "idx_brc_ticket_post_submit_ticket_status",
        TABLE_NAME,
        ["ticket_id", "status", "created_at_ms"],
    )
    op.create_index(
        "idx_brc_ticket_post_submit_scope",
        TABLE_NAME,
        ["strategy_group_id", "symbol", "created_at_ms"],
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE_NAME)
