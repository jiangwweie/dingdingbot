"""Observe CCXT queue/network latency without inspecting requests or responses."""

from __future__ import annotations

import time
from typing import Any

from src.trading_kernel.application.entry_fact_collection import entry_read_telemetry


def instrument_entry_reads(exchange: Any) -> None:
    throttle = getattr(exchange, "throttle", None)
    fetch = getattr(exchange, "fetch", None)
    if not callable(throttle) or not callable(fetch):
        return  # Recording/fake exchanges need not implement CCXT telemetry.

    async def timed_throttle(cost=None):
        trace = entry_read_telemetry.get()
        start = time.monotonic()
        try:
            return await throttle(cost)
        finally:
            if trace is not None:
                trace.throttle_wait_ms += int((time.monotonic()-start)*1000)

    async def timed_fetch(*args, **kwargs):
        trace = entry_read_telemetry.get()
        start = time.monotonic()
        try:
            return await fetch(*args, **kwargs)
        finally:
            if trace is not None:
                trace.http_reads += 1
                trace.http_ms += int((time.monotonic()-start)*1000)

    exchange.throttle = timed_throttle
    exchange.fetch = timed_fetch
