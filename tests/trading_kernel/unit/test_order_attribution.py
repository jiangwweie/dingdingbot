from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    ValuedFee,
)
from src.trading_kernel.domain.order_attribution import (
    AttributedTradeFill,
    OrderNamespace,
    OrderRole,
    ResolvedOrderIdentity,
    TicketOrderReference,
    attribution_digest,
)


def _reference(*, namespace: OrderNamespace = OrderNamespace.REGULAR) -> TicketOrderReference:
    values = {
        "command_id": "command:entry",
        "command_kind": ExchangeCommandKind.ENTRY,
        "role": OrderRole.ENTRY,
        "namespace": namespace,
        "venue_client_order_id": "brc-entry",
        "submitted_exchange_order_id": "12345",
    }
    if namespace is OrderNamespace.CONDITIONAL:
        values["conditional_expectation"] = {
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "position_side": "long",
            "side": "sell",
            "order_type": "stop_market",
            "quantity": Decimal("0.01"),
        }
    return TicketOrderReference(**values)


def _fee() -> ValuedFee:
    return ValuedFee(
        native=NativeFee(asset="USDT", amount=Decimal("0.10")),
        usdt_value=Decimal("0.10"),
        evidence=FeeValuationEvidence(
            method="native_usdt",
            rate_usdt_per_asset=Decimal("1"),
            price_pair=None,
            observed_at_ms=None,
            valued_at_ms=1_000,
        ),
    )


def test_regular_order_requires_its_submitted_order_id_as_actual_order_id() -> None:
    resolved = ResolvedOrderIdentity(
        reference=_reference(),
        resolution_status="executable",
        actual_order_id="12345",
        resolved_at_ms=1_000,
    )

    assert resolved.actual_order_id == "12345"

    with pytest.raises(ValidationError, match="regular order identity"):
        ResolvedOrderIdentity(
            reference=_reference(),
            resolution_status="executable",
            actual_order_id="other-order",
            resolved_at_ms=1_000,
        )


def test_conditional_not_triggered_order_has_no_actual_order_id() -> None:
    resolved = ResolvedOrderIdentity(
        reference=_reference(namespace=OrderNamespace.CONDITIONAL),
        resolution_status="not_triggered",
        actual_order_id=None,
        resolved_at_ms=1_000,
    )

    assert resolved.actual_order_id is None

    with pytest.raises(ValidationError, match="not-triggered"):
        ResolvedOrderIdentity(
            reference=_reference(namespace=OrderNamespace.CONDITIONAL),
            resolution_status="not_triggered",
            actual_order_id="12345",
            resolved_at_ms=1_000,
        )


def test_attributed_fill_uses_exact_actual_order_identity_and_valued_fee() -> None:
    resolved = ResolvedOrderIdentity(
        reference=_reference(),
        resolution_status="executable",
        actual_order_id="12345",
        resolved_at_ms=1_000,
    )

    fill = AttributedTradeFill(
        exchange_trade_id="trade-1",
        exchange_order_id="12345",
        command_id="command:entry",
        role=OrderRole.ENTRY,
        quantity=Decimal("0.1"),
        price=Decimal("60000"),
        fee=_fee(),
        realized_pnl_quote=Decimal("0"),
        occurred_at_ms=1_001,
    )

    assert fill.exchange_order_id == resolved.actual_order_id
    assert fill.fee.usdt_value == Decimal("0.10")


def test_attribution_digest_is_stable_for_fill_order_and_changes_for_content() -> None:
    first = AttributedTradeFill(
        exchange_trade_id="trade-1",
        exchange_order_id="12345",
        command_id="command:entry",
        role=OrderRole.ENTRY,
        quantity=Decimal("0.1"),
        price=Decimal("60000"),
        fee=_fee(),
        realized_pnl_quote=Decimal("0"),
        occurred_at_ms=1_001,
    )
    second = first.model_copy(update={"exchange_trade_id": "trade-2"})

    assert attribution_digest((second, first)) == attribution_digest((first, second))
    assert attribution_digest((first,)) != attribution_digest((second,))
