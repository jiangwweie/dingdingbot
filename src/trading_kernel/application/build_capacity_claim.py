"""Build one immutable CapacityClaim from fresh action-time authority."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from src.trading_kernel.domain.capacity import (
    ActionTimeFacts,
    CapacityClaimDecision,
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
    freeze_capacity_claim,
)
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.exit_policy import exit_policy_for, split_tp1_quantity
from src.trading_kernel.domain.signal import StrategySignal
from src.trading_kernel.domain.ticket import (
    EntryOrderType,
    build_ticket_id,
)


def build_capacity_claim(
    *,
    signal: StrategySignal,
    runtime_profile_id: str,
    venue_id: str,
    account_id: str,
    position_mode: str,
    policy: CapacityPolicy,
    usage: CapacityUsage,
    instrument_rules: CapacityInstrumentRules,
    action_facts: ActionTimeFacts,
    entry_order_type: EntryOrderType,
    netting_domain_occupied: bool,
    now_ms: int,
) -> CapacityClaimDecision:
    if now_ms < signal.observed_at_ms or now_ms >= signal.expires_at_ms:
        return _refused(CapacityClaimStatus.SIGNAL_INVALID_OR_STALE)
    if (
        action_facts.signal_event_id != signal.signal_event_id
        or action_facts.runtime_scope_id != signal.runtime_scope_id
        or action_facts.venue_id != venue_id
        or action_facts.account_id != account_id
        or action_facts.exchange_instrument_id != signal.exchange_instrument_id
        or action_facts.position_side != signal.position_side
    ):
        return _refused(CapacityClaimStatus.SCOPE_OR_POLICY_MISMATCH)
    if (
        now_ms < action_facts.observed_at_ms
        or now_ms >= action_facts.valid_until_ms
    ):
        return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
    if position_mode != "independent_sides":
        return _refused(CapacityClaimStatus.ACCOUNT_MODE_INVALID)
    if (
        netting_domain_occupied
        or action_facts.netting_domain_position_qty != 0
        or action_facts.netting_domain_open_order_count != 0
    ):
        return _refused(CapacityClaimStatus.NETTING_DOMAIN_OCCUPIED)
    if (
        now_ms < instrument_rules.observed_at_ms
        or now_ms >= instrument_rules.valid_until_ms
    ):
        return _refused(CapacityClaimStatus.INSTRUMENT_RULES_INVALID)
    if usage.active_ticket_count >= policy.max_concurrent_tickets:
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)

    entry_price = (
        action_facts.best_ask_price
        if signal.position_side == "long"
        else action_facts.best_bid_price
    )
    stop_reference = _protection_reference(signal)
    if stop_reference is None:
        return _refused(CapacityClaimStatus.PROTECTION_UNAVAILABLE)
    stop_price = _round_stop(
        stop_reference,
        instrument_rules.price_tick,
        position_side=signal.position_side,
    )
    if (
        signal.position_side == "long" and stop_price >= entry_price
    ) or (
        signal.position_side == "short" and stop_price <= entry_price
    ):
        return _refused(CapacityClaimStatus.PROTECTION_UNAVAILABLE)

    risk_per_unit = abs(entry_price - stop_price)
    remaining_notional = policy.max_gross_notional - usage.gross_notional
    remaining_risk = policy.max_gross_risk_at_stop - usage.gross_risk_at_stop
    ticket_risk_budget = min(policy.max_ticket_risk_at_stop, remaining_risk)
    margin_notional = (
        min(action_facts.available_margin, action_facts.account_equity)
        * policy.target_leverage
    )
    available_notional = min(remaining_notional, margin_notional)
    if (
        risk_per_unit <= 0
        or ticket_risk_budget <= 0
        or available_notional <= 0
    ):
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)

    quantity_by_risk = _floor_step(
        ticket_risk_budget / risk_per_unit,
        instrument_rules.quantity_step,
    )
    quantity_by_notional = _floor_step(
        available_notional / entry_price,
        instrument_rules.quantity_step,
    )
    quantity = min(quantity_by_risk, quantity_by_notional)
    notional = quantity * entry_price
    risk_at_stop = quantity * risk_per_unit
    if (
        quantity < instrument_rules.min_quantity
        or notional < instrument_rules.min_notional
        or risk_at_stop <= 0
    ):
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)

    take_profit_price = _round_take_profit(
        entry_price,
        risk_per_unit,
        instrument_rules.price_tick,
        position_side=signal.position_side,
    )
    exit_policy = exit_policy_for(signal.event_spec_id)
    try:
        take_profit_split = split_tp1_quantity(
            total_quantity=quantity,
            quantity_step=instrument_rules.quantity_step,
            quantity_fraction=exit_policy.tp1.quantity_fraction,
        )
    except ValueError:
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)
    runtime = RuntimeIdentity(
        runtime_profile_id=runtime_profile_id,
        strategy_group_id=signal.strategy_group_id,
        strategy_version_id=signal.strategy_version_id,
        event_spec_id=signal.event_spec_id,
    )
    netting_domain = NettingDomain(
        venue_id=venue_id,
        account_id=account_id,
        exchange_instrument_id=signal.exchange_instrument_id,
        position_side=signal.position_side,
    )
    ticket_id = build_ticket_id(
        signal_event_id=signal.signal_event_id,
        runtime=runtime,
        netting_domain=netting_domain,
    )
    ticket_identity = TicketIdentity(
        ticket_id=ticket_id,
        exposure_episode_id=f"episode:{ticket_id.removeprefix('ticket:')}",
        signal_event_id=signal.signal_event_id,
        runtime=runtime,
        netting_domain=netting_domain,
    )
    expires_at_ms = min(
        signal.expires_at_ms,
        action_facts.valid_until_ms,
        instrument_rules.valid_until_ms,
    )
    claim = freeze_capacity_claim(
        ticket_identity=ticket_identity,
        owner_policy_id=policy.owner_policy_id,
        owner_policy_version=policy.policy_version,
        runtime_scope_id=signal.runtime_scope_id,
        runtime_scope_version=signal.runtime_scope_version,
        fact_digest=signal.fact_digest,
        action_facts_digest=action_facts.digest(),
        instrument_rules_projection_version=instrument_rules.projection_version,
        created_at_ms=now_ms,
        expires_at_ms=expires_at_ms,
        entry_reference_price=entry_price,
        quantity=quantity,
        notional=notional,
        leverage=policy.target_leverage,
        risk_at_stop=risk_at_stop,
        entry_order_type=entry_order_type,
        entry_limit_price=(
            entry_price if entry_order_type is EntryOrderType.LIMIT else None
        ),
        initial_stop_price=stop_price,
        take_profit_prices=(take_profit_price,),
        take_profit_quantities=(take_profit_split.tp1_quantity,),
    )
    return CapacityClaimDecision(
        status=CapacityClaimStatus.CLAIMED,
        claim=claim,
    )


def _protection_reference(signal: StrategySignal) -> Decimal | None:
    references = [fact for fact in signal.facts if fact.role == "protection_reference"]
    if len(references) != 1:
        return None
    try:
        value = Decimal(str(references[0].value))
    except Exception:
        return None
    return value if value > 0 else None


def _floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_stop(
    value: Decimal,
    tick: Decimal,
    *,
    position_side: str,
) -> Decimal:
    return (
        _floor_step(value, tick)
        if position_side == "long"
        else _ceil_step(value, tick)
    )


def _round_take_profit(
    entry_price: Decimal,
    risk_per_unit: Decimal,
    tick: Decimal,
    *,
    position_side: str,
) -> Decimal:
    if position_side == "long":
        return _ceil_step(entry_price + risk_per_unit, tick)
    return _floor_step(entry_price - risk_per_unit, tick)


def _refused(status: CapacityClaimStatus) -> CapacityClaimDecision:
    return CapacityClaimDecision(status=status, claim=None)
