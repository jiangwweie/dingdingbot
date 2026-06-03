"""Align orders PG numeric audit columns with ORM.

Revision ID: 040
Revises: 039
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


NUMERIC_COLUMNS = [
    "price",
    "trigger_price",
    "requested_qty",
    "filled_qty",
    "average_exec_price",
]

BIGINT_COLUMNS = [
    "created_at",
    "updated_at",
    "filled_at",
]


def _column_type(table_name: str, column_name: str) -> str | None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return str(column["type"]).lower()
    return None


def _has_column(table_name: str, column_name: str) -> bool:
    return _column_type(table_name, column_name) is not None


def _drop_default(table_name: str, column_name: str) -> None:
    # Existing varchar defaults cannot always be cast during ALTER TYPE.
    op.execute(sa.text(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP DEFAULT"))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" or not sa.inspect(bind).has_table("orders"):
        return
    for column_name in NUMERIC_COLUMNS:
        if not _has_column("orders", column_name):
            continue
        if "numeric" in (_column_type("orders", column_name) or ""):
            continue
        _drop_default("orders", column_name)
        op.alter_column(
            "orders",
            column_name,
            type_=sa.Numeric(36, 18),
            existing_nullable=(column_name not in {"requested_qty", "filled_qty"}),
            postgresql_using=f"NULLIF({column_name}, '')::numeric",
        )
    for column_name in BIGINT_COLUMNS:
        if not _has_column("orders", column_name):
            continue
        if "bigint" in (_column_type("orders", column_name) or ""):
            continue
        _drop_default("orders", column_name)
        op.alter_column(
            "orders",
            column_name,
            type_=sa.BIGINT(),
            existing_nullable=(column_name == "filled_at"),
            postgresql_using=f"{column_name}::bigint",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" or not sa.inspect(bind).has_table("orders"):
        return
    for column_name in BIGINT_COLUMNS:
        if _has_column("orders", column_name):
            op.alter_column(
                "orders",
                column_name,
                type_=sa.Integer(),
                existing_nullable=(column_name == "filled_at"),
                postgresql_using=f"{column_name}::integer",
            )
    for column_name in NUMERIC_COLUMNS:
        if _has_column("orders", column_name):
            op.alter_column(
                "orders",
                column_name,
                type_=sa.String(),
                existing_nullable=(column_name not in {"requested_qty", "filled_qty"}),
                postgresql_using=f"{column_name}::text",
            )
