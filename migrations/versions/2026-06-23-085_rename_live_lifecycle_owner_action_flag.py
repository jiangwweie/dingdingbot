"""Rename live lifecycle review owner action flag.

Revision ID: 085
Revises: 084
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "085"
down_revision: Union[str, None] = "084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_live_lifecycle_reviews"
LEGACY_OWNER_ACTION_COLUMN = "".join(("front", "end_action_enabled"))
NEW_COLUMN = "owner_action_enabled"
LEGACY_OWNER_ACTION_CHECK = "ck_brc_live_lifecycle_reviews_no_" + "front" + "end_action"
NEW_CHECK = "ck_brc_live_lifecycle_reviews_no_owner_action"


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def _columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(TABLE_NAME)}


def _checks() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {
        constraint["name"]
        for constraint in inspector.get_check_constraints(TABLE_NAME)
        if constraint.get("name")
    }


def _is_sqlite() -> bool:
    return str(op.get_bind().dialect.name) == "sqlite"


def _rename_column(
    *,
    old_column: str,
    new_column: str,
    old_check: str,
    new_check: str,
    new_condition: str,
) -> None:
    if not _has_table():
        return
    columns = _columns()
    if old_column not in columns or new_column in columns:
        return
    checks = _checks()
    if _is_sqlite():
        with op.batch_alter_table(TABLE_NAME, recreate="always") as batch_op:
            if old_check in checks:
                batch_op.drop_constraint(old_check, type_="check")
            batch_op.alter_column(
                old_column,
                new_column_name=new_column,
                existing_type=sa.Boolean(),
                existing_nullable=False,
                existing_server_default=sa.false(),
            )
            batch_op.create_check_constraint(new_check, new_condition)
        return

    if old_check in checks:
        op.drop_constraint(old_check, TABLE_NAME, type_="check")
    op.alter_column(
        TABLE_NAME,
        old_column,
        new_column_name=new_column,
        existing_type=sa.Boolean(),
        existing_nullable=False,
        existing_server_default=sa.false(),
    )
    op.create_check_constraint(new_check, TABLE_NAME, new_condition)


def upgrade() -> None:
    _rename_column(
        old_column=LEGACY_OWNER_ACTION_COLUMN,
        new_column=NEW_COLUMN,
        old_check=LEGACY_OWNER_ACTION_CHECK,
        new_check=NEW_CHECK,
        new_condition=f"{NEW_COLUMN} = false",
    )


def downgrade() -> None:
    _rename_column(
        old_column=NEW_COLUMN,
        new_column=LEGACY_OWNER_ACTION_COLUMN,
        old_check=NEW_CHECK,
        new_check=LEGACY_OWNER_ACTION_CHECK,
        new_condition=f"{LEGACY_OWNER_ACTION_COLUMN} = false",
    )
