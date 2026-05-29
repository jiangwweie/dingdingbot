"""Create BRC historical research sampling run tables

Revision ID: 024
Revises: 023
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "024"
down_revision: Union[str, None] = "023"
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
    if not _has_table("brc_historical_research_sampling_runs"):
        op.create_table(
            "brc_historical_research_sampling_runs",
            sa.Column("run_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
            sa.Column("dataset_ids", _jsonb_type(), nullable=False),
            sa.Column("symbols", _jsonb_type(), nullable=False),
            sa.Column("primary_timeframe", sa.String(length=32), nullable=False),
            sa.Column("context_timeframes", _jsonb_type(), nullable=False),
            sa.Column("start_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("end_time_ms", sa.BIGINT(), nullable=False),
            sa.Column("sampling_method", sa.String(length=64), nullable=False),
            sa.Column("sampling_interval_bars", sa.Integer(), nullable=False),
            sa.Column("sample_limit", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("summary_json", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_hist_sampling_runs_time_range"),
            sa.CheckConstraint("sampling_interval_bars >= 1", name="ck_brc_hist_sampling_runs_interval"),
            sa.CheckConstraint("sample_limit >= 1", name="ck_brc_hist_sampling_runs_sample_limit"),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_brc_hist_sampling_runs_status",
            ),
            sa.PrimaryKeyConstraint("run_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_sampling_runs_strategy",
        "brc_historical_research_sampling_runs",
        ["strategy_family_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_sampling_runs_status",
        "brc_historical_research_sampling_runs",
        ["status", "updated_at_ms"],
    )

    if not _has_table("brc_historical_research_sampling_points"):
        op.create_table(
            "brc_historical_research_sampling_points",
            sa.Column("point_id", sa.String(length=192), nullable=False),
            sa.Column("run_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("timestamp_ms", sa.BIGINT(), nullable=False),
            sa.Column("primary_timeframe", sa.String(length=32), nullable=False),
            sa.Column("context_timeframes", _jsonb_type(), nullable=False),
            sa.Column("point_status", sa.String(length=32), nullable=False),
            sa.Column("market_snapshot_status", sa.String(length=32), nullable=False),
            sa.Column("signal_input_status", sa.String(length=32), nullable=False),
            sa.Column("data_quality_status", sa.String(length=32), nullable=False),
            sa.Column("missing_fields", _jsonb_type(), nullable=False),
            sa.Column("stale_fields", _jsonb_type(), nullable=False),
            sa.Column("warnings", _jsonb_type(), nullable=False),
            sa.Column("atr_available", sa.Boolean(), nullable=False),
            sa.Column("candle_context_available", sa.Boolean(), nullable=False),
            sa.Column("input_contract_valid", sa.Boolean(), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "point_status IN ('ok', 'degraded', 'invalid')",
                name="ck_brc_hist_sampling_points_status",
            ),
            sa.CheckConstraint(
                "market_snapshot_status IN ('ok', 'degraded', 'invalid')",
                name="ck_brc_hist_sampling_points_market_status",
            ),
            sa.CheckConstraint(
                "signal_input_status IN ('ok', 'degraded', 'invalid')",
                name="ck_brc_hist_sampling_points_input_status",
            ),
            sa.CheckConstraint(
                "data_quality_status IN ('ok', 'degraded', 'invalid')",
                name="ck_brc_hist_sampling_points_quality_status",
            ),
            sa.PrimaryKeyConstraint("point_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_sampling_points_run",
        "brc_historical_research_sampling_points",
        ["run_id", "timestamp_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_sampling_points_symbol_time",
        "brc_historical_research_sampling_points",
        ["symbol", "timestamp_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_sampling_points_status",
        "brc_historical_research_sampling_points",
        ["point_status"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_hist_sampling_points_status",
        "idx_brc_hist_sampling_points_symbol_time",
        "idx_brc_hist_sampling_points_run",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_research_sampling_points")
    if _has_table("brc_historical_research_sampling_points"):
        op.drop_table("brc_historical_research_sampling_points")

    for index_name in [
        "idx_brc_hist_sampling_runs_status",
        "idx_brc_hist_sampling_runs_strategy",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_research_sampling_runs")
    if _has_table("brc_historical_research_sampling_runs"):
        op.drop_table("brc_historical_research_sampling_runs")
