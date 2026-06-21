"""Add owner report JSON to BRC historical signal evaluation runs

Revision ID: 026
Revises: 025
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("brc_historical_signal_evaluation_runs", "owner_report"):
        op.add_column(
            "brc_historical_signal_evaluation_runs",
            sa.Column("owner_report", _jsonb_type(), nullable=False, server_default=sa.text("'{}'")),
        )
        if op.get_bind().dialect.name != "sqlite":
            op.alter_column("brc_historical_signal_evaluation_runs", "owner_report", server_default=None)


def downgrade() -> None:
    if _has_column("brc_historical_signal_evaluation_runs", "owner_report"):
        op.drop_column("brc_historical_signal_evaluation_runs", "owner_report")
