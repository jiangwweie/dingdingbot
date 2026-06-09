"""Create runtime order lifecycle handoff draft audit table

Revision ID: 058
Revises: 057
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "058"
down_revision: Union[str, None] = "057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_order_lifecycle_handoff_drafts"


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
        sa.Column("handoff_draft_id", sa.String(length=360), primary_key=True),
        sa.Column("preflight_id", sa.String(length=260), nullable=False),
        sa.Column("authorization_id", sa.String(length=220), nullable=False),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_mutation_id", sa.String(length=320), nullable=False),
        sa.Column("protection_plan_id", sa.String(length=260), nullable=False),
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
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("entry_order_type", sa.String(length=32), nullable=False),
        sa.Column("entry_order_role", sa.String(length=16), nullable=False),
        sa.Column("requested_qty", sa.Numeric(36, 18), nullable=False),
        sa.Column("intended_notional", sa.Numeric(36, 18), nullable=True),
        sa.Column("entry_price_reference", sa.Numeric(36, 18), nullable=True),
        sa.Column("stop_price_reference", sa.Numeric(36, 18), nullable=True),
        sa.Column("take_profit_references", _json_type(), nullable=False, server_default="[]"),
        sa.Column("entry_order_draft", _json_type(), nullable=False, server_default="{}"),
        sa.Column("protection_order_drafts", _json_type(), nullable=False, server_default="[]"),
        sa.Column("order_model_drafts", _json_type(), nullable=False, server_default="[]"),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("preflight_status", sa.String(length=64), nullable=False),
        sa.Column("attempt_mutation_status", sa.String(length=64), nullable=False),
        sa.Column("protection_plan_status", sa.String(length=64), nullable=False),
        sa.Column("order_lifecycle_method", sa.String(length=128), nullable=False),
        sa.Column("handoff_draft_recorded", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "requires_order_lifecycle_adapter",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "order_lifecycle_adapter_implemented",
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
            "status IN ('blocked', 'ready_for_order_lifecycle_adapter')",
            name="ck_runtime_execution_order_lifecycle_handoff_status",
        ),
        sa.CheckConstraint(
            "handoff_draft_recorded = true",
            name="ck_runtime_execution_order_lifecycle_handoff_recorded",
        ),
        sa.CheckConstraint(
            "requires_order_lifecycle_adapter = true",
            name="ck_runtime_execution_order_lifecycle_handoff_requires_adapter",
        ),
        sa.CheckConstraint(
            "order_lifecycle_adapter_implemented = false",
            name="ck_runtime_execution_order_lifecycle_handoff_adapter_disabled",
        ),
        sa.CheckConstraint(
            "execution_intent_status_changed = false",
            name="ck_runtime_execution_order_lifecycle_handoff_no_intent_status_change",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_order_lifecycle_handoff_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_order_lifecycle_handoff_no_exchange_called",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_runtime_execution_order_lifecycle_handoff_no_owner_bounded_execution",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_runtime_execution_order_lifecycle_handoff_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_order_lifecycle_handoff_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_order_lifecycle_handoff_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_order_lifecycle_handoff_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_order_lifecycle_handoff_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_order_lifecycle_handoff_intent_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_order_lifecycle_handoff_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
