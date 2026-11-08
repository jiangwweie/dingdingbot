from types import SimpleNamespace
from unittest.mock import Mock

from src.trading_kernel.infrastructure.binance_management_stream import (
    ManagementBinanceUsdm,
)


def exchange():
    x = ManagementBinanceUsdm()
    x.options['future'] = {'listenKey': 'not-a-credential'}
    x.management_started_ms = 500
    return x


def test_starting_stream_does_not_prove_connection_coverage():
    x = exchange()
    assert not x.management_covers(start_ms=1000, end_ms=2000)


def test_private_connection_loss_cannot_be_covered_by_reconnect(monkeypatch):
    x = exchange()
    client = SimpleNamespace(url=x.get_private_ws_url('future', 'not-a-credential'),
        closed=lambda: False, error=None)
    monkeypatch.setattr(x, 'milliseconds', lambda: 900)
    x.on_connected(client)
    assert x.management_covers(start_ms=1000, end_ms=2000)
    x.on_error(client, RuntimeError('test'))
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    monkeypatch.setattr(x, 'milliseconds', lambda: 1800)
    x.on_connected(client)
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    assert x.management_covers(start_ms=1900, end_ms=2000)


def test_public_socket_cannot_establish_management_coverage():
    x = exchange()
    x.on_connected(SimpleNamespace(url='wss://public.invalid'))
    assert not x.management_covers(start_ms=1000, end_ms=2000)


def test_buffer_loss_and_closed_transport_invalidate_coverage(monkeypatch):
    x = exchange()
    closed = Mock(return_value=False)
    client = SimpleNamespace(url=x.get_private_ws_url('future', 'not-a-credential'), closed=closed)
    monkeypatch.setattr(x, 'milliseconds', lambda: 900)
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
    client = SimpleNamespace(url=x.get_private_ws_url('future', 'not-a-credential'), closed=lambda: False)
    monkeypatch.setattr(x, 'milliseconds', lambda: 900)
    monkeypatch.setattr(ccxt_pro.binanceusdm, 'handle_order_update', lambda *a: None)
    x.on_connected(client)
    x.management_messages = deque([(1100, {'e': 'ORDER_TRADE_UPDATE'})], maxlen=1)
    x.handle_order_update(client, {'e': 'ORDER_TRADE_UPDATE'})
    assert not x.management_covers(start_ms=1000, end_ms=2000)
    assert x.management_covers(start_ms=1500, end_ms=2000)
