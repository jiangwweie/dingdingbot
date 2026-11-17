from decimal import Decimal as D

from src.trading_kernel.application.evaluate_owner_reduced_lifecycle import (
    evaluate_owner_reduced_lifecycle,
)
from src.trading_kernel.domain.exit_policy import (
    LifecycleMarketFacts,
    registered_exit_profiles,
)
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionPhase,
    OwnerReductionState,
    preview_owner_reduction,
)
from tests.trading_kernel.support.owner_reduction import aggregate, facts


def inputs():
    a = aggregate()
    p = preview_owner_reduction(
        aggregate=a,
        facts=facts(a),
        requested_quantity=a.position_qty / 2,
        quantity_step=D(".0001"),
        minimum_quantity=D(".0001"),
        minimum_notional=D(1),
        now_ms=3000,
    )
    state = OwnerReductionState(
        operation_id="owner-reduce-1",
        preview=p,
        phase=OwnerReductionPhase.WAIT_PRICE,
        actual_reduction_quantity=p.reduction_quantity,
        reduction_observed_at_ms=3000,
    )
    f = facts(
        a,
        position_quantity=p.remaining_quantity,
        protected_quantity=p.remaining_quantity,
        current_price=p.tp_trigger_price,
        tp_state="cancelled",
        observed_at_ms=4000,
    )
    profile = next(
        p
        for p in registered_exit_profiles()
        if p.exit_profile_id == a.ticket.exit_policy_id
    )
    return {
        "state": state,
        "facts": f,
        "now_ms": 4000,
        "profile": profile,
        "market_facts": None,
        "entry_average_price": a.average_fill_price,
        "allocated_entry_fee_quote": D(".01"),
        "exit_taker_fee_rate": D(".001"),
        "price_tick": D(".1"),
        "pre_tp1_reclaim_price": a.ticket.pre_tp1_reclaim_price,
        "exposure_session_end_ms": a.ticket.exposure_session_end_ms,
    }


def test_price_condition_proposes_be_without_tp_quantity_reduction():
    kw = inputs()
    r = evaluate_owner_reduced_lifecycle(**kw)
    assert r.proposed_stop is not None and r.exit_reason is None
    assert (
        r.operation.state.actual_reduction_quantity
        == kw["state"].actual_reduction_quantity
    )
    assert r.operation.state.preview.source_tp_filled_quantity == 0


def test_original_failure_precedes_be():
    kw = inputs()
    kw["exposure_session_end_ms"] = 3500
    kw["market_facts"] = LifecycleMarketFacts(
        watermark_ms=3999,
        is_final_closed_candle=True,
        latest_close=kw["facts"].current_price,
        structure_reference=D(59000),
        atr=D(100),
        holding_bars=1,
    )
    r = evaluate_owner_reduced_lifecycle(**kw)
    assert r.exit_reason == "session_expired" and r.proposed_stop is None


def test_waiting_retains_original_failure_without_tp_order():
    kw = inputs()
    kw["facts"] = kw["facts"].model_copy(
        update={"current_price": kw["entry_average_price"]}
    )
    kw["exposure_session_end_ms"] = 3500
    kw["market_facts"] = LifecycleMarketFacts(
        watermark_ms=3999,
        is_final_closed_candle=True,
        latest_close=kw["facts"].current_price,
        structure_reference=D(59000),
        atr=D(100),
        holding_bars=1,
    )
    assert evaluate_owner_reduced_lifecycle(**kw).exit_reason == "session_expired"


def test_fee_floor_already_crossed_requests_exit_not_looser_stop():
    kw = inputs()
    kw["allocated_entry_fee_quote"] = D(100)
    r = evaluate_owner_reduced_lifecycle(**kw)
    assert r.exit_reason == "break_even_crossed" and r.proposed_stop is None


def test_profile_hash_mismatch_cannot_change_frozen_exit_plan():
    kw = inputs()
    kw["profile"] = kw["profile"].model_copy(update={"exit_profile_version": 99})
    import pytest

    with pytest.raises(ValueError, match="profile_side_mismatch"):
        evaluate_owner_reduced_lifecycle(**kw)
