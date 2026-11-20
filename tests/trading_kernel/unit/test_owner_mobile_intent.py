"""A signed mobile intent freezes the requested size against the shown position."""

from decimal import Decimal

import pytest

from src.trading_kernel.domain.owner_position_intent import OwnerPositionIntent


def test_reduction_rejects_more_than_half_of_the_confirmed_basis():
    common = {
        "ticket_id": "ticket:1",
        "kind": "position_reduce",
        "basis_quantity": "100",
        "basis_version": 3,
        "basis_token": "a" * 64,
    }
    assert OwnerPositionIntent(**common, quantity="50").amount == Decimal(50)
    with pytest.raises(ValueError, match="reduction_exceeds_half"):
        OwnerPositionIntent(**common, quantity="50.01")


def test_full_close_forbids_quantity():
    with pytest.raises(ValueError, match="unexpected_amount"):
        OwnerPositionIntent(ticket_id="ticket:1", kind="position_close", quantity="1")


def test_completed_manual_tp_does_not_block_runner_reduction():
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.manual_profit_plan import ManualProfitPlan
    from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
    from tests.trading_kernel.support.owner_reduction import aggregate, facts

    a = aggregate()
    plan = ManualProfitPlan(
        operation_id="original", command_id="tp", exchange_order_id="filled-order",
        price=Decimal(62000), target_quantity=a.tp1_target_qty,
        prior_tp_filled_quantity=Decimal(0), started_from_runner=True,
    )
    a = a.model_copy(update={
        "status": AggregateStatus.RUNNER_PROTECTED,
        "tp1_exchange_order_id": None,
        "tp1_filled_qty": a.tp1_target_qty,
        "manual_profit_plan": plan,
    })
    p = preview_owner_reduction(
        aggregate=a, facts=facts(a, tp_state="absent"),
        requested_quantity=a.position_qty / 2, quantity_step=Decimal(".0001"),
        minimum_quantity=Decimal(".0001"), minimum_notional=Decimal(1), now_ms=3000,
    )
    assert p.continue_runner and p.cancel_tp_order_id is None
    assert p.source_tp_filled_quantity == a.tp1_filled_qty
