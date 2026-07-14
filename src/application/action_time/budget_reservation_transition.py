"""One audited state machine for Ticket budget reservations."""

from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa


_ALLOWED_EDGES = {
    ("active", "consumed"),
    ("active", "expired"),
    ("active", "invalidated"),
    ("consumed", "released"),
}
_TERMINAL_PRESUBMIT_TICKET_STATUSES = {
    "expired",
    "finalgate_rejected",
    "invalidated",
    "superseded",
}


class BudgetReservationTransitionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget_reservation_id: str
    status: str
    transitioned: bool
    first_blocker: str | None = None


def transition_budget_reservation(
    conn: sa.Connection,
    *,
    budget_reservation_id: str,
    to_status: str,
    reason: str,
    evidence_ref: str,
    now_ms: int,
) -> BudgetReservationTransitionResult:
    """Lock, validate, transition, and audit one reservation exactly once."""

    if not all((budget_reservation_id, to_status, reason, evidence_ref)) or now_ms <= 0:
        raise ValueError("reservation transition requires complete positive evidence")
    reservations = _table(conn, "brc_budget_reservations")
    events = _table(conn, "brc_budget_reservation_events")
    row = conn.execute(
        sa.select(reservations)
        .where(reservations.c.budget_reservation_id == budget_reservation_id)
        .with_for_update()
    ).mappings().one_or_none()
    if row is None:
        return BudgetReservationTransitionResult(
            budget_reservation_id=budget_reservation_id,
            status="missing",
            transitioned=False,
            first_blocker="budget_reservation_missing",
        )
    from_status = str(row["status"])
    if from_status == to_status:
        return BudgetReservationTransitionResult(
            budget_reservation_id=budget_reservation_id,
            status=from_status,
            transitioned=False,
        )
    if (from_status, to_status) not in _ALLOWED_EDGES:
        return BudgetReservationTransitionResult(
            budget_reservation_id=budget_reservation_id,
            status=from_status,
            transitioned=False,
            first_blocker="budget_reservation_transition_invalid",
        )
    values: dict[str, object] = {"status": to_status}
    if "release_reason" in reservations.c and to_status in {"released", "expired", "invalidated"}:
        values["release_reason"] = reason
    conn.execute(
        reservations.update()
        .where(reservations.c.budget_reservation_id == budget_reservation_id)
        .values(**values)
    )
    event_id = _stable_id(
        "budget_reservation_event",
        budget_reservation_id,
        from_status,
        to_status,
        evidence_ref,
    )
    if not conn.execute(
        sa.select(events.c.budget_reservation_event_id).where(
            events.c.budget_reservation_event_id == event_id
        )
    ).first():
        conn.execute(
            events.insert().values(
                budget_reservation_event_id=event_id,
                budget_reservation_id=budget_reservation_id,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                evidence_ref=evidence_ref,
                created_at_ms=now_ms,
            )
        )
    return BudgetReservationTransitionResult(
        budget_reservation_id=budget_reservation_id,
        status=to_status,
        transitioned=True,
    )


def reclaim_terminal_presubmit_reservations(
    conn: sa.Connection,
    *,
    now_ms: int,
    evidence_ref_prefix: str,
) -> int:
    """Release only terminal Ticket claims proven absent from exchange and exposure."""

    required_tables = {
        "brc_budget_reservations",
        "brc_budget_reservation_events",
        "brc_action_time_tickets",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_ticket_bound_exchange_commands",
        "brc_account_exposure_current",
    }
    if not required_tables <= set(sa.inspect(conn).get_table_names()):
        return 0
    reservations = _table(conn, "brc_budget_reservations")
    tickets = _table(conn, "brc_action_time_tickets")
    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    exposure = _table(conn, "brc_account_exposure_current")
    rows = conn.execute(
        sa.select(reservations.c.budget_reservation_id, reservations.c.ticket_id)
        .join(tickets, tickets.c.ticket_id == reservations.c.ticket_id)
        .where(reservations.c.status == "consumed")
        .where(tickets.c.status.in_(_TERMINAL_PRESUBMIT_TICKET_STATUSES))
    ).mappings()
    reclaimed = 0
    for row in rows:
        ticket_id = str(row["ticket_id"] or "")
        if not ticket_id:
            continue
        if _ticket_has_exchange_write_or_unknown(
            conn,
            attempts=attempts,
            commands=commands,
            ticket_id=ticket_id,
        ) or _ticket_claimed_position_slot(exposure, conn, ticket_id):
            continue
        result = transition_budget_reservation(
            conn,
            budget_reservation_id=str(row["budget_reservation_id"]),
            to_status="released",
            reason="terminal_presubmit_ticket_capacity_reclaimed",
            evidence_ref=f"{evidence_ref_prefix}:{ticket_id}",
            now_ms=now_ms,
        )
        reclaimed += int(result.transitioned)
    return reclaimed


def _table(conn: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _ticket_has_exchange_write_or_unknown(
    conn: sa.Connection,
    *,
    attempts: sa.Table,
    commands: sa.Table,
    ticket_id: str,
) -> bool:
    attempt_predicates = [attempts.c.ticket_id == ticket_id]
    if "exchange_write_called" in attempts.c:
        attempt_predicates.append(attempts.c.exchange_write_called.is_(True))
    else:
        return True
    if conn.execute(sa.select(attempts.c.ticket_id).where(sa.and_(*attempt_predicates)).limit(1)).first():
        return True
    required_command_columns = {"ticket_id", "command_state", "dispatch_started_at_ms", "exchange_order_id"}
    if not required_command_columns <= set(commands.c.keys()):
        return True
    unsafe_command = sa.or_(
        commands.c.dispatch_started_at_ms.is_not(None),
        commands.c.exchange_order_id.is_not(None),
        commands.c.command_state.not_in(("prepared", "reconciled_absent")),
    )
    return conn.execute(
        sa.select(commands.c.ticket_id)
        .where(commands.c.ticket_id == ticket_id)
        .where(unsafe_command)
        .limit(1)
    ).first() is not None


def _ticket_claimed_position_slot(
    exposure: sa.Table,
    conn: sa.Connection,
    ticket_id: str,
) -> bool:
    if not {"owner_ticket_id", "position_slot_claimed"} <= set(exposure.c.keys()):
        return True
    return conn.execute(
        sa.select(exposure.c.owner_ticket_id)
        .where(exposure.c.owner_ticket_id == ticket_id)
        .where(exposure.c.position_slot_claimed.is_(True))
        .limit(1)
    ).first() is not None


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]}"
