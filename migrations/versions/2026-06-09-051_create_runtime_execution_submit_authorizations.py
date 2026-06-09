"""Create runtime execution submit authorization audit table

Revision ID: 051
Revises: 050
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_submit_authorizations"


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
        sa.Column("authorization_id", sa.String(length=220), primary_key=True),
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
        sa.Column(
            "owner_confirmed_for_submit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "owner_submit_authorized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("submit_executed", sa.Boolean(), nullable=False, server_default=sa.false()),
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
            "status IN ('approved_pending_controlled_submit')",
            name="ck_runtime_execution_submit_authorizations_status",
        ),
        sa.CheckConstraint(
            "owner_confirmed_for_submit = true",
            name="ck_runtime_execution_submit_authorizations_owner_confirmed",
        ),
        sa.CheckConstraint(
            "owner_submit_authorized = true",
            name="ck_runtime_execution_submit_authorizations_owner_authorized",
        ),
        sa.CheckConstraint(
            "submit_executed = false",
            name="ck_runtime_execution_submit_authorizations_no_submit_executed",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_submit_authorizations_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_runtime_execution_submit_authorizations_no_exchange_called",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_runtime_execution_submit_authorizations_no_owner_bounded_execution",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_runtime_execution_submit_authorizations_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_submit_auth_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_submit_auth_runtime_time",
        TABLE,
        ["runtime_instance_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_submit_auth_source",
        TABLE,
        ["source_type", "source_id"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_submit_auth_source", table_name=TABLE)
    op.drop_index("idx_runtime_execution_submit_auth_runtime_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_submit_auth_intent_time", table_name=TABLE)
    op.drop_table(TABLE)
