from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from src.trading_kernel.domain.exit_policy import (
    EventExitBinding,
    build_event_exit_binding,
    exit_policy_for,
)
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
    if "exit_policy_id" in updates and "exit_policy_semantic_hash" not in updates:
        payload["exit_policy_semantic_hash"] = "sha256:" + sha256(
            str(payload["exit_policy_id"]).encode()
        ).hexdigest()
    identity = payload["identity"]
    assert isinstance(identity, TicketIdentity)
    if not all(
        name in updates
        for name in (
            "exit_binding_id",
            "exit_binding_semantic_hash",
            "exit_binding_authority_version",
        )
    ):
        binding = fixture_binding_for(
            event_spec_id=identity.runtime.event_spec_id,
            exit_profile_id=str(payload["exit_policy_id"]),
            exit_profile_semantic_hash=str(payload["exit_policy_semantic_hash"]),
        )
        payload.update(
            {
                "exit_binding_id": binding.exit_binding_id,
                "exit_binding_semantic_hash": binding.binding_semantic_hash,
                "exit_binding_authority_version": 1,
            }
        )
    return TradeTicket.model_validate(payload)


def fixture_profile_identity_for_ticket(ticket: TradeTicket) -> tuple[str, str]:
    try:
        policy = exit_policy_for(ticket.identity.runtime.event_spec_id)
    except ValueError:
        return ticket.exit_policy_id, ticket.exit_policy_semantic_hash
    return policy.exit_policy_id, policy.semantic_hash()


def fixture_binding_for_ticket(ticket: TradeTicket) -> EventExitBinding:
    exit_profile_id, exit_profile_semantic_hash = (
        fixture_profile_identity_for_ticket(ticket)
    )
    return fixture_binding_for(
        event_spec_id=ticket.identity.runtime.event_spec_id,
        exit_profile_id=exit_profile_id,
        exit_profile_semantic_hash=exit_profile_semantic_hash,
    )


def fixture_binding_for(
    *,
    event_spec_id: str,
    exit_profile_id: str,
    exit_profile_semantic_hash: str,
) -> EventExitBinding:
    return build_event_exit_binding(
        exit_binding_id=f"exit-binding:{event_spec_id}:test-v1",
        binding_version=1,
        event_spec_id=event_spec_id,
        exit_profile_id=exit_profile_id,
        exit_profile_semantic_hash=exit_profile_semantic_hash,
        activation_reason="test_fixture",
        created_at_ms=1,
    )
