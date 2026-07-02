"""Create runtime execution attempt reservation audit table

Revision ID: 055
Revises: 054
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_attempt_reservations"


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
        sa.Column("reservation_id", sa.String(length=260), primary_key=True),
        sa.Column("reservation_preview_id", sa.String(length=260), nullable=False),
        sa.Column("preflight_id", sa.String(length=260), nullable=False),
        sa.Column("authorization_id", sa.String(length=220), nullable=False),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("trial_binding_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
        sa.Column("signal_evaluation_id", sa.String(length=128), nullable=True),
        sa.Column("order_candidate_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("proposed_quantity", sa.Numeric(36, 18), nullable=True),
        sa.Column("intended_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("attempts_used_before", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_before", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_after", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("budget_remaining_before", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_remaining_after", sa.Numeric(36, 18), nullable=True),
        sa.Column("max_notional_per_attempt", sa.Numeric(36, 18), nullable=True),
        sa.Column("total_budget", sa.Numeric(36, 18), nullable=True),
        sa.Column("max_active_positions", sa.Integer(), nullable=False),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("reservation_recorded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("runtime_mutation_pending", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("runtime_budget_mutated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempt_consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "execution_intent_status_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("order_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('blocked', 'pending_runtime_mutation')",
            name="ck_runtime_execution_attempt_reservations_status",
        ),
        sa.CheckConstraint(
            "reservation_recorded = true",
            name="ck_runtime_execution_attempt_reservations_recorded",
        ),
        sa.CheckConstraint(
            "runtime_budget_mutated = false",
            name="ck_runtime_execution_attempt_reservations_no_budget_mutation",
        ),
        sa.CheckConstraint(
            "attempt_consumed = false",
            name="ck_runtime_execution_attempt_reservations_no_attempt_consumed",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_attempt_res_no_intent_status_change",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_attempt_reservations_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_attempt_reservations_no_exchange_called",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_attempt_res_no_owner_bounded_exec",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_runtime_execution_attempt_reservations_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_attempt_reservations_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_attempt_reservations_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_attempt_reservations_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_attempt_reservations_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_attempt_reservations_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_attempt_reservations_intent_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_attempt_reservations_runtime_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_attempt_reservations_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
