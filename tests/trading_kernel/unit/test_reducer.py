from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
    CreateTradeReview,
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
)
from src.trading_kernel.domain.reducer import InvalidLifecycleTransition, reduce_event
from tests.trading_kernel.unit.test_ticket import _ticket


def test_ticket_issued_creates_entry_pending_aggregate_and_entry_effect() -> None:
    ticket = _ticket()

    reduction = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    )

    assert reduction.aggregate.status is AggregateStatus.ENTRY_PENDING
    assert reduction.aggregate.version == 1
    assert reduction.effects == (PrepareEntryCommand(ticket=ticket),)


def test_authoritative_entry_rejection_is_terminal_and_never_retries() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    rejected = reduce_event(
        issued,
        EntryRejected(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert rejected.effects == (
        ReleaseBudget(ticket_id=issued.identity.ticket_id),
        ReleaseEntryLane(ticket_id=issued.identity.ticket_id),
    )

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            rejected.aggregate,
            EntryFilled(
                event_id="event-3",
                ticket_id=issued.identity.ticket_id,
                sequence=3,
                occurred_at_ms=1_200,
                filled_qty=Decimal("0.001"),
                average_fill_price=Decimal("60000"),
            ),
        )


def test_entry_acceptance_is_conserved_before_fill() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    accepted = reduce_event(
        issued,
        EntryAccepted(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_050,
            exchange_order_id="entry-order-1",
        ),
    )

    assert accepted.aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert accepted.aggregate.entry_exchange_order_id == "entry-order-1"
    assert accepted.effects == ()


def test_unknown_entry_outcome_opens_incident_and_blocks_progression() -> None:
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    unknown = reduce_event(
        issued,
        EntryOutcomeUnknown(
            event_id="event-2",
            ticket_id=issued.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_050,
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert unknown.effects == (
        OpenIncident(
            ticket_id=issued.identity.ticket_id,
            incident_kind="entry_outcome_unknown",
        ),
    )


def test_full_entry_fill_requires_initial_stop_before_releasing_entry_lane() -> None:
    ticket = _ticket()
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    filled = reduce_event(
        issued,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal("60000"),
        ),
    )

    assert filled.aggregate.status is AggregateStatus.PROTECTION_PENDING
    assert filled.aggregate.position_qty == ticket.quantity
    assert filled.effects == (
        PrepareInitialStopCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            stop_price=ticket.initial_stop_price,
        ),
    )

    protected = reduce_event(
        filled.aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    )

    assert protected.aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert protected.aggregate.initial_stop_exchange_order_id == "stop-1"
    assert protected.effects == (
        ReleaseEntryLane(ticket_id=ticket.identity.ticket_id),
    )


def test_partial_entry_fill_is_incident_and_controlled_flatten_not_normal_position() -> None:
    ticket = _ticket()
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    reduction = reduce_event(
        issued,
        EntryPartiallyFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=Decimal("0.0004"),
            requested_qty=ticket.quantity,
            average_fill_price=Decimal("60000"),
        ),
    )

    assert reduction.aggregate.status is AggregateStatus.PARTIAL_FILL_INCIDENT
    assert reduction.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="unsupported_partial_entry_fill",
        ),
        CancelEntryRemainder(ticket_id=ticket.identity.ticket_id),
        RequestControlledFlatten(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.0004"),
        ),
    )


def test_protected_ticket_exits_reconciles_settles_reviews_and_terminates() -> None:
    ticket = _ticket()
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        EntryFilled(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            filled_qty=ticket.quantity,
            average_fill_price=Decimal("60000"),
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-1",
            protected_qty=ticket.quantity,
        ),
    ).aggregate

    exit_requested = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    )
    assert exit_requested.aggregate.status is AggregateStatus.EXIT_PENDING
    assert exit_requested.effects == (
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="strategy_exit",
        ),
    )

    flat = reduce_event(
        exit_requested.aggregate,
        PositionFlatConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
        ),
    )
    assert flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert flat.effects == (
        CancelProtectionOrders(ticket_id=ticket.identity.ticket_id),
    )

    reconciled = reduce_event(
        flat.aggregate,
        ReconciliationMatched(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=2_200,
        ),
    )
    assert reconciled.aggregate.status is AggregateStatus.SETTLEMENT_PENDING
    assert reconciled.effects == (
        SettleBudget(ticket_id=ticket.identity.ticket_id),
    )

    settled = reduce_event(
        reconciled.aggregate,
        BudgetSettled(
            event_id="event-7",
            ticket_id=ticket.identity.ticket_id,
            sequence=7,
            occurred_at_ms=2_300,
        ),
    )
    assert settled.aggregate.status is AggregateStatus.REVIEW_PENDING
    assert settled.effects == (
        CreateTradeReview(ticket_id=ticket.identity.ticket_id),
    )

    terminal = reduce_event(
        settled.aggregate,
        ReviewRecorded(
            event_id="event-8",
            ticket_id=ticket.identity.ticket_id,
            sequence=8,
            occurred_at_ms=2_400,
            review_id="review-1",
        ),
    )
    assert terminal.aggregate.status is AggregateStatus.TERMINAL
    assert terminal.aggregate.review_id == "review-1"
    assert terminal.effects == (
        ReleaseBudget(ticket_id=ticket.identity.ticket_id),
    )


def test_reducer_rejects_wrong_ticket_and_non_monotonic_sequence() -> None:
    aggregate = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=_ticket(),
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            aggregate,
            EntryRejected(
                event_id="event-2",
                ticket_id="ticket-wrong",
                sequence=2,
                occurred_at_ms=1_100,
                reason="venue_rejected",
            ),
        )

    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            aggregate,
            EntryRejected(
                event_id="event-2",
                ticket_id=aggregate.identity.ticket_id,
                sequence=1,
                occurred_at_ms=1_100,
                reason="venue_rejected",
            ),
        )
