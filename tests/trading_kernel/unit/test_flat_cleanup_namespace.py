from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import ExternalFlatDetected, PositionFlatConfirmed
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def test_external_flat_cleans_regular_tp_before_conditional_stop():
    a = position_protected_aggregate()
    e = ExternalFlatDetected(
        event_id="flat",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=5000,
    )
    r = reduce_event(a, e)
    cancel = next(x for x in r.effects if hasattr(x, "order_namespace"))
    assert cancel.exchange_order_id == a.tp1_exchange_order_id
    assert cancel.order_namespace == "regular"


def test_commanded_flat_cleans_regular_tp():
    a = position_protected_aggregate().model_copy(
        update={"status": AggregateStatus.EXIT_ACCEPTED}
    )
    e = PositionFlatConfirmed(
        event_id="flat",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=5000,
    )
    cancel = next(
        x for x in reduce_event(a, e).effects if hasattr(x, "order_namespace")
    )
    assert cancel.order_namespace == "regular"


def test_flat_observation_does_not_skip_unfilled_entry_authority():
    from decimal import Decimal

    from src.trading_kernel.application.observe_trade_management import (
        is_flat_closure_observation,
    )
    a=position_protected_aggregate().model_copy(update={'position_qty':Decimal(0),'status':AggregateStatus.ENTRY_PENDING})
    assert not is_flat_closure_observation(a)
    assert is_flat_closure_observation(a.model_copy(update={'status':AggregateStatus.RECONCILIATION_PENDING}))
