"""Add additive ExecutionIntent source metadata

Revision ID: 049
Revises: 048
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "execution_intents"


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


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    columns = [
        ("source_type", sa.Column("source_type", sa.String(length=64), nullable=True)),
        ("source_id", sa.Column("source_id", sa.String(length=128), nullable=True)),
        ("source_payload", sa.Column("source_payload", _json_type(), nullable=True)),
        (
            "runtime_execution_intent_draft_id",
            sa.Column("runtime_execution_intent_draft_id", sa.String(length=180), nullable=True),
        ),
    ]
    for column_name, column in columns:
        if not _has_column(TABLE, column_name):
            op.add_column(TABLE, column)
    if not _has_index(TABLE, "idx_execution_intents_source"):
        op.create_index("idx_execution_intents_source", TABLE, ["source_type", "source_id"])
    if not _has_index(TABLE, "idx_execution_intents_runtime_draft"):
        op.create_index(
            "idx_execution_intents_runtime_draft",
            TABLE,
            ["runtime_execution_intent_draft_id"],
        )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    if _has_index(TABLE, "idx_execution_intents_runtime_draft"):
        op.drop_index("idx_execution_intents_runtime_draft", table_name=TABLE)
    if _has_index(TABLE, "idx_execution_intents_source"):
        op.drop_index("idx_execution_intents_source", table_name=TABLE)
    for column_name in [
        "runtime_execution_intent_draft_id",
        "source_payload",
        "source_id",
        "source_type",
    ]:
        if _has_column(TABLE, column_name):
            op.drop_column(TABLE, column_name)
