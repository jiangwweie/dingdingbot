"""Reusable pure-domain aggregate states for Trading Kernel tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    MaintenanceMarginBracket,
    StressPosition,
    evaluate_cross_margin_stress,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    ExitRequested,
    InitialStopConfirmed,
    OwnedOrphanOrderDetected,
    PositionFlatConfirmed,
    PostFillStressAssessed,
    ProtectionCancelConfirmed,
    TakeProfitConfirmed,
    TicketIssued,
)
from src.trading_kernel.domain.post_fill_risk import PostFillRiskRequest, assess_post_fill_risk
from src.trading_kernel.domain.reducer import reduce_event
from tests.trading_kernel.support.tickets import make_ticket


def post_fill_stress_event(aggregate, *, passed: bool = True):
    ticket = aggregate.ticket
    assert aggregate.average_fill_price is not None
    assert aggregate.initial_stop_exchange_order_id is not None
    account = AccountRiskSnapshot.create(
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        account_risk_mode="standard_usdm_single_asset",
        settlement_asset="USDT",
        position_mode="independent_sides",
        margin_mode="cross",
        exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
        mark_price=aggregate.average_fill_price,
        configured_leverage=ticket.selected_leverage,
        total_wallet_balance=Decimal(100 if passed else 0),
        total_margin_balance=Decimal(100 if passed else 0),
        total_initial_margin=Decimal(0),
        total_maintenance_margin=Decimal(0),
        available_margin=Decimal(100 if passed else 0),
        account_positions=(
            AccountRiskPosition(
                exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
                position_side=ticket.identity.netting_domain.position_side,
                quantity=aggregate.position_qty,
                average_entry_price=aggregate.average_fill_price,
                current_unrealized_pnl=Decimal(0),
                current_maintenance_margin=Decimal(0),
            ),
        ),
        observed_at_ms=1_250,
        valid_until_ms=2_250,
    )
    evidence = evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=account,
            maintenance_margin_brackets=(
                MaintenanceMarginBracket(
                    bracket_id="test:1",
                    notional_floor=Decimal(0),
                    notional_cap=None,
                    maintenance_margin_rate=Decimal("0.004"),
                    maintenance_amount=Decimal(0),
                ),
            ),
            maintenance_margin_brackets_digest="sha256:" + "5" * 64,
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            evaluated_side=ticket.identity.netting_domain.position_side,
            reference_entry_price=aggregate.average_fill_price,
            initial_stop_price=ticket.initial_stop_price,
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            projected_instrument_positions=(
                StressPosition(
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=aggregate.position_qty,
                    average_entry_price=aggregate.average_fill_price,
                ),
            ),
        )
    )
    expected_status: Literal["passed", "failed"] = "passed" if passed else "failed"
    assert evidence.proof.status.value == expected_status
    return PostFillStressAssessed(
        event_id=f"event-stress-{aggregate.last_event_sequence + 1}",
        ticket_id=ticket.identity.ticket_id,
        sequence=aggregate.last_event_sequence + 1,
        occurred_at_ms=1_250,
        status=expected_status,
        evidence=evidence,
        owner_policy_id=ticket.owner_policy_id,
        owner_policy_version=ticket.owner_policy_version,
        filled_qty=aggregate.position_qty,
        average_fill_price=aggregate.average_fill_price,
        initial_stop_price=ticket.initial_stop_price,
        initial_stop_exchange_order_id=aggregate.initial_stop_exchange_order_id,
    )


def position_protected_aggregate():
    ticket = make_ticket()
    aggregate = reduce_event(None, TicketIssued(event_id="event-1", ticket=ticket, sequence=1, occurred_at_ms=1_001)).aggregate
    post_fill_risk = assess_post_fill_risk(PostFillRiskRequest(
        position_side=ticket.identity.netting_domain.position_side,
        filled_quantity=ticket.quantity,
        average_fill_price=Decimal(60_000),
        initial_stop_price=ticket.initial_stop_price,
        planned_stop_risk_budget=ticket.planned_stop_risk_budget,
        post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
    ))
    aggregate = reduce_event(aggregate, EntryFilled(event_id="event-2", ticket_id=ticket.identity.ticket_id, sequence=2, occurred_at_ms=1_100, filled_qty=ticket.quantity, average_fill_price=Decimal(60_000), venue_reported_liquidation_price=None, position_observed_at_ms=1_100, post_fill_risk=post_fill_risk)).aggregate
    aggregate = reduce_event(aggregate, InitialStopConfirmed(event_id="event-3", ticket_id=ticket.identity.ticket_id, sequence=3, occurred_at_ms=1_200, exchange_order_id="stop-1", protected_qty=ticket.quantity)).aggregate
    aggregate = reduce_event(aggregate, post_fill_stress_event(aggregate)).aggregate
    return reduce_event(aggregate, TakeProfitConfirmed(event_id="event-5", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=1_300, exchange_order_id="tp-1", target_qty=ticket.take_profit_quantities[0])).aggregate


def reconciliation_pending_aggregate():
    aggregate = position_protected_aggregate()
    ticket = aggregate.ticket
    aggregate = reduce_event(aggregate, ExitRequested(event_id="event-4", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=2_000, reason="strategy_exit")).aggregate
    aggregate = reduce_event(aggregate, PositionFlatConfirmed(event_id="event-5", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=2_100)).aggregate
    aggregate = reduce_event(aggregate, ProtectionCancelConfirmed(event_id="event-6", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=2_150, exchange_order_id="tp-1")).aggregate
    aggregate = reduce_event(aggregate, OwnedOrphanOrderDetected(event_id="event-7", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=2_175, exchange_order_id="stop-1", order_namespace="conditional")).aggregate
    return reduce_event(aggregate, ProtectionCancelConfirmed(event_id="event-8", ticket_id=ticket.identity.ticket_id, sequence=aggregate.last_event_sequence + 1, occurred_at_ms=2_190, exchange_order_id="stop-1")).aggregate
