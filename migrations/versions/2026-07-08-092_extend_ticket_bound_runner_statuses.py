"""Extend ticket-bound lifecycle statuses for runner protection.

Revision ID: 092
Revises: 091
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "092"
down_revision: Union[str, None] = "091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _upgrade_sqlite_batch()
        return
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_order_lifecycle_runs
        DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_status
        """
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_status",
        "brc_ticket_bound_order_lifecycle_runs",
        "status IN ('entry_submit_sent', 'entry_fill_pending', "
        "'entry_filled', 'exit_protection_submitted', 'position_protected', "
        "'tp1_filled', 'sl_adjust_pending', 'runner_protected', 'blocked')",
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_exit_protection_sets
        DROP CONSTRAINT IF EXISTS ck_brc_exit_set_status
        """
    )
    op.create_check_constraint(
        "ck_brc_exit_set_status",
        "brc_ticket_bound_exit_protection_sets",
        "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
        "'runner_protected', 'failed', 'closed')",
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_lifecycle_events
        DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_event_type
        """
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_event_type",
        "brc_ticket_bound_lifecycle_events",
        "event_type IN ('entry_submitted', 'entry_filled', "
        "'exit_protection_materialization_started', 'sl_submitted', "
        "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
        "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
        "'hard_stopped')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _downgrade_sqlite_batch()
        return
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_order_lifecycle_runs
        DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_status
        """
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_status",
        "brc_ticket_bound_order_lifecycle_runs",
        "status IN ('entry_submit_sent', 'entry_fill_pending', "
        "'entry_filled', 'exit_protection_submitted', "
        "'position_protected', 'blocked')",
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_exit_protection_sets
        DROP CONSTRAINT IF EXISTS ck_brc_exit_set_status
        """
    )
    op.create_check_constraint(
        "ck_brc_exit_set_status",
        "brc_ticket_bound_exit_protection_sets",
        "status IN ('pending', 'materializing', 'submitted', "
        "'reconciled', 'failed', 'closed')",
    )
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_lifecycle_events
        DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_event_type
        """
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_event_type",
        "brc_ticket_bound_lifecycle_events",
        "event_type IN ('entry_submitted', 'entry_filled', "
        "'exit_protection_materialization_started', 'sl_submitted', "
        "'tp1_submitted', 'exit_protection_reconciled', 'hard_stopped')",
    )


def _upgrade_sqlite_batch() -> None:
    with op.batch_alter_table(
        "brc_ticket_bound_order_lifecycle_runs", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_status", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_lifecycle_status",
            "status IN ('entry_submit_sent', 'entry_fill_pending', "
            "'entry_filled', 'exit_protection_submitted', 'position_protected', "
            "'tp1_filled', 'sl_adjust_pending', 'runner_protected', 'blocked')",
        )
    with op.batch_alter_table(
        "brc_ticket_bound_exit_protection_sets", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_exit_set_status", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_exit_set_status",
            "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
            "'runner_protected', 'failed', 'closed')",
        )
    with op.batch_alter_table(
        "brc_ticket_bound_lifecycle_events", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_lifecycle_event_type",
            "event_type IN ('entry_submitted', 'entry_filled', "
            "'exit_protection_materialization_started', 'sl_submitted', "
            "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
            "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
            "'hard_stopped')",
        )


def _downgrade_sqlite_batch() -> None:
    with op.batch_alter_table(
        "brc_ticket_bound_order_lifecycle_runs", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_status", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_lifecycle_status",
            "status IN ('entry_submit_sent', 'entry_fill_pending', "
            "'entry_filled', 'exit_protection_submitted', "
            "'position_protected', 'blocked')",
        )
    with op.batch_alter_table(
        "brc_ticket_bound_exit_protection_sets", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_exit_set_status", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_exit_set_status",
            "status IN ('pending', 'materializing', 'submitted', "
            "'reconciled', 'failed', 'closed')",
        )
    with op.batch_alter_table(
        "brc_ticket_bound_lifecycle_events", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_event_type", type_="check")
        batch_op.create_check_constraint(
            "ck_brc_lifecycle_event_type",
            "event_type IN ('entry_submitted', 'entry_filled', "
            "'exit_protection_materialization_started', 'sl_submitted', "
            "'tp1_submitted', 'exit_protection_reconciled', 'hard_stopped')",
        )
