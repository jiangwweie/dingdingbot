from decimal import Decimal

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.events import (
    ManualTakeoverConfirmed,
    RunnerStopRequested,
)
from src.trading_kernel.domain.reducer import InvalidLifecycleTransition, reduce_event
from src.trading_kernel.domain.trade_management import ManagementMode
from tests.trading_kernel.support.tickets import make_ticket


def protected():
    t = make_ticket()
    return TradeAggregate(
        identity=t.identity,
        ticket=t,
        status=AggregateStatus.POSITION_PROTECTED,
        version=4,
        last_event_sequence=4,
        entry_lane_held=False,
        position_qty=t.quantity,
        protected_qty=t.quantity,
        initial_stop_exchange_order_id="stop-1",
        active_stop_exchange_order_id="stop-1",
        active_stop_price=t.initial_stop_price,
        tp1_exchange_order_id="tp-1",
        tp1_target_qty=t.quantity / 2,
    )


def takeover(a):
    return ManualTakeoverConfirmed(
        event_id="takeover-1",
        ticket_id=a.identity.ticket_id,
        sequence=5,
        occurred_at_ms=2000,
        evidence_id="e1",
        reason="external_order_amendment",
    )


def test_takeover_preserves_orders_and_immutable_ticket_without_exchange_effects():
    a = protected()
    r = reduce_event(a, takeover(a))
    b = r.aggregate
    assert b.management_mode is ManagementMode.MANUAL
    assert b.status is AggregateStatus.MANUAL_OPEN
    assert b.ticket == a.ticket and b.position_qty == a.position_qty
    assert (
        b.active_stop_exchange_order_id == "stop-1"
        and b.tp1_exchange_order_id == "tp-1"
    )
    assert r.effects == ()


def test_manual_state_cannot_resume_runner():
    a = protected()
    b = reduce_event(a, takeover(a)).aggregate
    with pytest.raises(InvalidLifecycleTransition, match="manual"):
        reduce_event(
            b,
            RunnerStopRequested(
                event_id="runner",
                ticket_id=a.identity.ticket_id,
                sequence=6,
                occurred_at_ms=3000,
                stop_price=Decimal(60000),
                source_watermark_ms=2000,
            ),
        )


def test_takeover_rejected_before_initial_protection():
    a = protected().model_copy(update={"initial_stop_exchange_order_id": None})
    with pytest.raises(InvalidLifecycleTransition, match="initial protection"):
        reduce_event(a, takeover(a))


def test_runner_takeover_uses_current_protection_not_cancelled_initial_order():
    a=protected().model_copy(update={'status':AggregateStatus.RUNNER_PROTECTED,'initial_stop_exchange_order_id':None,'active_stop_exchange_order_id':'runner-stop','post_fill_stress_status':'passed'})
    assert reduce_event(a,takeover(a)).aggregate.management_mode is ManagementMode.MANUAL
