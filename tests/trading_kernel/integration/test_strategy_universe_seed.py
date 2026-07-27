from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.strategy_universe import (
    registered_strategy_universes,
)
from src.trading_kernel.infrastructure.pg_models import (
    instruments,
    strategy_candidate_scopes,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (
    UniverseSeedConflict,
    seed_strategy_universes,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


@pytest.mark.asyncio
async def test_universe_seed_is_exact_idempotent_and_separate_from_registry(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        registry = await seed_strategy_registry(
            uow,
            seeded_at_ms=1_800_000_000_000,
        )
        first = await seed_strategy_universes(
            uow,
            seeded_at_ms=1_800_000_000_000,
        )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_strategy_universes(
            uow,
            seeded_at_ms=1_800_000_000_001,
        )

    assert registry.inserted_instrument_count == 0
    assert registry.inserted_candidate_scope_count == 0
    assert first.inserted_universe_version_count == 7
    assert first.inserted_member_count == 51
    assert first.inserted_instrument_count == 27
    assert first.inserted_candidate_scope_count == 49
    assert first.inserted_current_pointer_count == 6
    assert first.total_inserted_count > 0
    assert second.total_inserted_count == 0

    async with registry_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_versions)
        ) == 7
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_members)
        ) == 51
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_universe_current)
        ) == 6
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(instruments)
        ) == 27
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(strategy_candidate_scopes)
        ) == 49
        assert await connection.scalar(
            sa.select(sa.func.count())
            .select_from(strategy_candidate_scopes)
            .where(
                strategy_candidate_scopes.c.exchange_instrument_id
                == "binance-usdm:AVAXUSDT:perpetual"
            )
        ) == 0
        states = {
            str(row["event_spec_id"]): str(row["lifecycle_state"])
            for row in (
                await connection.execute(sa.select(strategy_universe_versions))
            ).mappings()
        }
        assert states[
            "event_spec:RSRVCB-001:RSRVCB-LONG-15M:v1"
        ] == "warming"
        assert set(states.values()) == {"active", "warming"}


@pytest.mark.asyncio
async def test_universe_seed_fails_closed_on_immutable_member_conflict(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
        await seed_strategy_universes(uow, seeded_at_ms=1_800_000_000_000)

    universe = registered_strategy_universes()[0]
    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.update(strategy_universe_members)
            .where(
                strategy_universe_members.c.universe_version_id
                == universe.universe_version_id,
                strategy_universe_members.c.priority_rank == 1,
                strategy_universe_members.c.member_role == "candidate",
            )
            .values(venue_symbol="TAMPEREDUSDT")
        )

    with pytest.raises(UniverseSeedConflict, match="universe member conflict"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_universes(
                uow,
                seeded_at_ms=1_800_000_000_001,
            )
