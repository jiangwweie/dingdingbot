"""Create runtime exchange submit adapter result table

Revision ID: 071
Revises: 070
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "071"
down_revision: Union[str, None] = "070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_adapter_results"


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
        sa.Column("adapter_result_id", sa.String(length=520), primary_key=True),
        sa.Column("enablement_decision_id", sa.String(length=500), nullable=False),
        sa.Column("gate_id", sa.String(length=460), nullable=False),
        sa.Column("packet_preview_id", sa.String(length=460), nullable=False),
        sa.Column("binding_id", sa.String(length=460), nullable=False),
        sa.Column(
            "local_registration_adapter_result_id",
            sa.String(length=420),
            nullable=False,
        ),
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
        sa.Column("status", sa.String(length=72), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("local_order_ids", _json_type(), nullable=False, server_default="[]"),
        sa.Column("entry_order_id", sa.String(length=260), nullable=True),
        sa.Column(
            "protection_order_ids",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "submit_request_previews",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "submit_request_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "entry_submit_request_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "protection_submit_request_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "order_lifecycle_submit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exchange_submit_adapter_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exchange_submit_action_authorized",
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
            "exchange_submit_adapter_implemented",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.Column(
            "exchange_called",
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
        sa.UniqueConstraint(
            "authorization_id",
            name="uq_rt_exchange_submit_result_authorization",
        ),
        sa.CheckConstraint(
            "status IN ('blocked', 'exchange_submit_adapter_disabled', "
            "'exchange_submit_lock_required', 'exchange_submit_lock_acquired', "
            "'exchange_submit_adapter_not_implemented')",
            name="ck_rt_exchange_submit_result_status",
        ),
        sa.CheckConstraint(
            "submit_request_count >= 0",
            name="ck_rt_exchange_submit_result_request_count",
        ),
        sa.CheckConstraint(
            "entry_submit_request_count >= 0",
            name="ck_rt_exchange_submit_result_entry_count",
        ),
        sa.CheckConstraint(
            "protection_submit_request_count >= 0",
            name="ck_rt_exchange_submit_result_protection_count",
        ),
        sa.CheckConstraint(
            "order_lifecycle_submit_called = false",
            name="ck_rt_exchange_submit_result_no_lifecycle_submit",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_exchange_submit_result_no_intent_status",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_exchange_submit_result_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_exchange_submit_result_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_exchange_submit_result_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_exchange_submit_result_no_withdrawal",
        ),
        sa.CheckConstraint(
            "exchange_submit_adapter_implemented = false",
            name="ck_rt_exchange_submit_result_not_implemented",
        ),
    )
    op.create_index(
        "idx_rt_exchange_submit_result_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_submit_result_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_submit_result_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_exchange_submit_result_status_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_submit_result_intent_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_submit_result_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
