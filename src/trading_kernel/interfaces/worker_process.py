"""Long-lived process loop for one bounded trading-kernel worker role."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
import json
import signal
import time

from pydantic import BaseModel


def _status_value(result: BaseModel) -> str:
    status = getattr(result, "status")
    value = getattr(status, "value", status)
    return str(value)


def _shutdown_event() -> asyncio.Event:
    event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, event.set)
        except (NotImplementedError, RuntimeError):
            pass
    return event


async def run_worker_process(
    tick: Callable[[], Awaitable[BaseModel]],
    *,
    run_forever: bool,
    poll_interval_ms: int,
    idle_log_interval_ms: int,
    idle_statuses: Collection[str],
    emit: Callable[[str], None] | None = None,
) -> int:
    """Run one tick or a signal-aware loop while suppressing idle log floods."""

    if poll_interval_ms <= 0 or idle_log_interval_ms <= 0:
        raise ValueError("worker process intervals must be positive")
    output = emit or (lambda value: print(value, flush=True))
    idle_values = frozenset(idle_statuses)
    last_idle_log_ms: int | None = None
    stop = _shutdown_event() if run_forever else None

    while True:
        result = await tick()
        status = _status_value(result)
        monotonic_ms = time.monotonic_ns() // 1_000_000
        should_emit = status not in idle_values or (
            last_idle_log_ms is None
            or monotonic_ms - last_idle_log_ms >= idle_log_interval_ms
        )
        if should_emit:
            output(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
            if status in idle_values:
                last_idle_log_ms = monotonic_ms

        if not run_forever:
            return 0
        assert stop is not None
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=poll_interval_ms / 1_000,
            )
        except TimeoutError:
            continue
        return 0
