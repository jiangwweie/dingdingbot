from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.effects import (
    CancelProtectionOrders,
    PrepareProtectionReplacementCommand,
    PrepareTakeProfitCommand,
    ReleaseEntryLane,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    InitialStopConfirmed,
    ProtectionCancelConfirmed,
    ProtectionReplacementConfirmed,
    RunnerStopRequested,
    TakeProfitConfirmed,
    TakeProfitFilled,
    TicketIssued,
)
from src.trading_kernel.domain.exit_policy import exit_policy_for
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from tests.trading_kernel.unit.test_ticket import _ticket


@pytest.mark.parametrize(
    "event_spec_id",
    [contract.event_spec_id for contract in registered_strategy_contracts()],
)
def test_each_registered_event_progresses_tp1_to_break_even_runner(
    event_spec_id: str,
) -> None:
    policy = exit_policy_for(event_spec_id)
    ticket = _ticket_for_event(event_spec_id)
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
            average_fill_price=Decimal("100"),
        ),
    ).aggregate

    stop_confirmed = reduce_event(
        aggregate,
        InitialStopConfirmed(
            event_id="event-3",
            ticket_id=ticket.identity.ticket_id,
            sequence=3,
            occurred_at_ms=1_200,
            exchange_order_id="stop-initial-1",
            protected_qty=ticket.quantity,
        ),
    )

    assert stop_confirmed.aggregate.status is AggregateStatus.TP1_PENDING
    assert stop_confirmed.effects == (
        ReleaseEntryLane(ticket_id=ticket.identity.ticket_id),
        PrepareTakeProfitCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.002"),
            limit_price=ticket.take_profit_prices[0],
        ),
    )
    tp1_confirmed = reduce_event(
        stop_confirmed.aggregate,
        TakeProfitConfirmed(
            event_id="event-4",
            ticket_id=ticket.identity.ticket_id,
            sequence=4,
            occurred_at_ms=1_300,
            exchange_order_id="tp1-1",
            target_qty=Decimal("0.002"),
        ),
    ).aggregate
    assert tp1_confirmed.status is AggregateStatus.POSITION_PROTECTED

    tp1_filled = reduce_event(
        tp1_confirmed,
        TakeProfitFilled(
            event_id="event-5",
            ticket_id=ticket.identity.ticket_id,
            sequence=5,
            occurred_at_ms=1_400,
            filled_qty=Decimal("0.002"),
            average_fill_price=ticket.take_profit_prices[0],
            runner_floor_price=Decimal("100.4")
            if policy.position_side == "long"
            else Decimal("99.6"),
        ),
    )

    assert tp1_filled.aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert tp1_filled.aggregate.position_qty == Decimal("0.003")
    assert tp1_filled.effects == (
        PrepareProtectionReplacementCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.003"),
            stop_price=(
                Decimal("100.4")
                if policy.position_side == "long"
                else Decimal("99.6")
            ),
            replaces_exchange_order_id="stop-initial-1",
            source_watermark_ms=1_400,
        ),
    )
    replacement = reduce_event(
        tp1_filled.aggregate,
        ProtectionReplacementConfirmed(
            event_id="event-6",
            ticket_id=ticket.identity.ticket_id,
            sequence=6,
            occurred_at_ms=1_500,
            exchange_order_id="runner-stop-1",
            protected_qty=Decimal("0.003"),
            stop_price=(
                Decimal("100.4")
                if policy.position_side == "long"
                else Decimal("99.6")
            ),
            replaces_exchange_order_id="stop-initial-1",
            source_watermark_ms=1_400,
        ),
    )

    assert replacement.aggregate.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING
    assert replacement.aggregate.active_stop_exchange_order_id == "runner-stop-1"
    assert replacement.effects == (
        CancelProtectionOrders(
            ticket_id=ticket.identity.ticket_id,
            exchange_order_id="stop-initial-1",
        ),
    )
    runner = reduce_event(
        replacement.aggregate,
        ProtectionCancelConfirmed(
            event_id="event-7",
            ticket_id=ticket.identity.ticket_id,
            sequence=7,
            occurred_at_ms=1_600,
            exchange_order_id="stop-initial-1",
        ),
    ).aggregate
    assert runner.status is AggregateStatus.RUNNER_PROTECTED

    moved = reduce_event(
        runner,
        RunnerStopRequested(
            event_id="event-8",
            ticket_id=ticket.identity.ticket_id,
            sequence=8,
            occurred_at_ms=2_000,
            stop_price=(
                Decimal("101")
                if policy.position_side == "long"
                else Decimal("99")
            ),
            source_watermark_ms=2_000,
        ),
    )
    assert moved.aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert moved.effects == (
        PrepareProtectionReplacementCommand(
            ticket_id=ticket.identity.ticket_id,
            quantity=Decimal("0.003"),
            stop_price=(
                Decimal("101")
                if policy.position_side == "long"
                else Decimal("99")
            ),
            replaces_exchange_order_id="runner-stop-1",
            source_watermark_ms=2_000,
        ),
    )


def _ticket_for_event(event_spec_id: str):
    contract = next(
        item
        for item in registered_strategy_contracts()
        if item.event_spec_id == event_spec_id
    )
    ticket = _ticket()
    identity = ticket.identity.model_copy(
        update={
            "runtime": ticket.identity.runtime.model_copy(
                update={
                    "strategy_group_id": contract.strategy_group_id,
                    "strategy_version_id": contract.strategy_version_id,
                    "event_spec_id": contract.event_spec_id,
                }
            ),
            "netting_domain": ticket.identity.netting_domain.model_copy(
                update={"position_side": contract.position_side}
            ),
        }
    )
    return ticket.model_copy(
        update={
            "identity": identity,
            "quantity": Decimal("0.005"),
            "notional": Decimal("0.5"),
            "entry_reference_price": Decimal("100"),
            "initial_stop_price": (
                Decimal("95") if contract.position_side == "long" else Decimal("105")
            ),
            "take_profit_prices": (
                Decimal("105") if contract.position_side == "long" else Decimal("95"),
            ),
            "take_profit_quantities": (Decimal("0.002"),),
        }
    )
