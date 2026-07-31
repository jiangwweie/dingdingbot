from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal, TypedDict
from uuid import uuid4

import asyncpg
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_specs,
    instrument_certification_current,
    instruments,
    runtime_scopes_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
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
from tests.trading_kernel.unit.detectors.fixtures import mpg_long_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
DIRECT_CONTRACT = next(
    contract
    for contract in registered_strategy_contracts()
    if contract.event_id == "SOR-LONG"
)
COMPARATIVE_CONTRACT = next(
    contract
    for contract in registered_strategy_contracts()
    if contract.event_id == "MPG-LONG"
)
ACTIVE_MEMBERS = (
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:SOLUSDT:perpetual",
)
REPLACEMENT_MEMBERS = (
    "binance-usdm:ETHUSDT:perpetual",
    "binance-usdm:OPUSDT:perpetual",
)
NOW_MS = 1_800_000_100_000
SCHEMA_REVISION: Literal["0002_sor_v3_strategy_group_capacity"] = (
    "0002_sor_v3_strategy_group_capacity"
)
_READINESS_DIGEST = "sha256:" + ("a" * 64)
_FACTS_DIGEST = "sha256:" + ("b" * 64)
_RULES_DIGEST = "sha256:" + ("c" * 64)


@pytest_asyncio.fixture
async def activation_engine() -> AsyncGenerator[AsyncEngine, None]:
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
                    account_id="subaccount-activation-test",
                    runtime_commit="task-10-test",
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 1_000_000,
                ),
            )
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


async def prepare_active_and_warming(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract = DIRECT_CONTRACT,
) -> tuple[str, str]:
    old_version_id = await _install(
        engine,
        contract=contract,
        members=ACTIVE_MEMBERS,
        installed_at_ms=NOW_MS - 900_000,
    )
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == old_version_id
            )
            .values(
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=2,
                warm_closed_bar_time_ms=NOW_MS - 800_000,
                warm_completed_at_ms=NOW_MS - 800_000,
                warm_readiness_digest=_READINESS_DIGEST,
                warm_valid_until_ms=NOW_MS + 600_000,
                next_observation_due_at_ms=NOW_MS + 3_600_000,
                lease_owner=None,
                lease_expires_at_ms=None,
                observation_generation=2,
                updated_at_ms=NOW_MS - 800_000,
            )
        )
        await connection.execute(
            sa.update(strategy_universe_versions)
            .where(
                strategy_universe_versions.c.universe_version_id
                == old_version_id
            )
            .values(
                lifecycle_state="active",
                activated_at_ms=NOW_MS - 800_000,
            )
        )
        old = (
            await connection.execute(
                sa.select(strategy_universe_versions).where(
                    strategy_universe_versions.c.universe_version_id
                    == old_version_id
                )
            )
        ).mappings().one()
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id=contract.event_spec_id,
                universe_version_id=old_version_id,
                semantic_digest=old["semantic_digest"],
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=NOW_MS - 800_000,
            )
        )

    new_version_id = await _install(
        engine,
        contract=contract,
        members=REPLACEMENT_MEMBERS,
        installed_at_ms=NOW_MS - 100_000,
    )
    return old_version_id, new_version_id


async def prepare_retired_v2_active_and_v3_warming(
    engine: AsyncEngine,
) -> tuple[str, str]:
    """Build the exact post-Registry-seed, pre-Universe-switch SOR state."""

    old_version_id = "universe:legacy-sor-long:v2:1"
    old_event_spec_id = "event_spec:SOR-001:SOR-LONG:v2"
    old_semantic_digest = "sha256:" + "9" * 64
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_versions).values(
                strategy_version_id="sgv:SOR-001:v2",
                strategy_group_id="SOR-001",
                version=2,
                semantics={"source": "committed_old_main_program_v2"},
                status="retired",
                created_at_ms=NOW_MS - 2_000_000,
            )
        )
        await connection.execute(
            sa.insert(event_specs).values(
                event_spec_id=old_event_spec_id,
                strategy_version_id="sgv:SOR-001:v2",
                event_id="SOR-LONG",
                position_side="long",
                timeframe="15m",
                freshness_window_ms=900_000,
                event_time_authority="trigger_candle_close_time_ms",
                entry_order_type="market",
                protection_reference_fact_definition_id="fact:legacy-range-low:v1",
                exit_policy_id="exit-policy:SOR-001:SOR-LONG:right-tail-v1",
                execution_semantics={"source": "committed_old_main_program_v2"},
                status="retired",
                created_at_ms=NOW_MS - 2_000_000,
            )
        )
        await connection.execute(
            sa.insert(instruments),
            [
                {
                    "exchange_instrument_id": instrument_id,
                    "venue_id": "binance-usdm",
                    "asset_class": "crypto",
                    "venue_symbol": instrument_id.split(":")[1],
                    "contract_kind": "perpetual",
                    "status": "active",
                }
                for instrument_id in ACTIVE_MEMBERS
            ],
        )
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id=old_version_id,
                strategy_group_id="SOR-001",
                event_spec_id=old_event_spec_id,
                universe_version=1,
                semantic_digest=old_semantic_digest,
                lifecycle_state="active",
                installed_at_ms=NOW_MS - 1_900_000,
                activated_at_ms=NOW_MS - 1_800_000,
                retired_at_ms=None,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members),
            [
                {
                    "universe_version_id": old_version_id,
                    "exchange_instrument_id": instrument_id,
                }
                for instrument_id in ACTIVE_MEMBERS
            ],
        )
        await connection.execute(
            sa.insert(runtime_scopes_current),
            [
                {
                    "runtime_scope_id": f"scope:legacy-v2:{index}",
                    "strategy_group_id": "SOR-001",
                    "strategy_version_id": "sgv:SOR-001:v2",
                    "event_spec_id": old_event_spec_id,
                    "runtime_profile_id": RUNTIME_PROFILE_ID,
                    "owner_policy_id": OWNER_POLICY_ID,
                    "exchange_instrument_id": instrument_id,
                    "position_side": "long",
                    "universe_version_id": old_version_id,
                    "universe_semantic_digest": old_semantic_digest,
                    "lifecycle_state": "active",
                    "observation_enabled": True,
                    "entry_enabled": True,
                    "scope_version": 2,
                    "warm_closed_bar_time_ms": NOW_MS - 1_800_000,
                    "warm_completed_at_ms": NOW_MS - 1_800_000,
                    "warm_readiness_digest": _READINESS_DIGEST,
                    "warm_valid_until_ms": NOW_MS + 60_000,
                    "next_observation_due_at_ms": NOW_MS + 900_000,
                    "lease_expires_at_ms": None,
                    "lease_owner": None,
                    "observation_generation": 2,
                    "updated_at_ms": NOW_MS - 1_800_000,
                }
                for index, instrument_id in enumerate(ACTIVE_MEMBERS, start=1)
            ],
        )
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id=old_event_spec_id,
                universe_version_id=old_version_id,
                semantic_digest=old_semantic_digest,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=NOW_MS - 1_800_000,
            )
        )

    new_version_id = await _install(
        engine,
        contract=DIRECT_CONTRACT,
        members=REPLACEMENT_MEMBERS,
        installed_at_ms=NOW_MS - 100_000,
    )
    return old_version_id, new_version_id


async def make_warming_ready(
    engine: AsyncEngine,
    *,
    universe_version_id: str,
    warm_closed_bar_time_ms: int = NOW_MS - 10_000,
    valid_until_ms: int = NOW_MS + 60_000,
) -> None:
    async with engine.begin() as connection:
        scopes = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.runtime_profile_id,
                    runtime_scopes_current.c.exchange_instrument_id,
                ).where(
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id
                )
            )
        ).mappings().all()
        for scope in scopes:
            key = {
                "runtime_profile_id": scope["runtime_profile_id"],
                "exchange_instrument_id": scope["exchange_instrument_id"],
            }
            await connection.execute(
                sa.insert(instrument_certification_current).values(
                    **key,
                    status="eligible",
                    blocker_code=None,
                    facts_digest=_FACTS_DIGEST,
                    product_rules_digest=_RULES_DIGEST,
                    configured_leverage=5,
                    margin_mode="cross",
                    position_mode="independent_sides",
                    observed_at_ms=warm_closed_bar_time_ms,
                    valid_until_ms=valid_until_ms,
                    next_check_at_ms=valid_until_ms,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    projection_version=1,
                )
            )
            await connection.execute(
                sa.update(instruments)
                .where(
                    instruments.c.exchange_instrument_id
                    == scope["exchange_instrument_id"]
                )
                .values(status="active")
            )
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == universe_version_id
            )
            .values(
                warm_closed_bar_time_ms=warm_closed_bar_time_ms,
                warm_completed_at_ms=warm_closed_bar_time_ms,
                warm_readiness_digest=_READINESS_DIGEST,
                warm_valid_until_ms=valid_until_ms,
                updated_at_ms=warm_closed_bar_time_ms,
            )
        )


async def save_complete_comparative_projection(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
    universe_version_id: str,
    members: tuple[str, ...] = REPLACEMENT_MEMBERS,
    closed_bar_time_ms: int = NOW_MS - 10_000,
) -> None:
    source_candles = mpg_long_snapshot().candles_1h
    delta_ms = closed_bar_time_ms - source_candles[-1].close_time_ms
    candles = tuple(
        candle.model_copy(
            update={
                "open_time_ms": candle.open_time_ms + delta_ms,
                "close_time_ms": candle.close_time_ms + delta_ms,
            }
        )
        for candle in source_candles
    )
    projection = build_comparative_universe_projection(
        event_spec_id=contract.event_spec_id,
        universe_version_id=universe_version_id,
        strategy_group_id=contract.strategy_group_id,
        exchange_instrument_ids=members,
        closed_bar_time_ms=closed_bar_time_ms,
        lookback_bars=8,
        freshness_window_ms=contract.freshness_window_ms,
        member_windows=tuple(
            ComparativeMemberWindow(
                exchange_instrument_id=member,
                candles_1h=candles,
            )
            for member in members
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await uow.strategy_universes.save_comparative_projection(
            projection
        )


class _CurrentUniverseSnapshot(TypedDict):
    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    lifecycle_state: str
    activation_generation: int
    activated_at_ms: int


class ActivationSnapshot(TypedDict):
    current: _CurrentUniverseSnapshot
    versions: tuple[tuple[str, str, object, object], ...]
    scopes: tuple[tuple[str, str, str, bool, bool, int], ...]
    scope_projections: tuple[dict[str, object], ...]
    side_effect_counts: tuple[int, ...]


async def activation_snapshot(
    engine: AsyncEngine,
    *,
    event_spec_id: str,
) -> ActivationSnapshot:
    async with engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(strategy_universe_current).where(
                    strategy_universe_current.c.event_spec_id
                    == event_spec_id
                )
            )
        ).mappings().one()
        versions = tuple(
            (
                str(row["universe_version_id"]),
                str(row["lifecycle_state"]),
                row["activated_at_ms"],
                row["retired_at_ms"],
            )
            for row in (
                await connection.execute(
                    sa.select(strategy_universe_versions)
                    .where(
                        strategy_universe_versions.c.event_spec_id
                        == event_spec_id
                    )
                    .order_by(
                        strategy_universe_versions.c.universe_version
                    )
                )
            ).mappings()
        )
        scope_rows = (
            await connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.event_spec_id
                    == event_spec_id
                )
                .order_by(
                    runtime_scopes_current.c.universe_version_id,
                    runtime_scopes_current.c.exchange_instrument_id,
                )
            )
        ).mappings().all()
        scopes = tuple(
            (
                str(row["universe_version_id"]),
                str(row["exchange_instrument_id"]),
                str(row["lifecycle_state"]),
                bool(row["observation_enabled"]),
                bool(row["entry_enabled"]),
                int(row["scope_version"]),
            )
            for row in scope_rows
        )
        side_effect_counts = tuple(
            int(value)
            for value in (
                await connection.execute(
                    sa.text(
                        "SELECT "
                        "(SELECT count(*) FROM brc_signal_events), "
                        "(SELECT count(*) FROM brc_capacity_claims), "
                        "(SELECT count(*) FROM brc_trade_tickets), "
                        "(SELECT count(*) FROM brc_exchange_commands), "
                        "(SELECT count(*) FROM brc_trade_events)"
                    )
                )
            ).one()
        )
    return {
        "current": {
            "event_spec_id": str(current["event_spec_id"]),
            "universe_version_id": str(current["universe_version_id"]),
            "semantic_digest": str(current["semantic_digest"]),
            "lifecycle_state": str(current["lifecycle_state"]),
            "activation_generation": int(current["activation_generation"]),
            "activated_at_ms": int(current["activated_at_ms"]),
        },
        "versions": versions,
        "scopes": scopes,
        "scope_projections": tuple(dict(row) for row in scope_rows),
        "side_effect_counts": side_effect_counts,
    }


async def _install(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
    members: tuple[str, ...],
    installed_at_ms: int,
) -> str:
    async with PostgresKernelUnitOfWork(engine) as uow:
        installed = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=contract.event_spec_id,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                owner_policy_id=OWNER_POLICY_ID,
                exchange_instrument_ids=members,
                installed_at_ms=installed_at_ms,
            ),
        )
    assert installed.universe is not None
    return installed.universe.universe_version_id


def _database_url(database_name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return (
        f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}"
        f"/{database_name}"
    )


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
