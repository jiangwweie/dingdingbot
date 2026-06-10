"""Relax strategy runtime live enablement constraints

Revision ID: 065
Revises: 064
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "065"
down_revision: Union[str, None] = "064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RUNTIME_TABLE = "strategy_runtime_instances"
EXECUTION_DISABLED_CONSTRAINT = "ck_strategy_runtime_instances_execution_disabled"
SHADOW_MODE_CONSTRAINT = "ck_strategy_runtime_instances_shadow_mode"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_check_constraint(name: str) -> bool:
    if not _has_table(RUNTIME_TABLE):
        return False
    checks = sa.inspect(op.get_bind()).get_check_constraints(RUNTIME_TABLE)
    return any(check.get("name") == name for check in checks)


def _drop_check_constraint(name: str) -> None:
    if not _has_check_constraint(name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(RUNTIME_TABLE, recreate="always") as batch_op:
            batch_op.drop_constraint(name, type_="check")
        return
    op.drop_constraint(name, RUNTIME_TABLE, type_="check")


def _create_check_constraint(name: str, condition: str) -> None:
    if not _has_table(RUNTIME_TABLE) or _has_check_constraint(name):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(RUNTIME_TABLE, recreate="always") as batch_op:
            batch_op.create_check_constraint(name, condition)
        return
    op.create_check_constraint(name, RUNTIME_TABLE, condition)


def upgrade() -> None:
    _drop_check_constraint(EXECUTION_DISABLED_CONSTRAINT)
    _drop_check_constraint(SHADOW_MODE_CONSTRAINT)


def downgrade() -> None:
    _create_check_constraint(
        EXECUTION_DISABLED_CONSTRAINT,
        "execution_enabled = false",
    )
    _create_check_constraint(
        SHADOW_MODE_CONSTRAINT,
        "shadow_mode = true",
    )
