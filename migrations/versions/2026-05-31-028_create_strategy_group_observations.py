"""Create strategy group read-only observation evidence table

Revision ID: 028
Revises: 027
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "028"
down_revision: Union[str, None] = "027"
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
    if not _has_table("brc_strategy_group_observations"):
        op.create_table(
            "brc_strategy_group_observations",
            sa.Column("observation_id", sa.String(length=192), nullable=False),
            sa.Column("observed_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("strategy_group_id", sa.String(length=128), nullable=False),
            sa.Column("candidate_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=False),
            sa.Column("signal_type", sa.String(length=32), nullable=False),
            sa.Column("confidence", sa.Numeric(18, 8), nullable=False),
            sa.Column("reason_codes", _jsonb_type(), nullable=False),
            sa.Column("evidence_payload", _jsonb_type(), nullable=False),
            sa.Column("signal_snapshot", _jsonb_type(), nullable=False),
            sa.Column("invalidation_conditions", _jsonb_type(), nullable=False),
            sa.Column("human_summary", sa.Text(), nullable=False),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("market_source", sa.String(length=128), nullable=False),
            sa.Column("market_bar_timestamp_ms", sa.BIGINT(), nullable=False),
            sa.Column("market_bar_close", sa.Numeric(36, 18), nullable=True),
            sa.Column("review_windows", _jsonb_type(), nullable=False),
            sa.Column("review_status", _jsonb_type(), nullable=False),
            sa.Column("input_refs", _jsonb_type(), nullable=False),
            sa.Column("not_order", sa.Boolean(), nullable=False),
            sa.Column("not_execution_intent", sa.Boolean(), nullable=False),
            sa.Column("no_execution_permission", sa.Boolean(), nullable=False),
            sa.Column("no_order_permission", sa.Boolean(), nullable=False),
            sa.Column("no_runtime_start", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "signal_type IN ('no_action', 'would_enter', 'invalid')",
                name="ck_brc_strategy_group_observations_signal_type",
            ),
            sa.CheckConstraint("side IN ('long', 'short', 'none')", name="ck_brc_strategy_group_observations_side"),
            sa.CheckConstraint("not_order IS TRUE", name="ck_brc_strategy_group_observations_not_order"),
            sa.CheckConstraint(
                "not_execution_intent IS TRUE",
                name="ck_brc_strategy_group_observations_not_exec_intent",
            ),
            sa.CheckConstraint(
                "no_execution_permission IS TRUE",
                name="ck_brc_strategy_group_observations_no_exec_permission",
            ),
            sa.CheckConstraint(
                "no_order_permission IS TRUE",
                name="ck_brc_strategy_group_observations_no_order_permission",
            ),
            sa.CheckConstraint("no_runtime_start IS TRUE", name="ck_brc_strategy_group_observations_no_runtime"),
            sa.PrimaryKeyConstraint("observation_id"),
        )
    _create_index_if_missing(
        "idx_brc_strategy_group_observations_candidate",
        "brc_strategy_group_observations",
        ["candidate_id", "observed_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_group_observations_group",
        "brc_strategy_group_observations",
        ["strategy_group_id", "observed_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_group_observations_symbol",
        "brc_strategy_group_observations",
        ["symbol", "observed_at_ms"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_group_observations_signal",
        "brc_strategy_group_observations",
        ["signal_type", "side"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_strategy_group_observations_signal",
        "idx_brc_strategy_group_observations_symbol",
        "idx_brc_strategy_group_observations_group",
        "idx_brc_strategy_group_observations_candidate",
    ]:
        _drop_index_if_exists(index_name, "brc_strategy_group_observations")
    if _has_table("brc_strategy_group_observations"):
        op.drop_table("brc_strategy_group_observations")
