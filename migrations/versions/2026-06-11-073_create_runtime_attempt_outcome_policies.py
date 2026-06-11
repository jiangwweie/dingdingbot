"""Create runtime attempt outcome policy table

Revision ID: 073
Revises: 072
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "073"
down_revision: Union[str, None] = "072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_attempt_outcome_policies"


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
        sa.Column("policy_id", sa.String(360), primary_key=True),
        sa.Column("reservation_id", sa.String(260), nullable=False),
        sa.Column("reservation_preview_id", sa.String(260), nullable=False),
        sa.Column("mutation_id", sa.String(320), nullable=True),
        sa.Column("authorization_id", sa.String(220), nullable=False),
        sa.Column("execution_intent_id", sa.String(64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(128), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(96), nullable=False),
        sa.Column("outcome_kind", sa.String(96), nullable=False),
        sa.Column("budget_action", sa.String(96), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("side", sa.String(32), nullable=True),
        sa.Column("any_fill", sa.Boolean(), nullable=False),
        sa.Column("partial_fill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_to_exchange", sa.Boolean(), nullable=False),
        sa.Column(
            "protection_creation_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("attempt_should_be_consumed", sa.Boolean(), nullable=False),
        sa.Column("budget_release_allowed", sa.Boolean(), nullable=False),
        sa.Column("budget_consumption_confirmed", sa.Boolean(), nullable=False),
        sa.Column("reserved_budget_should_remain_held", sa.Boolean(), nullable=False),
        sa.Column("requires_reconciliation_before_retry", sa.Boolean(), nullable=False),
        sa.Column("requires_owner_recovery_review", sa.Boolean(), nullable=False),
        sa.Column("requires_reduce_only_recovery_mode", sa.Boolean(), nullable=False),
        sa.Column("blocks_new_entries_until_resolved", sa.Boolean(), nullable=False),
        sa.Column("budget_reservation_basis", sa.String(96), nullable=True),
        sa.Column("budget_reservation_amount", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_reserved_before", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_reserved_after", sa.Numeric(36, 18), nullable=True),
        sa.Column("runtime_state_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_counter_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("budget_released", sa.Boolean(), nullable=False, server_default=sa.false()),
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
            "owner_bounded_execution_called",
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
        sa.CheckConstraint(
            "status IN ('blocked', 'ready_for_attempt_budget_outcome_accounting')",
            name="ck_rt_attempt_outcome_policy_status",
        ),
        sa.CheckConstraint(
            "runtime_state_mutated = false",
            name="ck_rt_attempt_outcome_policy_no_runtime_mutation",
        ),
        sa.CheckConstraint(
            "attempt_counter_mutated = false",
            name="ck_rt_attempt_outcome_policy_no_attempt_mutation",
        ),
        sa.CheckConstraint(
            "budget_released = false",
            name="ck_rt_attempt_outcome_policy_no_budget_release",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_attempt_outcome_policy_no_intent_status",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_rt_attempt_outcome_policy_no_order_create",
        ),
        sa.CheckConstraint(
            "order_cancelled = false",
            name="ck_rt_attempt_outcome_policy_no_order_cancel",
        ),
        sa.CheckConstraint(
            "position_closed = false",
            name="ck_rt_attempt_outcome_policy_no_position_close",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_attempt_outcome_policy_no_exchange",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_attempt_outcome_policy_no_exchange_order",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_attempt_outcome_policy_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_attempt_outcome_policy_no_lifecycle",
        ),
        sa.CheckConstraint(
            "withdrawal_instruction_created = false",
            name="ck_rt_attempt_outcome_policy_no_withdrawal",
        ),
        sa.CheckConstraint(
            "transfer_instruction_created = false",
            name="ck_rt_attempt_outcome_policy_no_transfer",
        ),
    )
    op.create_index(
        "idx_rt_attempt_outcome_policy_reservation_time",
        TABLE,
        ["reservation_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_attempt_outcome_policy_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_attempt_outcome_policy_kind_time",
        TABLE,
        ["outcome_kind", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_attempt_outcome_policy_kind_time", table_name=TABLE)
    op.drop_index("idx_rt_attempt_outcome_policy_auth_time", table_name=TABLE)
    op.drop_index("idx_rt_attempt_outcome_policy_reservation_time", table_name=TABLE)
    op.drop_table(TABLE)
