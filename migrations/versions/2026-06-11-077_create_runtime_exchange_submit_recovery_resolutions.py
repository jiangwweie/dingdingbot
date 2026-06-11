"""Create runtime exchange submit recovery resolution table

Revision ID: 077
Revises: 076
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "077"
down_revision: Union[str, None] = "076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_recovery_resolutions"


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
        sa.Column("resolution_id", sa.String(length=300), primary_key=True),
        sa.Column("recovery_task_id", sa.String(length=64), nullable=False),
        sa.Column("recovery_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("authorization_id", sa.String(length=220), nullable=True),
        sa.Column("execution_result_id", sa.String(length=540), nullable=True),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("related_order_id", sa.String(length=260), nullable=True),
        sa.Column("related_exchange_order_id", sa.String(length=260), nullable=True),
        sa.Column("entry_order_id", sa.String(length=260), nullable=True),
        sa.Column("entry_exchange_order_id", sa.String(length=260), nullable=True),
        sa.Column("failed_protection_order_id", sa.String(length=260), nullable=True),
        sa.Column("failed_reason", sa.String(length=500), nullable=True),
        sa.Column("owner_operator_id", sa.String(length=128), nullable=False),
        sa.Column("owner_confirmation_reference", sa.String(length=240), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("reconciliation_evidence_id", sa.String(length=240), nullable=True),
        sa.Column(
            "owner_confirmed_recovery_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_reconciliation_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_no_unprotected_position",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_no_unresolved_exchange_order",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_budget_reconciled_or_held",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_attempt_consumed_or_accounted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "recovery_task_marked_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "order_lifecycle_submit_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "execution_intent_status_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exchange_order_submitted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "owner_bounded_execution_called",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "withdrawal_or_transfer_created",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("metadata", _json_type(), nullable=False, server_default="{}"),
        sa.Column("payload", _json_type(), nullable=False, server_default="{}"),
        sa.UniqueConstraint(
            "recovery_task_id",
            name="uq_rt_exchange_recovery_resolution_task",
        ),
        sa.CheckConstraint(
            "recovery_type = 'exchange_submit_protection_fail'",
            name="ck_rt_exchange_recovery_resolution_type",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'resolved')",
            name="ck_rt_exchange_recovery_resolution_status",
        ),
        sa.CheckConstraint(
            "status != 'resolved' OR owner_confirmed_recovery_resolved = true",
            name="ck_rt_exchange_recovery_resolution_owner",
        ),
        sa.CheckConstraint(
            "status != 'resolved' OR owner_confirmed_reconciliation_reviewed = true",
            name="ck_rt_exchange_recovery_resolution_reconciled",
        ),
        sa.CheckConstraint(
            "status != 'resolved' "
            "OR owner_confirmed_no_unprotected_position = true",
            name="ck_rt_exchange_recovery_resolution_no_unprotected",
        ),
        sa.CheckConstraint(
            "status != 'resolved' "
            "OR owner_confirmed_no_unresolved_exchange_order = true",
            name="ck_rt_exchange_recovery_resolution_no_unresolved_order",
        ),
        sa.CheckConstraint(
            "status != 'resolved' "
            "OR owner_confirmed_budget_reconciled_or_held = true",
            name="ck_rt_exchange_recovery_resolution_budget",
        ),
        sa.CheckConstraint(
            "status != 'resolved' "
            "OR owner_confirmed_attempt_consumed_or_accounted = true",
            name="ck_rt_exchange_recovery_resolution_attempt",
        ),
        sa.CheckConstraint(
            "status != 'resolved' OR recovery_task_marked_resolved = true",
            name="ck_rt_exchange_recovery_resolution_marked",
        ),
        sa.CheckConstraint(
            "order_lifecycle_submit_called = false",
            name="ck_rt_exchange_recovery_resolution_no_lifecycle",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_exchange_recovery_resolution_no_intent_status",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_exchange_recovery_resolution_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_exchange_recovery_resolution_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_exchange_recovery_resolution_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_exchange_recovery_resolution_no_withdrawal",
        ),
    )
    op.create_index(
        "idx_rt_exchange_recovery_resolution_task_time",
        TABLE,
        ["recovery_task_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_recovery_resolution_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_exchange_recovery_resolution_status_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_recovery_resolution_task_time", table_name=TABLE)
    op.drop_table(TABLE)
