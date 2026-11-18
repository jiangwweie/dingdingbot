from decimal import Decimal as D

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import (
    OwnerProtectionRequested,
    ProtectionCancelConfirmed,
    ProtectionReplacementConfirmed,
)
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def event(a, cls, **values):
    return cls(
        event_id=f"e:{a.version}",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=5000,
        **values,
    )


def test_pre_tp_protection_conversion_does_not_start_runner_or_cancel_tp():
    a = position_protected_aggregate()
    r = reduce_event(
        a,
        event(
            a,
            OwnerProtectionRequested,
            operation_id="op",
            stop_price=a.active_stop_price,
            close_position=True,
            source_watermark_ms=4500,
        ),
    )
    assert r.effects[0].close_position is True
    a = r.aggregate
    a = reduce_event(
        a,
        event(
            a,
            ProtectionReplacementConfirmed,
            exchange_order_id="close-all",
            protected_qty=a.position_qty,
            stop_price=a.active_stop_price,
            replaces_exchange_order_id=a.active_stop_exchange_order_id,
            source_watermark_ms=4500,
            close_position=True,
        ),
    ).aggregate
    a = reduce_event(
        a,
        event(
            a,
            ProtectionCancelConfirmed,
            exchange_order_id=a.pending_replaced_stop_exchange_order_id,
        ),
    ).aggregate
    assert a.status is AggregateStatus.POSITION_PROTECTED
    assert a.active_stop_close_position is True
    assert a.tp1_exchange_order_id is not None and a.tp1_filled_qty == 0
    assert a.runner_stop_watermark_ms is None


def test_owner_stop_tightening_preserves_existing_phase():
    a = position_protected_aggregate()
    r = reduce_event(
        a,
        event(
            a,
            OwnerProtectionRequested,
            operation_id="op",
            stop_price=D(59500),
            close_position=False,
            source_watermark_ms=4500,
        ),
    )
    assert r.aggregate.protection_return_status is AggregateStatus.POSITION_PROTECTED
    assert r.effects[0].stop_price == D(59500)


def test_failed_owner_protection_does_not_exit_original_trade():
    from src.trading_kernel.domain.events import ProtectionReplacementRejected
    a = position_protected_aggregate()
    a = reduce_event(a, event(a, OwnerProtectionRequested, operation_id='op',
        stop_price=D(59500), close_position=False, source_watermark_ms=4500)).aggregate
    result = reduce_event(a, event(a, ProtectionReplacementRejected, reason='rejected'))
    assert result.aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert result.aggregate.active_stop_price == D(59000)
    assert not result.effects


def test_close_all_runner_mode_survives_next_automatic_move():
    from src.trading_kernel.domain.events import RunnerStopRequested
    a=position_protected_aggregate().model_copy(update={'status':AggregateStatus.RUNNER_PROTECTED,
        'active_stop_close_position':True,'active_stop_price':D(60050),'break_even_floor_price':D(60050)})
    r=reduce_event(a,event(a,RunnerStopRequested,stop_price=D(60100),source_watermark_ms=4500))
    assert r.effects[0].close_position and r.aggregate.pending_stop_close_position
