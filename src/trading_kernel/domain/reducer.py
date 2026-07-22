"""Deterministic state reduction for one Ticket lifecycle."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    CreateTradeReview,
    KernelEffect,
    OpenIncident,
    PrepareEntryCommand,
    PrepareExitCommand,
    PrepareInitialStopCommand,
    ReleaseBudget,
    ReleaseEntryLane,
    RequestControlledFlatten,
    SettleBudget,
)
from src.trading_kernel.domain.events import (
    BudgetSettled,
    EntryAccepted,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRejected,
    ExitRequested,
    InitialStopConfirmed,
    PositionFlatConfirmed,
    ReconciliationMatched,
    ReviewRecorded,
    TicketIssued,
    TradeEvent,
)


class InvalidLifecycleTransition(ValueError):
    """Raised when an event contradicts current Ticket lifecycle truth."""


class Reduction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    aggregate: TradeAggregate
    effects: tuple[KernelEffect, ...] = ()


def reduce_event(
    current: TradeAggregate | None,
    event: TradeEvent,
) -> Reduction:
    if current is None:
        return _issue_ticket(event)

    _require_event_identity_and_sequence(current, event)

    if isinstance(event, EntryAccepted):
        _require_status(current, AggregateStatus.ENTRY_PENDING)
        exchange_order_id = str(event.exchange_order_id or "").strip()
        if not exchange_order_id:
            raise InvalidLifecycleTransition("ENTRY acceptance requires order identity")
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_ACCEPTED,
            updates={"entry_exchange_order_id": exchange_order_id},
        )

    if isinstance(event, EntryOutcomeUnknown):
        _require_status(current, AggregateStatus.ENTRY_PENDING)
        if not str(event.reason or "").strip():
            raise InvalidLifecycleTransition("unknown ENTRY outcome requires reason")
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_OUTCOME_UNKNOWN,
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="entry_outcome_unknown",
                ),
            ),
        )

    if isinstance(event, EntryRejected):
        _require_status(current, AggregateStatus.ENTRY_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.ENTRY_REJECTED,
            effects=(
                ReleaseBudget(ticket_id=current.identity.ticket_id),
                ReleaseEntryLane(ticket_id=current.identity.ticket_id),
            ),
        )

    if isinstance(event, EntryFilled):
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.ENTRY_ACCEPTED},
        )
        if event.filled_qty != current.ticket.quantity:
            raise InvalidLifecycleTransition("full entry fill must equal Ticket quantity")
        if event.average_fill_price <= 0:
            raise InvalidLifecycleTransition("average fill price must be positive")
        return _transition(
            current,
            event,
            status=AggregateStatus.PROTECTION_PENDING,
            updates={
                "position_qty": event.filled_qty,
                "average_fill_price": event.average_fill_price,
            },
            effects=(
                PrepareInitialStopCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=event.filled_qty,
                    stop_price=current.ticket.initial_stop_price,
                ),
            ),
        )

    if isinstance(event, EntryPartiallyFilled):
        _require_status_in(
            current,
            {AggregateStatus.ENTRY_PENDING, AggregateStatus.ENTRY_ACCEPTED},
        )
        if not Decimal("0") < event.filled_qty < event.requested_qty:
            raise InvalidLifecycleTransition("partial fill quantity is contradictory")
        if event.requested_qty != current.ticket.quantity:
            raise InvalidLifecycleTransition("partial fill request differs from Ticket")
        return _transition(
            current,
            event,
            status=AggregateStatus.PARTIAL_FILL_INCIDENT,
            updates={
                "position_qty": event.filled_qty,
                "average_fill_price": event.average_fill_price,
            },
            effects=(
                OpenIncident(
                    ticket_id=current.identity.ticket_id,
                    incident_kind="unsupported_partial_entry_fill",
                ),
                CancelEntryRemainder(ticket_id=current.identity.ticket_id),
                RequestControlledFlatten(
                    ticket_id=current.identity.ticket_id,
                    quantity=event.filled_qty,
                ),
            ),
        )

    if isinstance(event, InitialStopConfirmed):
        _require_status(current, AggregateStatus.PROTECTION_PENDING)
        if event.protected_qty != current.position_qty:
            raise InvalidLifecycleTransition("initial stop does not cover exact position")
        if not str(event.exchange_order_id or "").strip():
            raise InvalidLifecycleTransition("initial stop order identity is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.POSITION_PROTECTED,
            updates={
                "protected_qty": event.protected_qty,
                "initial_stop_exchange_order_id": event.exchange_order_id.strip(),
            },
            effects=(ReleaseEntryLane(ticket_id=current.identity.ticket_id),),
        )

    if isinstance(event, ExitRequested):
        _require_status(current, AggregateStatus.POSITION_PROTECTED)
        reason = str(event.reason or "").strip()
        if not reason:
            raise InvalidLifecycleTransition("exit reason is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.EXIT_PENDING,
            effects=(
                PrepareExitCommand(
                    ticket_id=current.identity.ticket_id,
                    quantity=current.position_qty,
                    reason=reason,
                ),
            ),
        )

    if isinstance(event, PositionFlatConfirmed):
        _require_status(current, AggregateStatus.EXIT_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.RECONCILIATION_PENDING,
            updates={"position_qty": Decimal("0")},
            effects=(CancelProtectionOrders(ticket_id=current.identity.ticket_id),),
        )

    if isinstance(event, ReconciliationMatched):
        _require_status(current, AggregateStatus.RECONCILIATION_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.SETTLEMENT_PENDING,
            effects=(SettleBudget(ticket_id=current.identity.ticket_id),),
        )

    if isinstance(event, BudgetSettled):
        _require_status(current, AggregateStatus.SETTLEMENT_PENDING)
        return _transition(
            current,
            event,
            status=AggregateStatus.REVIEW_PENDING,
            effects=(CreateTradeReview(ticket_id=current.identity.ticket_id),),
        )

    if isinstance(event, ReviewRecorded):
        _require_status(current, AggregateStatus.REVIEW_PENDING)
        review_id = str(event.review_id or "").strip()
        if not review_id:
            raise InvalidLifecycleTransition("review identity is required")
        return _transition(
            current,
            event,
            status=AggregateStatus.TERMINAL,
            updates={"review_id": review_id},
            effects=(ReleaseBudget(ticket_id=current.identity.ticket_id),),
        )

    raise InvalidLifecycleTransition(f"unsupported event: {type(event).__name__}")


def _issue_ticket(event: TradeEvent) -> Reduction:
    if not isinstance(event, TicketIssued):
        raise InvalidLifecycleTransition("first event must issue a Ticket")
    if event.sequence != 1:
        raise InvalidLifecycleTransition("first event sequence must be one")
    aggregate = TradeAggregate(
        identity=event.ticket.identity,
        ticket=event.ticket,
        status=AggregateStatus.ENTRY_PENDING,
        version=1,
        last_event_sequence=event.sequence,
    )
    return Reduction(
        aggregate=aggregate,
        effects=(PrepareEntryCommand(ticket=event.ticket),),
    )


def _require_event_identity_and_sequence(
    current: TradeAggregate,
    event: TradeEvent,
) -> None:
    if isinstance(event, TicketIssued):
        raise InvalidLifecycleTransition("Ticket cannot be issued twice")
    if event.ticket_id != current.identity.ticket_id:
        raise InvalidLifecycleTransition("event Ticket identity mismatch")
    if event.sequence != current.last_event_sequence + 1:
        raise InvalidLifecycleTransition("event sequence is not monotonic")


def _require_status(current: TradeAggregate, expected: AggregateStatus) -> None:
    if current.status is not expected:
        raise InvalidLifecycleTransition(
            f"event requires {expected.value}, current is {current.status.value}"
        )


def _require_status_in(
    current: TradeAggregate,
    expected: set[AggregateStatus],
) -> None:
    if current.status not in expected:
        allowed = ", ".join(sorted(status.value for status in expected))
        raise InvalidLifecycleTransition(
            f"event requires one of {allowed}, current is {current.status.value}"
        )


def _transition(
    current: TradeAggregate,
    event: TradeEvent,
    *,
    status: AggregateStatus,
    updates: dict[str, object] | None = None,
    effects: tuple[KernelEffect, ...] = (),
) -> Reduction:
    aggregate = current.model_copy(
        update={
            "status": status,
            "version": current.version + 1,
            "last_event_sequence": event.sequence,
            **(updates or {}),
        }
    )
    return Reduction(aggregate=aggregate, effects=effects)
