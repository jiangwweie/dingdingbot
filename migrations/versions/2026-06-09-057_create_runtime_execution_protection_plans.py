"""Create runtime execution protection plan audit table

Revision ID: 057
Revises: 056
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "057"
down_revision: Union[str, None] = "056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_protection_plans"


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
        sa.Column("protection_plan_id", sa.String(length=260), primary_key=True),
        sa.Column("protection_plan_preview_id", sa.String(length=260), nullable=False),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("runtime_execution_intent_draft_id", sa.String(length=180), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("runtime_instance_id", sa.String(length=128), nullable=True),
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
        sa.Column("entry_price_reference", sa.Numeric(36, 18), nullable=True),
        sa.Column("requires_protection", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stop_reference", sa.String(length=256), nullable=True),
        sa.Column("stop_price_reference", sa.Numeric(36, 18), nullable=True),
        sa.Column("take_profit_references", _json_type(), nullable=False, server_default="[]"),
        sa.Column("risk_preview", _json_type(), nullable=False, server_default="{}"),
        sa.Column("protection_preview", _json_type(), nullable=False, server_default="{}"),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("protection_plan_recorded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("not_order", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("not_exchange_payload", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            "status IN ('blocked', 'ready_for_submit_adapter')",
            name="ck_runtime_execution_protection_plans_status",
        ),
        sa.CheckConstraint(
            "protection_plan_recorded = true",
            name="ck_runtime_execution_protection_plans_recorded",
        ),
        sa.CheckConstraint(
            "not_order = true",
            name="ck_runtime_execution_protection_plans_not_order",
        ),
        sa.CheckConstraint(
            "not_exchange_payload = true",
            name="ck_runtime_execution_protection_plans_not_exchange_payload",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_runtime_execution_protection_plans_no_intent_status_change",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_protection_plans_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_protection_plans_no_exchange_called",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_protection_plan_no_owner_bounded_exec",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_runtime_execution_protection_plans_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_protection_plans_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_protection_plans_source",
        TABLE,
        ["source_type", "source_id"],
    )
    op.create_index(
        "idx_runtime_execution_protection_plans_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_protection_plans_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_protection_plans_source", table_name=TABLE)
    op.drop_index("idx_runtime_execution_protection_plans_intent_time", table_name=TABLE)
    op.drop_table(TABLE)
