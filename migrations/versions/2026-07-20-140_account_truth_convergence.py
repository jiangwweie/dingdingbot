"""Converge ticket-bound local-order identity and terminal failed-submit state.

Revision ID: 140
Revises: 139
Create Date: 2026-07-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "140"
down_revision: Union[str, None] = "139"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDER_TABLE = "orders"
LINEAGE_COLUMNS = (
    ("ticket_id", sa.String(192)),
    ("exchange_command_id", sa.String(192)),
    ("account_id", sa.String(192)),
    ("exchange_id", sa.String(128)),
    ("exchange_instrument_id", sa.String(192)),
    ("runtime_profile_id", sa.String(192)),
    ("strategy_group_id", sa.String(128)),
    ("exposure_episode_id", sa.String(192)),
)
LIFECYCLE_STATUS = (
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
    "'settlement_blocked', 'review_blocked', 'presubmit_reconciled_absent')"
)
LIFECYCLE_EVENTS = (
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
    "'settlement_blocked', 'review_blocked', 'presubmit_reconciled_absent')"
)


def upgrade() -> None:
    if _has_table(ORDER_TABLE):
        _widen_order_identity_columns()
        existing = _columns(ORDER_TABLE)
        for name, column_type in LINEAGE_COLUMNS:
            if name not in existing:
                op.add_column(ORDER_TABLE, sa.Column(name, column_type, nullable=True))
        if op.get_bind().dialect.name == "postgresql":
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_exchange_command_id "
                "ON orders (exchange_command_id) WHERE exchange_command_id IS NOT NULL"
            )
            op.execute(
                "ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_ticket_bound_lineage"
            )
            op.create_check_constraint(
                "ck_orders_ticket_bound_lineage",
                ORDER_TABLE,
                "exchange_command_id IS NULL OR "
                "(ticket_id IS NOT NULL AND account_id IS NOT NULL AND "
                "exchange_id IS NOT NULL AND exchange_instrument_id IS NOT NULL AND "
                "runtime_profile_id IS NOT NULL AND strategy_group_id IS NOT NULL AND "
                "exposure_episode_id IS NOT NULL)",
            )
    _replace_lifecycle_constraints()


def downgrade() -> None:
    _replace_lifecycle_constraints(include_presubmit=False)
    if not _has_table(ORDER_TABLE):
        return
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uq_orders_exchange_command_id")
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_ticket_bound_lineage")
    # Historical ticket-bound records remain representable during downgrade;
    # dropping their columns would be destructive and is intentionally avoided.


def _widen_order_identity_columns() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for name in ("id", "signal_id", "parent_order_id", "signal_evaluation_id"):
        if name in _columns(ORDER_TABLE):
            op.alter_column(ORDER_TABLE, name, type_=sa.String(192), existing_nullable=True)


def _replace_lifecycle_constraints(*, include_presubmit: bool = True) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    status = LIFECYCLE_STATUS
    events = LIFECYCLE_EVENTS
    if not include_presubmit:
        status = status.replace(", 'presubmit_reconciled_absent'", "")
        events = events.replace(", 'presubmit_reconciled_absent'", "")
    if _has_table("brc_ticket_bound_order_lifecycle_runs"):
        op.execute(
            "ALTER TABLE brc_ticket_bound_order_lifecycle_runs "
            "DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_status"
        )
        op.create_check_constraint(
            "ck_brc_lifecycle_status",
            "brc_ticket_bound_order_lifecycle_runs",
            status,
        )
    if _has_table("brc_ticket_bound_lifecycle_events"):
        op.execute(
            "ALTER TABLE brc_ticket_bound_lifecycle_events "
            "DROP CONSTRAINT IF EXISTS ck_brc_lifecycle_event_type"
        )
        op.create_check_constraint(
            "ck_brc_lifecycle_event_type",
            "brc_ticket_bound_lifecycle_events",
            events,
        )


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _columns(table_name: str) -> set[str]:
    return {str(item["name"]) for item in sa.inspect(op.get_bind()).get_columns(table_name)}
