"""Add BRC campaign carrier metadata

Revision ID: 020
Revises: 019
Create Date: 2026-05-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def upgrade() -> None:
    if _has_table("brc_campaigns") and not _has_column("brc_campaigns", "metadata"):
        op.add_column(
            "brc_campaigns",
            sa.Column("metadata", _jsonb_type(), nullable=False, server_default=sa.text("'{}'")),
        )
        if _dialect_name() != "sqlite":
            op.alter_column("brc_campaigns", "metadata", server_default=None)


def downgrade() -> None:
    if _has_column("brc_campaigns", "metadata"):
        op.drop_column("brc_campaigns", "metadata")
