"""Add candidate entry/risk/protection snapshots to runtime intent drafts

Revision ID: 054
Revises: 053
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "054"
down_revision: Union[str, None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_intent_drafts"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    if not _has_column(TABLE, "entry_price_reference"):
        op.add_column(
            TABLE,
            sa.Column("entry_price_reference", sa.Numeric(36, 18), nullable=True),
        )
    if not _has_column(TABLE, "risk_preview"):
        op.add_column(
            TABLE,
            sa.Column("risk_preview", _json_type(), nullable=False, server_default="{}"),
        )
    if not _has_column(TABLE, "protection_preview"):
        op.add_column(
            TABLE,
            sa.Column("protection_preview", _json_type(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    if _has_column(TABLE, "protection_preview"):
        op.drop_column(TABLE, "protection_preview")
    if _has_column(TABLE, "risk_preview"):
        op.drop_column(TABLE, "risk_preview")
    if _has_column(TABLE, "entry_price_reference"):
        op.drop_column(TABLE, "entry_price_reference")
