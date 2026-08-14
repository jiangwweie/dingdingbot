"""Shared disposable PostgreSQL fixtures for current-head kernel tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import asyncpg
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE,
    TEST_POSTGRES_ADMIN_DSN,
    async_database_url,
    run_alembic,
)


@pytest_asyncio.fixture
async def dispatch_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_TEST_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = async_database_url(database_name)
    run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
        await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin.close()


@pytest_asyncio.fixture
async def issue_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def lifecycle_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def stress_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def runtime_fact_worker_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def controlled_exit_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def owner_projection_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine


@pytest_asyncio.fixture
async def order_attribution_engine(
    dispatch_engine: AsyncEngine,
) -> AsyncGenerator[AsyncEngine, None]:
    yield dispatch_engine
