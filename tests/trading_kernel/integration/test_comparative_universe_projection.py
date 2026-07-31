from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    ComparativeProjectionAuthorityChanged,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import (
    comparative_projection_current,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from tests.trading_kernel.integration.universe_certification_support import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    ETH,
    NOW_MS,
    OP,
    SOL,
    mpg_long_snapshot,
)

CONTRACT = next(
    contract
    for contract in registered_strategy_contracts()
    if contract.event_id == "MPG-LONG"
)
MEMBERS = tuple(sorted((ETH, OP, SOL)))


@pytest_asyncio.fixture
async def projection_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    engine: AsyncEngine | None = None
    try:
        _run_alembic(database_url, "upgrade", "head")
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-projection-test",
                    runtime_commit="task-9-test",
                    schema_revision="0002_sor_v3_strategy_group_capacity",
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )
            installed = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=CONTRACT.event_spec_id,
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    owner_policy_id=OWNER_POLICY_ID,
                    exchange_instrument_ids=MEMBERS,
                    installed_at_ms=NOW_MS - 1_000,
                ),
            )
        assert installed.universe is not None
        yield engine
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest.mark.asyncio
async def test_projection_round_trips_only_for_exact_key_and_digest(
    projection_engine: AsyncEngine,
) -> None:
    universe_version_id = await _universe_version_id(projection_engine)
    candles = mpg_long_snapshot().candles_1h
    projection = build_comparative_universe_projection(
        event_spec_id=CONTRACT.event_spec_id,
        universe_version_id=universe_version_id,
        strategy_group_id=CONTRACT.strategy_group_id,
        exchange_instrument_ids=MEMBERS,
        closed_bar_time_ms=NOW_MS,
        lookback_bars=8,
        freshness_window_ms=CONTRACT.freshness_window_ms,
        member_windows=tuple(
            ComparativeMemberWindow(
                exchange_instrument_id=member,
                candles_1h=candles,
            )
            for member in MEMBERS
        ),
    )

    async def save_projection():
        async with PostgresKernelUnitOfWork(projection_engine) as uow:
            return await uow.strategy_universes.save_comparative_projection(
                projection,
            )

    first, second = await asyncio.gather(
        save_projection(),
        save_projection(),
    )
    async with PostgresKernelUnitOfWork(projection_engine) as uow:
        exact = await uow.strategy_universes.get_comparative_projection(
            event_spec_id=projection.event_spec_id,
            universe_version_id=projection.universe_version_id,
            closed_bar_time_ms=projection.closed_bar_time_ms,
            member_set_digest=projection.member_set_digest,
        )
        wrong_close = await uow.strategy_universes.get_comparative_projection(
            event_spec_id=projection.event_spec_id,
            universe_version_id=projection.universe_version_id,
            closed_bar_time_ms=projection.closed_bar_time_ms + 3_600_000,
            member_set_digest=projection.member_set_digest,
        )
        wrong_digest = await uow.strategy_universes.get_comparative_projection(
            event_spec_id=projection.event_spec_id,
            universe_version_id=projection.universe_version_id,
            closed_bar_time_ms=projection.closed_bar_time_ms,
            member_set_digest="sha256:" + ("0" * 64),
        )

    async with projection_engine.connect() as connection:
        projection_rows = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    comparative_projection_current
                )
            )
            or 0
        )

    assert first == second
    assert exact == projection
    assert wrong_close is None
    assert wrong_digest is None
    assert projection_rows == 1
    assert exact is not None
    assert exact.projection_version == 1


@pytest.mark.asyncio
async def test_newer_projection_replaces_current_and_rejects_stale_writer(
    projection_engine: AsyncEngine,
) -> None:
    universe_version_id = await _universe_version_id(projection_engine)
    candles = mpg_long_snapshot().candles_1h

    def projection_at(*, closed_at_ms: int, delta_ms: int):
        shifted = tuple(
            candle.model_copy(
                update={
                    "open_time_ms": candle.open_time_ms + delta_ms,
                    "close_time_ms": candle.close_time_ms + delta_ms,
                }
            )
            for candle in candles
        )
        return build_comparative_universe_projection(
            event_spec_id=CONTRACT.event_spec_id,
            universe_version_id=universe_version_id,
            strategy_group_id=CONTRACT.strategy_group_id,
            exchange_instrument_ids=MEMBERS,
            closed_bar_time_ms=closed_at_ms,
            lookback_bars=8,
            freshness_window_ms=CONTRACT.freshness_window_ms,
            member_windows=tuple(
                ComparativeMemberWindow(
                    exchange_instrument_id=member,
                    candles_1h=shifted,
                )
                for member in MEMBERS
            ),
        )

    old = projection_at(closed_at_ms=NOW_MS, delta_ms=0)
    newer = projection_at(
        closed_at_ms=NOW_MS + 3_600_000,
        delta_ms=3_600_000,
    )
    async with PostgresKernelUnitOfWork(projection_engine) as uow:
        first = await uow.strategy_universes.save_comparative_projection(old)
    async with PostgresKernelUnitOfWork(projection_engine) as uow:
        second = await uow.strategy_universes.save_comparative_projection(
            newer
        )

    with pytest.raises(ComparativeProjectionAuthorityChanged):
        async with PostgresKernelUnitOfWork(projection_engine) as uow:
            await uow.strategy_universes.save_comparative_projection(old)

    assert first.projection_version == 1
    assert second.projection_version == 2
    assert second.closed_bar_time_ms == NOW_MS + 3_600_000


async def _universe_version_id(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        return str(
            await connection.scalar(
                sa.select(runtime_scopes_current.c.universe_version_id)
                .where(
                    runtime_scopes_current.c.event_spec_id
                    == CONTRACT.event_spec_id
                )
                .limit(1)
            )
        )
