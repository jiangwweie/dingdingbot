from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.issue_ticket import IssueTicketRequest
from src.trading_kernel.domain.capacity import freeze_capacity_claim
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    MaintenanceMarginBracket,
    StressPosition,
    evaluate_cross_margin_stress,
)


def make_issue_request(
    *,
    ticket,
    now_ms: int,
    claim_owner: str,
    stress_balance: Decimal | None = None,
    ticket_margin_budget: Decimal = Decimal(30),
) -> IssueTicketRequest:
    configured_leverage = (
        ticket.selected_leverage - 1
        if ticket.leverage_change_required
        else ticket.selected_leverage
    )
    resolved_stress_balance = Decimal(300) if stress_balance is None else stress_balance
    return IssueTicketRequest(
        capacity_claim=freeze_capacity_claim(
            ticket_identity=ticket.identity,
            owner_policy_id=ticket.owner_policy_id,
            owner_policy_version=ticket.owner_policy_version,
            runtime_scope_id=ticket.runtime_scope_id,
            runtime_scope_version=ticket.runtime_scope_version,
            universe_version_id=ticket.universe_version_id,
            universe_semantic_digest=ticket.universe_semantic_digest,
            selection_authority_id=ticket.selection_authority_id,
            fact_digest=ticket.fact_digest,
            exit_policy_id=ticket.exit_policy_id,
            exit_policy_semantic_hash=ticket.exit_policy_semantic_hash,
            entry_admission_snapshot_digest="sha256:" + "2" * 64,
            account_entry_health_digest="sha256:" + "3" * 64,
            instrument_entry_health_digest="sha256:" + "4" * 64,
            instrument_rules_projection_version=1,
            account_capacity_domain_key=(
                f"{ticket.identity.netting_domain.venue_id}:"
                f"{ticket.identity.netting_domain.account_id}"
            ),
            leverage_domain_key=(
                f"{ticket.identity.netting_domain.venue_id}:"
                f"{ticket.identity.netting_domain.account_id}:"
                f"{ticket.identity.netting_domain.exchange_instrument_id}"
            ),
            total_wallet_balance_at_claim=resolved_stress_balance,
            total_margin_balance_at_claim=resolved_stress_balance,
            total_initial_margin_at_claim=Decimal(0),
            total_maintenance_margin_at_claim=Decimal(0),
            available_margin_at_claim=resolved_stress_balance,
            mark_price_at_claim=ticket.entry_reference_price,
            position_mode_at_claim="independent_sides",
            margin_mode_at_claim=ticket.margin_mode,
            active_ticket_count_at_claim=0,
            remaining_slots_at_claim=3,
            exposure_family=ticket.exposure_family,
            active_family_ticket_count_at_claim=0,
            family_ticket_limit=ticket.family_ticket_limit,
            remaining_family_slots_at_claim=ticket.family_ticket_limit,
            gross_risk_at_stop_at_claim=Decimal(0),
            directional_risk_at_stop_at_claim=Decimal(0),
            current_reserved_margin_at_claim=Decimal(0),
            max_ticket_stop_risk_fraction=Decimal("0.02"),
            max_gross_stop_risk_fraction=Decimal("0.06"),
            directional_stop_risk_limit_fraction=Decimal("0.04"),
            max_ticket_initial_margin_fraction=Decimal("0.30"),
            min_materialization_ratio=Decimal("0.50"),
            minimum_stop_risk_budget=Decimal(3),
            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
            max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
            post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
            max_gross_initial_margin_utilization=Decimal("0.90"),
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            ticket_margin_budget=ticket_margin_budget,
            required_leverage=ticket.selected_leverage,
            selected_leverage=ticket.selected_leverage,
            configured_leverage_at_claim=configured_leverage,
            leverage_change_required=ticket.leverage_change_required,
            exchange_max_leverage=10,
            reserved_margin=ticket.reserved_margin,
            cross_margin_stress_evidence=make_stress_evidence(
                ticket,
                stress_balance=resolved_stress_balance,
            ),
            created_at_ms=ticket.created_at_ms,
            expires_at_ms=ticket.expires_at_ms,
            entry_reference_price=ticket.entry_reference_price,
            quantity=ticket.quantity,
            notional=ticket.notional,
            risk_at_stop=ticket.risk_at_stop,
            entry_order_type=ticket.entry_order_type,
            entry_limit_price=ticket.entry_limit_price,
            initial_stop_price=ticket.initial_stop_price,
            pre_tp1_reclaim_price=ticket.pre_tp1_reclaim_price,
            exposure_session_end_ms=ticket.exposure_session_end_ms,
            take_profit_prices=ticket.take_profit_prices,
            take_profit_quantities=ticket.take_profit_quantities,
        ),
        now_ms=now_ms,
        claim_owner=claim_owner,
    )


def make_stress_evidence(ticket, *, stress_balance: Decimal | None = None):
    resolved_stress_balance = (
        max(Decimal(100), ticket.notional * Decimal(10))
        if stress_balance is None
        else stress_balance
    )
    configured_leverage = (
        ticket.selected_leverage - 1
        if ticket.leverage_change_required
        else ticket.selected_leverage
    )
    snapshot = AccountRiskSnapshot.create(
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        account_risk_mode="standard_usdm_single_asset",
        settlement_asset="USDT",
        position_mode="independent_sides",
        margin_mode="cross",
        exchange_instrument_id=(ticket.identity.netting_domain.exchange_instrument_id),
        mark_price=ticket.entry_reference_price,
        configured_leverage=configured_leverage,
        total_wallet_balance=resolved_stress_balance,
        total_margin_balance=resolved_stress_balance,
        total_initial_margin=Decimal(0),
        total_maintenance_margin=Decimal(0),
        available_margin=resolved_stress_balance,
        account_positions=(),
        observed_at_ms=ticket.created_at_ms,
        valid_until_ms=ticket.expires_at_ms,
    )
    bracket = MaintenanceMarginBracket(
        bracket_id="test:1",
        notional_floor=Decimal(0),
        notional_cap=None,
        maintenance_margin_rate=Decimal("0.004"),
        maintenance_amount=Decimal(0),
    )
    return evaluate_cross_margin_stress(
        CrossMarginStressRequest(
            account_snapshot=snapshot,
            maintenance_margin_brackets=(bracket,),
            maintenance_margin_brackets_digest="sha256:" + "5" * 64,
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            evaluated_side=ticket.identity.netting_domain.position_side,
            reference_entry_price=ticket.entry_reference_price,
            initial_stop_price=ticket.initial_stop_price,
            post_stop_stress_multiple=ticket.post_stop_stress_multiple,
            projected_instrument_positions=(
                StressPosition(
                    position_side=ticket.identity.netting_domain.position_side,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                ),
            ),
        )
    )
