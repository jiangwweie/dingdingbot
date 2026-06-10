"""Add local_orders_registered ExecutionIntent status

Revision ID: 070
Revises: 069
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "070"
down_revision: Union[str, None] = "069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "execution_intents"
STATUS_CHECK = "ck_execution_intents_status"
OLD_STATUS_EXPR = (
    "status IN ('recorded', 'pending', 'blocked', 'submitted', 'failed', "
    "'protecting', 'partially_protected', 'completed')"
)
NEW_STATUS_EXPR = (
    "status IN ('recorded', 'local_orders_registered', 'pending', 'blocked', "
    "'submitted', 'failed', 'protecting', 'partially_protected', 'completed')"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    _replace_status_constraint(NEW_STATUS_EXPR)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    _replace_status_constraint(OLD_STATUS_EXPR)


def _replace_status_constraint(status_expr: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(STATUS_CHECK, type_="check")
            batch_op.create_check_constraint(STATUS_CHECK, status_expr)
        return

    op.drop_constraint(STATUS_CHECK, TABLE, type_="check")
    op.create_check_constraint(STATUS_CHECK, TABLE, status_expr)
