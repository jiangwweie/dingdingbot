"""Allow local CREATED order status in orders table

Revision ID: 067
Revises: 066
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "067"
down_revision: Union[str, None] = "066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "orders"
LEGACY_STATUS_CONSTRAINT = "check_orders_status"
STATUS_CONSTRAINT = "ck_orders_status"

OLD_STATUS_CONDITION = (
    "status IN ('PENDING', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', "
    "'CANCELED', 'REJECTED', 'EXPIRED')"
)
NEW_STATUS_CONDITION = (
    "status IN ('CREATED', 'SUBMITTED', 'PENDING', 'OPEN', "
    "'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'REJECTED', 'EXPIRED')"
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _check_constraint_names() -> set[str]:
    if not _has_table(TABLE):
        return set()
    return {
        str(check.get("name"))
        for check in _inspector().get_check_constraints(TABLE)
        if check.get("name")
    }


def _replace_status_constraint(condition: str, *, name: str) -> None:
    if not _has_table(TABLE):
        return

    names = _check_constraint_names()
    if _dialect_name() == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            for constraint_name in (LEGACY_STATUS_CONSTRAINT, STATUS_CONSTRAINT):
                if constraint_name in names:
                    batch_op.drop_constraint(constraint_name, type_="check")
            batch_op.create_check_constraint(name, condition)
        return

    for constraint_name in (LEGACY_STATUS_CONSTRAINT, STATUS_CONSTRAINT):
        if constraint_name in names:
            op.drop_constraint(constraint_name, TABLE, type_="check")
    op.create_check_constraint(name, TABLE, condition)


def upgrade() -> None:
    _replace_status_constraint(NEW_STATUS_CONDITION, name=STATUS_CONSTRAINT)


def downgrade() -> None:
    _replace_status_constraint(OLD_STATUS_CONDITION, name=LEGACY_STATUS_CONSTRAINT)
