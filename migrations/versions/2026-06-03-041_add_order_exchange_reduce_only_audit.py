"""Add exchange reduce-only payload audit to orders.

Revision ID: 041
Revises: 040
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def upgrade() -> None:
    if not _has_table("orders"):
        return
    if not _has_column("orders", "exchange_reduce_only_param_sent"):
        op.add_column(
            "orders",
            sa.Column("exchange_reduce_only_param_sent", sa.Boolean(), nullable=True),
        )
    if not _has_column("orders", "exchange_reduce_only_omit_reason"):
        op.add_column(
            "orders",
            sa.Column("exchange_reduce_only_omit_reason", sa.String(length=128), nullable=True),
        )


def downgrade() -> None:
    if not _has_table("orders"):
        return
    if _has_column("orders", "exchange_reduce_only_omit_reason"):
        op.drop_column("orders", "exchange_reduce_only_omit_reason")
    if _has_column("orders", "exchange_reduce_only_param_sent"):
        op.drop_column("orders", "exchange_reduce_only_param_sent")
