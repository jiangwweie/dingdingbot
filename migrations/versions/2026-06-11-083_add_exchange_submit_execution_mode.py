"""Add exchange submit execution mode

Revision ID: 083
Revises: 082
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "083"
down_revision: Union[str, None] = "082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_execution_results"
MODE_CONSTRAINT = "ck_rt_exchange_exec_result_mode"
MODE_EXPR = (
    "execution_mode IN ('disabled', 'in_memory_simulation', "
    "'real_gateway_action')"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    constraints = sa.inspect(op.get_bind()).get_check_constraints(table_name)
    return any(constraint["name"] == constraint_name for constraint in constraints)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    has_execution_mode = _has_column(TABLE, "execution_mode")
    has_mode_constraint = _has_check_constraint(TABLE, MODE_CONSTRAINT)
    with op.batch_alter_table(TABLE) as batch_op:
        if not has_execution_mode:
            batch_op.add_column(
                sa.Column(
                    "execution_mode",
                    sa.String(length=48),
                    nullable=False,
                    server_default="disabled",
                )
            )
        if not has_mode_constraint:
            batch_op.create_check_constraint(MODE_CONSTRAINT, MODE_EXPR)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    has_execution_mode = _has_column(TABLE, "execution_mode")
    has_mode_constraint = _has_check_constraint(TABLE, MODE_CONSTRAINT)
    with op.batch_alter_table(TABLE) as batch_op:
        if has_mode_constraint:
            batch_op.drop_constraint(MODE_CONSTRAINT, type_="check")
        if has_execution_mode:
            batch_op.drop_column("execution_mode")
