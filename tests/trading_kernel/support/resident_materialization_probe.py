"""Official Materialization runtime entrypoint in an isolated test process."""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.selection_runtime_worker import (
    SelectionRuntimeRequest,
    run_materialization_runtime_once,
)


async def main() -> None:
    group,clock,worker=sys.argv[1:]
    now_ms=int(clock)
    engine=create_async_engine(os.environ["BRC_RESIDENT_TEST_DATABASE_URL"])
    try:
        with patch.object(PostgresInstrumentSelectionRepository,"read_authority_clock_ms",new=AsyncMock(return_value=now_ms)):
            result=await run_materialization_runtime_once(uow_factory=lambda:PostgresKernelUnitOfWork(engine),audit_source=None,
                request=SelectionRuntimeRequest(strategy_group_id=group,selection_spec_id=generic_selection_spec(group).selection_spec_id,
                    worker_id=worker,now_ms=now_ms),clock_ms=lambda:now_ms)
        print(result.model_dump_json(),flush=True)
    finally:
        await engine.dispose()


if __name__=="__main__":
    asyncio.run(main())
