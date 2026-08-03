from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    ingest_signal,
)
from src.trading_kernel.application.issue_ready_signal import (
    IssueReadySignalRequest,
    issue_ready_signal,
)
from src.trading_kernel.application.observe_strategy_scope import ObservationStatus
from src.trading_kernel.application.project_shadow_outcome import (
    project_claimed_shadow_outcome,
)
from src.trading_kernel.domain.cross_margin_stress import AccountRiskSnapshot
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeProjection,
    ShadowOutcomeSpec,
)
from src.trading_kernel.infrastructure.pg_models import (
    budget_reservations,
    capacity_claims,
    exchange_commands,
    shadow_outcomes_current,
    trade_tickets,
)
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
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _admission_snapshot,
    _seed_runtime_authority,
)
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _signal as _runtime_signal,
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
            now_ms=spec.horizon_end_ms,
            lease_until_ms=spec.horizon_end_ms + 10,
        )
    assert claim is not None
    assert claim.spec == spec

    candles = _complete_hour_candles(spec)
    await project_claimed_shadow_outcome(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        claim,
        candles,
        completed_at_ms=spec.horizon_end_ms,
    )
    await project_claimed_shadow_outcome(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        claim,
        candles,
        completed_at_ms=spec.horizon_end_ms + 1,
    )

    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        assert await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=spec.horizon_end_ms + 2,
            lease_until_ms=spec.horizon_end_ms + 3,
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
        _worker_request(now_ms=spec.horizon_end_ms),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert result.shadow_outcome_id == spec.shadow_outcome_id
    assert [(request.timeframe, request.limit) for request in source.requests] == [
        ("1h", 24)
    ]
    assert source.checked_transaction_boundary is True


@pytest.mark.asyncio
async def test_idle_worker_reads_the_frozen_historical_hour_window(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)
    source = _CompleteHistoricalSource()

    result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        source,
        _worker_request(now_ms=spec.horizon_end_ms),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert source.requests[0].since_ms == spec.horizon_start_ms
    assert source.requests[0].closed_at_ms == spec.horizon_end_ms
    assert source.requests[0].limit == 24


@pytest.mark.asyncio
async def test_idle_worker_releases_partial_historical_window_for_retry(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)

    result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        _PartialHistoricalSource(),
        _worker_request(now_ms=spec.horizon_end_ms),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_RETRY_SCHEDULED
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        claimed_again = await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=spec.horizon_end_ms,
            lease_until_ms=spec.horizon_end_ms + 10,
        )
    assert claimed_again is not None


@pytest.mark.asyncio
async def test_idle_worker_releases_empty_historical_window_for_retry(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)

    result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        _EmptyHistoricalSource(),
        _worker_request(now_ms=spec.horizon_end_ms),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_RETRY_SCHEDULED
    assert result.detail == "incomplete_historical_window"


@pytest.mark.asyncio
async def test_expired_same_worker_claim_cannot_complete_or_release_new_claim(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        stale_claim = await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=spec.horizon_end_ms,
            lease_until_ms=spec.horizon_end_ms + 1,
        )
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        replacement_claim = await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=spec.horizon_end_ms + 1,
            lease_until_ms=spec.horizon_end_ms + 10,
        )

    assert stale_claim is not None
    assert replacement_claim is not None
    assert stale_claim.claim_token != replacement_claim.claim_token
    with pytest.raises(RuntimeError, match="lost Shadow claim"):
        await project_claimed_shadow_outcome(
            lambda: PostgresKernelUnitOfWork(shadow_engine),
            stale_claim,
            _complete_hour_candles(spec),
            completed_at_ms=spec.horizon_end_ms,
        )
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        with pytest.raises(RuntimeError, match="lost Shadow claim"):
            await uow.shadow_outcomes.release_expired_claim(claim=stale_claim)
    async with shadow_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(shadow_outcomes_current).where(
                    shadow_outcomes_current.c.shadow_outcome_id
                    == spec.shadow_outcome_id
                )
            )
        ).mappings().one()
    assert row["status"] == "claimed"
    assert row["claim_token"] == replacement_claim.claim_token


@pytest.mark.asyncio
async def test_zero_risk_shadow_is_terminally_unavailable_with_explicit_reason(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec(initial_stop_price=Decimal(100))
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)

    result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        _CompleteHistoricalSource(),
        _worker_request(now_ms=spec.horizon_end_ms),
    )

    assert result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    async with shadow_engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(shadow_outcomes_current).where(
                    shadow_outcomes_current.c.shadow_outcome_id
                    == spec.shadow_outcome_id
                )
            )
        ).mappings().one()
    assert row["status"] == "unavailable"
    assert row["completion_reason"] == "zero_initial_risk_distance"
    assert row["mfe_r"] is None
    assert row["mae_r"] is None


@pytest.mark.asyncio
async def test_repository_rejects_pseudo_completed_projection(
    shadow_engine: AsyncEngine,
) -> None:
    spec = _hour_spec()
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await uow.shadow_outcomes.add_pending(spec)
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        claim = await uow.shadow_outcomes.claim_one_due(
            worker_id="shadow-worker",
            now_ms=spec.horizon_end_ms,
            lease_until_ms=spec.horizon_end_ms + 1,
        )
        assert claim is not None
        pseudo_projection = ShadowOutcomeProjection.model_construct(
            evaluation_kind="fixed_horizon_excursion_v1",
            max_favorable_price=None,
            max_adverse_price=None,
            mfe_r=None,
            mae_r=None,
            observed_through_ms=None,
        )
        with pytest.raises(ValueError, match="must be complete"):
            await uow.shadow_outcomes.complete(
                claim=claim,
                projection=pseudo_projection,
                completed_at_ms=spec.horizon_end_ms,
            )


@pytest.mark.asyncio
async def test_capacity_rejection_creates_only_one_pending_shadow_and_no_trading_authority(
    shadow_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(shadow_engine)
    signal = _runtime_signal(signal_event_id="signal-shadow-budget")
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0002_sor_v3_strategy_group_capacity",
                now_ms=1_001,
            ),
        )
    risk_values = _admission_snapshot().account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )
    risk_values.update({"available_margin": Decimal(0), "configured_leverage": 5})
    snapshot = _admission_snapshot().model_copy(
        update={"account_risk_snapshot": AccountRiskSnapshot.create(**risk_values)}
    )
    async with PostgresKernelUnitOfWork(shadow_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=snapshot,
                claim_owner="shadow-test",
                runtime_commit="kernel-test-head",
                schema_revision="0002_sor_v3_strategy_group_capacity",
                now_ms=1_002,
            ),
        )

    assert result.ticket_id is None
    async with shadow_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(shadow_outcomes_current)
        ) == 1
        for table in (
            capacity_claims,
            trade_tickets,
            budget_reservations,
            exchange_commands,
        ):
            assert await connection.scalar(
                sa.select(sa.func.count()).select_from(table)
            ) == 0


def test_shadow_metadata_closes_claim_and_terminal_shapes() -> None:
    checks = {
        str(constraint.sqltext)
        for constraint in shadow_outcomes_current.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }

    assert any("claim_token IS NOT NULL" in check for check in checks)
    assert any("status = 'completed'" in check and "mfe_r IS NOT NULL" in check for check in checks)
    assert any("status = 'unavailable'" in check and "mfe_r IS NULL" in check for check in checks)


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
        _worker_request(now_ms=second.horizon_end_ms),
    )
    second_result = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(shadow_engine),
        source,
        _worker_request(now_ms=first.horizon_end_ms),
    )

    assert first_result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert second_result.status is ObservationWorkerStatus.SHADOW_COMPLETED
    assert [(request.timeframe, request.limit) for request in source.requests] == [
        ("15m", 96),
        ("1h", 24),
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
    duration_ms = 3_600_000 if timeframe == "1h" else 900_000
    horizon_start_ms = duration_ms
    horizon_end_ms = horizon_start_ms + (24 if timeframe == "1h" else 96) * duration_ms
    return ShadowOutcomeSpec(
        shadow_outcome_id=f"shadow:{admission_decision_id}",
        admission_decision_id=admission_decision_id,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        timeframe=timeframe,
        entry_reference_price=Decimal(100),
        initial_stop_price=Decimal(95),
        horizon_start_ms=horizon_start_ms,
        horizon_end_ms=horizon_end_ms,
        created_at_ms=1,
    )


def _hour_spec(
    *,
    initial_stop_price: Decimal = Decimal(95),
) -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(
        shadow_outcome_id="shadow:historical-hour",
        admission_decision_id="admission:historical-hour",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        timeframe="1h",
        entry_reference_price=Decimal(100),
        initial_stop_price=initial_stop_price,
        horizon_start_ms=3_600_000,
        horizon_end_ms=90_000_000,
        created_at_ms=1,
    )


def _complete_hour_candles(spec: ShadowOutcomeSpec) -> tuple[ClosedCandle, ...]:
    duration_ms = 3_600_000 if spec.timeframe == "1h" else 900_000
    return tuple(
        _candle(
            close_time_ms=close_time_ms,
            high=Decimal(110),
            low=Decimal(97),
        )
        for close_time_ms in range(
            spec.horizon_start_ms + duration_ms,
            spec.horizon_end_ms + 1,
            duration_ms,
        )
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
        return _complete_hour_candles(
            ShadowOutcomeSpec(
                shadow_outcome_id="shadow:recording",
                admission_decision_id="admission:recording",
                exchange_instrument_id=request.exchange_instrument_id,
                position_side="long",
                timeframe=request.timeframe,
                entry_reference_price=Decimal(100),
                initial_stop_price=Decimal(95),
                horizon_start_ms=request.since_ms,
                horizon_end_ms=request.closed_at_ms,
                created_at_ms=1,
            )
        )


class _CompleteHistoricalSource:
    def __init__(self) -> None:
        self.requests = []

    async def fetch_closed_candles(self, request):
        self.requests.append(request)
        return _complete_hour_candles(
            ShadowOutcomeSpec(
                shadow_outcome_id="shadow:source",
                admission_decision_id="admission:source",
                exchange_instrument_id=request.exchange_instrument_id,
                position_side="long",
                timeframe="1h",
                entry_reference_price=Decimal(100),
                initial_stop_price=Decimal(95),
                horizon_start_ms=request.since_ms,
                horizon_end_ms=request.closed_at_ms,
                created_at_ms=1,
            )
        )


class _PartialHistoricalSource(_CompleteHistoricalSource):
    async def fetch_closed_candles(self, request):
        candles = await super().fetch_closed_candles(request)
        return (*candles[:10], *candles[11:])


class _EmptyHistoricalSource:
    async def fetch_closed_candles(self, request):
        return ()


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
