"""Actual-fill exit plans for lifecycle fixtures with explicit local venue rules."""

from decimal import Decimal

from src.trading_kernel.domain.exit_policy import registered_exit_profiles
from src.trading_kernel.domain.post_fill_exit import (
    PostFillExitRequest,
    build_post_fill_exit_plan,
)


def make_post_fill_exit_plan(aggregate, *, at_ms: int):
    ticket = aggregate.ticket
    profile = next(
        p
        for p in registered_exit_profiles()
        if p.exit_profile_id == ticket.exit_policy_id
    )
    assert profile.semantic_hash() == ticket.exit_policy_semantic_hash
    assert aggregate.average_fill_price is not None
    assert ticket.exit_binding_id is not None
    result = build_post_fill_exit_plan(
        PostFillExitRequest(
            ticket_id=ticket.identity.ticket_id,
            exit_binding_id=ticket.exit_binding_id,
            profile=profile,
            quantity=aggregate.position_qty,
            average_fill_price=aggregate.average_fill_price,
            initial_stop_price=ticket.initial_stop_price,
            quantity_step=Decimal("0.00000001"),
            price_tick=Decimal("0.01"),
            min_quantity=Decimal("0.00000001"),
            min_notional=Decimal("0.00000001"),
            rules_digest="sha256:" + "a" * 64,
            rules_observed_at_ms=at_ms,
            rules_valid_until_ms=at_ms + 1000,
            created_at_ms=at_ms,
            reference_take_profit_price=ticket.take_profit_prices[0],
            reference_tp1_quantity=ticket.take_profit_quantities[0],
        )
    )
    assert result.plan is not None, result
    return result.plan
