"""Plan continuation from an already verified Owner reduction, without dispatch.

The original failure/time exits take precedence. This is not a TP fill and
cannot change accounting; the caller must durably commit any resulting event.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    ExitProfile,
    LifecycleMarketFacts,
    calculate_cost_adjusted_break_even,
    evaluate_profile_pre_tp1_exit,
)
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionDecision,
    OwnerReductionFacts,
    OwnerReductionState,
    advance_owner_reduction,
)


class OwnerContinuationDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: OwnerReductionDecision
    exit_reason: str | None = None
    proposed_stop: Decimal | None = None


def evaluate_owner_reduced_lifecycle(
    *,
    state: OwnerReductionState,
    facts: OwnerReductionFacts,
    now_ms: int,
    profile: ExitProfile,
    market_facts: LifecycleMarketFacts | None,
    entry_average_price: Decimal,
    allocated_entry_fee_quote: Decimal,
    exit_taker_fee_rate: Decimal,
    price_tick: Decimal,
    pre_tp1_reclaim_price: Decimal | None = None,
    exposure_session_end_ms: int | None = None,
) -> OwnerContinuationDecision:
    if (
        profile.position_side != state.preview.side
        or profile.exit_profile_id != state.preview.exit_policy_id
        or profile.semantic_hash() != state.preview.exit_policy_semantic_hash
    ):
        raise ValueError("owner_continuation_profile_side_mismatch")
    decision = advance_owner_reduction(state, facts, now_ms=now_ms)
    if decision.action not in {"no_change", "request_break_even"}:
        return OwnerContinuationDecision(operation=decision)
    if decision.reason not in {
        "waiting_original_tp_price",
        "original_price_condition_satisfied",
    }:
        return OwnerContinuationDecision(operation=decision)
    if market_facts is not None:
        failure = evaluate_profile_pre_tp1_exit(
            profile=profile,
            market_facts=market_facts,
            observed_at_ms=facts.observed_at_ms,
            pre_tp1_reclaim_price=pre_tp1_reclaim_price,
            exposure_session_end_ms=exposure_session_end_ms,
        )
        if failure.kind is ExitDecisionKind.EXIT:
            return OwnerContinuationDecision(
                operation=decision, exit_reason=failure.reason
            )
    if decision.action != "request_break_even":
        return OwnerContinuationDecision(operation=decision)
    floor = calculate_cost_adjusted_break_even(
        side=state.preview.side,
        entry_average_price=entry_average_price,
        runner_quantity=facts.position_quantity,
        allocated_entry_fee_quote=allocated_entry_fee_quote,
        exit_taker_fee_rate=exit_taker_fee_rate,
        price_tick=price_tick,
        slippage_buffer_ticks=profile.break_even_floor.slippage_buffer_ticks,
    )
    assert facts.stop_price is not None  # checked by the domain decision
    floor = (
        max(floor, facts.stop_price)
        if state.preview.side == "long"
        else min(floor, facts.stop_price)
    )
    if (
        facts.current_price <= floor
        if state.preview.side == "long"
        else facts.current_price >= floor
    ):
        return OwnerContinuationDecision(
            operation=decision, exit_reason="break_even_crossed"
        )
    return OwnerContinuationDecision(operation=decision, proposed_stop=floor)
