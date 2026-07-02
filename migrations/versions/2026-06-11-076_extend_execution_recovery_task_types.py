"""Extend execution recovery task types

Revision ID: 076
Revises: 075
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "076"
down_revision: Union[str, None] = "075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "execution_recovery_tasks"
CONSTRAINT = "ck_execution_recovery_tasks_recovery_type"
UPGRADED_EXPR = (
    "recovery_type IN ('replace_sl_failed', "
    "'exchange_submit_protection_fail')"
)
DOWNGRADED_EXPR = "recovery_type IN ('replace_sl_failed')"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(CONSTRAINT, UPGRADED_EXPR)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")
        batch_op.create_check_constraint(CONSTRAINT, DOWNGRADED_EXPR)
