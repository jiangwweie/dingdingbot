"""Close Ticket exit Runner static-reference and terminal projection gaps.

Revision ID: 139
Revises: 138
Create Date: 2026-07-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "139"
down_revision: Union[str, None] = "138"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CURRENT_TABLE = "brc_ticket_exit_policy_current"


def upgrade() -> None:
    if not _has_table(CURRENT_TABLE):
        return
    _add_column_if_missing(
        "exit_reference_schema_version",
        sa.Column("exit_reference_schema_version", sa.String(96), nullable=True),
    )
    _add_column_if_missing(
        "exit_reference_snapshot",
        sa.Column("exit_reference_snapshot", sa.JSON(), nullable=True),
    )
    _add_column_if_missing(
        "exit_reference_hash",
        sa.Column("exit_reference_hash", sa.String(64), nullable=True),
    )
    _add_column_if_missing(
        "exit_reference_bound_at_ms",
        sa.Column("exit_reference_bound_at_ms", sa.BIGINT(), nullable=True),
    )
    _add_column_if_missing(
        "terminal_at_ms",
        sa.Column("terminal_at_ms", sa.BIGINT(), nullable=True),
    )
    _extend_exit_order_role_constraint(include_final_exit=True)


def downgrade() -> None:
    if not _has_table(CURRENT_TABLE):
        return
    for name in (
        "terminal_at_ms",
        "exit_reference_bound_at_ms",
        "exit_reference_hash",
        "exit_reference_snapshot",
        "exit_reference_schema_version",
    ):
        _drop_column_if_present(name)
    _extend_exit_order_role_constraint(include_final_exit=False)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(column_name: str) -> bool:
    return column_name in {
        str(item["name"])
        for item in sa.inspect(op.get_bind()).get_columns(CURRENT_TABLE)
    }


def _add_column_if_missing(column_name: str, column: sa.Column) -> None:
    if not _has_column(column_name):
        op.add_column(CURRENT_TABLE, column)


def _drop_column_if_present(column_name: str) -> None:
    if not _has_column(column_name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(CURRENT_TABLE, recreate="always") as batch_op:
            batch_op.drop_column(column_name)
    else:
        op.drop_column(CURRENT_TABLE, column_name)


def _extend_exit_order_role_constraint(*, include_final_exit: bool) -> None:
    table_name = "brc_ticket_bound_exit_protection_orders"
    constraint = "ck_brc_exit_order_role"
    if not _has_table(table_name):
        return
    condition = (
        "role IN ('SL', 'TP1', 'SL_ADJUSTMENT', 'RUNNER_SL', 'FINAL_EXIT')"
        if include_final_exit
        else "role IN ('SL', 'TP1', 'SL_ADJUSTMENT', 'RUNNER_SL')"
    )
    names = {
        str(item.get("name") or "")
        for item in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    }
    if constraint not in names:
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch_op:
            batch_op.drop_constraint(constraint, type_="check")
            batch_op.create_check_constraint(constraint, condition)
    else:
        op.drop_constraint(constraint, table_name, type_="check")
        op.create_check_constraint(constraint, table_name, condition)
