"""Raw account order events retained before CCXT's current-order cache merges them."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from copy import deepcopy
from uuid import uuid4

import ccxt.pro as ccxt_pro  # type: ignore[import-untyped]

_ORDER_FIELDS = frozenset(
    [
        "s",
        "c",
        "S",
        "o",
        "f",
        "q",
        "p",
        "sp",
        "x",
        "X",
        "i",
        "z",
        "ps",
        "cp",
        "R",
        "wt",
        "pP",
        "AP",
        "cr",
        "pm",
        "V",
        "gtd",
        "O",
        "aid",
        "caid",
        "tp",
        "ia",
        "aq",
        "actualOrderId",
    ]
)


def safe_order_message(message):
    """Persist only order protocol fields; credentials and transport URLs are excluded."""
    safe = {
        k: deepcopy(message[k])
        for k in ("e", "E", "T")
        if k in message and isinstance(message[k], (str, int, bool, type(None)))
    }
    order = message.get("o")
    safe["o"] = (
        {
            k: deepcopy(v)
            for k, v in order.items()
            if k in _ORDER_FIELDS and isinstance(v, (str, int, bool, type(None)))
        }
        if isinstance(order, dict)
        else {}
    )
    return safe


class ManagementBinanceUsdm(ccxt_pro.binanceusdm):
    def __init__(self, config=None):
        super().__init__(config or {})
        self.management_messages = deque(maxlen=2048)
        self.management_started_ms = None
        self.management_gap = True
        self.management_lost_before_ms = None
        self._management_task = None
        self._management_client = None
        self._management_connected_ms = None
        self.management_epoch_id = "management-epoch:" + uuid4().hex
        self.management_receive_sequence = 0
        self.management_pending_events = deque(maxlen=4096)
        self.management_receive_gap = None
        self.management_closed_batches = deque(maxlen=8)

    async def fetch(self, url, method="GET", headers=None, body=None):
        from src.trading_kernel.infrastructure.mutation_send_guard import (
            current_mutation_guard,
        )

        guard = current_mutation_guard.get()
        if method.upper() in {"POST", "PUT", "DELETE"} and guard is not None:
            from src.trading_kernel.application.ports import VenueMutationFailure

            if guard.attempted:
                raise VenueMutationFailure("transport_retry_forbidden_after_send")
            await guard.before_send()
            guard.attempted = True
        return await super().fetch(url, method, headers, body)

    def _is_management_client(self, client):
        key = self.options.get("future", {}).get("listenKey")
        return bool(key and client.url == self.get_private_ws_url("future", key))

    def on_connected(self, client, message=None):
        if self._is_management_client(client):
            if self.management_pending_events:
                self.management_closed_batches.append(
                    {
                        "epoch_id": self.management_epoch_id,
                        "events": self.management_pending_events,
                        "connected_at_ms": None,
                        "gap_reason": self.management_receive_gap
                        or "private_stream_epoch_replaced",
                    }
                )
            self.management_pending_events = deque(maxlen=4096)
            self.management_epoch_id = "management-epoch:" + uuid4().hex
            self.management_receive_sequence = 0
            self.management_pending_events.clear()
            self.management_receive_gap = None
            self._management_client = client
            self._management_connected_ms = self.milliseconds()
            self.management_gap = False
        return super().on_connected(client, message)

    def _lose_management_connection(self, client):
        if client is self._management_client:
            self.management_gap = True
            self.management_receive_gap = "private_stream_disconnected"
            self._management_connected_ms = None

    def on_error(self, client, error):
        self._lose_management_connection(client)
        return super().on_error(client, error)

    def on_close(self, client, error):
        self._lose_management_connection(client)
        return super().on_close(client, error)

    def management_covers(self, *, start_ms, end_ms):
        client = self._management_client
        return bool(
            client is not None
            and not client.closed()
            and not self.management_gap
            and self._management_connected_ms is not None
            and self._management_connected_ms <= start_ms <= end_ms
            and (
                self.management_lost_before_ms is None
                or self.management_lost_before_ms < start_ms
            )
        )

    def handle_order_update(self, client, message):
        if message.get("e") in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE"):
            self.management_receive_sequence += 1
            if (
                len(self.management_pending_events)
                == self.management_pending_events.maxlen
            ):
                self.management_receive_gap = "management_receive_queue_overflow"
            self.management_pending_events.append(
                {
                    "sequence": self.management_receive_sequence,
                    "received_at_ms": int(time.time() * 1000),
                    "payload": safe_order_message(message),
                }
            )
            if len(self.management_messages) == self.management_messages.maxlen:
                self.management_lost_before_ms = self.management_messages[0][0]
            self.management_messages.append(
                (int(time.time() * 1000), deepcopy(message))
            )
        return super().handle_order_update(client, message)

    async def _management_loop(self):
        while True:
            try:
                await self.watch_orders()
                if self.management_receive_gap is not None:
                    raise RuntimeError("management receive gap requires new transport")
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - uncertain stream state starts a new connection epoch.
                self.management_gap = True
                self.management_receive_gap = "private_stream_watch_failed"
                self._management_connected_ms = None
                client = self._management_client
                if client is not None and not client.closed():
                    try:
                        await asyncio.wait_for(client.close(), timeout=5)
                    except Exception:  # noqa: BLE001 - transport failure must not kill reconnection.
                        self.management_receive_gap="private_stream_close_failed"
                self._management_client = None
                await asyncio.sleep(2)

    def start_management_stream(self):
        if self._management_task is None:
            self.management_started_ms = int(time.time() * 1000)
            self._management_task = asyncio.create_task(self._management_loop())

    def management_events(self, *, symbol, side, start_ms, end_ms):
        return tuple(
            (received, message)
            for received, message in self.management_messages
            if start_ms <= received <= end_ms
            and message.get("o", {}).get("s") == symbol
            and str(message.get("o", {}).get("ps", "")).lower() == side
        )

    async def close(self):
        if self._management_task is not None:
            self._management_task.cancel()
            await asyncio.gather(self._management_task, return_exceptions=True)
            self._management_task = None
        await super().close()
