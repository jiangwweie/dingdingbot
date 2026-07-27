from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.exit_policy import exit_policy_for
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


def _identity() -> TicketIdentity:
    runtime = RuntimeIdentity(
        runtime_profile_id="tiny-live-v1",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v2",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
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


def _ticket(**updates: object) -> TradeTicket:
    payload: dict[str, object] = {
        "identity": _identity(),
        "owner_policy_id": "policy-main",
        "owner_policy_version": 7,
        "runtime_scope_id": "scope-sor-btc-long",
        "runtime_scope_version": 4,
        "fact_digest": "sha256:" + "1" * 64,
        "universe_version_id": "universe:event_spec:SOR-001:SOR-LONG:v2:v1",
        "universe_digest": "sha256:" + "2" * 64,
        "projection_run_id": None,
        "armed_structure_id": None,
        "product_policy_version_id": None,
        "session_code": "CRYPTO_CONTINUOUS",
        "session_multiplier": Decimal("1"),
        "product_admission_digest": None,
        "capacity_claim_id": "claim:" + "2" * 32,
        "created_at_ms": 1_000,
        "expires_at_ms": 31_000,
        "entry_reference_price": Decimal("60000"),
        "quantity": Decimal("0.001"),
        "notional": Decimal("60"),
        "planned_stop_risk_budget": Decimal("3"),
        "post_fill_stop_risk_limit": Decimal("3.3"),
        "selected_leverage": 5,
        "leverage_change_required": False,
        "reserved_margin": Decimal("12"),
        "risk_reservation_basis": "planned_stop_distance",
        "margin_mode": "cross",
        "min_liquidation_distance_to_stop_distance_ratio": Decimal("2"),
        "projected_liquidation_price": Decimal("57000"),
        "projected_liquidation_distance_to_stop_distance_ratio": Decimal("2.5"),
        "risk_at_stop": Decimal("3"),
        "entry_order_type": EntryOrderType.MARKET,
        "entry_limit_price": None,
        "initial_stop_price": Decimal("59000"),
        "take_profit_prices": (Decimal("62000"),),
        "take_profit_quantities": (Decimal("0.0005"),),
        "status": TicketStatus.ISSUED,
    }
    payload.update(updates)
    identity = payload["identity"]
    assert isinstance(identity, TicketIdentity)
    exit_policy = exit_policy_for(identity.runtime.event_spec_id)
    payload.update(
        {
            "universe_version_id": (
                f"universe:{identity.runtime.event_spec_id}:v1"
            ),
            "exit_policy_id": exit_policy.exit_policy_id,
            "exit_policy_version": exit_policy.exit_policy_version,
            "exit_policy_digest": exit_policy.semantic_hash(),
            "exit_policy": exit_policy,
        }
    )
    return TradeTicket.model_validate(payload)


def test_trade_ticket_is_immutable_and_contains_complete_decision() -> None:
    ticket = _ticket()

    assert ticket.quantity == Decimal("0.001")
    assert ticket.selected_leverage == 5
    assert ticket.capacity_claim_id.startswith("claim:")
    assert ticket.identity.netting_domain.position_side == "long"
    assert ticket.decision_digest().startswith("sha256:")

    with pytest.raises(ValidationError):
        ticket.quantity = Decimal("0.002")  # type: ignore[misc]


def test_trade_ticket_freezes_policy_and_scope_identity_and_version() -> None:
    ticket = _ticket()

    assert ticket.owner_policy_id == "policy-main"
    assert ticket.owner_policy_version == 7
    assert ticket.runtime_scope_id == "scope-sor-btc-long"
    assert ticket.runtime_scope_version == 4


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Decimal("0")),
        ("notional", Decimal("-1")),
        ("selected_leverage", 0),
        ("reserved_margin", Decimal("0")),
        ("entry_reference_price", Decimal("0")),
        ("risk_at_stop", Decimal("-0.1")),
        ("initial_stop_price", Decimal("0")),
    ],
)
def test_trade_ticket_rejects_invalid_financial_values(
    field: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValidationError):
        _ticket(**{field: value})


def test_trade_ticket_requires_future_expiry() -> None:
    with pytest.raises(ValidationError):
        _ticket(expires_at_ms=1_000)


def test_limit_ticket_requires_limit_price_and_market_ticket_forbids_it() -> None:
    with pytest.raises(ValidationError):
        _ticket(entry_order_type=EntryOrderType.LIMIT, entry_limit_price=None)

    with pytest.raises(ValidationError):
        _ticket(
            entry_order_type=EntryOrderType.MARKET,
            entry_limit_price=Decimal("60000"),
        )


def test_ticket_id_is_deterministic_and_causal() -> None:
    identity = _identity()
    same = build_ticket_id(
        signal_event_id=identity.signal_event_id,
        runtime=identity.runtime,
        netting_domain=identity.netting_domain,
    )
    different_signal = build_ticket_id(
        signal_event_id="signal-2",
        runtime=identity.runtime,
        netting_domain=identity.netting_domain,
    )

    assert identity.ticket_id == same
    assert identity.ticket_id != different_signal
