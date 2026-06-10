"""Allow runtime adapter local registration failure results

Revision ID: 069
Revises: 068
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "069"
down_revision: Union[str, None] = "068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "runtime_execution_order_lifecycle_adapter_results"


OLD_STATUS_CHECK = (
    "status IN ('blocked', 'order_lifecycle_adapter_disabled', "
    "'local_order_registration_disabled', 'duplicate_submit_lock_required', "
    "'local_registration_lock_acquired', 'registered_created_local_orders')"
)
NEW_STATUS_CHECK = (
    "status IN ('blocked', 'order_lifecycle_adapter_disabled', "
    "'local_order_registration_disabled', 'duplicate_submit_lock_required', "
    "'local_registration_lock_acquired', 'local_order_registration_failed', "
    "'registered_created_local_orders')"
)
OLD_NONREG_NO_EXEC_CHECK = (
    "status = 'registered_created_local_orders' "
    "OR local_order_registration_executed = false"
)
OLD_NONREG_NO_LIFECYCLE_CHECK = (
    "status = 'registered_created_local_orders' OR order_lifecycle_called = false"
)
NEW_NONREG_NO_EXEC_CHECK = (
    "status IN ('registered_created_local_orders', 'local_order_registration_failed') "
    "OR local_order_registration_executed = false"
)
NEW_NONREG_NO_LIFECYCLE_CHECK = (
    "status IN ('registered_created_local_orders', 'local_order_registration_failed') "
    "OR order_lifecycle_called = false"
)


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if not _has_table(TABLE):
        return
    _replace_check_constraints(
        status_check=NEW_STATUS_CHECK,
        nonreg_no_exec_check=NEW_NONREG_NO_EXEC_CHECK,
        nonreg_no_lifecycle_check=NEW_NONREG_NO_LIFECYCLE_CHECK,
    )


def downgrade() -> None:
    if not _has_table(TABLE):
        return
    _replace_check_constraints(
        status_check=OLD_STATUS_CHECK,
        nonreg_no_exec_check=OLD_NONREG_NO_EXEC_CHECK,
        nonreg_no_lifecycle_check=OLD_NONREG_NO_LIFECYCLE_CHECK,
    )


def _replace_check_constraints(
    *,
    status_check: str,
    nonreg_no_exec_check: str,
    nonreg_no_lifecycle_check: str,
) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch_op:
            _drop_constraints(batch_op, is_batch=True)
            _create_constraints(
                batch_op,
                is_batch=True,
                status_check=status_check,
                nonreg_no_exec_check=nonreg_no_exec_check,
                nonreg_no_lifecycle_check=nonreg_no_lifecycle_check,
            )
        return

    _drop_constraints(op, is_batch=False)
    _create_constraints(
        op,
        is_batch=False,
        status_check=status_check,
        nonreg_no_exec_check=nonreg_no_exec_check,
        nonreg_no_lifecycle_check=nonreg_no_lifecycle_check,
    )


def _drop_constraints(target, *, is_batch: bool) -> None:
    for name in (
        "ck_rt_ol_adapter_result_nonreg_no_lifecycle",
        "ck_rt_ol_adapter_result_nonreg_no_exec",
        "ck_rt_ol_adapter_result_status",
    ):
        if is_batch:
            target.drop_constraint(name, type_="check")
        else:
            target.drop_constraint(name, TABLE, type_="check")


def _create_constraints(
    target,
    *,
    is_batch: bool,
    status_check: str,
    nonreg_no_exec_check: str,
    nonreg_no_lifecycle_check: str,
) -> None:
    constraints = (
        ("ck_rt_ol_adapter_result_status", status_check),
        ("ck_rt_ol_adapter_result_nonreg_no_exec", nonreg_no_exec_check),
        (
            "ck_rt_ol_adapter_result_nonreg_no_lifecycle",
            nonreg_no_lifecycle_check,
        ),
    )
    for name, condition in constraints:
        if is_batch:
            target.create_check_constraint(name, condition)
        else:
            target.create_check_constraint(name, TABLE, condition)
