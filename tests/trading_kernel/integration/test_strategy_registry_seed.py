from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.infrastructure.pg_models import (
    event_specs,
    exit_policies,
    owner_policy_current,
    runtime_profiles,
    runtime_scopes_current,
    strategy_candidate_scopes,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    RegistrySeedConflict,
    seed_strategy_registry,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_strategy_registry_seed_cli_is_runnable_outside_repo(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                REPO_ROOT
                / "scripts"
                / "trading_kernel"
                / "seed_strategy_registry.py"
            ),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--database-url" in result.stdout
    assert list(tmp_path.rglob("*")) == []


@pytest_asyncio.fixture
async def registry_engine() -> AsyncEngine:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    _run_alembic(database_url, "upgrade", "head")
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


@pytest.mark.asyncio
async def test_strategy_seed_is_exact_idempotent_and_does_not_grant_live_authority(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)
        event_ids = await uow.strategy_registry.list_current_event_ids()

    assert first.inserted_strategy_group_count == 5
    assert first.inserted_strategy_version_count == 5
    assert first.inserted_event_count == 6
    assert first.inserted_exit_policy_count == 6
    assert first.inserted_fact_definition_count == 18
    assert first.inserted_event_fact_count == 19
    assert first.inserted_instrument_count == 6
    assert first.inserted_candidate_scope_count == 22
    assert second.total_inserted_count == 0
    assert event_ids == (
        "BRF2-SHORT",
        "CPM-LONG",
        "MI-LONG",
        "MPG-LONG",
        "SOR-LONG",
        "SOR-SHORT",
    )

    async with registry_engine.connect() as connection:
        assert await connection.scalar(sa.select(sa.func.count()).select_from(runtime_profiles)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(runtime_scopes_current)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(owner_policy_current)) == 0
        assert await connection.scalar(sa.select(sa.func.count()).select_from(strategy_candidate_scopes)) == 22
        assert await connection.scalar(sa.select(sa.func.count()).select_from(exit_policies)) == 6


@pytest.mark.asyncio
async def test_strategy_seed_fails_closed_on_existing_semantic_conflict(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)

    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.update(event_specs)
            .where(event_specs.c.event_id == "SOR-LONG")
            .values(timeframe="1h")
        )

    with pytest.raises(RegistrySeedConflict, match="event_spec:SOR-001:SOR-LONG:v2"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)


@pytest.mark.asyncio
async def test_strategy_seed_fails_closed_on_exit_policy_semantic_conflict(
    registry_engine: AsyncEngine,
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_000)

    async with registry_engine.begin() as connection:
        await connection.execute(
            sa.update(exit_policies)
            .where(exit_policies.c.event_spec_id == "event_spec:SOR-001:SOR-LONG:v2")
            .values(semantic_hash="sha256:" + "0" * 64)
        )

    with pytest.raises(RegistrySeedConflict, match="exit-policy:SOR-001:SOR-LONG"):
        async with PostgresKernelUnitOfWork(registry_engine) as uow:
            await seed_strategy_registry(uow, seeded_at_ms=1_800_000_000_001)
