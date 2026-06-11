"""Create runtime exchange gateway readiness table

Revision ID: 078
Revises: 077
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "078"
down_revision: Union[str, None] = "077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_gateway_readiness"


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
        sa.Column("readiness_id", sa.String(length=128), primary_key=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("exchange_name", sa.String(length=64), nullable=False),
        sa.Column("trading_env", sa.String(length=64), nullable=False),
        sa.Column("exchange_testnet", sa.String(length=16), nullable=False),
        sa.Column("execution_permission_max", sa.String(length=64), nullable=False),
        sa.Column("runtime_control_api_enabled", sa.String(length=16), nullable=False),
        sa.Column(
            "runtime_test_signal_injection_enabled",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "runtime_exchange_submit_gateway_binding_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "exchange_credentials_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "owner_confirmed_gateway_readiness_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("owner_operator_id", sa.String(length=128), nullable=False),
        sa.Column("owner_confirmation_reference", sa.String(length=240), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column(
            "required_gateway_methods",
            _json_type(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column(
            "gateway_injected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("exchange_called", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "exchange_order_submitted",
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
        sa.CheckConstraint(
            "status IN ('blocked', 'ready_for_manual_gateway_binding')",
            name="ck_rt_exchange_gateway_readiness_status",
        ),
        sa.CheckConstraint(
            "status != 'ready_for_manual_gateway_binding' "
            "OR owner_confirmed_gateway_readiness_review = true",
            name="ck_rt_exchange_gateway_readiness_owner",
        ),
        sa.CheckConstraint(
            "status != 'ready_for_manual_gateway_binding' "
            "OR runtime_exchange_submit_gateway_binding_enabled = true",
            name="ck_rt_exchange_gateway_readiness_binding_enabled",
        ),
        sa.CheckConstraint(
            "status != 'ready_for_manual_gateway_binding' "
            "OR exchange_credentials_present = true",
            name="ck_rt_exchange_gateway_readiness_credentials",
        ),
        sa.CheckConstraint(
            "gateway_injected = false",
            name="ck_rt_exchange_gateway_readiness_not_injected",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_exchange_gateway_readiness_no_exchange",
        ),
        sa.CheckConstraint(
            "exchange_order_submitted = false",
            name="ck_rt_exchange_gateway_readiness_no_exchange_submit",
        ),
        sa.CheckConstraint(
            "order_lifecycle_submit_called = false",
            name="ck_rt_exchange_gateway_readiness_no_lifecycle",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_rt_exchange_gateway_readiness_no_intent_status",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_exchange_gateway_readiness_no_owner_bounded",
        ),
        sa.CheckConstraint(
            "withdrawal_or_transfer_created = false",
            name="ck_rt_exchange_gateway_readiness_no_withdrawal",
        ),
    )
    op.create_index(
        "idx_rt_exchange_gateway_readiness_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )
    op.create_index(
        "idx_rt_exchange_gateway_readiness_env_time",
        TABLE,
        ["trading_env", "exchange_testnet", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_rt_exchange_gateway_readiness_env_time", table_name=TABLE)
    op.drop_index("idx_rt_exchange_gateway_readiness_status_time", table_name=TABLE)
    op.drop_table(TABLE)
