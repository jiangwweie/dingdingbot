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


def test_runner_reduction_keeps_original_stage_and_no_new_target():
    a = position_protected_aggregate().model_copy(
        update={
            "status": AggregateStatus.RUNNER_PROTECTED,
            "position_qty": D(".0005"),
            "protected_qty": D(".0005"),
            "tp1_filled_qty": D(".0005"),
            "tp1_exchange_order_id": None,
            "active_stop_price": D(60050),
            "break_even_floor_price": D(60050),
            "runner_stop_watermark_ms": 4500,
        }
    )
    event = recorded(a).model_copy(update={"original_tp_price": None})
    result = reduce_event(a, event).aggregate
    assert result.status is AggregateStatus.RUNNER_PROTECTED
    assert (
        result.tp1_filled_qty == a.tp1_filled_qty
        and result.break_even_floor_price == a.break_even_floor_price
    )
    assert result.runner_stop_watermark_ms == a.runner_stop_watermark_ms
    assert result.owner_reduction_context.original_tp_price is None


def test_proven_retired_initial_stop_is_cleared_but_unproven_stop_is_kept():
    a = position_protected_aggregate()
    from src.trading_kernel.domain.exit_execution import EntryFill
    from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof

    event = recorded(a)
    proof = OwnerReductionProof(
        source_stage="pre_tp",
        source_tp_filled_quantity=D(0),
        authorization_id="auth-1",
        operation_id=event.operation_id,
        ticket_id=a.identity.ticket_id,
        domain=a.identity.netting_domain,
        command_id=event.command_id,
        exchange_order_id=event.exchange_order_id,
        venue_client_order_id="client",
        order_status="FILLED",
        requested_quantity=event.filled_quantity,
        executed_quantity=event.filled_quantity,
        source_quantity=a.position_qty,
        remaining_quantity=event.remaining_quantity,
        fills=(
            EntryFill(
                trade_id="fill",
                quantity=event.filled_quantity,
                price=event.average_fill_price,
            ),
        ),
        original_tp_order_id=a.tp1_exchange_order_id,
        original_tp_cancelled=True,
        original_tp_filled_quantity=D(0),
        protection_order_id=event.protection_order_id,
        protection_price=event.protection_price,
        protected_quantity=event.remaining_quantity,
        observed_at_ms=5000,
        valid_until_ms=8000,
        retired_protections=(
            {
                "evidence_id": "retired-old-stop",
                "exchange_order_id": a.initial_stop_exchange_order_id,
                "client_order_id": "old-client",
                "status": "CANCELED",
                "executed_quantity": "0",
                "observed_at_ms": 4999,
            },
        ),
    )
    event = event.model_copy(update={"proof": proof})
    assert reduce_event(a, event).aggregate.initial_stop_exchange_order_id is None
    assert (
        reduce_event(a, recorded(a)).aggregate.initial_stop_exchange_order_id
        == a.initial_stop_exchange_order_id
    )
