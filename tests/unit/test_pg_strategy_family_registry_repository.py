from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.strategy_family_registry import StrategyFamilyStatus
from src.domain.strategy_family_signal import SignalType
from src.infrastructure.pg_models import (
    PGBrcStrategyFamilyPlaybookORM,
    PGBrcStrategyFamilyRegistryORM,
)
from src.infrastructure.pg_strategy_family_registry_repository import (
    PgStrategyFamilyRegistryRepository,
)


@pytest_asyncio.fixture()
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGBrcStrategyFamilyRegistryORM.__table__.create)
        await conn.run_sync(PGBrcStrategyFamilyPlaybookORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgStrategyFamilyRegistryRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def test_migration_creates_strategy_family_registry_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-28-022_create_strategy_family_registry.py"
    )
    spec = importlib.util.spec_from_file_location("strategy_family_registry_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "brc_strategy_family_registry" in tables
    assert "brc_strategy_family_playbooks" in tables


@pytest.mark.asyncio
async def test_repository_round_trip_seed_and_queries(repo):
    await repo.upsert_initial_seed(now_ms=1770000000000)

    tf = await repo.get_family_metadata_version(
        "TF-001-live-readonly-v0",
        "TF-001-live-readonly-v0",
    )
    assert tf is not None
    assert tf.status == StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE
    assert tf.alpha_claim is False
    assert tf.carrier_validation is True
    assert {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"} == set(tf.supported_symbols)
    assert tf.primary_timeframe == "1h"
    assert {"4h", "1d"}.issubset(set(tf.context_timeframes))
    assert SignalType.NO_ACTION in tf.allowed_signal_types
    assert SignalType.WOULD_ENTER in tf.allowed_signal_types
    assert SignalType.INVALID in tf.allowed_signal_types

    fetched_by_family = await repo.get_family_metadata("TF-001-live-readonly-v0")
    assert fetched_by_family == tf

    tf_playbook = await repo.get_playbook_metadata("TF-001-live-readonly-v0")
    assert tf_playbook is not None
    assert tf_playbook.family_id == tf.family_id
    assert tf_playbook.playbook_status == StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE
    assert SignalType.WOULD_EXIT not in tf_playbook.allowed_signal_types
    assert SignalType.WOULD_REDUCE not in tf_playbook.allowed_signal_types
    assert SignalType.WOULD_CANCEL not in tf_playbook.allowed_signal_types

    active = await repo.list_active_observation_candidates()
    assert [item.family_id for item in active] == ["TF-001-live-readonly-v0"]

    hypothesis_only = await repo.list_registered_hypothesis_only_families()
    assert {item.family_id for item in hypothesis_only} == {
        "VB-001-live-readonly-v0",
        "CPM-RO-001",
    }


@pytest.mark.asyncio
async def test_repository_upsert_is_idempotent(repo):
    await repo.upsert_initial_seed(now_ms=1770000000000)
    await repo.upsert_initial_seed(now_ms=1770000000000)

    active = await repo.list_active_observation_candidates()
    hypothesis_only = await repo.list_registered_hypothesis_only_families()

    assert len(active) == 1
    assert len(hypothesis_only) == 2
