from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
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
from src.trading_kernel.application.certify_universe_instrument import (
    CertifyUniverseInstrumentRequest,
    certify_universe_instrument,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseConfigurationRequest,
    configure_strategy_universe,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    runtime_scopes_current,
    strategy_universe_versions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    ADMIN_DSN,
    SAFE_DATABASE,
    RecordingReadonlyCertificationSource,
    _database_url,
    _run_alembic,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    NOW_MS,
    cpm_long_snapshot,
    sor_snapshot,
)

RUNTIME_COMMIT = "task-13-query-bounds"
SCHEMA_REVISION = "0003_portfolio_admission_observability"
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
            await arm_acceptance_policy(
                uow,
                ArmAcceptancePolicyRequest(armed_at_ms=NOW_MS - 9_999_999),
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
async def test_observation_selector_claims_one_from_real_70_scope_lifecycle(
    query_bounds_engine: AsyncEngine,
) -> None:
    """Official configure/certify/warm/activate creates the bounded shape."""

    contracts = registered_strategy_contracts()
    assert len(contracts) == 6
    for contract in contracts:
        await _configure_certify_warm_and_activate(
            query_bounds_engine,
            contract=contract,
        )
    await _configure(
        query_bounds_engine,
        contract=contracts[0],
        members=WARMING_MEMBERS,
    )

    async with query_bounds_engine.connect() as connection:
        states = {
            str(lifecycle_state): int(count)
            for lifecycle_state, count in (
                await connection.execute(
                    sa.select(
                        runtime_scopes_current.c.lifecycle_state,
                        sa.func.count(),
                    ).group_by(runtime_scopes_current.c.lifecycle_state)
                )
            ).all()
        }
        active_not_warm = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.lifecycle_state == "active",
                    runtime_scopes_current.c.warm_closed_bar_time_ms.is_(None),
                )
            )
            or 0
        )
        current_active_versions = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.lifecycle_state == "active"
                )
            )
            or 0
        )
    assert states == {"active": 60, "warming": 10}
    assert active_not_warm == 0
    assert current_active_versions == 6

    captured = _capture_claim_statement(query_bounds_engine)
    try:
        async with PostgresKernelUnitOfWork(query_bounds_engine) as uow:
            claim = await uow.signals.claim_next_observation_scope(
                worker_id="query-bounds-observation",
                now_ms=NOW_MS,
                lease_until_ms=NOW_MS + 60_000,
            )
    finally:
        captured.detach()
    assert claim is not None
    assert captured.statement is not None
    assert captured.parameters is not None

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
        plan = await _captured_claim_plan(
            connection,
            statement=captured.statement,
            parameters=captured.parameters,
        )
    assert leased_count == 1
    assert "ix_brc_runtime_scopes_current_observation_due" in _plan_indexes(
        plan
    )


@pytest.mark.asyncio
async def test_activation_member_and_scope_selects_are_all_limited_to_eleven(
    query_bounds_engine: AsyncEngine,
) -> None:
    """No activation member or scope read may widen beyond the hard cap."""

    contract = registered_strategy_contracts()[0]
    universe_version_id = await _configure(
        query_bounds_engine,
        contract=contract,
        members=WARMING_MEMBERS,
    )
    async with PostgresKernelUnitOfWork(query_bounds_engine) as uow:
        due_certification = (
            await uow.strategy_universes.peek_next_due_instrument_certification_action(
                now_ms=NOW_MS
            )
        )
    assert due_certification is not None
    assert due_certification.due_at_ms <= NOW_MS
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
    member_or_scope_selects = [
        (statement, parameters)
        for statement, parameters in statements
        if (
            "brc_strategy_universe_members" in statement
            or "brc_runtime_scopes_current" in statement
        )
    ]
    assert member_or_scope_selects
    assert all(
        "LIMIT" in statement.upper() and _contains_limit_eleven(parameters)
        for statement, parameters in member_or_scope_selects
    )


async def _configure_certify_warm_and_activate(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
) -> None:
    universe_version_id = await _configure(
        engine,
        contract=contract,
        members=ACTIVE_MEMBERS,
    )
    async with engine.connect() as connection:
        warming_scope_count = int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id,
                    runtime_scopes_current.c.lifecycle_state == "warming",
                )
            )
            or 0
        )
    assert warming_scope_count == len(ACTIVE_MEMBERS)
    certification_source = RecordingReadonlyCertificationSource(engine)
    for _ in ACTIVE_MEMBERS:
        async with PostgresKernelUnitOfWork(engine) as uow:
            target = await uow.strategy_universes.claim_due_instrument_certification(
                worker_id="query-bounds-certification-worker",
                now_ms=NOW_MS,
                lease_until_ms=NOW_MS + 60_000,
            )
        if target is None:
            break
        certified = await certify_universe_instrument(
            lambda: PostgresKernelUnitOfWork(engine),
            certification_source,
            CertifyUniverseInstrumentRequest(
                target=target,
                now_ms=NOW_MS,
                timeout_seconds=1,
                required_leverage=5,
                required_margin_mode="cross",
                valid_for_ms=60_000,
                eligible_check_interval_ms=60_000,
                owner_action_check_interval_ms=300_000,
                transient_retry_interval_ms=30_000,
            ),
        )
        assert certified.certification.status == "eligible"

    source = _WorkflowMarketSource(contract=contract)
    for _ in ACTIVE_MEMBERS:
        observed = await run_observation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            source,
            ObservationWorkerRequest(
                worker_id="query-bounds-observation-worker",
                runtime_commit=RUNTIME_COMMIT,
                schema_revision=SCHEMA_REVISION,
                now_ms=NOW_MS,
                lease_until_ms=NOW_MS + 60_000,
                timeout_seconds=1,
                retry_interval_ms=10_000,
            ),
        )
        assert observed.status is ObservationWorkerStatus.OBSERVED
    async with engine.connect() as connection:
        state = await connection.scalar(
            sa.select(strategy_universe_versions.c.lifecycle_state).where(
                strategy_universe_versions.c.universe_version_id
                == universe_version_id
            )
        )
    assert state == "active"
    assert certification_source.mutation_calls == []


async def _configure(
    engine: AsyncEngine,
    *,
    contract: RegisteredStrategyContract,
    members: tuple[str, ...],
) -> str:
    async with PostgresKernelUnitOfWork(engine) as uow:
        configured = await configure_strategy_universe(
            uow,
            UniverseConfigurationRequest(
                runtime_profile_id=RUNTIME_PROFILE_ID,
                event_id=contract.event_id,
                exchange_instrument_ids=members,
                installed_at_ms=NOW_MS - 1_000,
            ),
        )
    assert configured.universe is not None
    return configured.universe.universe_version_id


class _WorkflowMarketSource:
    def __init__(
        self,
        *,
        contract: RegisteredStrategyContract,
    ) -> None:
        self._cpm = cpm_long_snapshot()
        self._sor = sor_snapshot(
            side="short" if contract.event_id == "SOR-SHORT" else "long"
        )

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        if request.timeframe == "15m":
            return self._sor.candles_15m[-request.limit :]
        if request.timeframe == "1h":
            return self._cpm.candles_1h[-request.limit :]
        if request.timeframe == "4h":
            return self._cpm.candles_4h[-request.limit :]
        raise AssertionError(f"unexpected timeframe: {request.timeframe}")


class _CapturedClaimStatement:
    statement: str | None = None
    parameters: object | None = None

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        event.listen(engine.sync_engine, "before_cursor_execute", self._capture)

    def detach(self) -> None:
        event.remove(
            self._engine.sync_engine,
            "before_cursor_execute",
            self._capture,
        )

    def _capture(
        self,
        _connection: object,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        normalized = statement.upper()
        if (
            "BRC_RUNTIME_SCOPES_CURRENT" not in normalized
            or "FOR UPDATE" not in normalized
            or "SKIP LOCKED" not in normalized
        ):
            return
        self.statement = statement
        self.parameters = parameters


def _capture_claim_statement(engine: AsyncEngine) -> _CapturedClaimStatement:
    return _CapturedClaimStatement(engine)


async def _captured_claim_plan(
    connection: AsyncConnection,
    *,
    statement: str,
    parameters: object,
) -> dict[str, object]:
    assert isinstance(parameters, tuple)
    raw_connection = await connection.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    assert driver_connection is not None
    await driver_connection.execute("SET LOCAL enable_seqscan = off")
    payload = await driver_connection.fetchval(
        "EXPLAIN (FORMAT JSON) " + statement,
        *parameters,
    )
    assert isinstance(payload, list) and len(payload) == 1
    plan = payload[0].get("Plan")
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
