from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)
from src.trading_kernel.domain.ticket import (
    EntryOrderType,
    TicketStatus,
    TradeTicket,
    build_ticket_id,
)


def make_ticket_identity() -> TicketIdentity:
    runtime = RuntimeIdentity(
        runtime_profile_id="tiny-live-v1",
        strategy_group_id="SOR-001",
        strategy_version_id="SOR-001:v3",
        event_spec_id="sor-long-v2",
    )
    domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
    )
    return TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id="signal-1",
            runtime=runtime,
            netting_domain=domain,
        ),
        exposure_episode_id="episode-1",
        signal_event_id="signal-1",
        runtime=runtime,
        netting_domain=domain,
    )


def make_ticket(**updates: object) -> TradeTicket:
    payload: dict[str, object] = {
        "identity": make_ticket_identity(),
        "owner_policy_id": "policy-main",
        "owner_policy_version": 7,
        "runtime_scope_id": "scope-sor-btc-long",
        "runtime_scope_version": 4,
        "universe_version_id": "universe:sor-long:4",
        "universe_semantic_digest": "sha256:" + "a" * 64,
        "fact_digest": "sha256:" + "1" * 64,
        "exposure_family": "opening_range",
        "active_family_ticket_count_at_claim": 0,
        "family_ticket_limit": 2,
        "directional_risk_at_stop_at_claim": Decimal(0),
        "directional_stop_risk_limit_fraction": Decimal("0.04"),
        "min_materialization_ratio": Decimal("0.50"),
        "minimum_stop_risk_budget": Decimal("1.5"),
        "exit_policy_id": "exit-policy:SOR-001:SOR-LONG:sor-v3-right-tail-v1",
        "exit_policy_semantic_hash": "sha256:" + "4" * 64,
        "capacity_claim_id": "claim:" + "2" * 32,
        "created_at_ms": 1_000,
        "expires_at_ms": 31_000,
        "entry_reference_price": Decimal(60000),
        "quantity": Decimal("0.001"),
        "notional": Decimal(60),
        "planned_stop_risk_budget": Decimal(3),
        "post_fill_stop_risk_limit": Decimal("3.3"),
        "selected_leverage": 5,
        "leverage_change_required": False,
        "reserved_margin": Decimal(12),
        "risk_reservation_basis": "planned_stop_distance",
        "margin_mode": "cross",
        "cross_margin_stress_model_id": "cross-margin-stop-stress-v1",
        "post_stop_stress_multiple": Decimal(2),
        "claim_stress_proof_digest": "sha256:" + "3" * 64,
        "risk_at_stop": Decimal(3),
        "entry_order_type": EntryOrderType.MARKET,
        "entry_limit_price": None,
        "initial_stop_price": Decimal(59000),
        "pre_tp1_reclaim_price": Decimal(60100),
        "exposure_session_end_ms": 86_400_000,
        "take_profit_prices": (Decimal(62000),),
        "take_profit_quantities": (Decimal("0.0005"),),
        "status": TicketStatus.ISSUED,
    }
    payload.update(updates)
    return TradeTicket.model_validate(payload)
