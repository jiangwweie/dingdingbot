from __future__ import annotations

import asyncio
import types
from decimal import Decimal

import pytest

from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.infrastructure.exchange_gateway import ExchangeGateway
from src import main


def _build_order(exchange_order_id: str = "ex-1") -> Order:
    return Order(
        id=exchange_order_id,
        signal_id="sig-1",
        exchange_order_id=exchange_order_id,
        symbol="ETH/USDT:USDT",
        direction=Direction.LONG,
        order_type=OrderType.MARKET,
        order_role=OrderRole.ENTRY,
        requested_qty=Decimal("1"),
        filled_qty=Decimal("1"),
        average_exec_price=Decimal("100"),
        status=OrderStatus.FILLED,
        created_at=1,
        updated_at=1,
    )


class _AsyncRecorder:
    def __init__(self, *, should_raise: bool = False):
        self.calls = []
        self.should_raise = should_raise

    async def __call__(self, value):
        self.calls.append(value)
        if self.should_raise:
            raise RuntimeError("callback boom")


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


@pytest.mark.asyncio
async def test_start_order_watch_tasks_dedupes_symbols_and_starts_tasks(monkeypatch):
    seen = []

    async def fake_run(symbol: str):
        seen.append(symbol)

    monkeypatch.setattr(main, "_run_order_watch", fake_run)

    tasks = main._start_order_watch_tasks(
        ["ETH/USDT:USDT", "ETH/USDT:USDT", "BTC/USDT:USDT"]
    )
    await asyncio.sleep(0)
    await asyncio.gather(*tasks)

    assert len(tasks) == 2
    assert seen == ["ETH/USDT:USDT", "BTC/USDT:USDT"]


@pytest.mark.asyncio
async def test_run_order_watch_failure_does_not_raise(monkeypatch):
    class _FailingGateway:
        async def watch_orders(self, symbol, callback):
            raise RuntimeError("ws failed")

    monkeypatch.setattr(main, "_exchange_gateway", _FailingGateway())

    await main._run_order_watch("ETH/USDT:USDT")


@pytest.mark.asyncio
async def test_cancel_order_watch_tasks_cancels_pending_tasks():
    gate = asyncio.Event()

    async def sleeper():
        await gate.wait()

    tasks = [asyncio.create_task(sleeper()) for _ in range(2)]
    await main._cancel_order_watch_tasks(tasks)

    assert all(task.done() for task in tasks)


@pytest.mark.asyncio
async def test_watch_orders_forwards_global_callback(monkeypatch):
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    monkeypatch.setattr(
        "src.infrastructure.exchange_gateway.ccxtpro",
        types.SimpleNamespace(binance=object()),
    )

    fake_ws = _FakeOrderWsExchange(gateway, [[{"id": "first"}]])
    monkeypatch.setattr(gateway, "_create_ws_exchange", lambda options: fake_ws)
    monkeypatch.setattr(
        gateway,
        "_handle_order_update",
        lambda raw_order: asyncio.sleep(0, result=_build_order("ex-1")),
    )

    global_callback = _AsyncRecorder()
    explicit_callback = _AsyncRecorder()
    gateway.set_global_order_callback(global_callback)

    sentinel_ws = object()
    gateway.ws_exchange = sentinel_ws
    gateway._ws_running = True

    await gateway.watch_orders("ETH/USDT:USDT", explicit_callback)

    assert len(global_callback.calls) == 1
    assert len(explicit_callback.calls) == 1
    assert gateway.ws_exchange is sentinel_ws
    assert gateway._ws_running is True
    assert gateway._order_watch_exchanges == []
    assert fake_ws.closed is True


@pytest.mark.asyncio
async def test_watch_orders_callback_exception_does_not_kill_loop(monkeypatch):
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    monkeypatch.setattr(
        "src.infrastructure.exchange_gateway.ccxtpro",
        types.SimpleNamespace(binance=object()),
    )

    fake_ws = _FakeOrderWsExchange(gateway, [[{"id": "first"}]])
    monkeypatch.setattr(gateway, "_create_ws_exchange", lambda options: fake_ws)
    monkeypatch.setattr(
        gateway,
        "_handle_order_update",
        lambda raw_order: asyncio.sleep(0, result=_build_order("ex-2")),
    )

    global_callback = _AsyncRecorder()
    explicit_callback = _AsyncRecorder(should_raise=True)
    gateway.set_global_order_callback(global_callback)

    await gateway.watch_orders("ETH/USDT:USDT", explicit_callback)

    assert len(global_callback.calls) == 1
    assert len(explicit_callback.calls) == 1
    assert "ex-2" in gateway.get_pending_recovery_orders()


@pytest.mark.asyncio
async def test_watch_orders_ignores_duplicate_updates(monkeypatch):
    gateway = ExchangeGateway("binance", "key", "secret", testnet=True)
    monkeypatch.setattr(
        "src.infrastructure.exchange_gateway.ccxtpro",
        types.SimpleNamespace(binance=object()),
    )

    fake_ws = _FakeOrderWsExchange(gateway, [[{"id": "first"}, {"id": "duplicate"}]])
    monkeypatch.setattr(gateway, "_create_ws_exchange", lambda options: fake_ws)

    first_order = _build_order("ex-3")
    results = iter([first_order, None])

    async def fake_handle(raw_order):
        return next(results)

    monkeypatch.setattr(gateway, "_handle_order_update", fake_handle)

    global_callback = _AsyncRecorder()
    explicit_callback = _AsyncRecorder()
    gateway.set_global_order_callback(global_callback)

    await gateway.watch_orders("ETH/USDT:USDT", explicit_callback)

    assert len(global_callback.calls) == 1
    assert len(explicit_callback.calls) == 1
