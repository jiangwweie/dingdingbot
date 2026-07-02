"""Create runtime execution attempt mutation audit table

Revision ID: 056
Revises: 055
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "056"
down_revision: Union[str, None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_attempt_mutations"


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
        sa.Column("mutation_id", sa.String(length=320), primary_key=True),
        sa.Column("reservation_id", sa.String(length=260), nullable=False),
        sa.Column("reservation_preview_id", sa.String(length=260), nullable=False),
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
        sa.Column("runtime_status_before", sa.String(length=64), nullable=False),
        sa.Column("runtime_status_after", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=True),
        sa.Column("proposed_quantity", sa.Numeric(36, 18), nullable=True),
        sa.Column("intended_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("attempts_used_before", sa.Integer(), nullable=False),
        sa.Column("attempts_used_after", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_before", sa.Integer(), nullable=False),
        sa.Column("attempts_remaining_after", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("budget_reserved_before", sa.Numeric(36, 18), nullable=False),
        sa.Column("budget_reserved_after", sa.Numeric(36, 18), nullable=False),
        sa.Column("budget_remaining_before", sa.Numeric(36, 18), nullable=True),
        sa.Column("budget_remaining_after", sa.Numeric(36, 18), nullable=True),
        sa.Column("reservation_budget_remaining_after", sa.Numeric(36, 18), nullable=True),
        sa.Column("max_notional_per_attempt", sa.Numeric(36, 18), nullable=True),
        sa.Column("total_budget", sa.Numeric(36, 18), nullable=True),
        sa.Column("max_active_positions", sa.Integer(), nullable=False),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("reservation_status", sa.String(length=64), nullable=False),
        sa.Column("reservation_recorded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "runtime_mutation_pending_before",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("runtime_budget_mutated", sa.Boolean(), nullable=False),
        sa.Column("attempt_consumed", sa.Boolean(), nullable=False),
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
        sa.Column("order_lifecycle_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "status IN ('blocked', 'applied')",
            name="ck_runtime_execution_attempt_mutations_status",
        ),
        sa.CheckConstraint(
            "reservation_recorded = true",
            name="ck_runtime_execution_attempt_mutations_reservation_recorded",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_runtime_execution_attempt_mutations_no_intent_status_change",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_attempt_mutations_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_attempt_mutations_no_exchange_called",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_attempt_mut_no_owner_bounded_exec",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_runtime_execution_attempt_mutations_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_attempt_mutations_reservation",
        TABLE,
        ["reservation_id"],
    )
    op.create_index(
        "idx_runtime_execution_attempt_mutations_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_attempt_mutations_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_attempt_mutations_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_attempt_mutations_runtime_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_attempt_mutations_reservation", table_name=TABLE)
    op.drop_table(TABLE)
