from decimal import Decimal as D

from src.trading_kernel.domain.events import (
    OwnerProfitPlanCancelled,
    OwnerProfitPlanInstalled,
)
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def event(a, cls, **values):
    return cls(event_id='e', ticket_id=a.identity.ticket_id, sequence=a.last_event_sequence+1, occurred_at_ms=6000, **values)


def test_manual_tp_is_one_new_quantity_plan_and_cancel_never_restores_old_tp():
    a = position_protected_aggregate()
    old = a.tp1_exchange_order_id
    a = reduce_event(a, event(a, OwnerProfitPlanInstalled, operation_id='op', command_id='cmd',
        exchange_order_id='manual-tp', replaces_exchange_order_id=old, price=D(63000), quantity=D('.0002'))).aggregate
    assert a.tp1_exchange_order_id == 'manual-tp' and a.tp1_target_qty == D('.0002')
    assert a.manual_profit_plan.price == D(63000)
    a = reduce_event(a, event(a, OwnerProfitPlanCancelled, operation_id='cancel-op', exchange_order_id='manual-tp')).aggregate
    assert a.tp1_exchange_order_id is None
    assert a.manual_profit_plan.cancelled
    assert a.active_stop_exchange_order_id is not None


def test_manual_tp_from_runner_does_not_disable_runner_before_real_fill():
    from src.trading_kernel.domain.aggregate import AggregateStatus as A
    from src.trading_kernel.domain.events import TakeProfitFilled
    a=position_protected_aggregate().model_copy(update={'status':A.RUNNER_PROTECTED,'active_stop_close_position':True,
        'active_stop_price':D(60050),'break_even_floor_price':D(60050),'tp1_exchange_order_id':None})
    a=reduce_event(a,event(a,OwnerProfitPlanInstalled,operation_id='op',command_id='cmd',exchange_order_id='manual-tp',
        replaces_exchange_order_id=None,price=D(63000),quantity=D('.0002'))).aggregate
    assert a.status is A.RUNNER_PROTECTED
    r=reduce_event(a,event(a,TakeProfitFilled,filled_qty=D('.0002'),average_fill_price=D(63000),runner_floor_price=D(60050)))
    assert r.aggregate.position_qty==a.position_qty-D('.0002')
    assert r.effects[0].close_position
