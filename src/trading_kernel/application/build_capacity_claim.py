"""Build one immutable CapacityClaim from a single fresh admission snapshot."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from src.trading_kernel.domain.account_entry_health import (
    AccountEntryHealth,
    AccountEntryHealthStatus,
)
from src.trading_kernel.domain.capacity import (
    CapacityClaimDecision,
    CapacityClaimStatus,
    CapacityInstrumentRules,
    CapacityPolicy,
    CapacityUsage,
    freeze_capacity_claim,
)
from src.trading_kernel.domain.capacity_sizing import (
    CapacitySizingRequest,
    CapacitySizingStatus,
    select_capacity_candidate,
)
from src.trading_kernel.domain.cross_margin_stress import (
    CrossMarginStressRequest,
    CrossMarginStressStatus,
    StressPosition,
    evaluate_cross_margin_stress,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.exit_policy import exit_policy_for
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.instrument_entry_health import (
    InstrumentEntryHealth,
    InstrumentEntryHealthStatus,
)
from src.trading_kernel.domain.signal import StrategySignal
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.domain.ticket import EntryOrderType, build_ticket_id


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
    admission_snapshot: EntryAdmissionSnapshot,
    account_entry_health: AccountEntryHealth,
    instrument_entry_health: InstrumentEntryHealth,
    entry_order_type: EntryOrderType,
    netting_domain_occupied: bool,
    now_ms: int,
) -> CapacityClaimDecision:
    account_risk = admission_snapshot.account_risk_snapshot
    if now_ms < signal.observed_at_ms or now_ms >= signal.expires_at_ms:
        return _refused(CapacityClaimStatus.SIGNAL_INVALID_OR_STALE)
    if (
        account_risk.venue_id != venue_id
        or account_risk.account_id != account_id
        or instrument_rules.venue_id != venue_id
        or instrument_rules.exchange_instrument_id != signal.exchange_instrument_id
    ):
        return _refused(CapacityClaimStatus.SCOPE_OR_POLICY_MISMATCH)
    if (
        now_ms < admission_snapshot.observed_at_ms
        or now_ms >= admission_snapshot.valid_until_ms
        or now_ms < instrument_rules.observed_at_ms
        or now_ms >= instrument_rules.valid_until_ms
    ):
        return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
    if (
        position_mode != "independent_sides"
        or account_risk.position_mode != "independent_sides"
        or account_risk.margin_mode != policy.supported_margin_mode
    ):
        return _refused(CapacityClaimStatus.ACCOUNT_MODE_INVALID)
    snapshot_digest = admission_snapshot.digest()
    if (
        account_entry_health.entry_admission_snapshot_digest != snapshot_digest
        or instrument_entry_health.entry_admission_snapshot_digest != snapshot_digest
    ):
        return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
    if account_entry_health.status is not AccountEntryHealthStatus.HEALTHY:
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)
    if instrument_entry_health.status is InstrumentEntryHealthStatus.SAME_DIRECTION_OCCUPIED:
        return _refused(CapacityClaimStatus.NETTING_DOMAIN_OCCUPIED)
    if instrument_entry_health.status not in {
        InstrumentEntryHealthStatus.HEALTHY_FLAT,
        InstrumentEntryHealthStatus.HEALTHY_OPPOSITE_SIDE,
    }:
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)
    if netting_domain_occupied:
        return _refused(CapacityClaimStatus.NETTING_DOMAIN_OCCUPIED)
    if usage.active_ticket_count >= policy.max_concurrent_tickets:
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)
    contract = strategy_contract_for(signal.event_spec_id)
    family_ticket_limit = policy.family_ticket_limits.for_family(
        contract.exposure_family
    )
    if (
        usage.active_family_ticket_count
        >= family_ticket_limit
    ):
        return _refused(
            CapacityClaimStatus.EXPOSURE_FAMILY_CAPACITY_EXHAUSTED
        )
    if usage.directional_risk_at_stop >= (
        account_risk.total_wallet_balance
        * policy.directional_stop_risk_limit_fraction
    ):
        return _refused(CapacityClaimStatus.DIRECTIONAL_RISK_EXHAUSTED)

    entry_price = (
        admission_snapshot.best_ask_price
        if signal.position_side == "long"
        else admission_snapshot.best_bid_price
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

    if account_risk.exchange_instrument_id != signal.exchange_instrument_id:
        return _refused(CapacityClaimStatus.SCOPE_OR_POLICY_MISMATCH)
    exit_policy = exit_policy_for(signal.event_spec_id)
    pre_tp1_reclaim_price = _contract_decimal_fact(
        signal,
        contract.pre_tp1_reclaim_reference_fact,
        expected_role="lifecycle_reference",
    )
    session_end_decimal = _contract_decimal_fact(
        signal,
        contract.exposure_session_end_reference_fact,
        expected_role="lifecycle_reference",
    )
    if (pre_tp1_reclaim_price is None) != (session_end_decimal is None):
        return _refused(CapacityClaimStatus.PROTECTION_UNAVAILABLE)
    exposure_session_end_ms: int | None = None
    if session_end_decimal is not None:
        if session_end_decimal != session_end_decimal.to_integral_value():
            return _refused(CapacityClaimStatus.PROTECTION_UNAVAILABLE)
        exposure_session_end_ms = int(session_end_decimal)
    sizing = select_capacity_candidate(
        CapacitySizingRequest(
            total_wallet_balance=account_risk.total_wallet_balance,
            total_margin_balance=account_risk.total_margin_balance,
            total_initial_margin=account_risk.total_initial_margin,
            current_reserved_margin=usage.current_reserved_margin,
            gross_risk_at_stop=usage.gross_risk_at_stop,
            directional_risk_at_stop=usage.directional_risk_at_stop,
            available_margin=account_risk.available_margin,
            active_ticket_count=usage.active_ticket_count,
            max_concurrent_tickets=policy.max_concurrent_tickets,
            max_ticket_stop_risk_fraction=(
                policy.max_ticket_stop_risk_fraction
            ),
            max_gross_stop_risk_fraction=(
                policy.max_gross_stop_risk_fraction
            ),
            max_ticket_initial_margin_fraction=(
                policy.max_ticket_initial_margin_fraction
            ),
            max_gross_initial_margin_utilization=(
                policy.max_gross_initial_margin_utilization
            ),
            directional_stop_risk_limit_fraction=(
                policy.directional_stop_risk_limit_fraction
            ),
            min_materialization_ratio=policy.min_materialization_ratio,
            permitted_max_leverage=min(
                policy.max_leverage,
                instrument_rules.exchange_max_leverage,
            ),
            configured_leverage=account_risk.configured_leverage,
            entry_reference_price=entry_price,
            initial_stop_price=stop_price,
            quantity_step=instrument_rules.quantity_step,
            min_quantity=instrument_rules.min_quantity,
            min_notional=instrument_rules.min_notional,
            tp1_quantity_fraction=exit_policy.tp1.quantity_fraction,
        )
    )
    if sizing.status is not CapacitySizingStatus.SELECTED or sizing.selected is None:
        return _refused(_sizing_refusal(sizing.status))
    selected = sizing.selected
    projected_positions = tuple(
        StressPosition(
            position_side=position.position_side,
            quantity=position.quantity,
            average_entry_price=position.average_entry_price,
        )
        for position in account_risk.account_positions
        if position.exchange_instrument_id == signal.exchange_instrument_id
    ) + (
        StressPosition(
            position_side=signal.position_side,
            quantity=selected.quantity,
            average_entry_price=entry_price,
        ),
    )
    stress_evidence = evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=account_risk,
            maintenance_margin_brackets=(
                instrument_rules.maintenance_margin_brackets
            ),
            maintenance_margin_brackets_digest=(
                instrument_rules.maintenance_margin_brackets_digest
            ),
            notional_coefficient=instrument_rules.notional_coefficient,
            notional_coefficient_certified=(
                instrument_rules.notional_coefficient_certified
            ),
            evaluated_side=signal.position_side,
            reference_entry_price=entry_price,
            initial_stop_price=stop_price,
            post_stop_stress_multiple=policy.post_stop_stress_multiple,
            projected_instrument_positions=projected_positions,
        )
    )
    if stress_evidence.proof.status is CrossMarginStressStatus.FACTS_CONTRADICTORY:
        return _refused(CapacityClaimStatus.INSTRUMENT_RULES_INVALID)
    if stress_evidence.proof.status is not CrossMarginStressStatus.PASSED:
        return _refused(CapacityClaimStatus.PROTECTION_UNAVAILABLE)
    take_profit_price = _round_take_profit(
        entry_price,
        abs(entry_price - stop_price),
        instrument_rules.price_tick,
        position_side=signal.position_side,
    )
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
        exposure_episode_id=signal.exposure_episode_id,
        signal_event_id=signal.signal_event_id,
        runtime=runtime,
        netting_domain=netting_domain,
    )
    post_fill_stop_risk_limit = selected.ticket_stop_risk_budget * (
        Decimal(1) + policy.max_post_fill_stop_risk_overrun_fraction
    )
    claim = freeze_capacity_claim(
        ticket_identity=ticket_identity,
        owner_policy_id=policy.owner_policy_id,
        owner_policy_version=policy.policy_version,
        runtime_scope_id=signal.runtime_scope_id,
        runtime_scope_version=signal.runtime_scope_version,
        universe_version_id=signal.universe_version_id,
        universe_semantic_digest=signal.universe_semantic_digest,
        fact_digest=signal.fact_digest,
        exit_policy_id=exit_policy.exit_policy_id,
        exit_policy_semantic_hash=exit_policy.semantic_hash(),
        entry_admission_snapshot_digest=snapshot_digest,
        account_entry_health_digest=account_entry_health.decision_digest,
        instrument_entry_health_digest=instrument_entry_health.decision_digest,
        instrument_rules_projection_version=instrument_rules.projection_version,
        account_capacity_domain_key=f"{venue_id}:{account_id}",
        leverage_domain_key=(
            f"{venue_id}:{account_id}:{signal.exchange_instrument_id}"
        ),
        total_wallet_balance_at_claim=account_risk.total_wallet_balance,
        total_margin_balance_at_claim=account_risk.total_margin_balance,
        total_initial_margin_at_claim=account_risk.total_initial_margin,
        total_maintenance_margin_at_claim=(
            account_risk.total_maintenance_margin
        ),
        available_margin_at_claim=account_risk.available_margin,
        mark_price_at_claim=account_risk.mark_price,
        position_mode_at_claim=account_risk.position_mode,
        margin_mode_at_claim=account_risk.margin_mode,
        active_ticket_count_at_claim=usage.active_ticket_count,
        remaining_slots_at_claim=selected.remaining_slots,
        exposure_family=contract.exposure_family,
        active_family_ticket_count_at_claim=(
            usage.active_family_ticket_count
        ),
        family_ticket_limit=family_ticket_limit,
        remaining_family_slots_at_claim=(
            family_ticket_limit - usage.active_family_ticket_count
        ),
        gross_risk_at_stop_at_claim=usage.gross_risk_at_stop,
        directional_risk_at_stop_at_claim=usage.directional_risk_at_stop,
        current_reserved_margin_at_claim=usage.current_reserved_margin,
        max_ticket_stop_risk_fraction=(
            policy.max_ticket_stop_risk_fraction
        ),
        max_gross_stop_risk_fraction=policy.max_gross_stop_risk_fraction,
        directional_stop_risk_limit_fraction=(
            policy.directional_stop_risk_limit_fraction
        ),
        max_ticket_initial_margin_fraction=(
            policy.max_ticket_initial_margin_fraction
        ),
        max_gross_initial_margin_utilization=(
            policy.max_gross_initial_margin_utilization
        ),
        min_materialization_ratio=policy.min_materialization_ratio,
        minimum_stop_risk_budget=selected.minimum_stop_risk_budget,
        planned_stop_risk_budget=selected.ticket_stop_risk_budget,
        max_post_fill_stop_risk_overrun_fraction=(
            policy.max_post_fill_stop_risk_overrun_fraction
        ),
        post_fill_stop_risk_limit=post_fill_stop_risk_limit,
        post_stop_stress_multiple=policy.post_stop_stress_multiple,
        ticket_margin_budget=selected.ticket_margin_budget,
        required_leverage=selected.required_leverage,
        selected_leverage=selected.selected_leverage,
        configured_leverage_at_claim=selected.configured_leverage,
        leverage_change_required=selected.leverage_change_required,
        exchange_max_leverage=instrument_rules.exchange_max_leverage,
        reserved_margin=selected.reserved_margin,
        cross_margin_stress_evidence=stress_evidence,
        created_at_ms=now_ms,
        expires_at_ms=min(
            signal.expires_at_ms,
            admission_snapshot.valid_until_ms,
            instrument_rules.valid_until_ms,
        ),
        entry_reference_price=entry_price,
        quantity=selected.quantity,
        notional=selected.notional,
        risk_at_stop=selected.planned_stop_risk,
        entry_order_type=entry_order_type,
        entry_limit_price=(
            entry_price if entry_order_type is EntryOrderType.LIMIT else None
        ),
        initial_stop_price=stop_price,
        pre_tp1_reclaim_price=pre_tp1_reclaim_price,
        exposure_session_end_ms=exposure_session_end_ms,
        take_profit_prices=(take_profit_price,),
        take_profit_quantities=(selected.tp1_quantity,),
    )
    return CapacityClaimDecision(status=CapacityClaimStatus.CLAIMED, claim=claim)


def _sizing_refusal(status: CapacitySizingStatus) -> CapacityClaimStatus:
    if status is CapacitySizingStatus.DIRECTIONAL_RISK_EXHAUSTED:
        return CapacityClaimStatus.DIRECTIONAL_RISK_EXHAUSTED
    if status in {
        CapacitySizingStatus.COUNT_EXHAUSTED,
        CapacitySizingStatus.STOP_RISK_EXHAUSTED,
        CapacitySizingStatus.MARGIN_EXHAUSTED,
        CapacitySizingStatus.VENUE_MINIMUM_UNMET,
        CapacitySizingStatus.EXIT_PLAN_UNEXECUTABLE,
        CapacitySizingStatus.MINIMUM_MATERIALIZATION_UNMET,
    }:
        return CapacityClaimStatus.BUDGET_EXHAUSTED
    return CapacityClaimStatus.INSTRUMENT_RULES_INVALID


def _protection_reference(signal: StrategySignal) -> Decimal | None:
    references = [fact for fact in signal.facts if fact.role == "protection_reference"]
    if len(references) != 1:
        return None
    try:
        value = Decimal(str(references[0].value))
    except (ArithmeticError, ValueError):
        return None
    return value if value.is_finite() and value > 0 else None


def _contract_decimal_fact(
    signal: StrategySignal,
    fact_name: str | None,
    *,
    expected_role: str,
) -> Decimal | None:
    if fact_name is None:
        return None
    contract = strategy_contract_for(signal.event_spec_id)
    expected_id = next(
        (
            requirement.fact_definition_id
            for requirement in contract.required_facts
            if requirement.fact_name == fact_name
            and requirement.role == expected_role
        ),
        None,
    )
    if expected_id is None:
        return None
    matches = [
        fact
        for fact in signal.facts
        if fact.fact_definition_id == expected_id and fact.role == expected_role
    ]
    if len(matches) != 1:
        return None
    try:
        value = Decimal(str(matches[0].value))
    except (ArithmeticError, ValueError):
        return None
    return value if value.is_finite() and value > 0 else None


def _floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_stop(value: Decimal, tick: Decimal, *, position_side: str) -> Decimal:
    return _floor_step(value, tick) if position_side == "long" else _ceil_step(value, tick)


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
