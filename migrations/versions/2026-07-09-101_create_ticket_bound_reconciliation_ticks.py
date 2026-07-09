"""Create ticket-bound reconciliation ticks and recovery hardening columns.

Revision ID: 101
Revises: 100
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "101"
down_revision: Union[str, None] = "100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TICK_TABLE = "brc_ticket_bound_reconciliation_ticks"
FREEZE_TABLE = "brc_ticket_bound_scope_freezes"
RECOVERY_TABLE = "brc_ticket_bound_protection_recovery_commands"

UP_LIFECYCLE_STATUS = (
    "status IN ('entry_submit_sent', 'entry_fill_pending', 'entry_filled', "
    "'exit_protection_submitted', 'position_protected', 'tp1_filled', "
    "'sl_adjust_pending', 'runner_protected', 'final_exit_detected', "
    "'reconciliation_matched', 'budget_settled', 'review_recorded', "
    "'lifecycle_closed', 'blocked', 'submit_failed', 'entry_unknown', "
    "'entry_orphaned', 'entry_partial_fill_unhandled', 'protection_missing', "
    "'protection_degraded', 'protection_submit_failed', "
    "'protection_reconciliation_mismatch', 'exchange_orphan_detected', "
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
    "'lifecycle_closed', 'blocked', 'submit_failed', 'entry_unknown', "
    "'entry_orphaned', 'entry_partial_fill_unhandled', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'tp1_or_sl_orphaned', 'runner_mutation_pending', "
    "'runner_mutation_failed', 'runner_reconciliation_mismatch', "
    "'position_closed_protection_live', 'final_exit_unknown', "
    "'settlement_blocked', 'review_blocked')"
)
UP_EXIT_SET_STATUS = (
    "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
    "'runner_protected', 'failed', 'closed', 'protection_missing', "
    "'protection_degraded', 'protection_submit_failed', "
    "'protection_reconciliation_mismatch', 'exchange_orphan_detected', "
    "'runner_mutation_pending', 'runner_mutation_failed', "
    "'runner_reconciliation_mismatch', 'position_closed_protection_live')"
)
DOWN_EXIT_SET_STATUS = (
    "status IN ('pending', 'materializing', 'submitted', 'reconciled', "
    "'runner_protected', 'failed', 'closed', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'runner_mutation_pending', 'runner_mutation_failed', "
    "'runner_reconciliation_mismatch', 'position_closed_protection_live')"
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
    "'protection_degraded', 'protection_submit_failed', "
    "'protection_reconciliation_mismatch', 'exchange_orphan_detected', "
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
    "'review_recorded', 'lifecycle_closed', 'hard_stopped', "
    "'submit_failed', 'entry_unknown', 'entry_orphaned', "
    "'entry_partial_fill_detected', 'protection_missing', "
    "'protection_submit_failed', 'protection_reconciliation_mismatch', "
    "'tp1_or_sl_orphaned', 'runner_mutation_pending', "
    "'runner_mutation_failed', 'runner_reconciliation_mismatch', "
    "'position_closed_protection_live', 'final_exit_unknown', "
    "'settlement_blocked', 'review_blocked')"
)


def upgrade() -> None:
    json_t = _json_type()
    if not _has_table(TICK_TABLE):
        op.create_table(
            TICK_TABLE,
            sa.Column("reconciliation_tick_id", sa.String(192), primary_key=True),
            sa.Column("ticket_id", sa.String(192), nullable=False),
            sa.Column("protected_submit_attempt_id", sa.String(192), nullable=False),
            sa.Column("tick_kind", sa.String(64), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("entry_state", sa.String(64), nullable=False),
            sa.Column("sl_state", sa.String(64), nullable=False),
            sa.Column("tp1_state", sa.String(64), nullable=False),
            sa.Column("position_state", sa.String(64), nullable=False),
            sa.Column("first_blocker", sa.String(160), nullable=True),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("warnings", json_t, nullable=False, server_default="[]"),
            sa.Column("next_action", sa.Text(), nullable=False),
            sa.Column("exchange_snapshot_ref", sa.String(192), nullable=True),
            sa.Column("exchange_snapshot_summary", json_t, nullable=False, server_default="{}"),
            sa.Column("visibility_deadline_ms", sa.BIGINT(), nullable=False),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_recon_tick_side"),
            sa.CheckConstraint(
                "tick_kind IN ('first_post_submit', 'scheduled', 'recovery_check')",
                name="ck_brc_recon_tick_kind",
            ),
            sa.CheckConstraint(
                "status IN ('pending_visibility', 'matched', 'mismatch', "
                "'recovery_required', 'hard_stopped')",
                name="ck_brc_recon_tick_status",
            ),
            sa.UniqueConstraint(
                "protected_submit_attempt_id",
                "tick_kind",
                name="uq_brc_recon_tick_attempt_kind",
            ),
        )
        op.create_index(
            "idx_brc_recon_tick_scope_status",
            TICK_TABLE,
            ["strategy_group_id", "symbol", "side", "status", "created_at_ms"],
        )
    if not _has_table(FREEZE_TABLE):
        op.create_table(
            FREEZE_TABLE,
            sa.Column("scope_freeze_id", sa.String(192), primary_key=True),
            sa.Column("strategy_group_id", sa.String(128), nullable=False),
            sa.Column("symbol", sa.String(128), nullable=False),
            sa.Column("side", sa.String(32), nullable=False),
            sa.Column("status", sa.String(64), nullable=False),
            sa.Column("source_kind", sa.String(96), nullable=False),
            sa.Column("source_id", sa.String(192), nullable=False),
            sa.Column("first_blocker", sa.String(160), nullable=False),
            sa.Column("blockers", json_t, nullable=False, server_default="[]"),
            sa.Column("freeze_scope", json_t, nullable=False, server_default="{}"),
            sa.Column("next_action", sa.Text(), nullable=False),
            sa.Column("authority_boundary", sa.Text(), nullable=False),
            sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
            sa.Column("updated_at_ms", sa.BIGINT(), nullable=False),
            sa.CheckConstraint("side IN ('long', 'short')", name="ck_brc_scope_freeze_side"),
            sa.CheckConstraint("status IN ('active', 'resolved')", name="ck_brc_scope_freeze_status"),
            sa.UniqueConstraint(
                "strategy_group_id",
                "symbol",
                "side",
                "status",
                name="uq_brc_scope_freeze_current",
            ),
        )
        op.create_index(
            "idx_brc_scope_freeze_scope",
            FREEZE_TABLE,
            ["strategy_group_id", "symbol", "side", "status"],
        )
    _add_recovery_column("execution_attempt_count", sa.Integer(), nullable=False, server_default="0")
    _add_recovery_column("max_execution_attempts", sa.Integer(), nullable=False, server_default="3")
    _add_recovery_column("scope_frozen", sa.Boolean(), nullable=False, server_default=sa.false())
    _add_recovery_column("freeze_scope", json_t, nullable=False, server_default="{}")
    _replace_lifecycle_constraints(
        lifecycle_status=UP_LIFECYCLE_STATUS,
        exit_set_status=UP_EXIT_SET_STATUS,
        events=UP_EVENTS,
    )


def downgrade() -> None:
    _replace_lifecycle_constraints(
        lifecycle_status=DOWN_LIFECYCLE_STATUS,
        exit_set_status=DOWN_EXIT_SET_STATUS,
        events=DOWN_EVENTS,
    )
    for column_name in (
        "freeze_scope",
        "scope_frozen",
        "max_execution_attempts",
        "execution_attempt_count",
    ):
        if _has_column(RECOVERY_TABLE, column_name):
            op.drop_column(RECOVERY_TABLE, column_name)
    if _has_table(FREEZE_TABLE):
        op.drop_table(FREEZE_TABLE)
    if _has_table(TICK_TABLE):
        op.drop_table(TICK_TABLE)


def _replace_lifecycle_constraints(
    *,
    lifecycle_status: str,
    exit_set_status: str,
    events: str,
) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
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


def _add_recovery_column(
    column_name: str,
    column_type: sa.types.TypeEngine,
    *,
    nullable: bool,
    server_default: str | sa.sql.elements.False_,
) -> None:
    if _has_table(RECOVERY_TABLE) and not _has_column(RECOVERY_TABLE, column_name):
        op.add_column(
            RECOVERY_TABLE,
            sa.Column(
                column_name,
                column_type,
                nullable=nullable,
                server_default=server_default,
            ),
        )


def _json_type() -> sa.types.TypeEngine:
    if str(op.get_bind().dialect.name) == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )
