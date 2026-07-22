from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.effects import (
    CancelEntryRemainder,
    CancelProtectionOrders,
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
    CancelOrderOutcomeUnknown,
    CancelOrderRejected,
    EntryAccepted,
    EntryFilled,
    EntryOutcomeUnknown,
    EntryPartiallyFilled,
    EntryRejected,
    ExternalFlatDetected,
    ExitAccepted,
    ExitOutcomeUnknown,
    ExitRejected,
    ExitRequested,
    InitialStopConfirmed,
    InitialStopOutcomeUnknown,
    InitialStopRejected,
    OwnedOrphanOrderDetected,
    PositionFlatConfirmed,
    ProtectionCancelConfirmed,
    ReconciliationMatched,
    ReviewRecorded,
    TicketIssued,
    UnownedOrderDetected,
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


def test_initial_stop_rejection_opens_hard_incident_and_requests_flatten() -> None:
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

    failed = reduce_event(
        aggregate,
        InitialStopRejected(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_rejected",
        ),
    )

    assert failed.aggregate.status is AggregateStatus.EXIT_PENDING
    assert failed.aggregate.entry_lane_held is True
    assert failed.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_rejected",
        ),
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="initial_stop_rejected",
        ),
    )

    flat = reduce_event(
        failed.aggregate,
        PositionFlatConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
        ),
    )
    assert flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert flat.aggregate.entry_lane_held is False
    assert flat.effects == (
        ReleaseEntryLane(ticket_id=ticket.identity.ticket_id),
    )


def test_unknown_initial_stop_outcome_is_conserved_and_flattened_without_retry() -> None:
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

    failed = reduce_event(
        aggregate,
        InitialStopOutcomeUnknown(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            reason="venue_timeout",
        ),
    )

    assert failed.aggregate.status is AggregateStatus.EXIT_PENDING
    assert failed.aggregate.entry_lane_held is True
    assert failed.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="initial_stop_outcome_unknown",
        ),
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="initial_stop_outcome_unknown",
        ),
    )


def test_external_flat_enters_reconciliation_and_cancels_owned_protection() -> None:
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

    external_flat = reduce_event(
        aggregate,
        ExternalFlatDetected(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
        ),
    )

    assert external_flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert external_flat.aggregate.position_qty == Decimal("0")
    assert external_flat.aggregate.pending_cancel_exchange_order_id == "stop-1"
    assert external_flat.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="external_flat",
        ),
        CancelProtectionOrders(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="stop-1",
        ),
    )


def test_unknown_exit_outcome_opens_incident_without_creating_retry() -> None:
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
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate

    unknown = reduce_event(
        aggregate,
        ExitOutcomeUnknown(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.EXIT_OUTCOME_UNKNOWN
    assert unknown.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="exit_outcome_unknown",
        ),
    )


def test_exit_rejection_enters_explicit_recovery_and_allows_new_request() -> None:
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
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate

    rejected = reduce_event(
        aggregate,
        ExitRejected(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.EXIT_REJECTED
    assert rejected.effects == (
        OpenIncident(
            ticket_id=ticket.identity.ticket_id,
            incident_kind="exit_rejected",
        ),
    )

    externally_flat = reduce_event(
        rejected.aggregate,
        PositionFlatConfirmed(
            event_id="event-6-flat",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=2_150,
        ),
    )
    assert externally_flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING

    retried = reduce_event(
        rejected.aggregate,
        ExitRequested(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=2_200,
            reason="recover_exit_rejection",
        ),
    )
    assert retried.aggregate.status is AggregateStatus.EXIT_PENDING
    assert retried.effects == (
        PrepareExitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=ticket.quantity,
            reason="recover_exit_rejection",
        ),
    )


def test_owned_orphan_order_requests_exact_durable_cancel() -> None:
    aggregate = _reconciliation_pending_aggregate()

    detected = reduce_event(
        aggregate,
        OwnedOrphanOrderDetected(
            event_id="event-8",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="owned-orphan-1",
        ),
    )

    assert detected.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert detected.effects == (
        CancelProtectionOrders(
            ticket_id=aggregate.identity.ticket_id,
            exchange_order_id="owned-orphan-1",
        ),
    )


def test_cancel_rejection_is_persisted_as_blocking_recovery_state() -> None:
    aggregate = _cancel_pending_aggregate()
    assert aggregate.pending_cancel_exchange_order_id == "stop-1"

    rejected = reduce_event(
        aggregate,
        CancelOrderRejected(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="stop-1",
            reason="venue_rejected",
        ),
    )

    assert rejected.aggregate.status is AggregateStatus.CANCEL_REJECTED
    assert rejected.aggregate.pending_cancel_exchange_order_id == "stop-1"
    assert rejected.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_rejected",
        ),
    )
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            rejected.aggregate,
            ReconciliationMatched(
                event_id="event-7",
                ticket_id=aggregate.identity.ticket_id,
                sequence=rejected.aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
            ),
        )


def test_unknown_cancel_outcome_is_conserved_and_blocks_reconciliation() -> None:
    aggregate = _cancel_pending_aggregate()

    unknown = reduce_event(
        aggregate,
        CancelOrderOutcomeUnknown(
            event_id="event-6",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_150,
            exchange_order_id="stop-1",
            reason="venue_timeout",
        ),
    )

    assert unknown.aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN
    assert unknown.aggregate.pending_cancel_exchange_order_id == "stop-1"
    assert unknown.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="cancel_order_outcome_unknown",
        ),
    )
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(
            unknown.aggregate,
            ReconciliationMatched(
                event_id="event-7",
                ticket_id=aggregate.identity.ticket_id,
                sequence=unknown.aggregate.last_event_sequence + 1,
                occurred_at_ms=2_200,
            ),
        )


def test_unowned_order_opens_incident_without_cancel_authority() -> None:
    aggregate = _reconciliation_pending_aggregate()

    detected = reduce_event(
        aggregate,
        UnownedOrderDetected(
            event_id="event-8",
            ticket_id=aggregate.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_200,
            exchange_order_id="manual-order-1",
        ),
    )

    assert detected.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert detected.effects == (
        OpenIncident(
            ticket_id=aggregate.identity.ticket_id,
            incident_kind="unowned_open_order",
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

    exit_accepted = reduce_event(
        exit_requested.aggregate,
        ExitAccepted(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_050,
            exchange_order_id="exit-order-1",
        ),
    )
    assert exit_accepted.aggregate.status is AggregateStatus.EXIT_ACCEPTED
    assert exit_accepted.aggregate.exit_exchange_order_id == "exit-order-1"

    flat = reduce_event(
        exit_accepted.aggregate,
        PositionFlatConfirmed(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=2_100,
        ),
    )
    assert flat.aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert flat.effects == (
        CancelProtectionOrders(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="stop-1",
        ),
    )

    cancelled = reduce_event(
        flat.aggregate,
        ProtectionCancelConfirmed(
            event_id="event-7",
            ticket_id=ticket.identity.ticket_id,
            sequence=7,
            occurred_at_ms=2_150,
            exchange_order_id="stop-1",
        ),
    )
    assert cancelled.aggregate.initial_stop_exchange_order_id is None
    assert cancelled.aggregate.protected_qty == Decimal("0")

    reconciled = reduce_event(
        cancelled.aggregate,
        ReconciliationMatched(
            event_id="event-8",
            ticket_id=ticket.identity.ticket_id,
            sequence=8,
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
            event_id="event-9",
            ticket_id=ticket.identity.ticket_id,
            sequence=9,
            occurred_at_ms=2_300,
        ),
    )
    assert settled.aggregate.status is AggregateStatus.REVIEW_PENDING
    assert settled.effects == ()

    terminal = reduce_event(
        settled.aggregate,
        ReviewRecorded(
            event_id="event-10",
            ticket_id=ticket.identity.ticket_id,
            sequence=10,
            occurred_at_ms=2_400,
            review_id="review-1",
        ),
    )
    assert terminal.aggregate.status is AggregateStatus.TERMINAL
    assert terminal.aggregate.review_id == "review-1"
    assert terminal.effects == ()


def _reconciliation_pending_aggregate():
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
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate
    aggregate = reduce_event(
        aggregate,
        PositionFlatConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        ProtectionCancelConfirmed(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=2_150,
            exchange_order_id="stop-1",
        ),
    ).aggregate


def _cancel_pending_aggregate():
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
    aggregate = reduce_event(
        aggregate,
        ExitRequested(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=2_000,
            reason="strategy_exit",
        ),
    ).aggregate
    return reduce_event(
        aggregate,
        PositionFlatConfirmed(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=2_100,
        ),
    ).aggregate


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
