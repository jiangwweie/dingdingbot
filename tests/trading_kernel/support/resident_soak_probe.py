"""Resource-constrained official Observation-plane loops on the frozen tape.

The host owns disposable setup and the close/command ledger. This process owns
only real worker ticks, independent leases and a wall-time-progressing test
clock. There are no synthetic target-warming or authority writes here.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.selection_runtime_worker import (
    CurrentFactRefreshRuntimeRequest,
    SelectionRuntimeRequest,
    run_current_fact_refresh_runtime_once,
    run_materialization_runtime_once,
    run_selection_runtime_once,
)
from src.trading_kernel.interfaces.worker_process import (
    WorkerProcessLoop,
    run_worker_process_group,
)
from tests.trading_kernel.support.generic_selection import HOUR
from tests.trading_kernel.support.generic_selection_soak import (
    SOAK_GROUPS,
    SoakResourceFacts,
    SoakWorkload,
)


async def main() -> None:
    resource = SoakResourceFacts.from_cgroup(
        cpu_max=Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        memory_max=Path("/sys/fs/cgroup/memory.max").read_text().strip(),
    )
    tape = SoakWorkload()
    began = time.monotonic_ns()
    base = [int(sys.argv[1]), began]

    def clock() -> int:
        return base[0]+(time.monotonic_ns()-base[1])//1_000_000

    def emit(value: str) -> None:
        payload = json.loads(value)
        payload.update(clock_ms=clock(), wall_elapsed_ms=(time.monotonic_ns()-began)//1_000_000)
        print(json.dumps(payload), flush=True)

    emit(json.dumps({"component_id": "environment", "status": "ready", "workload_digest": tape.semantic_digest,
                     "cpu_cores": str(resource.cpu_cores), "memory_limit_bytes": resource.memory_limit_bytes}))

    class Market:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            await asyncio.sleep(0.005)
            group = next(g for g in SOAK_GROUPS if tape.spec(g).event_spec_id == event_spec_id)
            source = tape.selection_input(group, cutoff_ms=observed_at_ms//(tape.spec(group).cadence_hours*HOUR)*(tape.spec(group).cadence_hours*HOUR))
            profiles = {p.exchange_instrument_id: p for p in product_profiles}
            return tuple(w.qualification.model_copy(update={"observed_at_ms": observed_at_ms,
                         "product_profile": profiles[w.exchange_instrument_id]}) for w in source.member_windows)

        async def fetch_generic_selection_klines(self, request):
            await asyncio.sleep(0.005)
            return tape.candles(request.exchange_instrument_id, close_ms=request.feature_cutoff_at_ms, count=request.expected_bars)

        async def fetch_closed_candles(self, request):
            await asyncio.sleep(0.005)
            interval = HOUR if request.timeframe == "1h" else 4*HOUR
            if request.timeframe not in {"1h", "4h"}:
                raise AssertionError("retired SOR unexpectedly requested market data")
            close = request.closed_at_ms//interval*interval
            output = []
            for index in range(request.limit):
                ending = close-(request.limit-1-index)*interval
                candles = tape.candles(request.exchange_instrument_id, close_ms=ending, count=interval//HOUR)
                output.append(ClosedCandle(open_time_ms=ending-interval, close_time_ms=ending,
                    open=candles[0].open, high=max(c.high for c in candles), low=min(c.low for c in candles),
                    close=candles[-1].close, volume=sum(c.base_volume for c in candles)))
            return tuple(output)

    engine = create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    factory = lambda: PostgresKernelUnitOfWork(engine)
    market = Market()
    cursors = {}
    loops = []
    for group in SOAK_GROUPS:
        spec = tape.spec(group)

        async def selection(group=group, spec=spec):
            return await run_selection_runtime_once(uow_factory=factory, market_source=market,
                request=SelectionRuntimeRequest(strategy_group_id=group, selection_spec_id=spec.selection_spec_id,
                    worker_id=f"soak:selector:{group}", now_ms=clock()), clock_ms=clock)

        async def materialization(group=group, spec=spec):
            return await run_materialization_runtime_once(uow_factory=factory, audit_source=None,
                request=SelectionRuntimeRequest(strategy_group_id=group, selection_spec_id=spec.selection_spec_id,
                    worker_id=f"soak:materializer:{group}", now_ms=clock()), clock_ms=clock)

        async def facts(group=group, spec=spec):
            result = await run_current_fact_refresh_runtime_once(uow_factory=factory, market_source=market,
                request=CurrentFactRefreshRuntimeRequest(strategy_group_id=group, selection_spec_id=spec.selection_spec_id,
                    worker_id=f"soak:facts:{group}", now_ms=clock(), runtime_commit="a"*40,
                    schema_revision=CURRENT_SCHEMA_REVISION, after_runtime_scope_id=cursors.get(group)))
            if result.runtime_scope_id is not None:
                cursors[group] = result.runtime_scope_id
            return result

        loops.extend((WorkerProcessLoop(f"selection:{group}", selection, 5000, frozenset({"not_due", "already_ready", "not_installed"})),
                      WorkerProcessLoop(f"materialization:{group}", materialization, 2000, frozenset({"not_due", "waiting"})),
                      WorkerProcessLoop(f"facts:{group}", facts, 5000, frozenset({"no_work"}))))

    async def observation():
        at = clock()
        return await run_observation_worker_once(factory, market, ObservationWorkerRequest(worker_id="soak:observation",
            runtime_commit="a"*40, schema_revision=CURRENT_SCHEMA_REVISION, now_ms=at, lease_until_ms=at+30000,
            timeout_seconds=10, retry_interval_ms=1000))

    loops.append(WorkerProcessLoop("observation", observation, 5000, frozenset({"no_work"})))
    async def diagnostic_tick(tick):
        try:
            return await tick()
        except ValidationError as exc:
            emit(json.dumps({"component_id": "test-diagnostic", "status": "validation_error",
                             "errors": exc.errors(include_input=False, include_context=False, include_url=False)}))
            raise
    loops = [WorkerProcessLoop(item.component_id, lambda tick=item.tick: diagnostic_tick(tick),
                               item.poll_interval_ms, item.idle_statuses) for item in loops]
    reader = asyncio.StreamReader()
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    async def advance_clock():
        while line := await reader.readline():
            target = int(line.decode().strip())
            if target < clock():
                raise ValueError("soak clock cannot move backwards")
            base[:] = [target, time.monotonic_ns()]

    async def authority_clock(_):
        return clock()

    clock_task = asyncio.create_task(advance_clock())
    try:
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=authority_clock):
            await run_worker_process_group(tuple(loops), run_forever=True, idle_log_interval_ms=30000, emit=emit)
    finally:
        clock_task.cancel()
        await asyncio.gather(clock_task, return_exceptions=True)
        transport.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
