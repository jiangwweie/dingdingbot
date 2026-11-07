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

    def handle_order_update(self, client, message):
        if message.get("e") in ("ORDER_TRADE_UPDATE", "ALGO_UPDATE"):
            if len(self.management_messages) == self.management_messages.maxlen:
                self.management_gap = True
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
