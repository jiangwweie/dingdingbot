from __future__ import annotations

import json
import threading
from decimal import Decimal
from unittest.mock import Mock

from src.trading_kernel.domain.events import (
    EntryAccepted,
    ExternalFlatDetected,
    TakeProfitFilled,
)
from src.trading_kernel.infrastructure import feishu_notice as module
from tests.trading_kernel.support.tickets import make_ticket


def test_tp1_and_runner_notice_text_only_reports_confirmed_facts(monkeypatch):
    monkeypatch.setenv(
        "TRADING_KERNEL_FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/test-token",
    )
    thread = Mock()
    monkeypatch.setattr(module.threading, "Thread", thread)
    ticket = make_ticket()
    common = {
        "event_id": "notice",
        "ticket_id": ticket.identity.ticket_id,
        "sequence": 6,
        "occurred_at_ms": 2000,
    }
    module.notify_tp1_filled(
        ticket,
        TakeProfitFilled(
            **common,
            filled_qty=Decimal("0.0005"),
            average_fill_price=Decimal(62000),
            runner_floor_price=Decimal("60080.3"),
        ),
        remaining_qty=Decimal("0.0005"),
    )
    payload = json.loads(thread.call_args.kwargs["args"][1])
    text = payload["content"]["text"]
    assert payload["msg_type"] == "text"
    assert "🎯 BRC｜TP1 已成交" in text
    assert "BTCUSDT · 做多" in text
    assert "成交数量：0.0005 BTC" in text
    assert "成交均价：62,000 USDT" in text
    assert "剩余仓位：0.0005 BTC" in text
    assert "1970-01-01 08:00:02（北京时间）" in text
    assert ticket.identity.ticket_id in text
    assert "60080.3" not in text  # Planned runner protection is not a fill.
    assert thread.call_args.kwargs["daemon"] is True
    thread.return_value.start.assert_called_once()

    module.notify_runner_exited(
        ticket,
        ExternalFlatDetected(**common),
        previous_qty=Decimal("0.0005"),
    )
    text = json.loads(thread.call_args.kwargs["args"][1])["content"]["text"]
    assert "🏁 BRC｜Runner 已退出，成交明细待确认" in text
    assert "退出前仓位：0.0005 BTC" in text
    assert "剩余仓位：0" in text
    assert "成交数量" not in text
    assert "成交均价" not in text
    assert "退出原因" not in text


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
        assert "🟢 BRC｜开仓已接单" in text and "order-1" in text
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
    assert "feishu_notice_failed" in caplog.text
    assert "secret-test-token" not in caplog.text
