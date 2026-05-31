"""Create strategy group read-only forward review table

Revision ID: 029
Revises: 028
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    if not _has_table("brc_strategy_group_forward_reviews"):
        op.create_table(
            "brc_strategy_group_forward_reviews",
            sa.Column("review_id", sa.String(length=224), nullable=False),
            sa.Column("observation_id", sa.String(length=192), nullable=False),
            sa.Column("candidate_id", sa.String(length=128), nullable=False),
            sa.Column("symbol", sa.String(length=128), nullable=False),
            sa.Column("side", sa.String(length=32), nullable=False),
            sa.Column("signal_type", sa.String(length=32), nullable=False),
            sa.Column("market_bar_timestamp_ms", sa.BIGINT(), nullable=False),
            sa.Column("review_window", sa.String(length=32), nullable=False),
            sa.Column("review_due_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("review_status", sa.String(length=32), nullable=False),
            sa.Column("forward_return_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("mfe_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("mae_pct", sa.Numeric(18, 8), nullable=True),
            sa.Column("source", sa.String(length=128), nullable=False),
            sa.Column("calculated_at_ms", sa.BIGINT(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("not_order", sa.Boolean(), nullable=False),
            sa.Column("not_execution_intent", sa.Boolean(), nullable=False),
            sa.Column("no_execution_permission", sa.Boolean(), nullable=False),
            sa.Column("no_order_permission", sa.Boolean(), nullable=False),
            sa.Column("no_runtime_start", sa.Boolean(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint(
                "signal_type IN ('no_action', 'would_enter', 'invalid')",
                name="ck_brc_strategy_group_forward_reviews_signal_type",
            ),
            sa.CheckConstraint(
                "side IN ('long', 'short', 'none')",
                name="ck_brc_strategy_group_forward_reviews_side",
            ),
            sa.CheckConstraint(
                "review_status IN ('pending', 'completed', 'not_applicable', 'failed')",
                name="ck_brc_strategy_group_forward_reviews_status",
            ),
            sa.CheckConstraint("not_order IS TRUE", name="ck_brc_strategy_group_forward_reviews_not_order"),
            sa.CheckConstraint(
                "not_execution_intent IS TRUE",
                name="ck_brc_strategy_group_forward_reviews_not_exec_intent",
            ),
            sa.CheckConstraint(
                "no_execution_permission IS TRUE",
                name="ck_brc_strategy_group_forward_reviews_no_exec_permission",
            ),
            sa.CheckConstraint(
                "no_order_permission IS TRUE",
                name="ck_brc_strategy_group_forward_reviews_no_order_permission",
            ),
            sa.CheckConstraint("no_runtime_start IS TRUE", name="ck_brc_strategy_group_forward_reviews_no_runtime"),
            sa.PrimaryKeyConstraint("review_id"),
        )
    _create_index_if_missing(
        "idx_brc_strategy_group_forward_reviews_observation",
        "brc_strategy_group_forward_reviews",
        ["observation_id", "review_window"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_group_forward_reviews_candidate",
        "brc_strategy_group_forward_reviews",
        ["candidate_id", "market_bar_timestamp_ms"],
    )
    _create_index_if_missing(
        "idx_brc_strategy_group_forward_reviews_status",
        "brc_strategy_group_forward_reviews",
        ["review_status", "review_due_at_ms"],
    )


def downgrade() -> None:
    for index_name in [
        "idx_brc_strategy_group_forward_reviews_status",
        "idx_brc_strategy_group_forward_reviews_candidate",
        "idx_brc_strategy_group_forward_reviews_observation",
    ]:
        _drop_index_if_exists(index_name, "brc_strategy_group_forward_reviews")
    if _has_table("brc_strategy_group_forward_reviews"):
        op.drop_table("brc_strategy_group_forward_reviews")
