"""Long-lived process loop for one bounded trading-kernel worker role."""

from __future__ import annotations

import asyncio
import json
import signal
import time
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class WorkerProcessLoop:
    """One logical loop hosted inside a shared persistent OS process."""

    component_id: str
    tick: Callable[[], Awaitable[BaseModel]]
    poll_interval_ms: int
    idle_statuses: frozenset[str]

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("worker component identity must be non-blank")
        if self.poll_interval_ms <= 0:
            raise ValueError("worker component poll interval must be positive")


def _status_value(result: BaseModel) -> str:
    status = getattr(result, "status", None)
    if status is None:
        raise TypeError("worker result must expose a status")
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


async def run_worker_process_group(
    loops: tuple[WorkerProcessLoop, ...],
    *,
    run_forever: bool,
    idle_log_interval_ms: int,
    emit: Callable[[str], None] | None = None,
) -> int:
    """Run independent logical loops without nesting their application ticks."""

    if not loops:
        raise ValueError("worker process group requires at least one loop")
    identities = tuple(item.component_id for item in loops)
    if len(identities) != len(set(identities)):
        raise ValueError("worker process group component identities must be unique")
    if not run_forever:
        await asyncio.gather(
            *(
                run_worker_process(
                    item.tick,
                    run_forever=False,
                    poll_interval_ms=item.poll_interval_ms,
                    idle_log_interval_ms=idle_log_interval_ms,
                    idle_statuses=item.idle_statuses,
                    emit=emit,
                )
                for item in loops
            )
        )
        return 0

    output = emit or (lambda value: print(value, flush=True))
    stop = _shutdown_event()

    async def run_component(item: WorkerProcessLoop) -> None:
        last_idle_log_ms: int | None = None
        while not stop.is_set():
            try:
                result = await item.tick()
                status = _status_value(result)
                monotonic_ms = time.monotonic_ns() // 1_000_000
                should_emit = status not in item.idle_statuses or (
                    last_idle_log_ms is None
                    or monotonic_ms - last_idle_log_ms >= idle_log_interval_ms
                )
                if should_emit:
                    payload = result.model_dump(mode="json")
                    payload["component_id"] = item.component_id
                    output(json.dumps(payload, ensure_ascii=False))
                    if status in item.idle_statuses:
                        last_idle_log_ms = monotonic_ms
            except Exception as exc:  # noqa: BLE001 - isolate one logical loop.
                trace = exc.__traceback__
                while trace is not None and trace.tb_next is not None:
                    trace = trace.tb_next
                location = None if trace is None else {
                    "file": trace.tb_frame.f_code.co_filename.rsplit("/", 1)[-1],
                    "function": trace.tb_frame.f_code.co_name,
                    "line": trace.tb_lineno,
                }
                output(
                    json.dumps(
                        {
                            "component_id": item.component_id,
                            "status": "tick_failed",
                            "detail": type(exc).__name__,
                            "error_location": location,
                        },
                        ensure_ascii=False,
                    )
                )
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=item.poll_interval_ms / 1_000,
                )
            except TimeoutError:
                continue

    await asyncio.gather(*(run_component(item) for item in loops))
    return 0
