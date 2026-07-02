"""Create runtime execution controlled submit result audit table

Revision ID: 052
Revises: 051
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_controlled_submit_results"


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
        sa.Column("result_id", sa.String(length=260), primary_key=True),
        sa.Column("plan_id", sa.String(length=240), nullable=False),
        sa.Column("authorization_id", sa.String(length=220), nullable=False),
        sa.Column("execution_intent_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("blockers", _json_type(), nullable=False, server_default="[]"),
        sa.Column("warnings", _json_type(), nullable=False, server_default="[]"),
        sa.Column("submit_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
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
            "status IN ('blocked', 'submit_adapter_not_enabled', "
            "'submit_adapter_not_implemented')",
            name="ck_runtime_execution_controlled_submit_results_status",
        ),
        sa.CheckConstraint(
            "submit_executed = false",
            name="ck_rt_submit_result_no_submit",
        ),
        sa.CheckConstraint(
            "order_created = false",
            name="ck_runtime_execution_controlled_submit_results_no_order_created",
        ),
        sa.CheckConstraint(
            "exchange_called = false",
            name="ck_rt_submit_result_no_exchange",
        ),
        sa.CheckConstraint(
            "owner_bounded_execution_called = false",
            name="ck_rt_submit_result_no_owner_bounded_exec",
        ),
        sa.CheckConstraint(
            "order_lifecycle_called = false",
            name="ck_rt_submit_result_no_order_lifecycle",
        ),
    )
    op.create_index(
        "idx_runtime_execution_controlled_submit_results_auth_time",
        TABLE,
        ["authorization_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_controlled_submit_results_intent_time",
        TABLE,
        ["execution_intent_id", "created_at_ms"],
    )
    op.create_index(
        "idx_runtime_execution_controlled_submit_results_status_time",
        TABLE,
        ["status", "created_at_ms"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_controlled_submit_results_status_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_controlled_submit_results_intent_time", table_name=TABLE)
    op.drop_index("idx_runtime_execution_controlled_submit_results_auth_time", table_name=TABLE)
    op.drop_table(TABLE)
