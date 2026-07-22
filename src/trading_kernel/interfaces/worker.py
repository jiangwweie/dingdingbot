"""Public one-shot worker interface."""

from src.trading_kernel.application.ports import UnitOfWorkFactory, VenuePort
from src.trading_kernel.application.runtime import (
    RuntimeTickRequest,
    RuntimeTickResult,
    run_runtime_once,
)


async def run_worker_once(
    uow_factory: UnitOfWorkFactory,
    venue: VenuePort,
    request: RuntimeTickRequest,
) -> RuntimeTickResult:
    return await run_runtime_once(uow_factory, venue, request)
