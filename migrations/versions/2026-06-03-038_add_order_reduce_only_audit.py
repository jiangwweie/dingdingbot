"""Add reduce_only audit field to orders.

Revision ID: 038
Revises: 037
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def upgrade() -> None:
    if not _has_column("orders", "reduce_only"):
        op.add_column(
            "orders",
            sa.Column(
                "reduce_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        if _dialect_name() != "sqlite":
            op.alter_column("orders", "reduce_only", server_default=None)


def downgrade() -> None:
    if _has_column("orders", "reduce_only"):
        op.drop_column("orders", "reduce_only")
