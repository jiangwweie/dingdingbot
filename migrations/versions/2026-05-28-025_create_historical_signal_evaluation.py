"""Create BRC historical signal evaluation tables

Revision ID: 025
Revises: 024
Create Date: 2026-05-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "025"
down_revision: Union[str, None] = "024"
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


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not _has_table("brc_historical_signal_evaluation_runs"):
        op.create_table(
            "brc_historical_signal_evaluation_runs",
            sa.Column("run_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_version_id", sa.String(length=128), nullable=False),
            sa.Column("playbook_id", sa.String(length=128), nullable=True),
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
            sa.CheckConstraint("end_time_ms >= start_time_ms", name="ck_brc_hist_signal_eval_runs_time_range"),
            sa.CheckConstraint("sampling_interval_bars >= 1", name="ck_brc_hist_signal_eval_runs_interval"),
            sa.CheckConstraint("sample_limit >= 1", name="ck_brc_hist_signal_eval_runs_sample_limit"),
            sa.CheckConstraint(
                "status IN ('pending', 'running', 'completed', 'failed')",
                name="ck_brc_hist_signal_eval_runs_status",
            ),
            sa.PrimaryKeyConstraint("run_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_signal_eval_runs_strategy",
        "brc_historical_signal_evaluation_runs",
        ["strategy_family_id", "created_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_signal_eval_runs_status",
        "brc_historical_signal_evaluation_runs",
        ["status", "updated_at_ms"],
    )

    if not _has_table("brc_historical_signal_outputs"):
        op.create_table(
            "brc_historical_signal_outputs",
            sa.Column("signal_id", sa.String(length=128), nullable=False),
            sa.Column("run_id", sa.String(length=128), nullable=False),
            sa.Column("evaluation_id", sa.String(length=128), nullable=False),
            sa.Column("strategy_family_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("timestamp_ms", sa.BIGINT(), nullable=False),
            sa.Column("timeframe", sa.String(length=32), nullable=False),
            sa.Column("signal_type", sa.String(length=32), nullable=False),
            sa.Column("side", sa.String(length=16), nullable=False),
            sa.Column("confidence", sa.Numeric(18, 8), nullable=False),
            sa.Column("reason_codes", _jsonb_type(), nullable=False),
            sa.Column("data_quality_status", sa.String(length=32), nullable=False),
            sa.Column("evidence_payload", _jsonb_type(), nullable=False),
            sa.Column("review_plan", _jsonb_type(), nullable=False),
            sa.Column("not_order", sa.Boolean(), nullable=False),
            sa.Column("not_execution_intent", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "signal_type IN ('no_action', 'would_enter', 'would_exit', 'would_reduce', 'would_cancel', 'invalid')",
                name="ck_brc_hist_signal_outputs_type",
            ),
            sa.CheckConstraint("side IN ('long', 'short', 'none')", name="ck_brc_hist_signal_outputs_side"),
            sa.CheckConstraint(
                "data_quality_status IN ('ok', 'degraded', 'invalid')",
                name="ck_brc_hist_signal_outputs_quality",
            ),
            sa.CheckConstraint("not_order IS TRUE", name="ck_brc_hist_signal_outputs_not_order"),
            sa.CheckConstraint("not_execution_intent IS TRUE", name="ck_brc_hist_signal_outputs_not_exec_intent"),
            sa.PrimaryKeyConstraint("signal_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_signal_outputs_run",
        "brc_historical_signal_outputs",
        ["run_id", "timestamp_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_signal_outputs_symbol",
        "brc_historical_signal_outputs",
        ["symbol", "timestamp_ms"],
    )
    _create_index_if_missing(
        "idx_brc_hist_signal_outputs_type",
        "brc_historical_signal_outputs",
        ["signal_type", "side"],
    )

    if not _has_table("brc_historical_forward_outcomes"):
        op.create_table(
            "brc_historical_forward_outcomes",
            sa.Column("outcome_id", sa.String(length=192), nullable=False),
            sa.Column("run_id", sa.String(length=128), nullable=False),
            sa.Column("signal_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("timestamp_ms", sa.BIGINT(), nullable=False),
            sa.Column("side", sa.String(length=16), nullable=False),
            sa.Column("window_label", sa.String(length=32), nullable=False),
            sa.Column("bars_ahead", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("mfe_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("mae_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("time_to_mfe_bars", sa.Integer(), nullable=True),
            sa.Column("time_to_mae_bars", sa.Integer(), nullable=True),
            sa.Column("pain_before_profit_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("profit_giveback_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("follow_through", sa.Boolean(), nullable=False),
            sa.Column("invalidation_hit", sa.Boolean(), nullable=False),
            sa.Column("return_time_curve", _jsonb_type(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_hist_forward_outcomes_side"),
            sa.CheckConstraint(
                "status IN ('complete', 'incomplete', 'invalid')",
                name="ck_brc_hist_forward_outcomes_status",
            ),
            sa.CheckConstraint("bars_ahead >= 1", name="ck_brc_hist_forward_outcomes_bars"),
            sa.PrimaryKeyConstraint("outcome_id"),
        )
    _create_index_if_missing(
        "idx_brc_hist_forward_outcomes_run",
        "brc_historical_forward_outcomes",
        ["run_id", "window_label"],
    )
    _create_index_if_missing(
        "idx_brc_hist_forward_outcomes_signal",
        "brc_historical_forward_outcomes",
        ["signal_id"],
    )
    _create_index_if_missing(
        "idx_brc_hist_forward_outcomes_symbol",
        "brc_historical_forward_outcomes",
        ["symbol", "timestamp_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_hist_forward_outcomes_symbol",
        "idx_brc_hist_forward_outcomes_signal",
        "idx_brc_hist_forward_outcomes_run",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_forward_outcomes")
    if _has_table("brc_historical_forward_outcomes"):
        op.drop_table("brc_historical_forward_outcomes")

    for index_name in [
        "idx_brc_hist_signal_outputs_type",
        "idx_brc_hist_signal_outputs_symbol",
        "idx_brc_hist_signal_outputs_run",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_signal_outputs")
    if _has_table("brc_historical_signal_outputs"):
        op.drop_table("brc_historical_signal_outputs")

    for index_name in [
        "idx_brc_hist_signal_eval_runs_status",
        "idx_brc_hist_signal_eval_runs_strategy",
    ]:
        _drop_index_if_exists(index_name, "brc_historical_signal_evaluation_runs")
    if _has_table("brc_historical_signal_evaluation_runs"):
        op.drop_table("brc_historical_signal_evaluation_runs")
