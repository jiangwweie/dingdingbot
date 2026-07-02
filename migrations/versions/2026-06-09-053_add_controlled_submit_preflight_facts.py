"""Add controlled submit preflight facts to result audit table

Revision ID: 053
Revises: 052
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_controlled_submit_results"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def _drop_check(name: str) -> None:
    if _dialect_name() == "sqlite":
        return
    op.drop_constraint(name, TABLE, type_="check")


def _create_check(name: str, condition: str) -> None:
    if _dialect_name() == "sqlite":
        return
    op.create_check_constraint(name, TABLE, condition)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    if not _has_column(TABLE, "preflight_id"):
        op.add_column(TABLE, sa.Column("preflight_id", sa.String(length=260), nullable=False))
    if not _has_column(TABLE, "preflight_status"):
        op.add_column(TABLE, sa.Column("preflight_status", sa.String(length=64), nullable=False))
    if not _has_column(TABLE, "final_gate_verdict"):
        op.add_column(TABLE, sa.Column("final_gate_verdict", sa.String(length=16), nullable=False))

    _create_check(
        "ck_rt_submit_result_preflight_status",
        "preflight_status IN ('blocked', 'ready_for_controlled_submit_adapter')",
    )
    _create_check(
        "ck_rt_submit_result_gate_verdict",
        "final_gate_verdict IN ('PASS', 'WARN', 'BLOCK')",
    )
    op.create_index(
        "idx_runtime_execution_controlled_submit_results_preflight",
        TABLE,
        ["preflight_id"],
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    op.drop_index("idx_runtime_execution_controlled_submit_results_preflight", table_name=TABLE)
    _drop_check("ck_rt_submit_result_gate_verdict")
    _drop_check("ck_rt_submit_result_preflight_status")
    if _has_column(TABLE, "final_gate_verdict"):
        op.drop_column(TABLE, "final_gate_verdict")
    if _has_column(TABLE, "preflight_status"):
        op.drop_column(TABLE, "preflight_status")
    if _has_column(TABLE, "preflight_id"):
        op.drop_column(TABLE, "preflight_id")
