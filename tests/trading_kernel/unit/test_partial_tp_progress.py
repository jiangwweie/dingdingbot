from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.events import TakeProfitFilled, TakeProfitProgressed
from src.trading_kernel.domain.reducer import InvalidLifecycleTransition, reduce_event
from src.trading_kernel.domain.trade_management import ManagementMode
from tests.trading_kernel.support.reducer_states import position_protected_aggregate


def progress(a, amount):
    return TakeProfitProgressed(
        event_id=f"progress:{a.version}",
        ticket_id=a.identity.ticket_id,
        sequence=a.last_event_sequence + 1,
        occurred_at_ms=3000,
        cumulative_filled_qty=D(amount),
        average_fill_price=D(61000),
        protection_covers_remainder=True,
    )


def test_partial_progress_reduces_exposure_without_requesting_break_even():
    a = position_protected_aggregate()
    r = reduce_event(a, progress(a, ".0002"))
    assert r.aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert r.aggregate.tp1_filled_qty == D(".0002")
    assert r.aggregate.position_qty == a.position_qty - D(".0002")
    assert not r.effects
    assert r.aggregate.break_even_floor_price is None


def test_full_fill_after_partial_subtracts_only_remaining_delta():
    a = position_protected_aggregate()
    partial = reduce_event(a, progress(a, ".0002")).aggregate
    event = TakeProfitFilled(
        event_id="full",
        ticket_id=a.identity.ticket_id,
        sequence=partial.last_event_sequence + 1,
        occurred_at_ms=3100,
        filled_qty=a.tp1_target_qty,
        average_fill_price=D(61000),
        runner_floor_price=D(60050),
    )
    r = reduce_event(partial, event)
    assert r.aggregate.position_qty == a.position_qty - a.tp1_target_qty
    assert r.aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_PENDING
    assert len(r.effects) == 1


@pytest.mark.parametrize(
    "mode", [ManagementMode.MANUAL, ManagementMode.REVIEW_REQUIRED]
)
def test_partial_progress_cannot_grant_management_authority(mode):
    a = position_protected_aggregate().model_copy(update={"management_mode": mode})
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(a, progress(a, ".0002"))


@pytest.mark.parametrize("amount", ["0", "-.001", "1"])
def test_partial_progress_rejects_non_monotonic_or_excess(amount):
    a = position_protected_aggregate()
    with pytest.raises(InvalidLifecycleTransition):
        reduce_event(a, progress(a, amount))


def test_partial_protection_replacement_returns_to_pre_tp_phase_after_exact_old_stop_cancel():
    from src.trading_kernel.domain.events import (
        ProtectionCancelConfirmed,
        ProtectionReplacementConfirmed,
    )

    a = position_protected_aggregate()
    p = progress(a, ".0002").model_copy(update={"protection_covers_remainder": False,"replacement_safety_verified":True})
    pending = reduce_event(a, p).aggregate
    assert pending.partial_tp_protection and pending.break_even_floor_price is None
    accepted = reduce_event(
        pending,
        ProtectionReplacementConfirmed(
            event_id="partial-stop",
            ticket_id=a.identity.ticket_id,
            sequence=pending.last_event_sequence + 1,
            occurred_at_ms=3100,
            exchange_order_id="new-partial-stop",
            protected_qty=pending.position_qty,
            stop_price=a.active_stop_price,
            replaces_exchange_order_id=a.active_stop_exchange_order_id,
            source_watermark_ms=3000,
        ),
    ).aggregate
    assert accepted.status is AggregateStatus.RUNNER_OLD_STOP_CANCEL_PENDING
    finished = reduce_event(
        accepted,
        ProtectionCancelConfirmed(
            event_id="old-stop-removed",
            ticket_id=a.identity.ticket_id,
            sequence=accepted.last_event_sequence + 1,
            occurred_at_ms=3200,
            exchange_order_id=a.active_stop_exchange_order_id,
        ),
    ).aggregate
    assert finished.status is AggregateStatus.POSITION_PROTECTED
    assert finished.break_even_floor_price is None
    assert not finished.partial_tp_protection
    assert finished.position_qty == a.position_qty - D(".0002")


def test_partial_without_proven_safe_coverage_converges_auto_through_exact_close():
    a=position_protected_aggregate()
    event=progress(a,'.0002').model_copy(update={'protection_covers_remainder':False})
    result=reduce_event(a,event)
    assert result.aggregate.status is AggregateStatus.EXIT_PENDING
    assert result.aggregate.break_even_floor_price is None
    assert any(getattr(effect,'quantity',None)==a.position_qty-D('.0002') for effect in result.effects)
    assert result.aggregate.management_mode is ManagementMode.AUTO
