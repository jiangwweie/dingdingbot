"""Create PG execution intents table

Revision ID: 033
Revises: 032
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], **kwargs) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, **kwargs)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("execution_intents"):
        op.create_table(
            "execution_intents",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("signal_id", sa.String(length=64), nullable=False),
            sa.Column("symbol", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("order_id", sa.String(length=64), nullable=True),
            sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
            sa.Column("blocked_reason", sa.Text(), nullable=True),
            sa.Column("blocked_message", sa.Text(), nullable=True),
            sa.Column("failed_reason", sa.Text(), nullable=True),
            sa.Column("signal_payload", _jsonb_type(), nullable=False),
            sa.Column("strategy_payload", _jsonb_type(), nullable=True),
            sa.Column("created_at", sa.BIGINT(), nullable=False),
            sa.Column("updated_at", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'blocked', 'submitted', 'failed', "
                "'protecting', 'partially_protected', 'completed')",
                name="ck_execution_intents_status",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("idx_execution_intents_status", "execution_intents", ["status"])
    _create_index_if_missing("idx_execution_intents_symbol", "execution_intents", ["symbol"])
    _create_index_if_missing("idx_execution_intents_created_at", "execution_intents", ["created_at"])
    _create_index_if_missing(
        "uq_execution_intents_order_id",
        "execution_intents",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("order_id IS NOT NULL"),
    )
    _create_index_if_missing(
        "uq_execution_intents_exchange_order_id",
        "execution_intents",
        ["exchange_order_id"],
        unique=True,
        postgresql_where=sa.text("exchange_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    for index_name in [
        "uq_execution_intents_exchange_order_id",
        "uq_execution_intents_order_id",
        "idx_execution_intents_created_at",
        "idx_execution_intents_symbol",
        "idx_execution_intents_status",
    ]:
        _drop_index_if_exists(index_name, "execution_intents")
    if _has_table("execution_intents"):
        op.drop_table("execution_intents")
