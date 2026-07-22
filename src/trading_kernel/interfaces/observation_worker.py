"""One bounded event-time observation invocation."""

from src.trading_kernel.application.market_ports import PublicMarketSource
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationResult,
    observe_strategy_scope,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory


async def run_observation_once(
    uow_factory: UnitOfWorkFactory,
    market_source: PublicMarketSource,
    request: ObservationRequest,
) -> ObservationResult:
    return await observe_strategy_scope(uow_factory, market_source, request)
