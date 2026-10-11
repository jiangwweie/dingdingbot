"""Independent official plane loops with an explicit accelerated test clock."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import patch

from sqlalchemy.ext.asyncio import create_async_engine

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
from tests.trading_kernel.support.generic_selection import (
    CUTOFF,
    HOUR,
    inputs,
    shift_window,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    mi_flat_snapshot,
    mpg_flat_snapshot,
)


async def main() -> None:
    group,initial=sys.argv[1:]
    clock=[int(initial)]
    source=inputs(group)
    template=mpg_flat_snapshot() if group=="MPG-001" else mi_flat_snapshot()
    class Market:
        async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms,
                "venue_status":"TRADING" if w.exchange_instrument_id==source.spec.candidate_ids[0] else "PENDING_TRADING"}) for w in source.member_windows)
        async def fetch_generic_selection_klines(self,request):
            return shift_window(source.member_windows[0],request.feature_cutoff_at_ms-CUTOFF).candles
        async def fetch_closed_candles(self,request):
            close=clock[0]//HOUR*HOUR
            delta=close-template.trigger_candle_close_time_ms
            candles=template.candles_1h if request.timeframe=="1h" else template.candles_4h
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)[-request.limit:]
    engine=create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    uow=lambda:PostgresKernelUnitOfWork(engine)
    market=Market()
    async def authority_clock(_): return clock[0]
    async def selection():
        return await run_selection_runtime_once(uow_factory=uow,market_source=market,
            request=SelectionRuntimeRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,worker_id="resident:selector",now_ms=clock[0]),clock_ms=lambda:clock[0])
    async def materialization():
        return await run_materialization_runtime_once(uow_factory=uow,audit_source=None,
            request=SelectionRuntimeRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,worker_id="resident:materializer",now_ms=clock[0]),clock_ms=lambda:clock[0])
    cursor=[None]
    async def facts():
        result=await run_current_fact_refresh_runtime_once(uow_factory=uow,market_source=market,
            request=CurrentFactRefreshRuntimeRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,worker_id="resident:facts",
                now_ms=clock[0],runtime_commit="a"*40,schema_revision=CURRENT_SCHEMA_REVISION,after_runtime_scope_id=cursor[0]))
        if result.runtime_scope_id is not None: cursor[0]=result.runtime_scope_id
        return result
    async def observation():
        return await run_observation_worker_once(uow,market,ObservationWorkerRequest(worker_id="resident:observation",runtime_commit="a"*40,
            schema_revision=CURRENT_SCHEMA_REVISION,now_ms=clock[0],lease_until_ms=clock[0]+30_000,timeout_seconds=10,retry_interval_ms=1_000))
    reader=asyncio.StreamReader()
    transport,_=await asyncio.get_running_loop().connect_read_pipe(lambda:asyncio.StreamReaderProtocol(reader),sys.stdin)
    async def advance_clock():
        while line:=await reader.readline():
            clock[0]=int(line)
    clock_task=asyncio.create_task(advance_clock())
    try:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=authority_clock):
            await run_worker_process_group(tuple(WorkerProcessLoop(name,tick,10,frozenset()) for name,tick in (
                ("selection",selection),("materialization",materialization),("facts",facts),("observation",observation))),
                run_forever=True,idle_log_interval_ms=1_000)
    finally:
        clock_task.cancel()
        await asyncio.gather(clock_task,return_exceptions=True)
        transport.close()
        await engine.dispose()


if __name__=="__main__":
    asyncio.run(main())
