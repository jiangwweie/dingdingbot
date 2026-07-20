"""Persist the terminal result for every conserved Action-Time invocation.

Revision ID: 142
Revises: 141
Create Date: 2026-07-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "142"
down_revision: Union[str, None] = "141"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "brc_action_time_invocations"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not sa.inspect(bind).has_table(TABLE):
        return
    columns = {item["name"] for item in sa.inspect(bind).get_columns(TABLE)}
    additions = (
        ("terminal_kind", sa.String(32)),
        ("terminal_reason_code", sa.String(160)),
        ("arbitration_rank", sa.Integer()),
        ("winner_signal_event_id", sa.String(192)),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column(TABLE, sa.Column(name, column_type, nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE brc_action_time_invocations
            SET terminal_kind = 'selected',
                terminal_reason_code = 'historical_ticket_bound_invocation'
            WHERE ticket_id IS NOT NULL
              AND closed_at_ms IS NOT NULL
              AND terminal_kind IS NULL
            """
        )
    )
    _replace_check(
        "ck_brc_action_time_invocation_terminal_kind",
        "terminal_kind IS NULL OR terminal_kind IN "
        "('selected','not_selected','expired','rejected','cancelled')",
    )
    _replace_check(
        "ck_brc_action_time_invocation_terminal_close",
        "terminal_kind IS NULL OR closed_at_ms IS NOT NULL",
    )
    _replace_check(
        "ck_brc_action_time_invocation_terminal_winner",
        "terminal_kind <> 'not_selected' OR winner_signal_event_id IS NOT NULL",
    )
    _replace_check(
        "ck_brc_action_time_invocation_arbitration_rank",
        "arbitration_rank IS NULL OR arbitration_rank > 0",
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brc_action_time_invocation_terminal "
        "ON brc_action_time_invocations (closed_at_ms, terminal_kind)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brc_action_time_invocation_winner "
        "ON brc_action_time_invocations (winner_signal_event_id) "
        "WHERE winner_signal_event_id IS NOT NULL"
    )


def _replace_check(name: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {name} CHECK ({expression})")


def downgrade() -> None:
    # Forward-only: terminal signal causality is audit lineage.
    return
