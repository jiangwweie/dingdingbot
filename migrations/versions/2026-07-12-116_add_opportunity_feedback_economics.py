"""Add nullable post-trade OFC economics.

Revision ID: 116
Revises: 115
Create Date: 2026-07-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "116"
down_revision: Union[str, None] = "115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "brc_live_outcome_ledger"


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLE):
        return
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name in ("exit_slippage", "net_pnl"):
        if name not in columns:
            op.add_column(
                TABLE,
                sa.Column(name, sa.Numeric(36, 18), nullable=True),
            )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLE):
        return
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(TABLE)}
    for name in ("net_pnl", "exit_slippage"):
        if name in columns:
            op.drop_column(TABLE, name)
