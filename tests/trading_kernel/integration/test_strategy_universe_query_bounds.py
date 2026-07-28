from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from typing import Literal
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    advance_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    runtime_scopes_current,
    strategy_universe_current,
    strategy_universe_versions,
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

RUNTIME_COMMIT = "task-13-query-bounds"
SCHEMA_REVISION: Literal["0002_crypto_strategy_universe"] = (
    "0002_crypto_strategy_universe"
)
NOW_MS = 1_800_002_000_000
READINESS_DIGEST = "sha256:" + "a" * 64
ACTIVE_MEMBERS = tuple(
    f"binance-usdm:{symbol}USDT:perpetual"
    for symbol in (
        "BTC",
        "ETH",
        "SOL",
        "OP",
        "SUI",
        "DOGE",
        "XRP",
        "ADA",
        "LINK",
        "ATOM",
    )
)
WARMING_MEMBERS = tuple(
    f"binance-usdm:{symbol}USDT:perpetual"
    for symbol in (
        "BNB",
        "LTC",
        "BCH",
        "DOT",
        "UNI",
        "AAVE",
        "NEAR",
        "FIL",
        "APT",
        "ARB",
    )
)


@pytest_asyncio.fixture
async def query_bounds_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url, "upgrade", "head")
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-query-bounds",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000_000,
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


@pytest.mark.asyncio
async def test_observation_selector_claims_one_index_backed_scope_from_70_current_rows(
    query_bounds_engine: AsyncEngine,
) -> None:
    """The 60-active plus 10-warming ceiling must not widen one cadence claim."""

    contracts = registered_strategy_contracts()
    assert len(contracts) == 6
    for contract in contracts:
        await _install_active_universe(query_bounds_engine, contract)
    await _install_warming_replacement(
        query_bounds_engine,
        contract=contracts[0],
    )

    async with query_bounds_engine.connect() as connection:
        scope_count = int(
            (
                await connection.execute(
                    sa.select(sa.func.count()).select_from(
                        runtime_scopes_current
                    )
                )
            ).scalar_one()
        )
    assert scope_count == 70

    async with PostgresKernelUnitOfWork(query_bounds_engine) as uow:
        claim = await uow.signals.claim_next_observation_scope(
            worker_id="query-bounds-observation",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    assert claim is not None

    async with query_bounds_engine.connect() as connection:
        leased_count = int(
            (
                await connection.execute(
                    sa.select(sa.func.count())
                    .select_from(runtime_scopes_current)
                    .where(
                        runtime_scopes_current.c.lease_owner
                        == "query-bounds-observation"
                    )
                )
            ).scalar_one()
        )
        plan = await _observation_selector_plan(connection)
    assert leased_count == 1
    assert "ix_brc_runtime_scopes_current_observation_due" in _plan_indexes(
        plan
    )


@pytest.mark.asyncio
async def test_activation_reads_exact_ten_member_and_scope_rows(
    query_bounds_engine: AsyncEngine,
) -> None:
    """Activation must retain its exact-member ceiling even at the hard limit."""

    contract = registered_strategy_contracts()[0]
    universe_version_id = await _install_warming_replacement(
        query_bounds_engine,
        contract=contract,
    )
    statements: list[tuple[str, object]] = []

    def _capture(
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(
        query_bounds_engine.sync_engine,
        "before_cursor_execute",
        _capture,
    )
    try:
        async with PostgresKernelUnitOfWork(query_bounds_engine) as uow:
            result = await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=universe_version_id,
                    attempted_at_ms=NOW_MS,
                ),
            )
    finally:
        event.remove(
            query_bounds_engine.sync_engine,
            "before_cursor_execute",
            _capture,
        )

    assert result.reason_code == "CERTIFICATION_MISSING"
    bounded_member_or_scope_selects = [
        parameters
        for statement, parameters in statements
        if (
            "brc_strategy_universe_members" in statement
            or "brc_runtime_scopes_current" in statement
        )
        and "LIMIT" in statement.upper()
    ]
    assert bounded_member_or_scope_selects
    assert all(
        _contains_limit_eleven(parameters)
        for parameters in bounded_member_or_scope_selects
    )


async def _install_active_universe(
    engine: AsyncEngine,
    contract: RegisteredStrategyContract,
) -> str:
    async with PostgresKernelUnitOfWork(engine) as uow:
        installed = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=contract.event_spec_id,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                owner_policy_id=OWNER_POLICY_ID,
                exchange_instrument_ids=ACTIVE_MEMBERS,
                installed_at_ms=NOW_MS - 1_000_000,
            ),
        )
    assert installed.universe is not None
    universe_version_id = installed.universe.universe_version_id
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == universe_version_id
            )
            .values(
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=2,
                warm_ready_at_ms=NOW_MS - 10_000,
                warm_readiness_digest=READINESS_DIGEST,
                warm_valid_until_ms=NOW_MS + 3_600_000,
                next_observation_due_at_ms=NOW_MS,
                updated_at_ms=NOW_MS - 10_000,
            )
        )
        await connection.execute(
            sa.update(strategy_universe_versions)
            .where(
                strategy_universe_versions.c.universe_version_id
                == universe_version_id
            )
            .values(
                lifecycle_state="active",
                activated_at_ms=NOW_MS - 10_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id=contract.event_spec_id,
                universe_version_id=universe_version_id,
                semantic_digest=installed.universe.semantic_digest,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=NOW_MS - 10_000,
            )
        )
    return universe_version_id


async def _install_warming_replacement(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
) -> str:
    async with PostgresKernelUnitOfWork(engine) as uow:
        installed = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=contract.event_spec_id,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                owner_policy_id=OWNER_POLICY_ID,
                exchange_instrument_ids=WARMING_MEMBERS,
                installed_at_ms=NOW_MS - 1_000,
            ),
        )
    assert installed.universe is not None
    return installed.universe.universe_version_id


async def _observation_selector_plan(
    connection: AsyncConnection,
) -> dict[str, object]:
    await connection.execute(sa.text("SET LOCAL enable_seqscan = off"))
    result = await connection.execute(
        sa.text(
            """
            EXPLAIN (FORMAT JSON)
            SELECT scope.runtime_scope_id
            FROM brc_runtime_scopes_current AS scope
            JOIN brc_event_specs AS event
              ON event.event_spec_id = scope.event_spec_id
            WHERE scope.observation_enabled
              AND scope.lifecycle_state IN ('warming', 'active')
              AND event.status = 'active'
              AND (
                scope.next_observation_due_at_ms IS NULL
                OR scope.next_observation_due_at_ms <= :now_ms
              )
              AND (
                scope.lease_expires_at_ms IS NULL
                OR scope.lease_expires_at_ms <= :now_ms
              )
            ORDER BY COALESCE(scope.next_observation_due_at_ms, 0),
                     scope.runtime_scope_id
            LIMIT 1
            FOR UPDATE OF scope SKIP LOCKED
            """
        ),
        {"now_ms": NOW_MS},
    )
    raw = result.scalar_one()
    assert isinstance(raw, list) and len(raw) == 1
    payload = raw[0]
    assert isinstance(payload, dict)
    plan = payload.get("Plan")
    assert isinstance(plan, dict)
    return plan


def _plan_indexes(plan: dict[str, object]) -> set[str]:
    indexes: set[str] = set()
    for node in _walk_plan(plan):
        index_name = node.get("Index Name")
        if isinstance(index_name, str):
            indexes.add(index_name)
    return indexes


def _walk_plan(plan: dict[str, object]) -> Iterator[dict[str, object]]:
    yield plan
    child_plans = plan.get("Plans", ())
    if not isinstance(child_plans, list):
        return
    for child in child_plans:
        if isinstance(child, dict):
            yield from _walk_plan(child)


def _contains_limit_eleven(parameters: object) -> bool:
    if isinstance(parameters, tuple):
        return 11 in parameters
    if isinstance(parameters, dict):
        return 11 in parameters.values()
    return False
