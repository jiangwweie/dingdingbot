"""Owner reduction decisions use facts, not manual takeover as a race escape."""

from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionPhase,
    OwnerReductionState,
    advance_owner_reduction,
    preview_owner_reduction,
)
from src.trading_kernel.domain.trade_management import ManagementMode
from tests.trading_kernel.support.owner_reduction import aggregate, facts


def preview(a=None):
    a = a or aggregate()
    return preview_owner_reduction(
        aggregate=a,
        facts=facts(a),
        requested_quantity=a.position_qty / 2,
        quantity_step=D(".0001"),
        minimum_quantity=D(".0001"),
        minimum_notional=D(1),
        now_ms=3000,
    )


def state(p=None, phase=OwnerReductionPhase.PREVIEWED):
    return OwnerReductionState(
        operation_id="owner-reduce-1",
        preview=p or preview(),
        phase=phase,
    )


def test_preview_keeps_tp_price_but_never_proportionally_recreates_tp():
    a = aggregate()
    p = preview(a)
    assert p.remaining_quantity == a.position_qty / 2
    assert p.tp_trigger_price == a.ticket.take_profit_prices[0]
    assert p.cancel_tp_order_id == a.tp1_exchange_order_id
    assert p.source_tp_filled_quantity == 0


@pytest.mark.parametrize(
    "mode", [ManagementMode.MANUAL, ManagementMode.REVIEW_REQUIRED]
)
def test_no_preview_without_auto(mode):
    a = aggregate().model_copy(update={"management_mode": mode})
    with pytest.raises(ValueError, match="auto_required"):
        preview(a)


@pytest.mark.parametrize("quantity", [D(0), D(-1), D(1)])
def test_reduction_does_not_allow_zero_addition_or_full_close(quantity):
    a = aggregate()
    with pytest.raises(ValueError):
        preview_owner_reduction(
            aggregate=a,
            facts=facts(a),
            requested_quantity=quantity,
            quantity_step=D(".0001"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            now_ms=3000,
        )


@pytest.mark.parametrize(
    "change",
    [
        {"tp_filled_quantity": D(".0001")},
        {"tp_state": "partial"},
        {"unresolved_other_command": True},
        {"stop_triggered": True},
        {"protected_quantity": D(0)},
        {"management_revision": 99},
        {"current_price": D(100000)},
    ],
)
def test_preview_rejects_interleaving_or_missing_protection(change):
    a = aggregate()
    with pytest.raises(ValueError):
        preview_owner_reduction(
            aggregate=a,
            facts=facts(a, **change),
            requested_quantity=a.position_qty / 2,
            quantity_step=D(".0001"),
            minimum_quantity=D(".0001"),
            minimum_notional=D(1),
            now_ms=3000,
        )


def test_cancel_before_reduction_and_keep_stop():
    s = state()
    decision = advance_owner_reduction(s, facts(), now_ms=3000)
    assert decision.action == "cancel_original_tp"
    assert decision.state.phase == OwnerReductionPhase.TP_CANCELLING
    assert decision.cancel_order_id == s.preview.cancel_tp_order_id
    assert decision.state.preview.protection_order_id != decision.cancel_order_id


def test_cancel_unknown_never_sends_reduction():
    s = state(phase=OwnerReductionPhase.TP_CANCELLING)
    d = advance_owner_reduction(s, facts(tp_state="unknown"), now_ms=3000)
    assert d.action == "reconcile" and d.state.phase == s.phase


def test_fill_during_cancel_never_sends_original_quantity():
    a = aggregate()
    s = state(phase=OwnerReductionPhase.TP_CANCELLING)
    d = advance_owner_reduction(
        s,
        facts(
            tp_state="cancelled",
            tp_filled_quantity=D(".0001"),
            position_quantity=a.position_qty - D(".0001"),
        ),
        now_ms=3000,
    )
    assert d.action == "restore_or_reconcile" and d.reason == "preview_changed"


def test_exact_cancel_allows_preparing_one_reduction():
    s = state(phase=OwnerReductionPhase.TP_CANCELLING)
    d = advance_owner_reduction(s, facts(tp_state="cancelled"), now_ms=3000)
    assert d.action == "prepare_reduction"
    assert d.state.phase == OwnerReductionPhase.REDUCTION_PENDING
    again = advance_owner_reduction(d.state, facts(tp_state="cancelled"), now_ms=3000)
    assert again.action == "reconcile"


@pytest.mark.parametrize("status", ["unknown", "working", "not_sent"])
def test_reduction_pending_never_blindly_resends(status):
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    d = advance_owner_reduction(
        s, facts(tp_state="cancelled", reduction_state=status), now_ms=3000
    )
    assert d.action == "reconcile"


def test_rejected_reduction_does_not_grant_price_condition():
    d = advance_owner_reduction(
        state(phase=OwnerReductionPhase.REDUCTION_PENDING),
        facts(tp_state="cancelled", reduction_state="rejected"),
        now_ms=3000,
    )
    assert d.action == "restore_or_reconcile"
    assert d.state.phase == OwnerReductionPhase.RESTORE_REQUIRED


def test_partial_terminal_is_actual_reduction_not_tp_fill():
    a = aggregate()
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    fill = s.preview.reduction_quantity / 2
    f = facts(
        tp_state="cancelled",
        reduction_state="terminal",
        reduction_filled_quantity=fill,
        position_quantity=a.position_qty - fill,
        protected_quantity=a.position_qty - fill,
    )
    d = advance_owner_reduction(s, f, now_ms=3000)
    assert d.action == "record_reduction"
    assert d.state.actual_reduction_quantity == fill
    assert d.state.phase == OwnerReductionPhase.WAIT_PRICE
    assert d.state.preview.source_tp_filled_quantity == 0


def test_partial_without_confirmed_protection_requires_reconciliation():
    a = aggregate()
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    fill = s.preview.reduction_quantity
    d = advance_owner_reduction(
        s,
        facts(
            tp_state="cancelled",
            reduction_state="terminal",
            reduction_filled_quantity=fill,
            position_quantity=a.position_qty - fill,
        ),
        now_ms=3000,
    )
    assert (
        d.action == "verify_protection"
        and d.state.phase == OwnerReductionPhase.PROTECTION_PENDING
    )


@pytest.mark.parametrize("unknown", [False, True])
def test_stop_flat_never_sets_manual_or_dispatches(unknown):
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    f = facts(
        position_quantity=D(0),
        stop_triggered=True,
        reduction_state="unknown" if unknown else "terminal",
        tp_state="cancelled",
        residual_orders=unknown,
    )
    d = advance_owner_reduction(s, f, now_ms=3000)
    assert d.action == ("reconcile" if unknown else "verified_closure_required")
    assert d.state.phase == OwnerReductionPhase.CLOSURE_PENDING


def test_stop_residual_is_review_not_invented_manual_takeover():
    d = advance_owner_reduction(state(), facts(stop_triggered=True), now_ms=3000)
    assert d.action == "review_required"
    assert d.state.phase == OwnerReductionPhase.REVIEW_REQUIRED


def test_price_condition_requires_fresh_post_reduction_fact():
    p = preview()
    s = OwnerReductionState(
        operation_id="owner-reduce-1",
        preview=p,
        phase=OwnerReductionPhase.WAIT_PRICE,
        actual_reduction_quantity=p.reduction_quantity,
        reduction_observed_at_ms=4000,
    )
    f = facts(
        position_quantity=p.remaining_quantity,
        protected_quantity=p.remaining_quantity,
        tp_state="cancelled",
        current_price=p.tp_trigger_price,
    )
    d = advance_owner_reduction(s, f, now_ms=4000)
    assert d.action == "reconcile" and d.reason == "price_fact_precedes_reduction"
    f = f.model_copy(update={"observed_at_ms": 4001})
    d = advance_owner_reduction(s, f, now_ms=4001)
    assert (
        d.action == "request_break_even"
        and d.state.phase == OwnerReductionPhase.BREAK_EVEN_PENDING
    )
    assert advance_owner_reduction(d.state, f, now_ms=4001).action == "reconcile"


def test_expired_preview_does_not_cancel_order():
    d = advance_owner_reduction(
        state(), facts(observed_at_ms=34000, valid_until_ms=40000), now_ms=34000
    )
    assert d.action == "rejected" and d.reason == "preview_expired"


def test_json_roundtrip_keeps_pending_no_resend():
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    restored = OwnerReductionState.model_validate_json(s.model_dump_json())
    assert (
        advance_owner_reduction(
            restored, facts(reduction_state="unknown"), now_ms=3000
        ).action
        == "reconcile"
    )


def test_financial_facts_reject_float_and_nan():
    with pytest.raises((ValueError, TypeError)):
        facts(position_quantity=0.1)
    with pytest.raises(ValueError):
        facts(position_quantity=D("NaN"))


def test_foreign_reduction_evidence_cannot_continue():
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    d = advance_owner_reduction(
        s,
        facts(
            tp_state="cancelled",
            reduction_state="terminal",
            reduction_operation_id="other-operation",
            reduction_filled_quantity=s.preview.reduction_quantity,
            position_quantity=s.preview.remaining_quantity,
            protected_quantity=s.preview.remaining_quantity,
        ),
        now_ms=3000,
    )
    assert (
        d.action == "review_required"
        and d.reason == "reduction_evidence_identity_mismatch"
    )


def test_tp_fill_after_cancel_does_not_become_owner_reduction():
    s = state(phase=OwnerReductionPhase.REDUCTION_PENDING)
    d = advance_owner_reduction(
        s,
        facts(
            tp_state="cancelled",
            tp_filled_quantity=D(".0001"),
            reduction_state="terminal",
            reduction_filled_quantity=s.preview.reduction_quantity,
            position_quantity=s.preview.remaining_quantity,
            protected_quantity=s.preview.remaining_quantity,
        ),
        now_ms=3000,
    )
    assert d.action == "review_required" and d.reason == "tp_fill_during_reduction"


def test_breakeven_not_requested_without_current_protection():
    p = preview()
    s = OwnerReductionState(
        operation_id="owner-reduce-1",
        preview=p,
        phase=OwnerReductionPhase.WAIT_PRICE,
        actual_reduction_quantity=p.reduction_quantity,
        reduction_observed_at_ms=3000,
    )
    d = advance_owner_reduction(
        s,
        facts(
            tp_state="cancelled",
            observed_at_ms=4000,
            position_quantity=p.remaining_quantity,
            protected_quantity=D(0),
            current_price=p.tp_trigger_price,
        ),
        now_ms=4000,
    )
    assert d.action == "reconcile" and d.reason == "price_condition_protection_unproven"


def test_preexisting_reduction_cannot_dispatch_a_second_one():
    d = advance_owner_reduction(state(), facts(reduction_state="working"), now_ms=3000)
    assert d.action == "reconcile"


def test_runner_reduction_keeps_runner_and_never_requests_tp_cancel():
    from src.trading_kernel.domain.aggregate import AggregateStatus

    a = aggregate().model_copy(
        update={
            "status": AggregateStatus.RUNNER_PROTECTED,
            "tp1_exchange_order_id": None,
            "tp1_filled_qty": aggregate().tp1_target_qty,
        }
    )
    f = facts(a, tp_state="absent")
    p = preview_owner_reduction(
        aggregate=a,
        facts=f,
        requested_quantity=a.position_qty / 2,
        quantity_step=D(".0001"),
        minimum_quantity=D(".0001"),
        minimum_notional=D(1),
        now_ms=3000,
    )
    assert p.continue_runner and p.tp_trigger_price is None
    initial = advance_owner_reduction(state(p), f, now_ms=3000)
    assert initial.action == "prepare_reduction"
    final = f.model_copy(
        update={
            "reduction_state": "terminal",
            "reduction_filled_quantity": p.reduction_quantity,
            "position_quantity": p.remaining_quantity,
            "protected_quantity": p.remaining_quantity,
        }
    )
    d = advance_owner_reduction(initial.state, final, now_ms=3000)
    assert d.state.phase == OwnerReductionPhase.RUNNER_CONTINUING


def test_short_price_condition_is_mirrored():
    p = preview().model_copy(
        update={"side": "short", "stop_price": D(61000), "tp_trigger_price": D(59000)}
    )
    s = OwnerReductionState(
        operation_id="owner-reduce-1",
        preview=p,
        phase=OwnerReductionPhase.WAIT_PRICE,
        actual_reduction_quantity=p.reduction_quantity,
        reduction_observed_at_ms=3000,
    )
    f = facts(
        observed_at_ms=4000,
        tp_state="cancelled",
        position_quantity=p.remaining_quantity,
        protected_quantity=p.remaining_quantity,
        stop_price=D(61000),
        current_price=D(59001),
    )
    assert advance_owner_reduction(s, f, now_ms=4000).action == "no_change"
    assert (
        advance_owner_reduction(
            s, f.model_copy(update={"current_price": D(59000)}), now_ms=4000
        ).action
        == "request_break_even"
    )
