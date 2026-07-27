from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.observe_ranked_strategy_scope import (
    prepare_ranked_strategy_snapshot,
)
from src.trading_kernel.application.project_strategy_universe import (
    project_strategy_universe,
)
from src.trading_kernel.domain.strategy_universe import universe_for_event_spec
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (
    seed_strategy_universes,
)
from tests.trading_kernel.integration.test_rsr_vcb_observation import (
    EVENT_SPEC_ID,
    WindowSource,
    _activate_rsr_universe,
    _projection_windows,
    _trigger_window,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_projection_and_trigger_market_queries_are_strictly_bounded(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    universe = universe_for_event_spec(EVENT_SPEC_ID)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)
    trigger_hour_ms, windows = _projection_windows(
        universe,
        compressed_top=True,
    )
    await _activate_rsr_universe(
        registry_engine,
        universe=universe,
        activated_at_ms=trigger_hour_ms - 1,
    )
    source = WindowSource(windows)
    projection = await project_strategy_universe(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        universe_version_id=universe.universe_version_id,
        trigger_time_ms=trigger_hour_ms,
    )

    assert len(source.calls) == 32
    assert sum(request.timeframe == "1h" for request in source.calls) == 30
    assert sum(request.timeframe == "4h" for request in source.calls) == 2
    assert sum(request.timeframe == "15m" for request in source.calls) == 0

    top = None
    armed = None
    for projected in projection.top_two:
        candidate_armed = await _load_armed(
            registry_engine,
            universe_version_id=universe.universe_version_id,
            projection_run_id=projection.projection_run_id,
            exchange_instrument_id=projected.exchange_instrument_id,
            trigger_hour_ms=trigger_hour_ms + 1,
        )
        if candidate_armed is not None:
            top = projected
            armed = candidate_armed
            break
    assert top is not None
    assert armed is not None
    trigger_close_ms = trigger_hour_ms + 900_000
    windows[(top.exchange_instrument_id, "15m")] = _trigger_window(
        armed_at_ms=trigger_hour_ms,
        boundary=armed.breakout_boundary,
    )

    non_top = next(
        member
        for member in universe.candidate_members
        if member.exchange_instrument_id
        not in {
            projected.exchange_instrument_id
            for projected in projection.top_two
        }
    )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        non_top_scope = await uow.signals.get_runtime_scope(
            f"scope-rsr:{non_top.exchange_instrument_id}"
        )
        top_scope = await uow.signals.get_runtime_scope(
            f"scope-rsr:{top.exchange_instrument_id}"
        )
    assert non_top_scope is not None
    assert top_scope is not None

    skipped = await prepare_ranked_strategy_snapshot(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        scope=non_top_scope,
        trigger_close_time_ms=trigger_close_ms,
    )
    assert skipped is None
    assert len(source.calls) == 32

    prepared = await prepare_ranked_strategy_snapshot(
        lambda: PostgresKernelUnitOfWork(registry_engine),
        source,
        scope=top_scope,
        trigger_close_time_ms=trigger_close_ms,
    )
    assert prepared is not None
    assert len(source.calls) == 34
    assert [request.timeframe for request in source.calls[-2:]] == [
        "15m",
        "1h",
    ]


async def _load_armed(
    engine: AsyncEngine,
    *,
    universe_version_id: str,
    projection_run_id: str,
    exchange_instrument_id: str,
    trigger_hour_ms: int,
):
    async with PostgresKernelUnitOfWork(engine) as uow:
        return await uow.strategy_universes.get_active_armed_structure(
            event_spec_id=EVENT_SPEC_ID,
            universe_version_id=universe_version_id,
            projection_run_id=projection_run_id,
            exchange_instrument_id=exchange_instrument_id,
            now_ms=trigger_hour_ms,
        )
