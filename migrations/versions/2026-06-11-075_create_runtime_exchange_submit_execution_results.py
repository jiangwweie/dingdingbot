"""Create runtime exchange submit execution result table

Revision ID: 075
Revises: 074
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "075"
down_revision: Union[str, None] = "074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_execution_results"


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
        sa.Column("execution_result_id", sa.String(length=540), primary_key=True),
        sa.Column("enablement_decision_id", sa.String(length=500), nullable=False),
        sa.Column("packet_preview_id", sa.String(length=460), nullable=False),
        sa.Column("binding_id", sa.String(length=460), nullable=False),
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
        sa.Column("status", sa.String(length=96), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column(
            "exchange_submit_action_authorization_id",
            sa.String(length=360),
            nullable=True,
        ),
        sa.Column("local_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("entry_order_id", sa.String(length=260), nullable=True),
        sa.Column(
            "protection_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "submitted_orders",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "submitted_local_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "submitted_exchange_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("entry_exchange_order_id", sa.String(length=260), nullable=True),
        sa.Column(
            "protection_exchange_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("failed_local_order_id", sa.String(length=260), nullable=True),
        sa.Column("failed_order_role", sa.String(length=32), nullable=True),
        sa.Column("failed_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "exchange_submit_execution_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "execution_mode",
            sa.String(length=48),
            nullable=False,
            server_default="disabled",
        ),
        sa.Column(
            "exchange_call_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "order_lifecycle_submit_call_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "real_exchange_submit_adapter_executed",
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
            "authorization_id",
            name="uq_rt_exchange_exec_result_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'exchange_submit_execution_disabled', "
            "'exchange_submit_execution_lock_acquired', 'entry_submit_failed', "
            "'protection_submit_failed', 'exchange_submit_orders_submitted')",
            name="ck_rt_exchange_exec_result_status",
        ),
        sa.CheckConstraint(
            "exchange_call_count >= 0",
            name="ck_rt_exchange_exec_result_exchange_count",
        ),
        sa.CheckConstraint(
            "order_lifecycle_submit_call_count >= 0",
            name="ck_rt_exchange_exec_result_lifecycle_count",
        ),
        sa.CheckConstraint(
            "execution_mode IN ('disabled', 'in_memory_simulation', "
            "'real_gateway_action')",
            name="ck_rt_exchange_exec_result_mode",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_exchange_exec_result_no_intent_status",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_exchange_exec_result_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_exchange_exec_result_no_withdrawal",
        ),
        sa.CheckConstraint(
            "status NOT IN ('blocked', 'exchange_submit_execution_disabled', "
            "'exchange_submit_execution_lock_acquired') "
            "OR exchange_called = false",
            name="ck_rt_exchange_exec_result_no_exchange_before_exec",
        ),
        sa.CheckConstraint(
            "status NOT IN ('blocked', 'exchange_submit_execution_disabled', "
            "'exchange_submit_execution_lock_acquired') "
            "OR exchange_order_submitted = false",
            name="ck_rt_exchange_exec_result_no_order_before_exec",
        ),
        sa.CheckConstraint(
            "status NOT IN ('blocked', 'exchange_submit_execution_disabled', "
            "'exchange_submit_execution_lock_acquired') "
            "OR order_lifecycle_submit_called = false",
            name="ck_rt_exchange_exec_result_no_lifecycle_before_exec",
        ),
        sa.CheckConstraint(
            "status != 'exchange_submit_execution_lock_acquired' "
            "OR exchange_submit_execution_enabled = true",
            name="ck_rt_exchange_exec_result_lock_enabled",
        ),
        sa.CheckConstraint(
            "status != 'exchange_submit_execution_lock_acquired' "
            "OR real_exchange_submit_adapter_executed = false",
            name="ck_rt_exchange_exec_result_lock_not_executed",
        ),
        sa.CheckConstraint(
            "status != 'exchange_submit_orders_submitted' "
            "OR exchange_called = true",
            name="ck_rt_exchange_exec_result_submitted_exchange_called",
        ),
        sa.CheckConstraint(
            "status != 'exchange_submit_orders_submitted' "
            "OR exchange_order_submitted = true",
            name="ck_rt_exchange_exec_result_submitted_exchange_order",
        ),
        sa.CheckConstraint(
            "status != 'exchange_submit_orders_submitted' "
            "OR order_lifecycle_submit_called = true",
            name="ck_rt_exchange_exec_result_submitted_lifecycle",
        ),
    )
    op.create_index(
        "idx_rt_exchange_exec_result_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_exec_result_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_exec_result_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_exchange_exec_result_status_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_exec_result_intent_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_exec_result_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
