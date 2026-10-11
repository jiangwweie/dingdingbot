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

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    run_entry_worker_once,
)
from src.trading_kernel.interfaces.lifecycle_worker import (
    LifecycleWorkerRequest,
    run_lifecycle_worker_once,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    run_reconciliation_worker_once,
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


async def inject_request_latency(milliseconds: int) -> None:
    deadline = time.monotonic_ns()+milliseconds*1_000_000
    while (remaining := deadline-time.monotonic_ns())>0:
        await asyncio.sleep(remaining/1_000_000_000)


def role_owns_component(role: str, component: str) -> bool:
    if role not in {"all", "observation", "entry", "lifecycle", "reconciliation"}:
        raise ValueError("unsupported soak Worker role")
    if role == "all":
        return True
    if role == "observation":
        return component == "observation" or component.startswith(("selection:", "materialization:", "facts:"))
    return role == component


async def main(role: str = "all") -> None:
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
        payload.update(clock_ms=clock(), wall_elapsed_ms=(time.monotonic_ns()-began)//1_000_000, worker_role=role)
        print(json.dumps(payload), flush=True)

    def source_evidence(method: str, started: int, identity: dict, data: object) -> None:
        emit(json.dumps({"component_id":"source", "status":"request_completed", "method":method,
                         "identity":identity, "elapsed_wall_ms":(time.monotonic_ns()-started)//1_000_000,
                         "source_digest":canonical_digest(data), "injected_wait_ms":5}))

    emit(json.dumps({"component_id": "environment", "status": "ready", "workload_digest": tape.semantic_digest,
                     "cpu_cores": str(resource.cpu_cores), "memory_limit_bytes": resource.memory_limit_bytes}))

    class Market:
        async def fetch_generic_selection_qualifications(self, *, event_spec_id, product_profiles, observed_at_ms):
            started = time.monotonic_ns()
            await inject_request_latency(5)
            group = next(g for g in SOAK_GROUPS if tape.spec(g).event_spec_id == event_spec_id)
            source = tape.selection_input(group, cutoff_ms=observed_at_ms//(tape.spec(group).cadence_hours*HOUR)*(tape.spec(group).cadence_hours*HOUR))
            profiles = {p.exchange_instrument_id: p for p in product_profiles}
            result = tuple(w.qualification.model_copy(update={"observed_at_ms": observed_at_ms,
                         "product_profile": profiles[w.exchange_instrument_id]}) for w in source.member_windows)
            source_evidence("qualifications",started,{"event_spec_id":event_spec_id,"observed_at_ms":observed_at_ms},
                            tuple(r.model_dump(mode="python") for r in result))
            return result

        async def fetch_generic_selection_klines(self, request):
            started = time.monotonic_ns()
            await inject_request_latency(5)
            result = tape.candles(request.exchange_instrument_id, close_ms=request.feature_cutoff_at_ms, count=request.expected_bars)
            source_evidence("selection_klines",started,request.model_dump(mode="json"),tuple(c.canonical_values for c in result))
            return result

        async def fetch_closed_candles(self, request):
            started = time.monotonic_ns()
            await inject_request_latency(5)
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
            result = tuple(output)
            source_evidence("closed_candles",started,request.model_dump(mode="json"),tuple(c.model_dump(mode="python") for c in result))
            return result

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
    class NoExchangeIO:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("healthy no-trigger soak must create zero exchange writes")
        def __getattr__(self, name):
            raise AssertionError(f"unexpected healthy source boundary: {name}")
    no_io = NoExchangeIO()
    async def entry():
        at = clock()
        return await run_entry_worker_once(factory,no_io,no_io,EntryWorkerRequest(worker_id="soak:entry",
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,now_ms=at,lease_until_ms=at+30000,
            timeout_seconds=10,admission_snapshot_validity_ms=5000))
    async def lifecycle():
        at = clock()
        return await run_lifecycle_worker_once(factory,no_io,no_io,LifecycleWorkerRequest(worker_id="soak:lifecycle",
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,now_ms=at,lease_until_ms=at+30000,
            timeout_seconds=10,idle_poll_interval_ms=2000))
    async def reconciliation():
        return await run_reconciliation_worker_once(factory,no_io,no_io,ReconciliationWorkerRequest(worker_id="soak:reconciliation",
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,now_ms=clock(),timeout_seconds=10,
            unknown_visibility_grace_ms=30000,idle_poll_interval_ms=5000))
    loops.extend((WorkerProcessLoop("entry",entry,2000,frozenset({"no_candidate","entry_lane_busy"})),
                  WorkerProcessLoop("lifecycle",lifecycle,2000,frozenset({"no_work","runtime_fenced","no_change"})),
                  WorkerProcessLoop("reconciliation",reconciliation,5000,frozenset({"no_work"}))))
    loops = [item for item in loops if role_owns_component(role,item.component_id)]
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
    async def resource_telemetry():
        while True:
            stats = dict(line.split() for line in Path("/sys/fs/cgroup/cpu.stat").read_text().splitlines())
            emit(json.dumps({"component_id":"resource", "status":"sample", "memory_bytes":int(Path("/sys/fs/cgroup/memory.current").read_text()),
                "cpu_usage_usec":int(stats["usage_usec"]),"throttled_usec":int(stats.get("throttled_usec",0))}))
            await asyncio.sleep(5)
    telemetry_task = asyncio.create_task(resource_telemetry())
    try:
        with patch.object(PostgresInstrumentSelectionRepository, "read_authority_clock_ms", new=authority_clock):
            await run_worker_process_group(tuple(loops), run_forever=True, idle_log_interval_ms=30000, emit=emit)
    finally:
        clock_task.cancel()
        telemetry_task.cancel()
        await asyncio.gather(clock_task,telemetry_task, return_exceptions=True)
        transport.close()
        await engine.dispose()


async def run_four_processes() -> None:
    """Four real children share the parent Docker cgroup and one test clock."""
    children = []
    forwarders = []
    for role in ("observation", "entry", "lifecycle", "reconciliation"):
        child = await asyncio.create_subprocess_exec(sys.executable, "-m", __spec__.name, sys.argv[1], role,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=sys.stderr)
        children.append(child)
        async def forward(child=child):
            while line := await child.stdout.readline():
                print(line.decode().strip(),flush=True)
        forwarders.append(asyncio.create_task(forward()))
    reader = asyncio.StreamReader()
    transport,_ = await asyncio.get_running_loop().connect_read_pipe(lambda:asyncio.StreamReaderProtocol(reader),sys.stdin)
    stop = asyncio.Event()
    import signal
    for handled in (signal.SIGTERM,signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(handled,stop.set)
    async def clock_commands():
        while line := await reader.readline():
            for child in children:
                if child.returncode is None:
                    child.stdin.write(line)
                    await child.stdin.drain()
    async def watch(child):
        await child.wait()
        stop.set()
    tasks = [asyncio.create_task(clock_commands()),*(asyncio.create_task(watch(child)) for child in children)]
    try:
        await stop.wait()
    finally:
        for child in children:
            if child.returncode is None:
                child.terminate()
        await asyncio.gather(*(child.wait() for child in children))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,*forwarders,return_exceptions=True)
        transport.close()
    if any(child.returncode!=0 for child in children):
        raise RuntimeError("one resource-soak Worker exited unsuccessfully")


if __name__ == "__main__":
    role = sys.argv[2] if len(sys.argv)>2 else "all"
    asyncio.run(run_four_processes() if role=="four" else main(role))
