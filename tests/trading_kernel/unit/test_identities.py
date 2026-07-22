from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)


def test_netting_domain_key_is_stable_and_separates_position_sides() -> None:
    long_domain = NettingDomain(
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
    )
    same_long_domain = NettingDomain.model_validate(long_domain.model_dump())
    short_domain = long_domain.model_copy(update={"position_side": "short"})

    assert long_domain.key() == same_long_domain.key()
    assert long_domain.key() != short_domain.key()
    assert long_domain.key().endswith(":long")
    assert short_domain.key().endswith(":short")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("venue_id", ""),
        ("account_id", "  "),
        ("exchange_instrument_id", ""),
        ("position_side", "net"),
    ],
)
def test_netting_domain_rejects_blank_or_unsupported_identity(
    field: str,
    value: str,
) -> None:
    payload = {
        "venue_id": "binance-usdm",
        "account_id": "experiment-1",
        "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
        "position_side": "long",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        NettingDomain.model_validate(payload)


def test_ticket_and_runtime_identity_are_frozen_and_exact() -> None:
    runtime = RuntimeIdentity(
        runtime_profile_id="tiny-live-v1",
        strategy_group_id="SOR-001",
        strategy_version_id="SOR-001:v3",
        event_spec_id="sor-long-v2",
    )
    identity = TicketIdentity(
        ticket_id="ticket-1",
        exposure_episode_id="episode-1",
        signal_event_id="signal-1",
        runtime=runtime,
        netting_domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
    )

    with pytest.raises(ValidationError):
        identity.ticket_id = "ticket-2"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        TicketIdentity.model_validate(
            {
                **identity.model_dump(),
                "unexpected": True,
            }
        )
