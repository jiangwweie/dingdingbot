"""Create BRC historical OHLCV dataset catalog

Revision ID: 023
Revises: 022
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_historical_ohlcv_datasets"):
        op.create_table(
            "brc_historical_ohlcv_datasets",
            sa.Column("dataset_id", sa.String(length=128), nullable=False),
            sa.Column("source", sa.String(length=128), nullable=False),
            sa.Column("market", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("timeframe", sa.String(length=32), nullable=False),
            sa.Column("start_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("end_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("storage_kind", sa.String(length=64), nullable=False),
            sa.Column("storage_ref", sa.String(length=512), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("data_quality_status", sa.String(length=64), nullable=False),
            sa.Column("missing_intervals", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_historical_ohlcv_time_range"),
            sa.CheckConstraint("row_count >= 0", name="ck_brc_historical_ohlcv_row_count"),
            sa.CheckConstraint(
                "storage_kind IN ('pg_table', 'local_file', 'external_ref')",
                name="ck_brc_historical_ohlcv_storage_kind",
            ),
            sa.CheckConstraint(
                "data_quality_status IN ('ok', 'degraded', 'invalid', 'unknown')",
                name="ck_brc_historical_ohlcv_quality",
            ),
            sa.PrimaryKeyConstraint("dataset_id"),
        )
    _create_index_if_missing(
        "idx_brc_historical_ohlcv_symbol_tf",
        "brc_historical_ohlcv_datasets",
        ["symbol", "timeframe"],
    )
    _create_index_if_missing(
        "idx_brc_historical_ohlcv_source_market",
        "brc_historical_ohlcv_datasets",
        ["source", "market"],
    )
    _create_index_if_missing(
        "idx_brc_historical_ohlcv_time_range",
        "brc_historical_ohlcv_datasets",
        ["start_time_ms", "end_time_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_historical_ohlcv_time_range",
        "idx_brc_historical_ohlcv_source_market",
        "idx_brc_historical_ohlcv_symbol_tf",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_ohlcv_datasets")
    if _has_table("brc_historical_ohlcv_datasets"):
        op.drop_table("brc_historical_ohlcv_datasets")
