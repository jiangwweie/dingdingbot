from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.commands import ExchangeCommandKind
from src.trading_kernel.domain.order_attribution import (
    OrderNamespace,
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.infrastructure.binance_order_attribution import (
    resolve_binance_order_identity,
)


class _AlgoExchange:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    async def fapiPrivateGetAlgoOrder(self, params):
        self.calls.append(dict(params))
        return self.response


def _reference(*, namespace: OrderNamespace) -> TicketOrderReference:
    values = {
        "command_id": "command:runner",
        "command_kind": ExchangeCommandKind.INITIAL_STOP,
        "role": OrderRole.EXIT,
        "namespace": namespace,
        "venue_client_order_id": "brc-runner",
        "submitted_exchange_order_id": "4000001795783472",
    }
    if namespace is OrderNamespace.CONDITIONAL:
        values["conditional_expectation"] = {
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "position_side": "long",
            "side": "sell",
            "order_type": "stop_market",
            "quantity": Decimal("0.0005"),
        }
    return TicketOrderReference(**values)


@pytest.mark.asyncio
async def test_regular_order_resolves_without_algo_query() -> None:
    resolved = await resolve_binance_order_identity(
        exchange=object(),
        reference=_reference(namespace=OrderNamespace.REGULAR),
        observed_at_ms=10_000,
    )

    assert resolved.actual_order_id == "4000001795783472"


@pytest.mark.asyncio
async def test_conditional_order_resolves_actual_order_id_from_exact_algo_identity() -> None:
    exchange = _AlgoExchange(
        {
            "algoId": "4000001795783472",
            "clientAlgoId": "brc-runner",
            "actualOrderId": "1085699838084",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "positionSide": "LONG",
            "type": "STOP_MARKET",
            "actualQty": "0.0005",
            "status": "FINISHED",
        }
    )

    resolved = await resolve_binance_order_identity(
        exchange=exchange,
        reference=_reference(namespace=OrderNamespace.CONDITIONAL),
        observed_at_ms=10_000,
    )

    assert exchange.calls == [{"algoId": "4000001795783472"}]
    assert resolved.resolution_status == "executable"
    assert resolved.actual_order_id == "1085699838084"


@pytest.mark.asyncio
async def test_terminal_untriggered_conditional_order_has_no_trade_order_identity() -> None:
    exchange = _AlgoExchange(
        {
            "algoId": "4000001795783472",
            "clientAlgoId": "brc-runner",
            "actualOrderId": "",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "positionSide": "LONG",
            "type": "STOP_MARKET",
            "actualQty": "0",
            "status": "CANCELED",
        }
    )

    resolved = await resolve_binance_order_identity(
        exchange=exchange,
        reference=_reference(namespace=OrderNamespace.CONDITIONAL),
        observed_at_ms=10_000,
    )

    assert resolved.resolution_status == "not_triggered"
    assert resolved.actual_order_id is None


@pytest.mark.asyncio
async def test_conditional_order_rejects_client_algo_identity_contradiction() -> None:
    exchange = _AlgoExchange(
        {
            "algoId": "4000001795783472",
            "clientAlgoId": "wrong-client-id",
            "actualOrderId": "1085699838084",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "positionSide": "LONG",
            "type": "STOP_MARKET",
            "actualQty": "0.0005",
            "status": "FINISHED",
        }
    )

    with pytest.raises(RuntimeError, match="clientAlgoId"):
        await resolve_binance_order_identity(
            exchange=exchange,
            reference=_reference(namespace=OrderNamespace.CONDITIONAL),
            observed_at_ms=10_000,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", "ETHUSDT"),
        ("side", "BUY"),
        ("positionSide", "SHORT"),
        ("type", "TAKE_PROFIT_MARKET"),
        ("actualQty", "0.0004"),
    ],
)
async def test_conditional_order_rejects_frozen_command_payload_contradiction(
    field: str,
    value: str,
) -> None:
    response = {
        "algoId": "4000001795783472",
        "clientAlgoId": "brc-runner",
        "actualOrderId": "1085699838084",
        "symbol": "BTCUSDT",
        "side": "SELL",
        "positionSide": "LONG",
        "type": "STOP_MARKET",
        "actualQty": "0.0005",
        "status": "FINISHED",
    }
    response[field] = value

    with pytest.raises(RuntimeError, match=field):
        await resolve_binance_order_identity(
            exchange=_AlgoExchange(response),
            reference=_reference(namespace=OrderNamespace.CONDITIONAL),
            observed_at_ms=10_000,
        )
