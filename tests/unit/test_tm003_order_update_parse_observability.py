from __future__ import annotations

import types
from decimal import Decimal

import pytest

from src.domain.models import OrderStatus
from src.infrastructure.exchange_gateway import ExchangeGateway


class _FakeOrderWsExchange:
    def __init__(self, gateway: ExchangeGateway, batches):
        self._gateway = gateway
        self._batches = list(batches)
        self.closed = False

    async def load_markets(self):
        return None

    async def watch_orders(self, symbol: str):
        if self._batches:
            batch = self._batches.pop(0)
            if not self._batches:
                self._gateway._order_ws_running = False
            return batch
        self._gateway._order_ws_running = False
        return []

    async def close(self):
        self.closed = True


class _AsyncRecorder:
    def __init__(self) -> None:
        self.calls = []

    async def __call__(self, value):
        self.calls.append(value)


def _valid_raw_order(order_id: str = "valid-order"):
    return {
        "id": order_id,
        "clientOrderId": "sig-tm003",
        "symbol": "ETH/USDT:USDT",
        "status": "closed",
        "type": "limit",
        "side": "sell",
        "amount": "1",
        "filled": "1",
        "remaining": "0",
        "price": "110",
        "average": "110",
        "timestamp": 1,
        "reduceOnly": True,
    }


def _invalid_raw_order(order_id: str = "bad-order"):
    return {
        "id": order_id,
        "symbol": "ETH/USDT:USDT",
        "status": "closed",
        "type": "limit",
        "side": "sell",
        "amount": {"not": "decimal"},
    }


@pytest.mark.asyncio
async def test_handle_order_update_parse_exception_is_observable_noop(caplog):
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)

    result = await gateway._handle_order_update(_invalid_raw_order())

    assert result is None
    assert "处理订单更新失败" in caplog.text
    assert "bad-order" in caplog.text


@pytest.mark.asyncio
async def test_watch_orders_parse_exception_does_not_exit_loop(monkeypatch, caplog):
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    monkeypatch.setattr(
        "src.infrastructure.exchange_gateway.ccxtpro",
        types.SimpleNamespace(binance=object()),
    )

    fake_ws = _FakeOrderWsExchange(
        gateway,
        [[_invalid_raw_order(), _valid_raw_order()]],
    )
    monkeypatch.setattr(gateway, "_create_ws_exchange", lambda options: fake_ws)

    callback = _AsyncRecorder()

    await gateway.watch_orders("ETH/USDT:USDT", callback)

    assert "处理订单更新失败" in caplog.text
    assert "bad-order" in caplog.text
    assert len(callback.calls) == 1
    assert callback.calls[0].exchange_order_id == "valid-order"
    assert callback.calls[0].status == OrderStatus.FILLED
    assert fake_ws.closed is True
