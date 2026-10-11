"""Simultaneous due strategies with one intentionally stalled public source."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.generic_selection_jobs import (
    GenericSelectionSourceTemporarilyUnavailable,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.selection_runtime_worker import (
    SelectionRuntimeRequest,
    run_selection_runtime_once,
)
from src.trading_kernel.interfaces.worker_process import (
    WorkerProcessLoop,
    run_worker_process_group,
)
from tests.trading_kernel.support.generic_selection import CUTOFF, inputs


async def main() -> None:
    failure=sys.argv[1]
    engine=create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    uow=lambda:PostgresKernelUnitOfWork(engine)
    now=CUTOFF+20
    class Market:
        def __init__(self,group): self.group=group; self.source=inputs(group)
        async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
            if self.group=="MI-001":
                if failure=="temporary":
                    raise GenericSelectionSourceTemporarilyUnavailable("HTTP_429")
                print(json.dumps({"component_id":"source:MI-001","status":"waiting"}),flush=True)
                await asyncio.Event().wait()
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for w in self.source.member_windows)
        async def fetch_generic_selection_klines(self,request):
            return next(w.candles for w in self.source.member_windows if w.exchange_instrument_id==request.exchange_instrument_id)
        async def fetch_closed_candles(self,request):
            raise AssertionError("Static policy-disabled Observation must not request market")
    def selector(group):
        market=Market(group)
        async def tick():
            return await run_selection_runtime_once(uow_factory=uow,market_source=market,
                request=SelectionRuntimeRequest(strategy_group_id=group,selection_spec_id=market.source.spec.selection_spec_id,
                    worker_id=f"parallel:{group}",now_ms=now),clock_ms=lambda:now)
        return tick
    async def observation():
        return await run_observation_worker_once(uow,Market("CPM-RO-001"),ObservationWorkerRequest(worker_id="parallel:observation",
            runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,now_ms=now,lease_until_ms=now+30_000,
            timeout_seconds=1,retry_interval_ms=1_000))
    try:
        await run_worker_process_group(tuple(WorkerProcessLoop(group,selector(group),10,frozenset({"already_ready"})) for group in
            ("CPM-RO-001","MPG-001","MI-001","BRF2-001"))+(WorkerProcessLoop("observation",observation,10,frozenset({"no_work"})),),
            run_forever=True,idle_log_interval_ms=1_000)
    finally:
        await engine.dispose()


if __name__=="__main__":
    asyncio.run(main())
