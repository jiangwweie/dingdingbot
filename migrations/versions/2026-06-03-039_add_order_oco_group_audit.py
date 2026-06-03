"""Add oco_group_id audit field to orders.

Revision ID: 039
Revises: 038
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("orders", "oco_group_id"):
        op.add_column("orders", sa.Column("oco_group_id", sa.String(length=64), nullable=True))
    if not _has_index("orders", "idx_orders_oco_group_id"):
        op.create_index("idx_orders_oco_group_id", "orders", ["oco_group_id"])


def downgrade() -> None:
    if _has_index("orders", "idx_orders_oco_group_id"):
        op.drop_index("idx_orders_oco_group_id", table_name="orders")
    if _has_column("orders", "oco_group_id"):
        op.drop_column("orders", "oco_group_id")
