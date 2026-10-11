"""Independent official plane loops with an explicit accelerated test clock."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import patch

import sqlalchemy as sa
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
    brf2_short_snapshot,
    cpm_flat_snapshot,
    mi_flat_snapshot,
    mpg_flat_snapshot,
)


async def main() -> None:
    group,initial=sys.argv[1:]
    clock=[int(initial)]
    blocked_member=[None]
    source=inputs(group)
    comparative=group in {"MPG-001","MI-001"}
    excluded=os.environ.get("BRC_RESIDENT_EXCLUDE_MEMBER")
    template={"MPG-001":mpg_flat_snapshot,"MI-001":mi_flat_snapshot,"CPM-RO-001":cpm_flat_snapshot,
        "BRF2-001":lambda:brf2_short_snapshot(strong_uptrend=True)}[group]()
    class Market:
        announced=False
        async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms,
                "venue_status":"TRADING" if (w.exchange_instrument_id!=excluded if excluded else
                    not comparative or w.exchange_instrument_id==source.spec.candidate_ids[0]) else "PENDING_TRADING"}) for w in source.member_windows)
        async def fetch_generic_selection_klines(self,request):
            window=source.member_windows[0] if comparative else next(w for w in source.member_windows if w.exchange_instrument_id==request.exchange_instrument_id)
            return shift_window(window,request.feature_cutoff_at_ms-CUTOFF).candles
        async def fetch_closed_candles(self,request):
            if request.exchange_instrument_id==blocked_member[0]:
                async with engine.connect() as connection:
                    warming=await connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM brc_strategy_universe_versions WHERE strategy_group_id=:group AND lifecycle_state='warming')"),{"group":group})
                if warming:
                    if not self.announced:
                        print(json.dumps({"component_id":"source","status":"blocked_for_restart"}),flush=True)
                        self.announced=True
                    await asyncio.Event().wait()
            candles=template.candles_1h if request.timeframe=="1h" else template.candles_4h
            interval=HOUR if request.timeframe=="1h" else 4*HOUR
            close=request.closed_at_ms//interval*interval
            delta=close-candles[-1].close_time_ms
            return tuple(c.model_copy(update={"open_time_ms":c.open_time_ms+delta,"close_time_ms":c.close_time_ms+delta}) for c in candles)[-request.limit:]
    engine=create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    @sa.event.listens_for(engine.sync_engine,"handle_error")
    def report_test_database_error(context):
        cause=context.original_exception.__cause__
        print(json.dumps({"component_id":"test-diagnostic","status":"database_error",
            "sqlstate":getattr(context.original_exception,"sqlstate",None),
            "database_error_class":None if cause is None else type(cause).__name__,
            "database_message":None if cause is None else str(cause).splitlines()[0][:240]}),flush=True)
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
            value=line.decode().strip()
            if value.startswith("BLOCK "):
                blocked_member[0]=value[6:]
            else:
                clock[0]=int(value)
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
