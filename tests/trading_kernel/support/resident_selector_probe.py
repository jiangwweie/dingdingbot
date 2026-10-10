"""OS-process probe of the official Selector entrypoint with frozen market time."""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.selection_runtime_worker import (
    SelectionRuntimeRequest,
    run_selection_runtime_once,
)
from tests.trading_kernel.support.generic_selection import HOUR, inputs, shift_window


async def main() -> None:
    group,now,worker,mode=sys.argv[1:]
    now_ms=int(now)
    source=inputs(group)
    cutoff=now_ms//(source.spec.cadence_hours*HOUR)*(source.spec.cadence_hours*HOUR)
    source=source.model_copy(update={"member_windows":tuple(shift_window(w,cutoff-source.feature_cutoff_at_ms) for w in source.member_windows)})
    class Market:
        async def fetch_generic_selection_qualifications(self,*,event_spec_id,product_profiles,observed_at_ms):
            if mode=="hang":
                print("source_waiting",flush=True)
                await asyncio.Event().wait()
            if mode=="forbidden":
                raise AssertionError("live Job lease must not read source")
            return tuple(w.qualification.model_copy(update={"observed_at_ms":observed_at_ms}) for w in source.member_windows)
        async def fetch_generic_selection_klines(self,request):
            return next(w.candles for w in source.member_windows if w.exchange_instrument_id==request.exchange_instrument_id)
    engine=create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    try:
        result=await run_selection_runtime_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),market_source=Market(),
            request=SelectionRuntimeRequest(strategy_group_id=group,selection_spec_id=source.spec.selection_spec_id,worker_id=worker,now_ms=now_ms),
            clock_ms=lambda:now_ms)
        print(result.model_dump_json(),flush=True)
    finally:
        await engine.dispose()


if __name__=="__main__":
    asyncio.run(main())
