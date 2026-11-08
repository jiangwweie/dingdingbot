"""Raw account order events retained before CCXT's current-order cache merges them."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from copy import deepcopy

import ccxt.pro as ccxt_pro  # type: ignore[import-untyped]


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

    def _is_management_client(self, client):
        key = self.options.get("future", {}).get("listenKey")
        return bool(key and client.url == self.get_private_ws_url("future", key))

    def on_connected(self, client, message=None):
        if self._is_management_client(client):
            self._management_client = client
            self._management_connected_ms = self.milliseconds()
            self.management_gap = False
        return super().on_connected(client, message)

    def _lose_management_connection(self, client):
        if client is self._management_client:
            self.management_gap = True
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
            and (self.management_lost_before_ms is None
                 or self.management_lost_before_ms < start_ms)
        )

    def handle_order_update(self, client, message):
        if message.get("e") in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE"):
            if len(self.management_messages) == self.management_messages.maxlen:
                self.management_lost_before_ms = self.management_messages[0][0]
            self.management_messages.append((int(time.time() * 1000), deepcopy(message)))
        return super().handle_order_update(client, message)

    async def _management_loop(self):
        while True:
            try:
                await self.watch_orders()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - stream failure marks a gap and reconnects.
                self.management_gap = True
                self._management_connected_ms = None
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
