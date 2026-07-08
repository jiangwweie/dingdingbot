"""Extend ticket-bound lifecycle safety core statuses.

Revision ID: 094
Revises: 093
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "094"
down_revision: Union[str, None] = "093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UP_LIFECYCLE_STATUS = (
    "status IN ('entry_submit_sent', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_submitted', 'position_protected', 'tp1_filled', "
    "'sl_adjust_pending', 'runner_protected', 'final_exit_detected', "
    "'reconciliation_matched', 'budget_settled', 'review_recorded', "
    "'lifecycle_closed', 'blocked', 'submit_failed', 'entry_unknown', "
    "'entry_orphaned', 'entry_partial_fill_unhandled', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'tp1_or_sl_orphaned', 'runner_mutation_pending', "
    "'runner_mutation_failed', 'runner_reconciliation_mismatch', "
    "'position_closed_protection_live', 'final_exit_unknown', "
    "'settlement_blocked', 'review_blocked')"
)
DOWN_LIFECYCLE_STATUS = (
    "status IN ('entry_submit_sent', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_submitted', 'position_protected', 'tp1_filled', "
    "'sl_adjust_pending', 'runner_protected', 'final_exit_detected', "
    "'reconciliation_matched', 'budget_settled', 'review_recorded', "
    "'lifecycle_closed', 'blocked')"
)
UP_EXIT_SET_STATUS = (
    "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
    "'runner_protected', 'failed', 'closed', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'runner_mutation_pending', 'runner_mutation_failed', "
    "'runner_reconciliation_mismatch', 'position_closed_protection_live')"
)
DOWN_EXIT_SET_STATUS = (
    "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
    "'runner_protected', 'failed', 'closed')"
)
UP_EVENTS = (
    "event_type IN ('entry_submitted', 'entry_filled', "
    "'exit_protection_materialization_started', 'sl_submitted', "
    "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
    "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
    "'final_exit_detected', 'reconciliation_matched', 'budget_settled', "
    "'review_recorded', 'lifecycle_closed', 'hard_stopped', "
    "'submit_failed', 'entry_unknown', 'entry_orphaned', "
    "'entry_partial_fill_detected', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'tp1_or_sl_orphaned', 'runner_mutation_pending', "
    "'runner_mutation_failed', 'runner_reconciliation_mismatch', "
    "'position_closed_protection_live', 'final_exit_unknown', "
    "'settlement_blocked', 'review_blocked')"
)
DOWN_EVENTS = (
    "event_type IN ('entry_submitted', 'entry_filled', "
    "'exit_protection_materialization_started', 'sl_submitted', "
    "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
    "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
    "'final_exit_detected', 'reconciliation_matched', 'budget_settled', "
    "'review_recorded', 'lifecycle_closed', 'hard_stopped')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(
            lifecycle_status=UP_LIFECYCLE_STATUS,
            exit_set_status=UP_EXIT_SET_STATUS,
            events=UP_EVENTS,
        )
        return
    _replace_constraints(
        lifecycle_status=UP_LIFECYCLE_STATUS,
        exit_set_status=UP_EXIT_SET_STATUS,
        events=UP_EVENTS,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(
            lifecycle_status=DOWN_LIFECYCLE_STATUS,
            exit_set_status=DOWN_EXIT_SET_STATUS,
            events=DOWN_EVENTS,
        )
        return
    _replace_constraints(
        lifecycle_status=DOWN_LIFECYCLE_STATUS,
        exit_set_status=DOWN_EXIT_SET_STATUS,
        events=DOWN_EVENTS,
    )


def _replace_constraints(
    *,
    lifecycle_status: str,
    exit_set_status: str,
    events: str,
) -> None:
    op.execute(
        """
        ALTER TABLE brc_ticket_bound_order_lifecycle_runs
        DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_status
        """
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_status",
        "brc_ticket_bound_order_lifecycle_runs",
        lifecycle_status,
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
        exit_set_status,
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
        events,
    )


def _sqlite_rebuild(
    *,
    lifecycle_status: str,
    exit_set_status: str,
    events: str,
) -> None:
    with op.batch_alter_table(
        "brc_ticket_bound_order_lifecycle_runs", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_status", type_="check")
        batch_op.create_check_constraint("ck_brc_lifecycle_status", lifecycle_status)
    with op.batch_alter_table(
        "brc_ticket_bound_exit_protection_sets", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_exit_set_status", type_="check")
        batch_op.create_check_constraint("ck_brc_exit_set_status", exit_set_status)
    with op.batch_alter_table(
        "brc_ticket_bound_lifecycle_events", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_event_type", type_="check")
        batch_op.create_check_constraint("ck_brc_lifecycle_event_type", events)
