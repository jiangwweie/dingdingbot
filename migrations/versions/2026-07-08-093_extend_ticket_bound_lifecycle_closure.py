"""Extend ticket-bound lifecycle constraints for final closure.

Revision ID: 093
Revises: 092
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "093"
down_revision: Union[str, None] = "092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UP_STATUS = (
    "status IN ('entry_submit_sent', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_submitted', 'position_protected', 'tp1_filled', "
    "'sl_adjust_pending', 'runner_protected', 'final_exit_detected', "
    "'reconciliation_matched', 'budget_settled', 'review_recorded', "
    "'lifecycle_closed', 'blocked')"
)
DOWN_STATUS = (
    "status IN ('entry_submit_sent', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_submitted', 'position_protected', 'tp1_filled', "
    "'sl_adjust_pending', 'runner_protected', 'blocked')"
)
UP_EVENTS = (
    "event_type IN ('entry_submitted', 'entry_filled', "
    "'exit_protection_materialization_started', 'sl_submitted', "
    "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
    "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
    "'final_exit_detected', 'reconciliation_matched', 'budget_settled', "
    "'review_recorded', 'lifecycle_closed', 'hard_stopped')"
)
DOWN_EVENTS = (
    "event_type IN ('entry_submitted', 'entry_filled', "
    "'exit_protection_materialization_started', 'sl_submitted', "
    "'tp1_submitted', 'exit_protection_reconciled', 'tp1_filled', "
    "'sl_cancel_requested', 'runner_sl_submitted', 'runner_protected', "
    "'hard_stopped')"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(status=UP_STATUS, events=UP_EVENTS)
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
        UP_STATUS,
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
        UP_EVENTS,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        _sqlite_rebuild(status=DOWN_STATUS, events=DOWN_EVENTS)
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
        DOWN_STATUS,
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
        DOWN_EVENTS,
    )


def _sqlite_rebuild(*, status: str, events: str) -> None:
    with op.batch_alter_table(
        "brc_ticket_bound_order_lifecycle_runs", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_status", type_="check")
        batch_op.create_check_constraint("ck_brc_lifecycle_status", status)
    with op.batch_alter_table(
        "brc_ticket_bound_lifecycle_events", recreate="always"
    ) as batch_op:
        batch_op.drop_constraint("ck_brc_lifecycle_event_type", type_="check")
        batch_op.create_check_constraint("ck_brc_lifecycle_event_type", events)
