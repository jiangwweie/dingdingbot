"""Add runtime profile proposal snapshot to promotion confirmations

Revision ID: 064
Revises: 063
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "064"
down_revision: Union[str, None] = "063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "strategy_runtime_promotion_confirmations"
COLUMN = "runtime_profile_proposal_snapshot"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(TABLE) or _has_column(TABLE, COLUMN):
        return
    op.add_column(TABLE, sa.Column(COLUMN, _json_type(), nullable=True))


def downgrade() -> None:
    if not _has_column(TABLE, COLUMN):
        return
    op.drop_column(TABLE, COLUMN)
