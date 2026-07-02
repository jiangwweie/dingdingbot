"""Align positions table with runtime read model ORM

Revision ID: 062
Revises: 061
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "positions"
ACTIVE_POSITION_INDEX = "uq_positions_active_symbol_direction"
INDEXES = [
    ("idx_positions_symbol", ["symbol"]),
    ("idx_positions_is_closed", ["is_closed"]),
    ("idx_positions_signal_id", ["signal_id"]),
    ("idx_positions_updated_at", ["updated_at"]),
]


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns() -> dict[str, dict]:
    if not _has_table(TABLE):
        return {}
    return {column["name"]: column for column in _inspector().get_columns(TABLE)}


def _has_index(index_name: str) -> bool:
    if not _has_table(TABLE):
        return False
    return any(index["name"] == index_name for index in _inspector().get_indexes(TABLE))


def _cast_text(column_name: str) -> str:
    return f"CAST({column_name} AS VARCHAR)"


def _coalesce_text(*column_names: str) -> str:
    parts = [_cast_text(name) for name in column_names]
    parts.append("'0'")
    return f"COALESCE({', '.join(parts)})"


def _coalesce_int(*column_names: str) -> str:
    parts = [name for name in column_names]
    parts.append("0")
    return f"COALESCE({', '.join(parts)})"


def _add_text_column(
    column_name: str,
    *,
    source_columns: Sequence[str],
    existing_columns: dict[str, dict],
) -> None:
    if column_name in existing_columns:
        return
    op.add_column(TABLE, sa.Column(column_name, sa.String(), nullable=True))
    available_sources = [name for name in source_columns if name in _columns()]
    expression = _coalesce_text(*available_sources) if available_sources else "'0'"
    op.execute(sa.text(f"UPDATE {TABLE} SET {column_name} = {expression} WHERE {column_name} IS NULL"))
    if _dialect_name() == "postgresql":
        op.alter_column(TABLE, column_name, nullable=False, existing_type=sa.String())


def _add_created_at(existing_columns: dict[str, dict]) -> None:
    if "created_at" in existing_columns:
        return
    op.add_column(TABLE, sa.Column("created_at", sa.BIGINT(), nullable=True))
    available_sources = [name for name in ("opened_at", "updated_at") if name in _columns()]
    expression = _coalesce_int(*available_sources) if available_sources else "0"
    op.execute(sa.text(f"UPDATE {TABLE} SET created_at = {expression} WHERE created_at IS NULL"))
    if _dialect_name() == "postgresql":
        op.alter_column(TABLE, "created_at", nullable=False, existing_type=sa.BIGINT())


def _column_type_name(column_name: str) -> str:
    column = _columns().get(column_name)
    if not column:
        return ""
    return str(column["type"]).lower()


def _align_is_closed_type() -> None:
    if _dialect_name() != "postgresql":
        return
    if "is_closed" not in _columns():
        op.add_column(
            TABLE,
            sa.Column("is_closed", sa.Integer(), nullable=False, server_default="0"),
        )
        return
    type_name = _column_type_name("is_closed")
    if "bool" not in type_name:
        return
    if _has_index(ACTIVE_POSITION_INDEX):
        op.drop_index(ACTIVE_POSITION_INDEX, table_name=TABLE)
    op.execute(sa.text(f"ALTER TABLE {TABLE} ALTER COLUMN is_closed DROP DEFAULT"))
    op.execute(
        sa.text(
            f"ALTER TABLE {TABLE} ALTER COLUMN is_closed TYPE integer "
            "USING CASE WHEN is_closed THEN 1 ELSE 0 END"
        )
    )
    op.execute(sa.text(f"ALTER TABLE {TABLE} ALTER COLUMN is_closed SET DEFAULT 0"))
    op.execute(sa.text(f"ALTER TABLE {TABLE} ALTER COLUMN is_closed SET NOT NULL"))
    op.create_index(
        ACTIVE_POSITION_INDEX,
        TABLE,
        ["symbol", "direction"],
        unique=True,
        postgresql_where=sa.text("is_closed = 0"),
    )


def _create_indexes() -> None:
    columns = _columns()
    for index_name, index_columns in INDEXES:
        if _has_index(index_name):
            continue
        if all(column_name in columns for column_name in index_columns):
            op.create_index(index_name, TABLE, index_columns)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    columns = _columns()
    _add_text_column(
        "current_qty",
        source_columns=("quantity",),
        existing_columns=columns,
    )
    columns = _columns()
    _add_text_column(
        "highest_price_since_entry",
        source_columns=("mark_price", "entry_price"),
        existing_columns=columns,
    )
    columns = _columns()
    _add_text_column(
        "total_fees_paid",
        source_columns=(),
        existing_columns=columns,
    )
    columns = _columns()
    _add_created_at(columns)
    _align_is_closed_type()
    _create_indexes()


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    columns = _columns()
    for column_name in (
        "created_at",
        "total_fees_paid",
        "highest_price_since_entry",
        "current_qty",
    ):
        if column_name in columns:
            op.drop_column(TABLE, column_name)
