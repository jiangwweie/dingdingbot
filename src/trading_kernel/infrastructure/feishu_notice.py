"""Optional, best-effort Owner notice; never awaited by the trading chain."""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.request
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src.trading_kernel.domain.events import (
    EntryAccepted,
    ExternalFlatDetected,
    PositionFlatConfirmed,
    TakeProfitFilled,
)
from src.trading_kernel.domain.instrument_identity import (
    BinanceUsdmInstrumentIdentity,
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.ticket import TradeTicket

_LOGGER = logging.getLogger(__name__)


def notify_entry_accepted(ticket: TradeTicket, event: EntryAccepted) -> None:
    _schedule(
        lambda: _text(
            ticket,
            event,
            title="🟢 BRC｜开仓已接单",
            details=(
                f"委托类型：{ticket.entry_order_type.value}",
                f"委托数量：{ticket.quantity:,f} {_instrument(ticket).base_asset}",
                f"计划初始止损：{ticket.initial_stop_price:,f} USDT",
                f"交易所订单：{event.exchange_order_id}",
            ),
        )
    )


def notify_tp1_filled(
    ticket: TradeTicket, event: TakeProfitFilled, *, remaining_qty: Decimal
) -> None:
    _schedule(
        lambda: _text(
            ticket,
            event,
            title="🎯 BRC｜TP1 已成交",
            details=(
                f"成交数量：{event.filled_qty:,f} {_instrument(ticket).base_asset}",
                f"成交均价：{event.average_fill_price:,f} USDT",
                f"剩余仓位：{remaining_qty:,f} {_instrument(ticket).base_asset}",
            ),
        )
    )


def notify_runner_exited(
    ticket: TradeTicket,
    event: PositionFlatConfirmed | ExternalFlatDetected,
    *,
    previous_qty: Decimal,
) -> None:
    _schedule(
        lambda: _text(
            ticket,
            event,
            title="🏁 BRC｜Runner 已退出，成交明细待确认",
            details=(
                f"退出前仓位：{previous_qty:,f} {_instrument(ticket).base_asset}",
                "剩余仓位：0",
            ),
        )
    )


def _instrument(ticket: TradeTicket) -> BinanceUsdmInstrumentIdentity:
    return parse_binance_usdm_instrument_id(
        ticket.identity.netting_domain.exchange_instrument_id
    )


def _text(
    ticket: TradeTicket,
    event: EntryAccepted
    | TakeProfitFilled
    | PositionFlatConfirmed
    | ExternalFlatDetected,
    *,
    title: str,
    details: tuple[str, ...],
) -> str:
    side = "做多" if ticket.identity.netting_domain.position_side == "long" else "做空"
    timestamp = datetime.fromtimestamp(
        event.occurred_at_ms / 1000, ZoneInfo("Asia/Shanghai")
    )
    return "\n".join(
        (
            title,
            "",
            f"策略：{ticket.identity.runtime.strategy_group_id}",
            f"标的：{_instrument(ticket).symbol} · {side}",
            *details,
            "",
            f"时间：{timestamp:%Y-%m-%d %H:%M:%S}（北京时间）",
            f"Ticket：{ticket.identity.ticket_id}",
        )
    )


def _schedule(build_text: Callable[[], str]) -> None:
    """Called only after commit. Missing configuration or any failure is harmless."""
    try:
        webhook = os.environ.get("TRADING_KERNEL_FEISHU_WEBHOOK_URL", "").strip()
        if not webhook:
            return
        target = urlsplit(webhook)
        if target.scheme != "https" or target.hostname != "open.feishu.cn":
            raise ValueError("invalid_feishu_webhook")
        body = json.dumps(
            {"msg_type": "text", "content": {"text": build_text()}}, ensure_ascii=False
        ).encode()
        threading.Thread(
            target=_send, args=(webhook, body), daemon=True, name="feishu-notice"
        ).start()
    except Exception:  # noqa: BLE001 - this optional display must not affect trading.
        _LOGGER.warning("feishu_notice_failed")


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
        _LOGGER.warning("feishu_notice_failed")
