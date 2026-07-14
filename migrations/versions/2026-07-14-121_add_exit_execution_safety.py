"""Persist exit-protection generation and execution truth.

Revision ID: 121
Revises: 120
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "121"
down_revision: Union[str, None] = "120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDER_TABLE = "brc_ticket_bound_exit_protection_orders"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
OUTCOME_TABLE = "brc_live_outcome_ledger"
ACTIVE_GENERATION_INDEX = "idx_brc_exit_order_active_generation"


def upgrade() -> None:
    if _has_table(ORDER_TABLE):
        _add_column_if_missing(
            ORDER_TABLE,
            sa.Column(
                "generation",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )
        if not _has_index(ORDER_TABLE, ACTIVE_GENERATION_INDEX):
            op.create_index(
                ACTIVE_GENERATION_INDEX,
                ORDER_TABLE,
                ["exit_protection_set_id", "role", "generation", "status"],
            )

    if _has_table(COMMAND_TABLE):
        _add_column_if_missing(
            COMMAND_TABLE,
            sa.Column("execution_style", sa.String(32), nullable=True),
        )
        _add_column_if_missing(
            COMMAND_TABLE,
            sa.Column("time_in_force", sa.String(16), nullable=True),
        )
        _add_column_if_missing(
            COMMAND_TABLE,
            sa.Column(
                "post_only",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        _add_column_if_missing(
            COMMAND_TABLE,
            sa.Column(
                "market_fallback_allowed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if _has_table(OUTCOME_TABLE):
        _add_column_if_missing(
            OUTCOME_TABLE,
            sa.Column("tp1_liquidity_role", sa.String(16), nullable=True),
        )
        _add_column_if_missing(
            OUTCOME_TABLE,
            sa.Column("tp1_fee", sa.Numeric(36, 18), nullable=True),
        )
        _add_column_if_missing(
            OUTCOME_TABLE,
            sa.Column("tp1_fee_asset", sa.String(32), nullable=True),
        )
        _add_column_if_missing(
            OUTCOME_TABLE,
            sa.Column(
                "exchange_configured_initial_leverage",
                sa.Numeric(18, 8),
                nullable=True,
            ),
        )
        _add_column_if_missing(
            OUTCOME_TABLE,
            sa.Column(
                "effective_account_exposure_leverage",
                sa.Numeric(18, 8),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _has_table(OUTCOME_TABLE):
        for column_name in (
            "effective_account_exposure_leverage",
            "exchange_configured_initial_leverage",
            "tp1_fee_asset",
            "tp1_fee",
            "tp1_liquidity_role",
        ):
            _drop_column_if_present(OUTCOME_TABLE, column_name)
    if _has_table(COMMAND_TABLE):
        for column_name in (
            "market_fallback_allowed",
            "post_only",
            "time_in_force",
            "execution_style",
        ):
            _drop_column_if_present(COMMAND_TABLE, column_name)
    if _has_table(ORDER_TABLE):
        if _has_index(ORDER_TABLE, ACTIVE_GENERATION_INDEX):
            op.drop_index(ACTIVE_GENERATION_INDEX, table_name=ORDER_TABLE)
        _drop_column_if_present(ORDER_TABLE, "generation")


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    return column_name in {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _has_index(table_name: str, index_name: str) -> bool:
    return index_name in {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _has_column(table_name, str(column.name)):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)
