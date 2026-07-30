from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import AsyncGenerator
from typing import Literal
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
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.application.project_comparative_universe import (
    COMPARATIVE_FAILURE_RETRY_MS,
    comparative_member_set_digest,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.infrastructure.pg_models import (
    comparative_projection_current,
    runtime_scopes_current,
    signal_events,
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
    AVAX,
    BTC,
    ETH,
    NOW_MS,
    OP,
    SOL,
    SUI,
    mpg_long_snapshot,
)

RUNTIME_COMMIT = "task-9-test"
SCHEMA_REVISION: Literal["0001_trading_kernel_baseline_v4"] = (
    "0001_trading_kernel_baseline_v4"
)
MPG_CONTRACT = next(
    contract
    for contract in registered_strategy_contracts()
    if contract.event_id == "MPG-LONG"
)
MI_CONTRACT = next(
    contract
    for contract in registered_strategy_contracts()
    if contract.event_id == "MI-LONG"
)
MEMBERS = tuple(
    sorted(
        (
            BTC,
            ETH,
            SOL,
            AVAX,
            OP,
            SUI,
            "binance-usdm:DOGEUSDT:perpetual",
            "binance-usdm:XRPUSDT:perpetual",
        )
    )
)
TEN_MEMBERS = tuple(
    sorted(
        (
            *MEMBERS,
            "binance-usdm:ADAUSDT:perpetual",
            "binance-usdm:LINKUSDT:perpetual",
        )
    )
)


@pytest_asyncio.fixture
async def comparative_engine(request) -> AsyncGenerator[AsyncEngine, None]:
    contract, members = getattr(
        request,
        "param",
        (MPG_CONTRACT, MEMBERS),
    )
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
                    account_id="subaccount-comparative-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )
            installed = await install_strategy_universe(
                uow,
                UniverseInstallRequest(
                    event_spec_id=contract.event_spec_id,
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    owner_policy_id=OWNER_POLICY_ID,
                    exchange_instrument_ids=members,
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


class CountingMarketSource:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        invalid_member: str | None = None,
        invalid_case: str | None = None,
        check_transaction_boundary: bool = True,
    ) -> None:
        self._engine = engine
        snapshot = mpg_long_snapshot()
        self._one_hour = snapshot.candles_1h
        self._four_hour = snapshot.candles_4h
        self.calls: list[ClosedCandleRequest] = []
        self._transaction_boundary_checked = False
        self._transaction_check_lock = asyncio.Lock()
        self._invalid_member = invalid_member
        self._invalid_case = invalid_case
        self._check_transaction_boundary = check_transaction_boundary

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.calls.append(request)
        async with self._transaction_check_lock:
            if (
                self._check_transaction_boundary
                and not self._transaction_boundary_checked
            ):
                async with self._engine.connect() as connection:
                    assert int(
                        (
                            await connection.exec_driver_sql(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE datname = current_database() "
                                "AND state = 'idle in transaction'"
                            )
                        ).scalar_one()
                    ) == 0
                self._transaction_boundary_checked = True
        if request.timeframe == "1h":
            if request.exchange_instrument_id == self._invalid_member:
                if self._invalid_case == "missing":
                    return ()
                if self._invalid_case == "mixed_close":
                    return self._one_hour[:-1][-request.limit :]
                if self._invalid_case == "internal_gap":
                    return (
                        *self._one_hour[:-5],
                        *self._one_hour[-4:],
                    )[-request.limit :]
            return self._one_hour[-request.limit :]
        if request.timeframe == "4h":
            return self._four_hour[-request.limit :]
        raise AssertionError(f"unexpected timeframe: {request.timeframe}")


@pytest.mark.asyncio
async def test_eight_mpg_scopes_read_each_member_once_per_closed_bar(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(comparative_engine)
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MPG_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                )
            ).all()
        )
    assert len(scope_ids) == 8

    results = []
    for scope_id in scope_ids:
        results.append(
            await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(comparative_engine),
                source,
                ObservationRequest(
                    runtime_scope_id=scope_id,
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    trigger_candle_close_time_ms=NOW_MS,
                ),
            )
        )

    assert [result.status for result in results] == [
        ObservationStatus.WARMED
    ] * 8
    one_hour_counts = Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    )
    four_hour_counts = Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "4h"
    )
    assert one_hour_counts == Counter({member: 1 for member in MEMBERS})
    assert four_hour_counts == Counter({member: 1 for member in MEMBERS})
    async with comparative_engine.connect() as connection:
        projection = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0
    assert projection["event_spec_id"] == MPG_CONTRACT.event_spec_id
    assert projection["closed_bar_time_ms"] == NOW_MS
    assert projection["member_set_digest"] == comparative_member_set_digest(
        MEMBERS
    )
    assert len(projection["projection"]["member_windows"]) == len(MEMBERS)
    assert (
        projection["projection"]["comparative_strength"][
            "trigger_candle_close_time_ms"
        ]
        == NOW_MS
    )
    assert projection["projection_version"] == 1


@pytest.mark.parametrize(
    "invalid_case",
    ("missing", "mixed_close", "internal_gap"),
)
@pytest.mark.asyncio
async def test_incomplete_or_mixed_close_projection_fails_all_scopes_closed(
    comparative_engine: AsyncEngine,
    invalid_case: str,
) -> None:
    source = CountingMarketSource(
        comparative_engine,
        invalid_member=MEMBERS[0],
        invalid_case=invalid_case,
    )
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MPG_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                )
            ).all()
        )

    results = []
    for scope_id in scope_ids:
        results.append(
            await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(comparative_engine),
                source,
                ObservationRequest(
                    runtime_scope_id=scope_id,
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    trigger_candle_close_time_ms=NOW_MS,
                ),
            )
        )

    assert [result.status for result in results] == [
        ObservationStatus.INVALID
    ] * len(MEMBERS)
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 1 for member in MEMBERS})
    async with comparative_engine.connect() as connection:
        failure = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
        assert failure["projection_status"] == "unavailable"
        assert (
            failure["failure_reason"]
            == "comparative_projection_incomplete"
        )
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count())
            .select_from(runtime_scopes_current)
            .where(runtime_scopes_current.c.warm_closed_bar_time_ms.is_not(None))
        ) == 0


@pytest.mark.asyncio
async def test_concurrent_failed_projection_shares_one_market_read(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(
        comparative_engine,
        invalid_member=MEMBERS[0],
        invalid_case="missing",
        check_transaction_boundary=False,
    )
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MPG_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                    .limit(2)
                )
            ).all()
        )

    async def observe(scope_id: str):
        return await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(comparative_engine),
            source,
            ObservationRequest(
                runtime_scope_id=scope_id,
                runtime_commit=RUNTIME_COMMIT,
                schema_revision=SCHEMA_REVISION,
                trigger_candle_close_time_ms=NOW_MS,
            ),
        )

    results = await asyncio.gather(*(observe(scope_id) for scope_id in scope_ids))

    assert [result.status for result in results] == [
        ObservationStatus.INVALID,
        ObservationStatus.INVALID,
    ]
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 1 for member in MEMBERS})
    async with comparative_engine.connect() as connection:
        failure = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
    assert failure["projection_status"] == "unavailable"
    assert failure["projection_version"] == 1


@pytest.mark.asyncio
async def test_failed_projection_retries_once_after_bounded_backoff(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(
        comparative_engine,
        invalid_member=MEMBERS[0],
        invalid_case="missing",
    )
    async with comparative_engine.connect() as connection:
        scope_id = str(
            await connection.scalar(
                sa.select(runtime_scopes_current.c.runtime_scope_id)
                .where(
                    runtime_scopes_current.c.event_spec_id
                    == MPG_CONTRACT.event_spec_id
                )
                .order_by(runtime_scopes_current.c.runtime_scope_id)
                .limit(1)
            )
        )

    async def observe(*, attempted_at_ms: int):
        return await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(comparative_engine),
            source,
            ObservationRequest(
                runtime_scope_id=scope_id,
                runtime_commit=RUNTIME_COMMIT,
                schema_revision=SCHEMA_REVISION,
                trigger_candle_close_time_ms=NOW_MS,
                attempted_at_ms=attempted_at_ms,
            ),
        )

    first = await observe(attempted_at_ms=NOW_MS)
    before_retry = await observe(
        attempted_at_ms=NOW_MS + COMPARATIVE_FAILURE_RETRY_MS - 1
    )
    assert first.status is ObservationStatus.INVALID
    assert before_retry.status is ObservationStatus.INVALID
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 1 for member in MEMBERS})

    source._invalid_member = None
    recovered = await observe(
        attempted_at_ms=NOW_MS + COMPARATIVE_FAILURE_RETRY_MS
    )

    assert recovered.status is ObservationStatus.WARMED
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 2 for member in MEMBERS})
    async with comparative_engine.connect() as connection:
        projection = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
    assert projection["projection_status"] == "ready"
    assert projection["failure_reason"] is None
    assert projection["projection_version"] == 2


@pytest.mark.asyncio
async def test_projection_member_digest_drift_is_not_consumed(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(comparative_engine)
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MPG_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                    .limit(2)
                )
            ).all()
        )
    first = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(comparative_engine),
        source,
        ObservationRequest(
            runtime_scope_id=scope_ids[0],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )
    assert first.status is ObservationStatus.WARMED
    corrupted_digest = "sha256:" + ("0" * 64)
    async with comparative_engine.begin() as connection:
        await connection.execute(
            sa.update(comparative_projection_current).values(
                member_set_digest=corrupted_digest
            )
        )

    second = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(comparative_engine),
        source,
        ObservationRequest(
            runtime_scope_id=scope_ids[1],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )

    assert second.status is ObservationStatus.INVALID
    assert second.detector_reason == "comparative_projection_invalid"
    async with comparative_engine.connect() as connection:
        projection = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
        second_scope = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id == scope_ids[1]
                )
            )
        ).mappings().one()
        assert projection["member_set_digest"] == corrupted_digest
        assert projection["projection_version"] == 1
        assert second_scope["warm_closed_bar_time_ms"] is None
        assert second_scope["warm_readiness_digest"] is None
        assert second_scope["warm_valid_until_ms"] is None
        assert (
            await connection.scalar(
                sa.select(sa.func.count()).select_from(signal_events)
            )
            == 0
        )


@pytest.mark.parametrize(
    "comparative_engine",
    [(MI_CONTRACT, TEN_MEMBERS)],
    indirect=True,
)
@pytest.mark.asyncio
async def test_ten_member_mi_projection_reads_each_member_once(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(comparative_engine)
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MI_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                )
            ).all()
        )
    assert len(scope_ids) == len(TEN_MEMBERS)

    results = []
    for scope_id in scope_ids:
        results.append(
            await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(comparative_engine),
                source,
                ObservationRequest(
                    runtime_scope_id=scope_id,
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    trigger_candle_close_time_ms=NOW_MS,
                ),
            )
        )

    assert [result.status for result in results] == [
        ObservationStatus.WARMED
    ] * len(TEN_MEMBERS)
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 1 for member in TEN_MEMBERS})
    assert all(request.timeframe != "4h" for request in source.calls)
    async with comparative_engine.connect() as connection:
        projection = (
            await connection.execute(
                sa.select(comparative_projection_current)
            )
        ).mappings().one()
    assert len(projection["projection"]["member_windows"]) == len(
        TEN_MEMBERS
    )
    assert projection["projection_version"] == 1


@pytest.mark.asyncio
async def test_concurrent_scopes_coalesce_one_projection_market_read(
    comparative_engine: AsyncEngine,
) -> None:
    source = CountingMarketSource(
        comparative_engine,
        check_transaction_boundary=False,
    )
    async with comparative_engine.connect() as connection:
        scope_ids = tuple(
            str(value)
            for value in (
                await connection.scalars(
                    sa.select(runtime_scopes_current.c.runtime_scope_id)
                    .where(
                        runtime_scopes_current.c.event_spec_id
                        == MPG_CONTRACT.event_spec_id
                    )
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                    .limit(2)
                )
            ).all()
        )

    async def observe(scope_id: str):
        return await observe_strategy_scope(
            lambda: PostgresKernelUnitOfWork(comparative_engine),
            source,
            ObservationRequest(
                runtime_scope_id=scope_id,
                runtime_commit=RUNTIME_COMMIT,
                schema_revision=SCHEMA_REVISION,
                trigger_candle_close_time_ms=NOW_MS,
            ),
        )

    results = await asyncio.gather(*(observe(scope_id) for scope_id in scope_ids))

    assert [result.status for result in results] == [
        ObservationStatus.WARMED,
        ObservationStatus.WARMED,
    ]
    assert Counter(
        request.exchange_instrument_id
        for request in source.calls
        if request.timeframe == "1h"
    ) == Counter({member: 1 for member in MEMBERS})
    async with comparative_engine.connect() as connection:
        projection_version = await connection.scalar(
            sa.select(
                comparative_projection_current.c.projection_version
            )
        )
    assert projection_version == 1
