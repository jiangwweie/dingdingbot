"""Integration test configuration.

PG fixtures for real PostgreSQL integration tests.
"""

from __future__ import annotations

import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.infrastructure.pg_execution_intent_repository import PgExecutionIntentRepository
from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository
from src.infrastructure.pg_signal_repository import PgSignalRepository

PG_DATABASE_URL = os.environ.get(
    "PG_DATABASE_URL",
    "postgresql+asyncpg://dingdingbot:dingdingbot_dev@localhost:5432/dingdingbot",
)

_TRUNCATE_ORDER = [
    "signal_take_profits",
    "signals",
    "execution_recovery_tasks",
    "orders",
    "positions",
    "execution_intents",
]


@pytest.fixture(scope="session")
def pg_url() -> str:
    return PG_DATABASE_URL


@pytest_asyncio.fixture()
async def pg_engine(pg_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(pg_url, echo=False, pool_size=5, max_overflow=5)
    from src.infrastructure.pg_models import PGCoreBase

    async with engine.begin() as conn:
        await conn.run_sync(PGCoreBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def pg_session_maker(
    pg_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        pg_engine, expire_on_commit=False, autocommit=False, autoflush=False
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(pg_engine: AsyncEngine):
    async with pg_engine.begin() as conn:
        for t in _TRUNCATE_ORDER:
            await conn.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))
    yield
    async with pg_engine.begin() as conn:
        for t in _TRUNCATE_ORDER:
            await conn.execute(text(f'TRUNCATE TABLE "{t}" CASCADE'))


@pytest_asyncio.fixture()
async def order_repo(
    pg_session_maker: async_sessionmaker[AsyncSession],
) -> PgOrderRepository:
    return PgOrderRepository(pg_session_maker)


@pytest_asyncio.fixture()
async def intent_repo(
    pg_session_maker: async_sessionmaker[AsyncSession],
) -> PgExecutionIntentRepository:
    return PgExecutionIntentRepository(pg_session_maker)


@pytest_asyncio.fixture()
async def position_repo(
    pg_session_maker: async_sessionmaker[AsyncSession],
) -> PgPositionRepository:
    return PgPositionRepository(pg_session_maker)


@pytest_asyncio.fixture()
async def recovery_repo(
    pg_session_maker: async_sessionmaker[AsyncSession],
) -> PgExecutionRecoveryRepository:
    return PgExecutionRecoveryRepository(pg_session_maker)


@pytest_asyncio.fixture()
async def signal_repo(
    pg_session_maker: async_sessionmaker[AsyncSession],
) -> PgSignalRepository:
    return PgSignalRepository(pg_session_maker)


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "test_pg_" in item.nodeid:
            item.add_marker(pytest.mark.asyncio)
