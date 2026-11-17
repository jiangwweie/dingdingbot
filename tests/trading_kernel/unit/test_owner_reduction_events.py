from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import (
    OwnerReductionPriceSatisfied,
    OwnerReductionRecorded,
)
from src.trading_kernel.domain.reducer import InvalidLifecycleTransition, reduce_event
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def recorded(a):
    return OwnerReductionRecorded(
        event_id="owner-reduced",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=5000,
        operation_id="op-1",
        command_id="owner-command-1",
        exchange_order_id="order-1",
        filled_quantity=a.position_qty / 2,
        average_fill_price=a.average_fill_price,
        remaining_quantity=a.position_qty / 2,
        original_tp_order_id=a.tp1_exchange_order_id,
        original_tp_price=a.ticket.take_profit_prices[0],
        protection_order_id="remaining-stop",
        protection_price=a.active_stop_price,
        proof_digest="sha256:" + "a" * 64,
    )


def test_reduction_is_not_tp_fill_and_keeps_auto():
    a = position_protected_aggregate()
    r = reduce_event(a, recorded(a))
    assert r.aggregate.position_qty == a.position_qty / 2
    assert r.aggregate.protected_qty == a.position_qty / 2
    assert (
        r.aggregate.tp1_filled_qty == 0
        and r.aggregate.tp1_target_qty == a.tp1_target_qty
    )
    assert r.aggregate.tp1_exchange_order_id is None
    assert (
        r.aggregate.owner_reduction_context.original_tp_price
        == a.ticket.take_profit_prices[0]
    )
    assert not r.effects and r.aggregate.management_mode.value == "AUTO"


def test_price_condition_creates_protection_not_second_quantity_reduction():
    a = position_protected_aggregate()
    a = reduce_event(a, recorded(a)).aggregate
    ev = OwnerReductionPriceSatisfied(
        event_id="condition",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=6000,
        operation_id="op-1",
        observed_price=a.ticket.take_profit_prices[0],
        observed_at_ms=6000,
        valid_until_ms=9000,
        proposed_stop=D(60050),
        source_digest="sha256:" + "b" * 64,
    )
    r = reduce_event(a, ev)
    assert (
        r.aggregate.position_qty == a.position_qty and r.aggregate.tp1_filled_qty == 0
    )
    assert r.aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert len(r.effects) == 1 and r.effects[0].quantity == a.position_qty


@pytest.mark.parametrize(
    "change",
    [
        {"remaining_quantity": D(0)},
        {"filled_quantity": D(0)},
        {"protection_price": D(58000)},
        {"original_tp_order_id": "other"},
    ],
)
def test_inconsistent_or_unprotected_reduction_is_rejected(change):
    a = position_protected_aggregate()
    ev = recorded(a).model_copy(update=change)
    with pytest.raises((InvalidLifecycleTransition, ValueError)):
        reduce_event(a, ev)


def test_condition_before_real_reduction_never_starts_runner():
    a = position_protected_aggregate()
    ev = OwnerReductionPriceSatisfied(
        event_id="condition",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=6000,
        operation_id="op-1",
        observed_price=a.ticket.take_profit_prices[0],
        observed_at_ms=6000,
        valid_until_ms=9000,
        proposed_stop=D(60050),
        source_digest="sha256:" + "b" * 64,
    )
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(a, ev)
