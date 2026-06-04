"""Align PG signals schema with runtime signal ORM.

Revision ID: 042
Revises: 041
Create Date: 2026-06-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "042"
down_revision: Union[str, None] = "041"
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


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    constraints = (
        inspector.get_foreign_keys(table_name)
        + inspector.get_unique_constraints(table_name)
        + inspector.get_pk_constraint(table_name).get("constrained_columns", [])
    )
    return any(
        isinstance(item, dict) and item.get("name") == constraint_name
        for item in constraints
    )


def _table_count(table_name: str) -> int:
    if not _has_table(table_name):
        return 0
    return int(op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], **kwargs) -> None:
    if _has_table(table_name) and not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, columns, **kwargs)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    if _has_table(table_name) and _has_index(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_constraint_if_exists(constraint_name: str, table_name: str, constraint_type: str) -> None:
    if _has_table(table_name) and _has_constraint(table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_=constraint_type)


def _create_runtime_signals_table() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("entry_price", sa.Numeric(36, 18), nullable=False),
        sa.Column("stop_loss", sa.Numeric(36, 18), nullable=False),
        sa.Column("position_size", sa.Numeric(36, 18), nullable=False),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("tags_json", _jsonb_type(), nullable=False),
        sa.Column("risk_info", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("take_profit_1", sa.Numeric(36, 18), nullable=True),
        sa.Column("closed_at", sa.Text(), nullable=True),
        sa.Column("pnl_ratio", sa.Numeric(36, 18), nullable=True),
        sa.Column("kline_timestamp", sa.BIGINT(), nullable=True),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Numeric(10, 6), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("pattern_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("ema_trend", sa.String(length=64), nullable=True),
        sa.Column("mtf_status", sa.String(length=64), nullable=True),
        sa.Column("superseded_by", sa.String(length=128), nullable=True),
        sa.Column("opposing_signal_id", sa.String(length=128), nullable=True),
        sa.Column("opposing_signal_score", sa.Numeric(10, 6), nullable=True),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_signals_direction"),
        sa.CheckConstraint("entry_price > 0", name="ck_signals_entry_price_positive"),
        sa.CheckConstraint("stop_loss > 0", name="ck_signals_stop_loss_positive"),
        sa.CheckConstraint("position_size > 0", name="ck_signals_position_size_positive"),
        sa.CheckConstraint("leverage > 0", name="ck_signals_leverage_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_id", name="uq_signals_signal_id"),
    )
    _create_index_if_missing("idx_signals_symbol", "signals", ["symbol"])
    _create_index_if_missing("idx_signals_created_at", "signals", ["created_at"])
    _create_index_if_missing("idx_signals_status", "signals", ["status"])
    _create_index_if_missing("idx_signals_symbol_timeframe_status", "signals", ["symbol", "timeframe", "status"])
    _create_index_if_missing("idx_signals_source", "signals", ["source"])


def _create_signal_take_profits_table() -> None:
    op.create_table(
        "signal_take_profits",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("tp_id", sa.String(length=16), nullable=False),
        sa.Column("position_ratio", sa.Numeric(20, 8), nullable=False),
        sa.Column("risk_reward", sa.Numeric(20, 8), nullable=False),
        sa.Column("price_level", sa.Numeric(36, 18), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filled_at", sa.Text(), nullable=True),
        sa.Column("pnl_ratio", sa.Numeric(36, 18), nullable=True),
        sa.CheckConstraint(
            "position_ratio >= 0",
            name="ck_signal_take_profits_position_ratio_non_negative",
        ),
        sa.CheckConstraint(
            "risk_reward >= 0",
            name="ck_signal_take_profits_risk_reward_non_negative",
        ),
        sa.CheckConstraint(
            "price_level > 0",
            name="ck_signal_take_profits_price_level_positive",
        ),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.signal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("idx_signal_take_profits_signal_id", "signal_take_profits", ["signal_id"])
    _create_index_if_missing("idx_signal_take_profits_status", "signal_take_profits", ["status"])


def _create_signal_attempts_table() -> None:
    op.create_table(
        "signal_attempts",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.Column("pattern_score", sa.Numeric(12, 8), nullable=True),
        sa.Column("final_result", sa.String(length=32), nullable=False),
        sa.Column("filter_stage", sa.String(length=64), nullable=True),
        sa.Column("filter_reason", sa.Text(), nullable=True),
        sa.Column("details", _jsonb_type(), nullable=False),
        sa.Column("kline_timestamp", sa.BIGINT(), nullable=True),
        sa.Column("evaluation_summary", sa.Text(), nullable=True),
        sa.Column("trace_tree", _jsonb_type(), nullable=True),
        sa.Column("config_version", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index_if_missing("idx_signal_attempts_symbol", "signal_attempts", ["symbol"])
    _create_index_if_missing("idx_signal_attempts_created_at", "signal_attempts", ["created_at"])
    _create_index_if_missing("idx_signal_attempts_final_result", "signal_attempts", ["final_result"])
    _create_index_if_missing("idx_signal_attempts_symbol_timeframe", "signal_attempts", ["symbol", "timeframe"])


def upgrade() -> None:
    if _has_table("signals") and not _has_column("signals", "signal_id"):
        signals_count = _table_count("signals")
        backtest_count = _table_count("backtest_reports")
        if signals_count or backtest_count:
            raise RuntimeError(
                "Cannot auto-align legacy signals schema with existing rows; "
                f"signals={signals_count}, backtest_reports={backtest_count}. "
                "Run a controlled backfill migration first."
            )
        _drop_constraint_if_exists(
            "backtest_reports_strategy_id_fkey",
            "backtest_reports",
            "foreignkey",
        )
        op.drop_table("signals")

    if not _has_table("signals"):
        _create_runtime_signals_table()

    if not _has_table("signal_take_profits"):
        _create_signal_take_profits_table()

    if not _has_table("signal_attempts"):
        _create_signal_attempts_table()


def downgrade() -> None:
    if _has_table("signal_attempts"):
        op.drop_table("signal_attempts")
    if _has_table("signal_take_profits"):
        op.drop_table("signal_take_profits")
    if _has_table("signals"):
        if _table_count("signals"):
            raise RuntimeError("Refusing to downgrade non-empty runtime signals table.")
        op.drop_table("signals")
    op.create_table(
        "signals",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.Integer(), nullable=False),
        sa.Column("expected_entry", sa.String(length=32), nullable=False),
        sa.Column("expected_sl", sa.String(length=32), nullable=False),
        sa.Column("pattern_score", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="check_signals_direction"),
        sa.CheckConstraint("pattern_score >= 0.0 AND pattern_score <= 1.0", name="check_pattern_score_range"),
    )
    _create_index_if_missing("idx_signals_symbol", "signals", ["symbol"])
    _create_index_if_missing("idx_signals_timestamp", "signals", ["timestamp"])
    _create_index_if_missing("idx_signals_strategy", "signals", ["strategy_id"])
    _create_index_if_missing("idx_signals_is_active", "signals", ["is_active"])
