from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.observe_strategy_scope import ObservationStatus
from src.trading_kernel.application.project_shadow_outcome import (
    project_claimed_shadow_outcome,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import ShadowOutcomeSpec
from src.trading_kernel.infrastructure.pg_models import shadow_outcomes_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


@pytest_asyncio.fixture
async def shadow_engine() -> AsyncGenerator[AsyncEngine, None]:
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    engine = create_async_engine(_database_url(database_name))
    try:
        _run_alembic(_database_url(database_name), "upgrade", "head")
        async with engine.begin() as connection:
            await connection.run_sync(shadow_outcomes_current.create)
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
async def test_pending_shadow_is_idempotent_and_terminal_retry_is_a_noop(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)
        await uow.shadow_outcomes.add_pending(spec)

    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        claim = await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=10,
            lease_until_ms=20,
        )
    assert claim == spec

    candles = (_candle(close_time_ms=10, high=Decimal(110), low=Decimal(97)),)
    await project_claimed_shadow_outcome(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        claim,
        candles,
        worker_id="shadow-worker",
        completed_at_ms=11,
    )
    await project_claimed_shadow_outcome(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        claim,
        candles,
        worker_id="shadow-worker",
        completed_at_ms=12,
    )

    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        assert await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=30,
            lease_until_ms=40,
        ) is None


@pytest.mark.asyncio
async def test_idle_worker_fetches_one_hour_shadow_outside_uow_with_24_limit(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)
    source = _RecordingMarketSource(shadow_engine)

    result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        source,
        _worker_request(),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert result.shadow_outcome_id == spec.shadow_outcome_id
    assert [(request.timeframe, request.limit) for request in source.requests] == [
        ("1h", 24)
    ]
    assert source.checked_transaction_boundary is True


@pytest.mark.asyncio
async def test_idle_worker_processes_at_most_one_shadow_and_caps_15m_at_96(
    shadow_engine: AsyncEngine,
) -> None:
    first = _spec(admission_decision_id="admission:first")
    second = _spec(
        admission_decision_id="admission:second",
        timeframe="15m",
    )
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(first)
        await uow.shadow_outcomes.add_pending(second)
    source = _RecordingMarketSource(shadow_engine)

    first_result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        source,
        _worker_request(),
    )
    second_result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        source,
        _worker_request(now_ms=11),
    )

    assert first_result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert second_result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert [(request.timeframe, request.limit) for request in source.requests] == [
        ("1h", 24),
        ("15m", 96),
    ]


@pytest.mark.asyncio
async def test_due_strategy_scope_wins_over_shadow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shadow_repository = _FakeShadowRepository()
    scope_claim = SimpleNamespace(
        runtime_scope_id="scope:due",
        trigger_candle_close_time_ms=10,
        observation_generation=1,
        timeframe="1h",
    )
    factory = _FakeUowFactory(scope_claim, shadow_repository)
    source = _FakeMarketSource()

    async def observed(*args, **kwargs) -> SimpleNamespace:
        return SimpleNamespace(status=ObservationStatus.NO_SIGNAL, detector_reason="")

    monkeypatch.setattr(
        "src.trading_kernel.interfaces.observation_worker.observe_strategy_scope",
        observed,
    )
    result = await run_observation_worker_once(factory, source, _worker_request())

    assert result.status is ObservationWorkerStatus.OBSERVED
    assert shadow_repository.claim_calls == 0
    assert source.requests == []


def _spec(
    *,
    admission_decision_id: str = "admission:test",
    timeframe: str = "1h",
) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id=f"shadow:{admission_decision_id}",
        admission_decision_id=admission_decision_id,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        timeframe=timeframe,
        entry_reference_price=Decimal(100),
        initial_stop_price=Decimal(95),
        horizon_start_ms=1,
        horizon_end_ms=10,
        created_at_ms=1,
    )


def _candle(*, close_time_ms: int, high: Decimal, low: Decimal) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=close_time_ms - 1,
        close_time_ms=close_time_ms,
        open=Decimal(100),
        high=high,
        low=low,
        close=Decimal(100),
        volume=Decimal(1),
    )


def _worker_request(*, now_ms: int = 10) -> ObservationWorkerRequest:
    return ObservationWorkerRequest(
        worker_id="shadow-worker",
        runtime_commit="test-commit",
        schema_revision="0002_sor_v3_strategy_group_capacity",
        now_ms=now_ms,
        lease_until_ms=now_ms + 10,
        timeout_seconds=1,
        retry_interval_ms=1,
    )


class _RecordingMarketSource:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.requests = []
        self.checked_transaction_boundary = False

    async def fetch_closed_candles(self, request):
        self.requests.append(request)
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
        self.checked_transaction_boundary = True
        return (
            _candle(
                close_time_ms=request.closed_at_ms,
                high=Decimal(110),
                low=Decimal(97),
            ),
        )


class _FakeUow:
    def __init__(self, scope_claim, shadow_repository) -> None:
        self.signals = SimpleNamespace(
            claim_next_observation_scope=self._claim_scope,
            schedule_observation_scope=self._schedule_scope,
        )
        self.shadow_outcomes = shadow_repository
        self._scope_claim = scope_claim

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def _claim_scope(self, **kwargs):
        claim = self._scope_claim
        self._scope_claim = None
        return claim

    async def _schedule_scope(self, **kwargs) -> None:
        return None


class _FakeUowFactory:
    def __init__(self, scope_claim, shadow_repository) -> None:
        self._scope_claim = scope_claim
        self._shadow_repository = shadow_repository

    def __call__(self) -> _FakeUow:
        uow = _FakeUow(self._scope_claim, self._shadow_repository)
        self._scope_claim = None
        return uow


class _FakeShadowRepository:
    claim_calls = 0

    async def claim_one_due(self, **kwargs):
        self.claim_calls += 1


class _FakeMarketSource:
    def __init__(self) -> None:
        self.requests = []

    async def fetch_closed_candles(self, request):
        self.requests.append(request)
        return ()
