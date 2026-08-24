from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.drain_strategy_entry_vacuum import (
    VacuumTicketDrainFacts,
    plan_vacuum_ticket_drain,
)
from src.trading_kernel.domain.events import (
    EntryAccepted,
    EntryFilled,
    EntryVacuumCancelConfirmed,
    EntryVacuumCancelRequested,
    EntryVacuumOrderAbsenceConfirmed,
    TicketIssued,
    VacuumPartialFlattenRequired,
    VacuumPartialRetained,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.tickets import make_ticket

VACUUM_ID = "vacuum:SOR-001:1704067200000"


def test_open_entry_order_persists_exact_vacuum_cancel_request() -> None:
    aggregate = _accepted_aggregate()
    snapshot = _snapshot(
        quantity=Decimal(0),
        average_entry_price=None,
        open_entry_order=True,
    )

    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=VACUUM_ID,
            now_ms=1_200,
            position_snapshot=snapshot,
        )
    )

    assert isinstance(planned.event, EntryVacuumCancelRequested)
    assert planned.event.exchange_order_id == "entry-1"
    assert planned.event.observed_qty == 0


def test_cancel_acceptance_waits_for_order_absence_before_quantity_freeze() -> None:
    aggregate = _cancel_accepted_aggregate(observed_qty=Decimal(0))
    snapshot = _snapshot(
        quantity=Decimal("0.0006"),
        average_entry_price=Decimal(60000),
        open_entry_order=False,
    )

    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=VACUUM_ID,
            now_ms=1_300,
            position_snapshot=snapshot,
        )
    )

    assert isinstance(planned.event, EntryVacuumOrderAbsenceConfirmed)
    assert planned.event.final_filled_qty == Decimal("0.0006")


def test_frozen_partial_uses_certified_two_leg_exit_policy_split() -> None:
    aggregate = _quantity_frozen_aggregate(final_qty=Decimal("0.0006"))

    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=VACUUM_ID,
            now_ms=1_400,
            quantity_step=Decimal("0.0001"),
            tp1_quantity_fraction=Decimal("0.5"),
        )
    )

    assert isinstance(planned.event, VacuumPartialRetained)
    assert planned.event.effective_tp1_qty == Decimal("0.0003")
    assert planned.event.effective_runner_qty == Decimal("0.0003")


def test_frozen_one_step_partial_requires_controlled_flatten() -> None:
    aggregate = _quantity_frozen_aggregate(final_qty=Decimal("0.0001"))

    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=VACUUM_ID,
            now_ms=1_400,
            quantity_step=Decimal("0.0001"),
            tp1_quantity_fraction=Decimal("0.5"),
        )
    )

    assert isinstance(planned.event, VacuumPartialFlattenRequired)
    assert planned.event.reason == "vacuum_partial_two_leg_unavailable"


def test_frozen_full_fill_enters_normal_protection_chain() -> None:
    aggregate = _quantity_frozen_aggregate(final_qty=Decimal("0.001"))

    planned = plan_vacuum_ticket_drain(
        VacuumTicketDrainFacts(
            aggregate=aggregate,
            entry_vacuum_id=VACUUM_ID,
            now_ms=1_400,
        )
    )

    assert isinstance(planned.event, EntryFilled)
    assert planned.event.filled_qty == aggregate.ticket.quantity


def _accepted_aggregate():
    ticket = make_ticket()
    issued = reduce_event(
        None,
        TicketIssued(
            event_id="event-1",
            ticket=ticket,
            sequence=1,
            occurred_at_ms=1_001,
        ),
    ).aggregate
    return reduce_event(
        issued,
        EntryAccepted(
            event_id="event-2",
            ticket_id=ticket.identity.ticket_id,
            sequence=2,
            occurred_at_ms=1_100,
            exchange_order_id="entry-1",
        ),
    ).aggregate


def _cancel_accepted_aggregate(*, observed_qty: Decimal):
    aggregate = _accepted_aggregate()
    cancelling = reduce_event(
        aggregate,
        EntryVacuumCancelRequested(
            event_id="event-3",
            ticket_id=aggregate.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_150,
            entry_vacuum_id=VACUUM_ID,
            exchange_order_id="entry-1",
            observed_qty=observed_qty,
            average_fill_price=(Decimal(60000) if observed_qty > 0 else None),
        ),
    ).aggregate
    return reduce_event(
        cancelling,
        EntryVacuumCancelConfirmed(
            event_id="event-4",
            ticket_id=aggregate.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_200,
            exchange_order_id="entry-1",
        ),
    ).aggregate


def _quantity_frozen_aggregate(*, final_qty: Decimal):
    aggregate = _cancel_accepted_aggregate(observed_qty=Decimal(0))
    return reduce_event(
        aggregate,
        EntryVacuumOrderAbsenceConfirmed(
            event_id="event-5",
            ticket_id=aggregate.identity.ticket_id,
            sequence=5,
            occurred_at_ms=1_300,
            entry_vacuum_id=VACUUM_ID,
            exchange_order_id="entry-1",
            final_filled_qty=final_qty,
            average_fill_price=Decimal(60000) if final_qty > 0 else None,
        ),
    ).aggregate


def _snapshot(
    *,
    quantity: Decimal,
    average_entry_price: Decimal | None,
    open_entry_order: bool,
) -> PositionSnapshot:
    ticket = make_ticket()
    return PositionSnapshot(
        netting_domain=ticket.identity.netting_domain,
        quantity=quantity,
        average_entry_price=average_entry_price,
        open_orders=(
            (
                VenueOrderSnapshot(
                    exchange_order_id="entry-1",
                    venue_client_order_id="brc-entry-1",
                    position_side="long",
                    reduce_only=False,
                    order_namespace="regular",
                ),
            )
            if open_entry_order
            else ()
        ),
        observed_at_ms=1_250,
    )
