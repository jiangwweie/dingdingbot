"""Release terminal pre-dispatch budget reservations conservatively.

Revision ID: 128
Revises: 127
Create Date: 2026-07-17
"""

from __future__ import annotations

from hashlib import sha256
import time
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "128"
down_revision: Union[str, None] = "127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TERMINAL_PRE_SUBMIT_STATUSES = ("expired", "finalgate_rejected", "invalidated", "superseded")
_REASON = "terminal_presubmit_ticket_capacity_reclaimed"
_EVIDENCE_REF = "migration:128"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    required = {
        "brc_budget_reservations",
        "brc_action_time_tickets",
        "brc_budget_reservation_events",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_ticket_bound_exchange_commands",
        "brc_account_exposure_current",
    }
    if not required <= set(inspector.get_table_names()):
        return
    reservations = sa.Table("brc_budget_reservations", sa.MetaData(), autoload_with=bind)
    tickets = sa.Table("brc_action_time_tickets", sa.MetaData(), autoload_with=bind)
    attempts = sa.Table(
        "brc_ticket_bound_protected_submit_attempts", sa.MetaData(), autoload_with=bind
    )
    commands = sa.Table(
        "brc_ticket_bound_exchange_commands", sa.MetaData(), autoload_with=bind
    )
    exposure = sa.Table("brc_account_exposure_current", sa.MetaData(), autoload_with=bind)
    events = sa.Table("brc_budget_reservation_events", sa.MetaData(), autoload_with=bind)
    candidates = bind.execute(
        sa.select(reservations.c.budget_reservation_id, reservations.c.ticket_id)
        .join(tickets, tickets.c.ticket_id == reservations.c.ticket_id)
        .where(reservations.c.status == "consumed")
        .where(tickets.c.status.in_(_TERMINAL_PRE_SUBMIT_STATUSES))
    ).mappings()
    now_ms = int(time.time() * 1000)
    for row in candidates:
        ticket_id = str(row["ticket_id"] or "")
        if (
            not ticket_id
            or _has_exchange_write(bind, attempts, ticket_id)
            or _has_command_write_or_unknown(bind, commands, ticket_id)
            or _has_slot_claim(bind, exposure, ticket_id)
        ):
            continue
        reservation_id = str(row["budget_reservation_id"])
        bind.execute(
            reservations.update()
            .where(reservations.c.budget_reservation_id == reservation_id)
            .where(reservations.c.status == "consumed")
            .values(status="released", release_reason=_REASON)
        )
        event_id = _stable_id(reservation_id)
        if not bind.execute(
            sa.select(events.c.budget_reservation_event_id).where(
                events.c.budget_reservation_event_id == event_id
            )
        ).first():
            bind.execute(
                events.insert().values(
                    budget_reservation_event_id=event_id,
                    budget_reservation_id=reservation_id,
                    from_status="consumed",
                    to_status="released",
                    reason=_REASON,
                    evidence_ref=_EVIDENCE_REF,
                    created_at_ms=now_ms,
                )
            )


def downgrade() -> None:
    # Data repair is intentionally non-destructive and has no automatic reversal.
    return None


def _has_exchange_write(bind: sa.Connection, attempts: sa.Table, ticket_id: str) -> bool:
    if "exchange_write_called" not in attempts.c:
        return True
    return bind.execute(
        sa.select(attempts.c.ticket_id)
        .where(attempts.c.ticket_id == ticket_id)
        .where(attempts.c.exchange_write_called.is_(True))
        .limit(1)
    ).first() is not None


def _has_command_write_or_unknown(
    bind: sa.Connection,
    commands: sa.Table,
    ticket_id: str,
) -> bool:
    required = {"ticket_id", "command_state", "dispatch_started_at_ms", "exchange_order_id"}
    if not required <= set(commands.c.keys()):
        return True
    return bind.execute(
        sa.select(commands.c.ticket_id)
        .where(commands.c.ticket_id == ticket_id)
        .where(
            sa.or_(
                commands.c.dispatch_started_at_ms.is_not(None),
                commands.c.exchange_order_id.is_not(None),
                commands.c.command_state.not_in(("prepared", "reconciled_absent")),
            )
        )
        .limit(1)
    ).first() is not None


def _has_slot_claim(bind: sa.Connection, exposure: sa.Table, ticket_id: str) -> bool:
    if not {"owner_ticket_id", "position_slot_claimed"} <= set(exposure.c.keys()):
        return True
    return bind.execute(
        sa.select(exposure.c.owner_ticket_id)
        .where(exposure.c.owner_ticket_id == ticket_id)
        .where(exposure.c.position_slot_claimed.is_(True))
        .limit(1)
    ).first() is not None


def _stable_id(reservation_id: str) -> str:
    return "budget_reservation_event:" + sha256(
        f"{reservation_id}|{_EVIDENCE_REF}".encode("utf-8")
    ).hexdigest()[:32]
