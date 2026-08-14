"""Shared disposable PostgreSQL fixtures for current-head kernel tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.trading_kernel.support.postgres import (
    HeadTemplateCloneHarness,
)


@pytest_asyncio.fixture
async def dispatch_engine() -> AsyncGenerator[AsyncEngine, None]:
    harness = HeadTemplateCloneHarness()
    database_name, database_url = await harness.create_clone()
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()
        await harness.drop_clone(database_name)


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
