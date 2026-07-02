"""Create runtime submit outcome review table

Revision ID: 079
Revises: 078
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "079"
down_revision: Union[str, None] = "078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_submit_outcome_reviews"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if _has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("review_id", sa.String(620), primary_key=True),
        sa.Column(
            "exchange_submit_execution_result_id",
            sa.String(540),
            nullable=False,
        ),
        sa.Column("authorization_id", sa.String(220), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=True),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("trial_binding_id", sa.String(128), nullable=True),
        sa.Column("strategy_family_id", sa.String(128), nullable=True),
        sa.Column("strategy_family_version_id", sa.String(128), nullable=True),
        sa.Column("signal_evaluation_id", sa.String(128), nullable=True),
        sa.Column("order_candidate_id", sa.String(128), nullable=True),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("observed_outcome", sa.String(96), nullable=False),
        sa.Column("recommended_attempt_outcome_kind", sa.String(96), nullable=True),
        sa.Column("attempt_outcome_policy_ready", sa.Boolean(), nullable=False),
        sa.Column("entry_order_id", sa.String(260), nullable=True),
        sa.Column("entry_order_status", sa.String(64), nullable=True),
        sa.Column("entry_requested_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column("entry_filled_qty", sa.Numeric(36, 18), nullable=True),
        sa.Column(
            "protection_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "missing_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("submitted_to_exchange", sa.Boolean(), nullable=False),
        sa.Column("any_fill", sa.Boolean(), nullable=False),
        sa.Column("partial_fill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("full_fill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("no_fill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "protection_creation_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "requires_reconciliation_before_retry",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "blocks_attempt_outcome_policy_until_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("runtime_state_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_counter_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("budget_released", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("budget_consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "execution_intent_status_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("order_cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "exchange_order_submitted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "order_lifecycle_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_bounded_execution_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "withdrawal_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "transfer_instruction_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_rt_submit_outcome_review_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', "
            "'classified_ready_for_attempt_outcome_policy')",
            name="ck_rt_submit_outcome_review_status",
        ),
        sa.CheckConstraint(
            "runtime_state_mutated = false",
            name="ck_rt_submit_outcome_review_no_runtime_mutation",
        ),
        sa.CheckConstraint(
            "attempt_counter_mutated = false",
            name="ck_rt_submit_outcome_review_no_attempt_mutation",
        ),
        sa.CheckConstraint(
            "budget_released = false",
            name="ck_rt_submit_outcome_review_no_budget_release",
        ),
        sa.CheckConstraint(
            "budget_consumed = false",
            name="ck_rt_submit_outcome_review_no_budget_consume",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_submit_outcome_review_no_intent_status",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_rt_submit_outcome_review_no_order_create",
        ),
        sa.CheckConstraint(
            "order_cancelled = false",
            name="ck_rt_submit_outcome_review_no_order_cancel",
        ),
        sa.CheckConstraint(
            "position_closed = false",
            name="ck_rt_submit_outcome_review_no_position_close",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_submit_outcome_review_no_exchange",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_submit_outcome_review_no_exchange_order",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_submit_outcome_review_no_lifecycle",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_submit_outcome_review_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_rt_submit_outcome_review_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_rt_submit_outcome_review_no_transfer",
        ),
    )
    op.create_index(
        "idx_rt_submit_outcome_review_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_submit_outcome_review_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_submit_outcome_review_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_submit_outcome_review_observed_time",
        TABLE,
        ["observed_outcome", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_submit_outcome_review_observed_time", table_name=TABLE)
    op.drop_index("idx_rt_submit_outcome_review_status_time", table_name=TABLE)
    op.drop_index("idx_rt_submit_outcome_review_intent_time", table_name=TABLE)
    op.drop_index("idx_rt_submit_outcome_review_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
