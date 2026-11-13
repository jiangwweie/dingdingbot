"""Raw account order events retained before CCXT's current-order cache merges them."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from copy import deepcopy
from uuid import uuid4

import ccxt.pro as ccxt_pro  # type: ignore[import-untyped]

MANAGEMENT_CLOSE_TIMEOUT_SECONDS = 5

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
        self._management_restart = asyncio.Event()
        self._management_restart_epoch = None
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
        if getattr(client, "_brc_management_retired", False):
            return None
        if self._is_management_client(client):
            if (
                self.management_pending_events
                and len(self.management_closed_batches)
                == self.management_closed_batches.maxlen
            ):
                # Pause receipt rather than evict an epoch that PostgreSQL has
                # not acknowledged. This connection cannot establish coverage.
                client._brc_management_retired = True
                self._management_client = client
                self.management_gap = True
                self.management_receive_gap = "management_epoch_queue_overflow"
                self._management_connected_ms = None
                self._management_restart.set()
                return None
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
        if self.clients.get(client.url) is client:
            return super().on_error(client, error)
        return None

    def on_close(self, client, error):
        self._lose_management_connection(client)
        if self.clients.get(client.url) is client:
            return super().on_close(client, error)
        return None

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
        if getattr(client, "_brc_management_retired", False):
            return None
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

    def request_management_restart(self, epoch_id):
        if (
            epoch_id != self.management_epoch_id
            or self._management_restart_epoch == epoch_id
        ):
            return
        self._management_restart_epoch = epoch_id
        self.management_receive_gap = "management_receiver_protocol_gap"
        self.management_gap = True
        self._management_connected_ms = None
        self._management_restart.set()
        self.start_management_stream()

    async def _close_management_transport(self):
        client = self._management_client
        self._management_client = None
        if client is None:
            key = self.options.get("future", {}).get("listenKey")
            if key:
                client = self.clients.get(self.get_private_ws_url("future", key))
        if client is None:
            return
        client._brc_management_retired = True
        # CCXT caches clients by URL. Retire that exact transport before
        # subscribing again, including when closing it fails or times out.
        if self.clients.get(client.url) is client:
            self.clients.pop(client.url)
        try:
            if not client.closed():
                await asyncio.wait_for(client.close(), MANAGEMENT_CLOSE_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 - reconnect with coverage fenced.
            self.management_receive_gap = "private_stream_close_failed"

    async def _management_loop(self):
        while True:
            if self._management_restart.is_set():
                self._management_restart.clear()
                await self._close_management_transport()
            if (
                self.management_pending_events
                and len(self.management_closed_batches)
                == self.management_closed_batches.maxlen
            ):
                await self._close_management_transport()
                await asyncio.sleep(0.5)
                continue
            watch = asyncio.create_task(self.watch_orders())
            restart = asyncio.create_task(self._management_restart.wait())
            failed = False
            try:
                done, _ = await asyncio.wait(
                    (watch, restart), return_when=asyncio.FIRST_COMPLETED
                )
                if restart in done:
                    continue
                # CCXT Client.close cancels the subscription Future. This is
                # distinct from cancellation of the receiver owner task.
                if watch.cancelled():
                    failed = True
                else:
                    await watch
                    failed = self.management_receive_gap is not None
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - uncertain stream starts a new epoch.
                failed = True
            finally:
                for task in (watch, restart):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(watch, restart, return_exceptions=True)
            if failed:
                self.management_gap = True
                self.management_receive_gap = "private_stream_watch_failed"
                self._management_connected_ms = None
                await self._close_management_transport()
                try:
                    await asyncio.wait_for(self._management_restart.wait(), timeout=2)
                except TimeoutError:
                    pass

    def start_management_stream(self):
        if self._management_task is None or self._management_task.done():
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
