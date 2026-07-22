from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.signal import (
    ActionableSignal,
    SignalFactSnapshot,
    SignalTicketTerms,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.ticket import EntryOrderType


def test_actionable_signal_is_immutable_and_rejects_invalid_ticket_terms() -> None:
    signal = _signal()

    with pytest.raises(ValidationError):
        signal.signal_event_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _signal(quantity=Decimal("0"))
    with pytest.raises(ValidationError):
        _signal(initial_stop_price=Decimal("-1"))
    with pytest.raises(ValidationError):
        _signal(risk_at_stop=Decimal("-0.01"))


def test_actionable_signal_rejects_blank_identity_and_invalid_deadline() -> None:
    with pytest.raises(ValidationError):
        _signal(signal_event_id=" ")
    with pytest.raises(ValidationError):
        _signal(runtime_scope_version=0)
    with pytest.raises(ValidationError):
        _signal(occurred_at_ms=1_000, expires_at_ms=1_000)


def test_signal_ticket_terms_enforce_market_and_limit_order_shape() -> None:
    with pytest.raises(ValidationError):
        _signal(entry_order_type=EntryOrderType.MARKET, entry_limit_price=Decimal("1"))
    with pytest.raises(ValidationError):
        _signal(entry_order_type=EntryOrderType.LIMIT, entry_limit_price=None)


def test_fact_digest_is_canonical_and_signal_requires_exact_sha256_identity() -> None:
    facts = (
        SignalFactSnapshot(
            fact_definition_id="fact-2",
            value={"b": 2, "a": 1},
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=3,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact-1",
            value="ready",
            satisfied=True,
            observed_at_ms=1_001,
            valid_until_ms=2_001,
            projection_version=4,
        ),
    )

    digest = build_signal_fact_digest(facts)

    assert digest == build_signal_fact_digest(tuple(reversed(facts)))
    assert digest.startswith("sha256:")
    assert len(digest) == 71
    with pytest.raises(ValidationError):
        _signal(fact_digest="sha256:not-a-real-digest")


def _signal(
    *,
    signal_event_id: str = "signal-1",
    runtime_scope_version: int = 1,
    occurred_at_ms: int = 1_000,
    expires_at_ms: int = 2_000,
    quantity: Decimal = Decimal("0.01"),
    risk_at_stop: Decimal = Decimal("2.5"),
    entry_order_type: EntryOrderType = EntryOrderType.MARKET,
    entry_limit_price: Decimal | None = None,
    initial_stop_price: Decimal = Decimal("99"),
    fact_digest: str | None = None,
) -> ActionableSignal:
    return ActionableSignal(
        signal_event_id=signal_event_id,
        runtime_scope_id="scope-1",
        runtime_scope_version=runtime_scope_version,
        strategy_group_id="SOR-001",
        strategy_version_id="SOR-001:v3",
        event_spec_id="SOR-LONG:v3",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        fact_digest=fact_digest or build_signal_fact_digest(()),
        occurred_at_ms=occurred_at_ms,
        expires_at_ms=expires_at_ms,
        terms=SignalTicketTerms(
            quantity=quantity,
            notional=Decimal("100"),
            leverage=Decimal("5"),
            risk_at_stop=risk_at_stop,
            entry_order_type=entry_order_type,
            entry_limit_price=entry_limit_price,
            initial_stop_price=initial_stop_price,
            take_profit_prices=(Decimal("105"),),
        ),
    )
