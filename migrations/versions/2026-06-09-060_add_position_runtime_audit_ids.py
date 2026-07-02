"""Add nullable runtime audit IDs to positions

Revision ID: 060
Revises: 059
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "060"
down_revision: Union[str, None] = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "positions"
AUDIT_ID_COLUMNS = [
    "runtime_instance_id",
    "trial_binding_id",
    "strategy_family_id",
    "strategy_family_version_id",
    "signal_evaluation_id",
    "order_candidate_id",
]
INDEXES = [
    ("idx_positions_runtime_instance_id", ["runtime_instance_id"]),
    ("idx_positions_strategy_family_version_id", ["strategy_family_version_id"]),
    ("idx_positions_order_candidate_id", ["order_candidate_id"]),
]


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    for column_name in AUDIT_ID_COLUMNS:
        if not _has_column(TABLE, column_name):
            op.add_column(
                TABLE,
                sa.Column(column_name, sa.String(length=128), nullable=True),
            )
    for index_name, columns in INDEXES:
        if not _has_index(TABLE, index_name):
            op.create_index(index_name, TABLE, columns)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    for index_name, _columns in reversed(INDEXES):
        if _has_index(TABLE, index_name):
            op.drop_index(index_name, table_name=TABLE)
    for column_name in reversed(AUDIT_ID_COLUMNS):
        if _has_column(TABLE, column_name):
            op.drop_column(TABLE, column_name)
