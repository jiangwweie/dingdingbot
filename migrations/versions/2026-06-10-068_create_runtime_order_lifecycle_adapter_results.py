"""Create runtime OrderLifecycle adapter result lock table

Revision ID: 068
Revises: 067
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "068"
down_revision: Union[str, None] = "067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_order_lifecycle_adapter_results"


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
        sa.Column("adapter_result_id", sa.String(length=420), primary_key=True),
        sa.Column("registration_preview_id", sa.String(length=380), nullable=False),
        sa.Column("adapter_preview_id", sa.String(length=360), nullable=False),
        sa.Column("handoff_draft_id", sa.String(length=360), nullable=False),
        sa.Column("preflight_id", sa.String(length=260), nullable=False),
        sa.Column("authorization_id", sa.String(length=220), nullable=False),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("trial_binding_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_id", sa.String(length=128), nullable=True),
        sa.Column("strategy_family_version_id", sa.String(length=128), nullable=True),
        sa.Column("signal_evaluation_id", sa.String(length=128), nullable=True),
        sa.Column("order_candidate_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=32), nullable=False),
        sa.Column("local_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("entry_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("protection_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("registered_order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "order_lifecycle_adapter_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "local_order_registration_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "duplicate_submit_lock_acquired",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "order_objects_constructed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "local_order_registration_executed",
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
            "order_lifecycle_called",
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
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_rt_ol_adapter_result_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'order_lifecycle_adapter_disabled', "
            "'local_order_registration_disabled', 'duplicate_submit_lock_required', "
            "'local_registration_lock_acquired', 'registered_created_local_orders')",
            name="ck_rt_ol_adapter_result_status",
        ),
        sa.CheckConstraint(
            "registered_order_count >= 0",
            name="ck_rt_ol_adapter_result_registered_count",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_ol_adapter_result_no_intent_status",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_ol_adapter_result_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_ol_adapter_result_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_ol_adapter_result_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_ol_adapter_result_no_withdrawal",
        ),
        sa.CheckConstraint(
            "status != 'registered_created_local_orders' OR local_order_registration_executed = true",
            name="ck_rt_ol_adapter_result_registered_exec",
        ),
        sa.CheckConstraint(
            "status != 'registered_created_local_orders' OR order_lifecycle_called = true",
            name="ck_rt_ol_adapter_result_registered_lifecycle",
        ),
        sa.CheckConstraint(
            "status = 'registered_created_local_orders' OR local_order_registration_executed = false",
            name="ck_rt_ol_adapter_result_nonreg_no_exec",
        ),
        sa.CheckConstraint(
            "status = 'registered_created_local_orders' OR order_lifecycle_called = false",
            name="ck_rt_ol_adapter_result_nonreg_no_lifecycle",
        ),
    )
    op.create_index(
        "idx_rt_ol_adapter_result_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_ol_adapter_result_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_ol_adapter_result_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_ol_adapter_result_status_time", table_name=TABLE)
    op.drop_index("idx_rt_ol_adapter_result_intent_time", table_name=TABLE)
    op.drop_index("idx_rt_ol_adapter_result_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
