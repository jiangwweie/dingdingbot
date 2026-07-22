from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

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


def _ticket(**updates: object) -> TradeTicket:
    payload: dict[str, object] = {
        "identity": _identity(),
        "owner_policy_id": "policy-main",
        "owner_policy_version": 7,
        "runtime_scope_id": "scope-sor-btc-long",
        "runtime_scope_version": 4,
        "fact_digest": "sha256:facts-1",
        "created_at_ms": 1_000,
        "expires_at_ms": 31_000,
        "quantity": Decimal("0.001"),
        "notional": Decimal("60"),
        "leverage": Decimal("5"),
        "risk_at_stop": Decimal("3"),
        "entry_order_type": EntryOrderType.MARKET,
        "entry_limit_price": None,
        "initial_stop_price": Decimal("59000"),
        "take_profit_prices": (Decimal("62000"),),
        "status": TicketStatus.ISSUED,
    }
    payload.update(updates)
    return TradeTicket.model_validate(payload)


def test_trade_ticket_is_immutable_and_contains_complete_decision() -> None:
    ticket = _ticket()

    assert ticket.quantity == Decimal("0.001")
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
        ("leverage", Decimal("0")),
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
