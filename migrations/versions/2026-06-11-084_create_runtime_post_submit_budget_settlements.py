"""Create runtime post-submit budget settlement table

Revision ID: 084
Revises: 083
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "084"
down_revision: Union[str, None] = "083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_post_submit_budget_settlements"


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
        sa.Column("settlement_id", sa.String(420), primary_key=True),
        sa.Column("accounting_id", sa.String(360), nullable=False),
        sa.Column("authorization_id", sa.String(220), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=False),
        sa.Column("reservation_id", sa.String(260), nullable=False),
        sa.Column("mutation_id", sa.String(320), nullable=True),
        sa.Column("attempt_outcome_policy_id", sa.String(360), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("runtime_status_before", sa.String(64), nullable=False),
        sa.Column("runtime_status_after", sa.String(64), nullable=False),
        sa.Column("budget_action", sa.String(96), nullable=True),
        sa.Column("outcome_kind", sa.String(96), nullable=True),
        sa.Column("budget_reservation_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_release_amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("budget_reserved_before", sa.Numeric(36, 18), nullable=False),
        sa.Column("budget_reserved_after", sa.Numeric(36, 18), nullable=False),
        sa.Column("budget_remaining_before", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_remaining_after", sa.Numeric(36, 18), nullable=True),
        sa.Column("attempts_used_before", sa.Integer(), nullable=False),
        sa.Column("attempts_used_after", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_before", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_after", sa.Integer(), nullable=False),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("runtime_state_mutated", sa.Boolean(), nullable=False),
        sa.Column("runtime_budget_mutated", sa.Boolean(), nullable=False),
        sa.Column(
            "attempt_counter_mutated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("attempt_already_consumed", sa.Boolean(), nullable=False),
        sa.Column("budget_released", sa.Boolean(), nullable=False),
        sa.Column("budget_consumption_recorded", sa.Boolean(), nullable=False),
        sa.Column("reserved_budget_remains_held", sa.Boolean(), nullable=False),
        sa.Column("requires_reconciliation_before_retry", sa.Boolean(), nullable=False),
        sa.Column("blocks_new_entries_until_resolved", sa.Boolean(), nullable=False),
        sa.Column(
            "not_execution_authority",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
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
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.UniqueConstraint(
            "authorization_id",
            "reservation_id",
            name="uq_rt_post_submit_budget_settlement_auth_reservation",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'released_reserved_budget', "
            "'recorded_reserved_budget_held', "
            "'recorded_reserved_budget_consumed')",
            name="ck_rt_post_submit_budget_settlement_status",
        ),
        sa.CheckConstraint(
            "attempt_counter_mutated = false",
            name="ck_rt_post_submit_budget_settlement_no_attempt_mutation",
        ),
        sa.CheckConstraint(
            "not_execution_authority = true",
            name="ck_rt_post_submit_budget_settlement_no_execution_authority",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_post_submit_budget_settlement_no_intent_status",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_rt_post_submit_budget_settlement_no_order_create",
        ),
        sa.CheckConstraint(
            "order_cancelled = false",
            name="ck_rt_post_submit_budget_settlement_no_order_cancel",
        ),
        sa.CheckConstraint(
            "position_closed = false",
            name="ck_rt_post_submit_budget_settlement_no_position_close",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_post_submit_budget_settlement_no_exchange",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_post_submit_budget_settlement_no_exchange_order",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_post_submit_budget_settlement_no_lifecycle",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_post_submit_budget_settlement_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_rt_post_submit_budget_settlement_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_rt_post_submit_budget_settlement_no_transfer",
        ),
    )
    op.create_index(
        "idx_rt_post_submit_budget_settlement_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_post_submit_budget_settlement_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_post_submit_budget_settlement_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index(
        "idx_rt_post_submit_budget_settlement_status_time",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_rt_post_submit_budget_settlement_runtime_time",
        table_name=TABLE,
    )
    op.drop_index(
        "idx_rt_post_submit_budget_settlement_auth_time",
        table_name=TABLE,
    )
    op.drop_table(TABLE)
