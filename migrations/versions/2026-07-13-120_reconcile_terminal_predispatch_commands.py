"""Reconcile protected-submit commands proven absent before dispatch.

Revision ID: 120
Revises: 119
Create Date: 2026-07-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "120"
down_revision: Union[str, None] = "119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
ATTEMPT_TABLE = "brc_ticket_bound_protected_submit_attempts"
REPAIR_CODE = "protected_submit_terminal_before_dispatch"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not (
        inspector.has_table(COMMAND_TABLE)
        and inspector.has_table(ATTEMPT_TABLE)
    ):
        return
    metadata = sa.MetaData()
    commands = sa.Table(COMMAND_TABLE, metadata, autoload_with=bind)
    attempts = sa.Table(ATTEMPT_TABLE, metadata, autoload_with=bind)
    terminal_attempt_ids = sa.select(
        attempts.c.protected_submit_attempt_id
    ).where(
        attempts.c.status.in_(("submit_failed", "hard_stopped", "blocked")),
        attempts.c.exchange_write_called.is_(False),
    )
    attempt_terminal_at_ms = (
        sa.select(attempts.c.updated_at_ms)
        .where(
            attempts.c.protected_submit_attempt_id
            == commands.c.protected_submit_attempt_id
        )
        .scalar_subquery()
    )
    bind.execute(
        commands.update()
        .where(
            commands.c.command_source == "protected_submit",
            commands.c.command_state == "prepared",
            commands.c.dispatch_started_at_ms.is_(None),
            commands.c.execution_attempt_count == 0,
            commands.c.exchange_order_id.is_(None),
            commands.c.protected_submit_attempt_id.in_(terminal_attempt_ids),
        )
        .values(
            command_state="reconciled_absent",
            outcome_class="reconciled_absence",
            exchange_error_code=REPAIR_CODE,
            exchange_error_message=(
                "source protected-submit attempt became terminal before any "
                "exchange dispatch"
            ),
            exchange_result={
                "exchange_write_called": False,
                "repair": REPAIR_CODE,
            },
            resolved_at_ms=attempt_terminal_at_ms,
            updated_at_ms=attempt_terminal_at_ms,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(COMMAND_TABLE):
        return
    commands = sa.Table(COMMAND_TABLE, sa.MetaData(), autoload_with=bind)
    bind.execute(
        commands.update()
        .where(
            commands.c.command_state == "reconciled_absent",
            commands.c.outcome_class == "reconciled_absence",
            commands.c.exchange_error_code == REPAIR_CODE,
        )
        .values(
            command_state="prepared",
            outcome_class="pending",
            exchange_error_code=None,
            exchange_error_message=None,
            exchange_result={},
            resolved_at_ms=None,
        )
    )
