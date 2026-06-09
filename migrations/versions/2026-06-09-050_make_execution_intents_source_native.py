"""Make ExecutionIntent source-native

Revision ID: 050
Revises: 049
Create Date: 2026-06-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "execution_intents"
STATUS_CHECK = "ck_execution_intents_status"
SOURCE_NATIVE_STATUS_EXPR = (
    "status IN ('recorded', 'pending', 'blocked', 'submitted', 'failed', "
    "'protecting', 'partially_protected', 'completed')"
)
LEGACY_STATUS_EXPR = (
    "status IN ('pending', 'blocked', 'submitted', 'failed', "
    "'protecting', 'partially_protected', 'completed')"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(STATUS_CHECK, TABLE, type_="check")
        if _has_column(TABLE, "signal_id"):
            op.alter_column(TABLE, "signal_id", existing_type=sa.String(length=64), nullable=True)
        if _has_column(TABLE, "signal_payload"):
            op.alter_column(TABLE, "signal_payload", existing_type=_json_type(), nullable=True)
        op.create_check_constraint(STATUS_CHECK, TABLE, SOURCE_NATIVE_STATUS_EXPR)
        return

    with op.batch_alter_table(TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint(STATUS_CHECK, type_="check")
        if _has_column(TABLE, "signal_id"):
            batch_op.alter_column("signal_id", existing_type=sa.String(length=64), nullable=True)
        if _has_column(TABLE, "signal_payload"):
            batch_op.alter_column("signal_payload", existing_type=_json_type(), nullable=True)
        batch_op.create_check_constraint(STATUS_CHECK, SOURCE_NATIVE_STATUS_EXPR)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(STATUS_CHECK, TABLE, type_="check")
        if _has_column(TABLE, "signal_id"):
            op.alter_column(TABLE, "signal_id", existing_type=sa.String(length=64), nullable=False)
        if _has_column(TABLE, "signal_payload"):
            op.alter_column(TABLE, "signal_payload", existing_type=_json_type(), nullable=False)
        op.create_check_constraint(STATUS_CHECK, TABLE, LEGACY_STATUS_EXPR)
        return

    with op.batch_alter_table(TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint(STATUS_CHECK, type_="check")
        if _has_column(TABLE, "signal_id"):
            batch_op.alter_column("signal_id", existing_type=sa.String(length=64), nullable=False)
        if _has_column(TABLE, "signal_payload"):
            batch_op.alter_column("signal_payload", existing_type=_json_type(), nullable=False)
        batch_op.create_check_constraint(STATUS_CHECK, LEGACY_STATUS_EXPR)
