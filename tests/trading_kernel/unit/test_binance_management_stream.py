from types import SimpleNamespace
from unittest.mock import Mock

from src.trading_kernel.infrastructure.binance_management_stream import (
    ManagementBinanceUsdm,
)


def exchange():
    x = ManagementBinanceUsdm()
    x.clients = {}
    x.options["future"] = {"listenKey": "not-a-credential"}
    x.management_started_ms = 500
    return x


def test_starting_stream_does_not_prove_connection_coverage():
    x = exchange()
    assert not x.management_covers(start_ms=1000, end_ms=2000)


def test_private_connection_loss_cannot_be_covered_by_reconnect(monkeypatch):
    x = exchange()
    client = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"),
        closed=lambda: False,
        error=None,
    )
    monkeypatch.setattr(x, "milliseconds", lambda: 900)
    x.on_connected(client)
    assert x.management_covers(start_ms=1000, end_ms=2000)
    x.on_error(client, RuntimeError("test"))
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    monkeypatch.setattr(x, "milliseconds", lambda: 1800)
    x.on_connected(client)
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    assert x.management_covers(start_ms=1900, end_ms=2000)


def test_public_socket_cannot_establish_management_coverage():
    x = exchange()
    x.on_connected(SimpleNamespace(url="wss://public.invalid"))
    assert not x.management_covers(start_ms=1000, end_ms=2000)


def test_buffer_loss_and_closed_transport_invalidate_coverage(monkeypatch):
    x = exchange()
    closed = Mock(return_value=False)
    client = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"), closed=closed
    )
    monkeypatch.setattr(x, "milliseconds", lambda: 900)
    x.on_connected(client)
    x.management_lost_before_ms = 1200
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    assert x.management_covers(start_ms=1300, end_ms=2000)
    closed.return_value = True
    assert not x.management_covers(start_ms=1300, end_ms=2000)


def test_buffer_overflow_fences_lost_interval_but_not_later_tickets(monkeypatch):
    from collections import deque

    import ccxt.pro as ccxt_pro

    x = exchange()
    client = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"), closed=lambda: False
    )
    monkeypatch.setattr(x, "milliseconds", lambda: 900)
    monkeypatch.setattr(ccxt_pro.binanceusdm, "handle_order_update", lambda *a: None)
    x.on_connected(client)
    x.management_messages = deque([(1100, {"e": "ORDER_TRADE_UPDATE"})], maxlen=1)
    x.handle_order_update(client, {"e": "ORDER_TRADE_UPDATE"})
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    assert x.management_covers(start_ms=1500, end_ms=2000)


def test_protocol_capture_excludes_transport_secrets_and_preserves_unacked_epoch(
    monkeypatch,
):
    import ccxt.pro as ccxt_pro

    x = exchange()
    client = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"), closed=lambda: False
    )
    monkeypatch.setattr(x, "milliseconds", lambda: 900)
    monkeypatch.setattr(ccxt_pro.binanceusdm, "handle_order_update", lambda *a: None)
    x.on_connected(client)
    epoch = x.management_epoch_id
    x.handle_order_update(
        client,
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1000,
            "T": 1000,
            "listenKey": "never-persist",
            "apiKey": "never-persist",
            "o": {"s": "BNBUSDT", "i": 1, "signature": "never-persist"},
        },
    )
    assert "never-persist" not in str(x.management_pending_events)
    x.on_error(client, RuntimeError("lost"))
    x.on_connected(client)
    assert x.management_epoch_id != epoch
    assert x.management_closed_batches[0]["epoch_id"] == epoch
    assert len(x.management_closed_batches[0]["events"]) == 1


async def test_protocol_restart_replaces_cancelled_watch_without_a_new_order(
    monkeypatch,
):
    import asyncio

    from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter

    x = exchange()
    calls = 0
    first = asyncio.Event()
    second = asyncio.Event()
    pending = asyncio.get_running_loop().create_future()

    class Client:
        url = x.get_private_ws_url("future", "not-a-credential")
        error = None

        def closed(self):
            return False

        async def close(self):
            pending.cancel()

    client = Client()
    x._management_client = client

    async def watch():
        nonlocal calls
        calls += 1
        if calls == 1:
            first.set()
            return await pending
        x.on_connected(Client())
        second.set()
        await asyncio.Future()

    monkeypatch.setattr(x, "watch_orders", watch)
    x.start_management_stream()
    await first.wait()
    old = x.management_epoch_id
    adapter = CcxtVenueAdapter(
        exchanges={("binance-usdm", "a"): x}, clock_ms=lambda: 1000
    )
    try:
        await adapter.restart_management_transport(old)
        try:
            await asyncio.wait_for(second.wait(), timeout=0.2)
        except TimeoutError:
            pass
        assert second.is_set(), (
            "cancelled CCXT order Future must not leave the receiver task dead"
        )
        assert x.management_epoch_id != old
    finally:
        if x._management_task:
            x._management_task.cancel()
            await asyncio.gather(x._management_task, return_exceptions=True)


async def test_restart_is_bounded_when_transport_close_hangs(monkeypatch):
    import asyncio

    import src.trading_kernel.infrastructure.binance_management_stream as stream

    x = exchange()
    first = asyncio.Event()
    second = asyncio.Event()
    calls = 0

    class Client:
        url = x.get_private_ws_url("future", "not-a-credential")
        error = None

        def closed(self):
            return False

        async def close(self):
            await asyncio.Future()

    client = Client()
    x._management_client = client
    x.clients[client.url] = client

    async def watch():
        nonlocal calls
        calls += 1
        if calls == 1:
            first.set()
        else:
            second.set()
        await asyncio.Future()

    monkeypatch.setattr(x, "watch_orders", watch)
    monkeypatch.setattr(stream, "MANAGEMENT_CLOSE_TIMEOUT_SECONDS", 0.01)
    x.start_management_stream()
    await first.wait()
    try:
        x.request_management_restart(x.management_epoch_id)
        await asyncio.wait_for(second.wait(), 0.2)
        assert client.url not in x.clients
        assert x.management_gap and x._management_connected_ms is None
    finally:
        x._management_task.cancel()
        await asyncio.gather(x._management_task, return_exceptions=True)


async def test_completed_receiver_task_is_recreated(monkeypatch):
    import asyncio

    x = exchange()
    started = asyncio.Event()

    async def watch():
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(x, "watch_orders", watch)
    x._management_task = asyncio.create_task(asyncio.sleep(0))
    await x._management_task
    x.start_management_stream()
    try:
        await asyncio.wait_for(started.wait(), 0.2)
    finally:
        x._management_task.cancel()
        await asyncio.gather(x._management_task, return_exceptions=True)


def test_retired_private_transport_cannot_replace_or_remove_the_new_connection(
    monkeypatch,
):
    x = exchange()
    old = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"),
        error=None,
        closed=lambda: False,
        _brc_management_retired=True,
    )
    live = SimpleNamespace(url=old.url, error=None, closed=lambda: False)
    monkeypatch.setattr(x, "milliseconds", lambda: 1000)
    x.on_connected(live)
    x.clients[live.url] = live
    epoch = x.management_epoch_id
    x.on_connected(old)
    x.on_close(old, None)
    assert x._management_client is live and x.management_epoch_id == epoch
    assert x.clients[live.url] is live


def test_repeated_restart_request_for_the_same_epoch_does_not_cancel_reconnect(
    monkeypatch,
):
    x = exchange()
    monkeypatch.setattr(x, "start_management_stream", lambda: None)
    x.request_management_restart(x.management_epoch_id)
    x._management_restart.clear()
    x.request_management_restart(x.management_epoch_id)
    assert not x._management_restart.is_set()


async def test_real_ccxt_watch_future_close_recovers_without_order_messages(
    monkeypatch,
):
    import asyncio
    from unittest.mock import AsyncMock

    from ccxt.async_support.base.ws.client import Client

    x = exchange()
    created = []
    monkeypatch.setattr(x, "open", lambda: None)
    monkeypatch.setattr(x, "load_markets", AsyncMock(return_value={}))
    monkeypatch.setattr(x, "authenticate", AsyncMock())
    monkeypatch.setattr(x, "set_balance_cache", lambda *a: None)
    monkeypatch.setattr(x, "set_positions_cache", lambda *a: None)

    def client(url):
        if url not in x.clients:
            c = Client(url, lambda *a: None, x.on_error, x.on_close, x.on_connected)
            c.connected.resolve(True)
            c.aiohttp_close = AsyncMock()
            x.clients[url] = c
            created.append(c)
            x.on_connected(c)
        return x.clients[url]

    monkeypatch.setattr(x, "client", client)
    original_watch = x.watch_orders
    errors = []

    async def checked_watch():
        try:
            return await original_watch()
        except Exception as exc:
            errors.append((type(exc).__name__, str(exc)))
            raise

    monkeypatch.setattr(x, "watch_orders", checked_watch)
    x.start_management_stream()
    try:
        for _ in range(20):
            if created and "orders" in created[0].futures:
                break
            await asyncio.sleep(0.001)
        assert len(created) == 1 and not created[0].future("orders").done(), errors
        old = x.management_epoch_id
        x.request_management_restart(old)
        for _ in range(100):
            if len(created) == 2 and "orders" in created[1].futures:
                break
            await asyncio.sleep(0.001)
        assert len(created) == 2 and x.management_epoch_id != old
        assert not x._management_task.done()
        assert created[0].future("orders") is not created[1].future("orders")
    finally:
        x._management_task.cancel()
        await asyncio.gather(x._management_task, return_exceptions=True)
        for c in created:
            for future in c.futures.values():
                future.cancel()
        x.clients.clear()


def test_reconnect_backpressure_never_discards_unacknowledged_epochs(monkeypatch):
    from collections import deque

    x = exchange()
    closed = [
        {"epoch_id": f"closed:{i}", "events": deque([{"sequence": 1}])}
        for i in range(8)
    ]
    x.management_closed_batches.extend(closed)
    x.management_pending_events.append(
        {"sequence": 1, "received_at_ms": 1000, "payload": {}}
    )
    epoch = x.management_epoch_id
    client = SimpleNamespace(
        url=x.get_private_ws_url("future", "not-a-credential"), closed=lambda: False
    )
    x.on_connected(client)
    assert list(x.management_closed_batches) == closed
    assert x.management_epoch_id == epoch and len(x.management_pending_events) == 1
    assert (
        x.management_receive_gap == "management_epoch_queue_overflow"
        and x.management_gap
    )
