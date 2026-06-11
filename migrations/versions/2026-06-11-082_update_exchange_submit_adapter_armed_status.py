"""Update exchange submit adapter armed status

Revision ID: 082
Revises: 081
Create Date: 2026-06-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "082"
down_revision: Union[str, None] = "081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_exchange_submit_adapter_results"
STATUS_CONSTRAINT = "ck_rt_exchange_submit_result_status"
ARMED_STATUS_EXPR = (
    "status IN ('blocked', 'exchange_submit_adapter_disabled', "
    "'exchange_submit_lock_required', 'exchange_submit_lock_acquired', "
    "'exchange_submit_adapter_armed', 'exchange_submit_adapter_not_implemented')"
)
LEGACY_STATUS_EXPR = (
    "status IN ('blocked', 'exchange_submit_adapter_disabled', "
    "'exchange_submit_lock_required', 'exchange_submit_lock_acquired', "
    "'exchange_submit_adapter_not_implemented')"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    has_action_authorization_id = _has_column(
        TABLE,
        "exchange_submit_action_authorization_id",
    )
    with op.batch_alter_table(TABLE) as batch_op:
        if not has_action_authorization_id:
            batch_op.add_column(
                sa.Column(
                    "exchange_submit_action_authorization_id",
                    sa.String(length=360),
                    nullable=True,
                )
            )
        batch_op.drop_constraint(STATUS_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(STATUS_CONSTRAINT, ARMED_STATUS_EXPR)


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    has_action_authorization_id = _has_column(
        TABLE,
        "exchange_submit_action_authorization_id",
    )
    with op.batch_alter_table(TABLE) as batch_op:
        batch_op.drop_constraint(STATUS_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(STATUS_CONSTRAINT, LEGACY_STATUS_EXPR)
        if has_action_authorization_id:
            batch_op.drop_column("exchange_submit_action_authorization_id")
