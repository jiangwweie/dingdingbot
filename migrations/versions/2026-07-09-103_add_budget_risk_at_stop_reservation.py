"""Add stop-risk fields to ticket-bound budget reservations.

Revision ID: 103
Revises: 102
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "103"
down_revision: Union[str, None] = "102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_budget_reservations"


def upgrade() -> None:
    _add_column("entry_reference_price", sa.Numeric(36, 18), nullable=True)
    _add_column("stop_price", sa.Numeric(36, 18), nullable=True)
    _add_column("intended_qty", sa.Numeric(36, 18), nullable=True)
    _add_column("risk_at_stop", sa.Numeric(36, 18), nullable=True)
    _add_column("risk_reservation_basis", sa.String(96), nullable=True)
    _add_check(
        "ck_brc_budget_res_stop_risk_positive",
        "risk_at_stop IS NULL OR "
        "(entry_reference_price > 0 AND stop_price > 0 "
        "AND intended_qty > 0 AND risk_at_stop > 0)",
    )
    _add_check(
        "ck_brc_budget_res_stop_risk_protective_side",
        "risk_at_stop IS NULL OR "
        "((side = 'long' AND stop_price < entry_reference_price) OR "
        "(side = 'short' AND stop_price > entry_reference_price))",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"ALTER TABLE {TABLE_NAME} "
            "DROP CONSTRAINT IF EXISTS ck_brc_budget_res_stop_risk_protective_side"
        )
        op.execute(
            f"ALTER TABLE {TABLE_NAME} "
            "DROP CONSTRAINT IF EXISTS ck_brc_budget_res_stop_risk_positive"
        )
    for column_name in (
        "risk_reservation_basis",
        "risk_at_stop",
        "intended_qty",
        "stop_price",
        "entry_reference_price",
    ):
        if _has_column(column_name):
            op.drop_column(TABLE_NAME, column_name)


def _add_column(
    column_name: str,
    column_type: sa.types.TypeEngine,
    *,
    nullable: bool,
) -> None:
    if not _has_column(column_name):
        op.add_column(TABLE_NAME, sa.Column(column_name, column_type, nullable=nullable))


def _add_check(name: str, condition: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {TABLE_NAME} DROP CONSTRAINT IF EXISTS {name}")
    op.create_check_constraint(name, TABLE_NAME, condition)


def _has_column(column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME)
    )
