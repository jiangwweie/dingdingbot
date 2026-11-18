"""Evaluate original failure/time exits before preparing an Owner quantity change."""

from src.trading_kernel.application.runtime_facts import LifecycleFactsRequest
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.exit_policy import (
    ExitDecisionKind,
    TimeStopMode,
    evaluate_profile_pre_tp1_exit,
    evaluate_profile_runner_exit,
)


async def read_original_operation_exit(
    source, *, aggregate, profile, rules, references, now_ms
):
    a = (
        aggregate.model_copy(update={"status": aggregate.protection_return_status})
        if aggregate.protection_return_status
        else aggregate
    )
    entry = next(
        (r for r in references if r.command_kind is ExchangeCommandKind.ENTRY), None
    )
    if entry is None:
        raise ValueError("operation_original_entry_missing")
    time_bars = (
        None
        if profile.time_stop is None
        or (
            a.status is AggregateStatus.RUNNER_PROTECTED
            and profile.time_stop.mode is TimeStopMode.PRE_TP1
        )
        else profile.time_stop.max_holding_bars
    )
    needed = (
        a.status is AggregateStatus.RUNNER_PROTECTED
        or bool(profile.pre_tp1_guards)
        or time_bars is not None
    )
    if not needed:
        return None
    f = await source.read_lifecycle_facts(
        LifecycleFactsRequest(
            ticket_id=a.identity.ticket_id,
            netting_domain=a.identity.netting_domain,
            event_spec_id=a.identity.runtime.event_spec_id,
            timeframe=profile.runner.timeframe,
            entry_quantity=a.ticket.quantity,
            expected_position_quantity=a.position_qty,
            entry_order_reference=entry,
            tp1_exchange_order_id=None,
            entry_fill_window_started_at_ms=entry.command_created_at_ms,
            price_tick=rules.price_tick,
            structure_window_bars=profile.runner.lookback_bars,
            atr_period=profile.runner.atr_period,
            time_stop_max_holding_bars=time_bars,
            runner_market_required=True,
            observed_at_ms=now_ms,
        )
    )
    if f.position_quantity != a.position_qty or f.market_facts is None:
        raise ValueError("operation_original_exit_facts_changed")
    if a.status is AggregateStatus.RUNNER_PROTECTED:
        if a.active_stop_price is None or a.break_even_floor_price is None:
            raise ValueError("operation_runner_protection_missing")
        decision = evaluate_profile_runner_exit(
            profile=profile,
            current_stop=a.active_stop_price,
            break_even_floor=a.break_even_floor_price,
            price_tick=rules.price_tick,
            last_runner_watermark_ms=a.runner_stop_watermark_ms or 0,
            market_facts=f.market_facts,
        )
    else:
        decision = evaluate_profile_pre_tp1_exit(
            profile=profile,
            market_facts=f.market_facts,
            observed_at_ms=f.observed_at_ms,
            pre_tp1_reclaim_price=a.ticket.pre_tp1_reclaim_price,
            exposure_session_end_ms=a.ticket.exposure_session_end_ms,
        )
    return decision.reason if decision.kind is ExitDecisionKind.EXIT else None
