"""Bind a ticket reservation to its account-capacity policy scope.

Revision ID: 124
Revises: 123
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "124"
down_revision: Union[str, None] = "123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_budget_reservations"


def upgrade() -> None:
    _add_column("exchange_instrument_id", sa.String(192))
    _add_column("account_risk_policy_version", sa.String(96))
    _add_column("risk_cluster_id", sa.String(128))
    _add_column("account_capacity_projection_version", sa.BIGINT())
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_brc_budget_res_account_capacity_scope "
            "ON brc_budget_reservations "
            "(account_id, account_risk_policy_version, risk_cluster_id) "
            "WHERE status IN ('active', 'consumed')"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_brc_budget_res_account_capacity_scope")
    for column_name in (
        "account_capacity_projection_version",
        "risk_cluster_id",
        "account_risk_policy_version",
        "exchange_instrument_id",
    ):
        if _has_column(column_name):
            op.drop_column(TABLE_NAME, column_name)


def _add_column(column_name: str, column_type: sa.types.TypeEngine) -> None:
    if not _has_column(column_name):
        op.add_column(TABLE_NAME, sa.Column(column_name, column_type, nullable=True))


def _has_column(column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(TABLE_NAME)
    )
