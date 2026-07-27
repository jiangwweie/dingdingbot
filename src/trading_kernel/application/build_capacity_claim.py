"""Build one immutable CapacityClaim from a single fresh admission snapshot."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

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
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.exit_policy import exit_policy_for
from src.trading_kernel.domain.identities import NettingDomain, RuntimeIdentity, TicketIdentity
from src.trading_kernel.domain.instrument_entry_health import (
    InstrumentEntryHealth,
    InstrumentEntryHealthStatus,
)
from src.trading_kernel.domain.product_admission import (
    ProductAdmissionContext,
    evaluate_product_admission,
)
from src.trading_kernel.domain.signal import StrategySignal
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
    product_admission_context: ProductAdmissionContext | None = None,
) -> CapacityClaimDecision:
    if now_ms < signal.observed_at_ms or now_ms >= signal.expires_at_ms:
        return _refused(CapacityClaimStatus.SIGNAL_INVALID_OR_STALE)
    if (
        admission_snapshot.venue_id != venue_id
        or admission_snapshot.account_id != account_id
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
        or admission_snapshot.position_mode != "independent_sides"
        or admission_snapshot.margin_mode != policy.supported_margin_mode
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

    instrument_facts = admission_snapshot.instrument_facts_for(
        signal.exchange_instrument_id
    )
    session_code = "CRYPTO_CONTINUOUS"
    session_multiplier = Decimal("1")
    if signal.strategy_group_id == "RSRVCB-001":
        if product_admission_context is None:
            return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
        session = product_admission_context.classify(action_time_ms=now_ms)
        session_code = session.session_code.value
        session_multiplier = session.stop_risk_multiplier
        if session_multiplier <= 0:
            return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
    effective_stop_risk_fraction = (
        policy.planned_stop_risk_fraction * session_multiplier
    )
    effective_initial_margin = max(
        admission_snapshot.total_initial_margin,
        usage.reserved_margin,
    )
    exit_policy = exit_policy_for(signal.event_spec_id)
    sizing = select_capacity_candidate(
        CapacitySizingRequest(
            total_wallet_balance=admission_snapshot.total_wallet_balance,
            total_margin_balance=admission_snapshot.total_margin_balance,
            total_initial_margin=effective_initial_margin,
            total_maintenance_margin=admission_snapshot.total_maintenance_margin,
            available_margin=admission_snapshot.available_margin,
            active_ticket_count=usage.active_ticket_count,
            max_concurrent_tickets=policy.max_concurrent_tickets,
            planned_stop_risk_fraction=effective_stop_risk_fraction,
            max_initial_margin_utilization=(
                policy.max_initial_margin_utilization
            ),
            permitted_max_leverage=min(
                policy.max_leverage,
                instrument_rules.exchange_max_leverage,
            ),
            configured_leverage=instrument_facts.configured_leverage,
            instrument_has_open_position=(
                instrument_entry_health.status
                is InstrumentEntryHealthStatus.HEALTHY_OPPOSITE_SIDE
            ),
            entry_reference_price=entry_price,
            initial_stop_price=stop_price,
            quantity_step=instrument_rules.quantity_step,
            min_quantity=instrument_rules.min_quantity,
            min_notional=instrument_rules.min_notional,
            tp1_quantity_fraction=exit_policy.tp1.quantity_fraction,
            maintenance_margin_brackets=instrument_rules.maintenance_margin_brackets,
            position_side=signal.position_side,
            mark_price=instrument_facts.mark_price,
            min_liquidation_distance_to_stop_distance_ratio=(
                policy.min_liquidation_distance_to_stop_distance_ratio
            ),
        )
    )
    if sizing.status is not CapacitySizingStatus.SELECTED or sizing.selected is None:
        return _refused(_sizing_refusal(sizing.status))
    selected = sizing.selected
    product_admission_digest: str | None = None
    if product_admission_context is not None:
        product_decision = evaluate_product_admission(
            action_time_ms=now_ms,
            order_notional=selected.notional,
            profile=product_admission_context.profile,
            market_facts=product_admission_context.market_facts,
            calendar=product_admission_context.calendar,
            corporate_event_admission=(
                product_admission_context.corporate_event_admission
            ),
            policy=product_admission_context.policy,
        )
        if (
            not product_decision.allowed
            or product_decision.session_code != session_code
            or product_decision.session_multiplier != session_multiplier
            or instrument_facts.configured_leverage != 5
        ):
            return _refused(CapacityClaimStatus.ACTION_FACTS_INVALID_OR_STALE)
        product_admission_digest = product_decision.product_admission_digest
    portfolio_stop_risk_after = (
        usage.gross_risk_at_stop + selected.planned_stop_risk
    )
    if portfolio_stop_risk_after > (
        admission_snapshot.total_wallet_balance
        * policy.max_portfolio_stop_risk_fraction
    ):
        return _refused(CapacityClaimStatus.BUDGET_EXHAUSTED)
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
        exposure_episode_id=f"episode:{ticket_id.removeprefix('ticket:')}",
        signal_event_id=signal.signal_event_id,
        runtime=runtime,
        netting_domain=netting_domain,
    )
    post_fill_stop_risk_limit = selected.planned_stop_risk_budget * (
        Decimal("1") + policy.max_post_fill_stop_risk_overrun_fraction
    )
    claim = freeze_capacity_claim(
        ticket_identity=ticket_identity,
        owner_policy_id=policy.owner_policy_id,
        owner_policy_version=policy.policy_version,
        runtime_scope_id=signal.runtime_scope_id,
        runtime_scope_version=signal.runtime_scope_version,
        fact_digest=signal.fact_digest,
        universe_version_id=signal.universe_version_id,
        universe_digest=signal.universe_digest,
        projection_run_id=signal.projection_run_id,
        armed_structure_id=signal.armed_structure_id,
        product_policy_version_id=(
            None
            if product_admission_context is None
            else product_admission_context.policy.product_policy_version_id
        ),
        exit_policy_id=exit_policy.exit_policy_id,
        exit_policy_version=exit_policy.exit_policy_version,
        exit_policy_digest=exit_policy.semantic_hash(),
        exit_policy=exit_policy,
        entry_admission_snapshot_digest=snapshot_digest,
        account_entry_health_digest=account_entry_health.decision_digest,
        instrument_entry_health_digest=instrument_entry_health.decision_digest,
        instrument_rules_projection_version=instrument_rules.projection_version,
        account_capacity_domain_key=f"{venue_id}:{account_id}",
        leverage_domain_key=(
            f"{venue_id}:{account_id}:{signal.exchange_instrument_id}"
        ),
        total_wallet_balance_at_claim=admission_snapshot.total_wallet_balance,
        total_margin_balance_at_claim=admission_snapshot.total_margin_balance,
        total_initial_margin_at_claim=effective_initial_margin,
        total_maintenance_margin_at_claim=(
            admission_snapshot.total_maintenance_margin
        ),
        available_margin_at_claim=admission_snapshot.available_margin,
        mark_price_at_claim=instrument_facts.mark_price,
        position_mode_at_claim=admission_snapshot.position_mode,
        margin_mode_at_claim=admission_snapshot.margin_mode,
        active_ticket_count_at_claim=usage.active_ticket_count,
        remaining_slots_at_claim=selected.remaining_slots,
        planned_stop_risk_fraction=effective_stop_risk_fraction,
        planned_stop_risk_budget=selected.planned_stop_risk_budget,
        portfolio_stop_risk_before=usage.gross_risk_at_stop,
        portfolio_stop_risk_after=portfolio_stop_risk_after,
        session_code=session_code,
        session_multiplier=session_multiplier,
        product_admission_digest=product_admission_digest,
        max_post_fill_stop_risk_overrun_fraction=(
            policy.max_post_fill_stop_risk_overrun_fraction
        ),
        post_fill_stop_risk_limit=post_fill_stop_risk_limit,
        max_initial_margin_utilization=policy.max_initial_margin_utilization,
        min_liquidation_distance_to_stop_distance_ratio=(
            policy.min_liquidation_distance_to_stop_distance_ratio
        ),
        ticket_margin_budget=selected.ticket_margin_budget,
        required_leverage=selected.required_leverage,
        selected_leverage=selected.selected_leverage,
        configured_leverage_at_claim=selected.configured_leverage,
        leverage_change_required=selected.leverage_change_required,
        exchange_max_leverage=instrument_rules.exchange_max_leverage,
        reserved_margin=selected.reserved_margin,
        maintenance_margin_bracket_id=selected.maintenance_margin_bracket_id,
        projected_liquidation_price=selected.projected_liquidation_price,
        projected_liquidation_distance=selected.projected_liquidation_distance,
        projected_liquidation_distance_to_stop_distance_ratio=(
            selected.projected_liquidation_distance_to_stop_distance_ratio
        ),
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
        take_profit_prices=(take_profit_price,),
        take_profit_quantities=(selected.tp1_quantity,),
    )
    return CapacityClaimDecision(status=CapacityClaimStatus.CLAIMED, claim=claim)


def _sizing_refusal(status: CapacitySizingStatus) -> CapacityClaimStatus:
    if status in {
        CapacitySizingStatus.COUNT_EXHAUSTED,
        CapacitySizingStatus.MARGIN_EXHAUSTED,
        CapacitySizingStatus.VENUE_MINIMUM_UNMET,
        CapacitySizingStatus.EXIT_PLAN_UNEXECUTABLE,
    }:
        return CapacityClaimStatus.BUDGET_EXHAUSTED
    if status is CapacitySizingStatus.LIQUIDATION_PROOF_FAILED:
        return CapacityClaimStatus.PROTECTION_UNAVAILABLE
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
