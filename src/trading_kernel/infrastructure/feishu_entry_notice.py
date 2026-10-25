"""Optional, best-effort Owner notice; never awaited by the trading chain."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.events import EntryAccepted
from src.trading_kernel.domain.ticket import TradeTicket

_LOGGER = logging.getLogger(__name__)


def notify_entry_accepted(ticket: TradeTicket, event: EntryAccepted) -> None:
    """Called only after commit. Missing configuration or any failure is harmless."""
    try:
        webhook = os.environ.get("TRADING_KERNEL_FEISHU_WEBHOOK_URL", "").strip()
        if not webhook:
            return
        target = urlsplit(webhook)
        if target.scheme != "https" or target.hostname != "open.feishu.cn":
            raise ValueError("invalid_feishu_webhook")
        identity = ticket.identity
        domain = identity.netting_domain
        timestamp = datetime.fromtimestamp(
            event.occurred_at_ms / 1000, ZoneInfo("Asia/Shanghai")
        )
        text = "\n".join(
            (
                "BRC｜开仓订单已被交易所接受",
                f"策略：{identity.runtime.strategy_group_id}",
                f"标的：{domain.exchange_instrument_id}",
                f"方向：{'做多' if domain.position_side == 'long' else '做空'}",
                f"委托类型：{ticket.entry_order_type.value}；数量：{ticket.quantity}",
                f"计划初始止损：{ticket.initial_stop_price}",
                f"接单确认时间：{timestamp:%Y-%m-%d %H:%M:%S}（北京时间）",
                f"Ticket：{identity.ticket_id}",
                f"交易所订单：{event.exchange_order_id}",
            )
        )
        body = json.dumps(
            {"msg_type": "text", "content": {"text": text}}, ensure_ascii=False
        ).encode()
        threading.Thread(
            target=_send, args=(webhook, body), daemon=True, name="feishu-entry-notice"
        ).start()
    except Exception:  # noqa: BLE001 - this optional display must not affect trading.
        _LOGGER.warning("feishu_entry_notice_failed")


def _send(webhook: str, body: bytes) -> None:
    try:
        request = urllib.request.Request(
            webhook,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read(65_536))
            if result.get("code", result.get("StatusCode")) != 0:
                raise ValueError("feishu_rejected_notice")
    except Exception:  # noqa: BLE001 - no retry and no sensitive exception output.
        _LOGGER.warning("feishu_entry_notice_failed")
