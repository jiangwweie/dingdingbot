"""Combine database authority with current venue facts for US product admission."""

from __future__ import annotations

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.corporate_events import (
    evaluate_corporate_event_admission,
)
from src.trading_kernel.domain.product_admission import (
    ProductAdmissionContext,
    ProductMarketFacts,
)


async def build_product_admission_context(
    uow: KernelUnitOfWork,
    *,
    market_facts: ProductMarketFacts,
    action_time_ms: int,
) -> ProductAdmissionContext | None:
    authority = await uow.product_admission.load_current_authority(
        market_facts.exchange_instrument_id
    )
    if authority is None:
        return None
    exact_events = tuple(
        event
        for event in authority.events
        if event.effective_at_ms is not None
        and event.effective_at_ms <= action_time_ms
    )
    latest_effective = max(
        (int(event.effective_at_ms or 0) for event in exact_events),
        default=0,
    )
    closed_bars = (
        0
        if latest_effective <= 0
        else max(0, (action_time_ms - latest_effective) // 900_000)
    )
    corporate_decision = evaluate_corporate_event_admission(
        action_time_ms=action_time_ms,
        exchange_instrument_id=market_facts.exchange_instrument_id,
        coverage=authority.coverage,
        events=authority.events,
        closed_15m_bars_after_event=closed_bars,
        product_profile_observed_at_ms=authority.profile.observed_at_ms,
    )
    return ProductAdmissionContext(
        profile=authority.profile,
        market_facts=market_facts,
        calendar=authority.calendar,
        corporate_event_admission=corporate_decision,
        policy=authority.policy,
    )
