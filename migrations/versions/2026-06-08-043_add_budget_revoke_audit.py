"""Add budget authorization revoke audit fields

Revision ID: 043
Revises: 042
Create Date: 2026-06-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "brc_multi_carrier_budget_authorizations"
STATUS_CONSTRAINT = "ck_brc_budget_auth_status"
STATUS_CHECK = (
    "status IN ('draft_disabled_pending_owner_authorization', "
    "'active_metadata_only', 'paused_metadata_only', 'revoked', 'expired')"
)
LEGACY_STATUS_CHECK = "status IN ('draft_disabled_pending_owner_authorization')"


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        constraint.get("name") == constraint_name
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    )


def _dialect_name() -> str:
    return str(op.get_bind().dialect.name)


def _add_column_if_missing(column: sa.Column) -> None:
    if _has_table(TABLE_NAME) and not _has_column(TABLE_NAME, str(column.name)):
        op.add_column(TABLE_NAME, column)


def _drop_column_if_exists(column_name: str) -> None:
    if _has_table(TABLE_NAME) and _has_column(TABLE_NAME, column_name):
        op.drop_column(TABLE_NAME, column_name)


def _replace_status_constraint(check_sql: str) -> None:
    if not _has_table(TABLE_NAME):
        return
    if _dialect_name() != "postgresql":
        return
    if _has_check_constraint(TABLE_NAME, STATUS_CONSTRAINT):
        op.drop_constraint(STATUS_CONSTRAINT, TABLE_NAME, type_="check")
    op.create_check_constraint(STATUS_CONSTRAINT, TABLE_NAME, check_sql)


def upgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    _add_column_if_missing(sa.Column("revoked_at_ms", sa.BIGINT(), nullable=True))
    _add_column_if_missing(sa.Column("revoked_by", sa.String(length=128), nullable=True))
    _add_column_if_missing(sa.Column("revoke_reason", sa.Text(), nullable=True))
    _add_column_if_missing(sa.Column("last_control_operation_id", sa.String(length=128), nullable=True))
    _replace_status_constraint(STATUS_CHECK)


def downgrade() -> None:
    if not _has_table(TABLE_NAME):
        return
    non_legacy_status = op.get_bind().execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE_NAME} "
            "WHERE status <> 'draft_disabled_pending_owner_authorization'"
        )
    ).scalar()
    if int(non_legacy_status or 0) > 0:
        raise RuntimeError(
            "Refusing to downgrade budget authorization status constraint while "
            "non-legacy budget statuses are present."
        )
    _replace_status_constraint(LEGACY_STATUS_CHECK)
    for column_name in [
        "last_control_operation_id",
        "revoke_reason",
        "revoked_by",
        "revoked_at_ms",
    ]:
        _drop_column_if_exists(column_name)
