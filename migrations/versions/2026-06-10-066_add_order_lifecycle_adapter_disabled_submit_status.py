"""Add order lifecycle disabled controlled-submit status

Revision ID: 066
Revises: 065
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "066"
down_revision: Union[str, None] = "065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_controlled_submit_results"
STATUS_CONSTRAINT = "ck_runtime_execution_controlled_submit_results_status"
ORDER_LIFECYCLE_ADAPTER_COLUMN = "order_lifecycle_adapter_enabled"

OLD_STATUS_CONDITION = (
    "status IN ('blocked', 'submit_adapter_not_enabled', "
    "'submit_adapter_not_implemented')"
)
NEW_STATUS_CONDITION = (
    "status IN ('blocked', 'submit_adapter_not_enabled', "
    "'order_lifecycle_adapter_disabled', "
    "'submit_adapter_not_implemented')"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(column_name: str) -> bool:
    if not _has_table(TABLE):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(TABLE)
    return any(column["name"] == column_name for column in columns)


def _has_check_constraint(name: str) -> bool:
    if not _has_table(TABLE):
        return False
    checks = sa.inspect(op.get_bind()).get_check_constraints(TABLE)
    return any(check.get("name") == name for check in checks)


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def _add_order_lifecycle_adapter_column() -> None:
    if not _has_table(TABLE) or _has_column(ORDER_LIFECYCLE_ADAPTER_COLUMN):
        return
    op.add_column(
        TABLE,
        sa.Column(
            ORDER_LIFECYCLE_ADAPTER_COLUMN,
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def _drop_order_lifecycle_adapter_column() -> None:
    if not _has_table(TABLE) or not _has_column(ORDER_LIFECYCLE_ADAPTER_COLUMN):
        return
    if _dialect_name() == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            batch_op.drop_column(ORDER_LIFECYCLE_ADAPTER_COLUMN)
        return
    op.drop_column(TABLE, ORDER_LIFECYCLE_ADAPTER_COLUMN)


def _replace_status_constraint(condition: str) -> None:
    if not _has_table(TABLE):
        return
    if _dialect_name() == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            if _has_check_constraint(STATUS_CONSTRAINT):
                batch_op.drop_constraint(STATUS_CONSTRAINT, type_="check")
            batch_op.create_check_constraint(STATUS_CONSTRAINT, condition)
        return
    if _has_check_constraint(STATUS_CONSTRAINT):
        op.drop_constraint(STATUS_CONSTRAINT, TABLE, type_="check")
    op.create_check_constraint(STATUS_CONSTRAINT, TABLE, condition)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    _add_order_lifecycle_adapter_column()
    _replace_status_constraint(NEW_STATUS_CONDITION)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    _replace_status_constraint(OLD_STATUS_CONDITION)
    _drop_order_lifecycle_adapter_column()
