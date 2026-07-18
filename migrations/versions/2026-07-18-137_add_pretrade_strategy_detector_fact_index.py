"""Index durable strategy detector decisions by current lane.

Revision ID: 137
Revises: 136
Create Date: 2026-07-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "137"
down_revision: Union[str, None] = "136"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_runtime_fact_snapshots"
INDEX = "idx_brc_runtime_fact_pretrade_strategy_lane_time"


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLE):
        return
    indexes = {item.get("name") for item in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if INDEX not in indexes:
        op.create_index(
            INDEX,
            TABLE,
            ["fact_surface", "strategy_group_id", "symbol", "side", "observed_at_ms"],
        )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(TABLE):
        return
    indexes = {item.get("name") for item in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if INDEX in indexes:
        op.drop_index(INDEX, table_name=TABLE)
