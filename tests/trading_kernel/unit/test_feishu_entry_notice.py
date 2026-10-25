from __future__ import annotations

import json
import threading
from unittest.mock import Mock

from src.trading_kernel.domain.events import EntryAccepted
from src.trading_kernel.infrastructure import feishu_entry_notice as module
from tests.trading_kernel.support.tickets import make_ticket


def test_missing_webhook_is_disabled(monkeypatch):
    monkeypatch.delenv("TRADING_KERNEL_FEISHU_WEBHOOK_URL", raising=False)
    start = Mock()
    monkeypatch.setattr(module.threading, "Thread", start)
    t = make_ticket()
    module.notify_entry_accepted(
        t,
        EntryAccepted(
            event_id="notice",
            ticket_id=t.identity.ticket_id,
            sequence=2,
            occurred_at_ms=2000,
            exchange_order_id="order-1",
        ),
    )
    start.assert_not_called()


def test_slow_or_failed_webhook_does_not_block_or_expose_url(monkeypatch, caplog):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/secret-test-token"
    monkeypatch.setenv("TRADING_KERNEL_FEISHU_WEBHOOK_URL", webhook)

    def failing_request(request, *, timeout):
        assert timeout == 2
        payload = json.loads(request.data)
        text = payload["content"]["text"]
        assert payload["msg_type"] == "text"
        assert "开仓订单已被交易所接受" in text and "order-1" in text
        assert "计划初始止损" in text and "已成交" not in text
        started.set()
        release.wait(5)
        raise TimeoutError(webhook)

    monkeypatch.setattr(module.urllib.request, "urlopen", failing_request)
    original = module._send

    def run(*args):
        try:
            original(*args)
        finally:
            finished.set()

    monkeypatch.setattr(module, "_send", run)
    t = make_ticket()
    try:
        module.notify_entry_accepted(
            t,
            EntryAccepted(
                event_id="notice",
                ticket_id=t.identity.ticket_id,
                sequence=2,
                occurred_at_ms=2000,
                exchange_order_id="order-1",
            ),
        )
        assert started.wait(2)
        # The notification entry point returned while the network was blocked.
        assert not finished.is_set()
    finally:
        release.set()
        assert finished.wait(2)
    assert "feishu_entry_notice_failed" in caplog.text
    assert "secret-test-token" not in caplog.text
