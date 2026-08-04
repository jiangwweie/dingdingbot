from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import scripts.trading_kernel.bootstrap_strategy_universes as bootstrap_module
from scripts.trading_kernel.bootstrap_strategy_universes import (
    INITIAL_MEMBERS,
    BootstrapBlocked,
    bootstrap_strategy_universes,
)
from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import ObservationStatus
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.strategy_registry import (
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    instrument_certification_batch_members,
    instrument_certification_batches,
    instruments,
    runtime_scopes_current,
    signal_events,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NoTicketPositionSource,
    NoTicketVenueTruth,
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    NOW_MS,
    cpm_long_snapshot,
    sor_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")
RUNTIME_COMMIT = "strategy-universe-rehearsal"
SCHEMA_REVISION = CURRENT_SCHEMA_REVISION


class RecordingWarmMarket:
    """A readonly market boundary sufficient for all six Warming contracts."""

    def __init__(self) -> None:
        self.requests: list[ClosedCandleRequest] = []
        self.mutation_calls: list[str] = []

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.requests.append(request)
        if request.timeframe == "15m":
            return sor_snapshot(side="long").candles_15m
        if request.timeframe == "4h":
            return cpm_long_snapshot().candles_4h
        return cpm_long_snapshot().candles_1h


@dataclass
class VirtualClock:
    now: int = NOW_MS

    def read(self) -> int:
        return self.now

    def advance(self, milliseconds: int = 1) -> int:
        self.now += milliseconds
        return self.now


def test_static_batch_manifest_rejects_registry_event_version_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contracts = registered_strategy_contracts()
    drifted = contracts[0].model_copy(
        update={
            "strategy_version_id": "sgv:CPM-RO-001:v4",
            "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v4",
        }
    )
    monkeypatch.setattr(
        bootstrap_module,
        "registered_strategy_contracts",
        lambda: (drifted, *contracts[1:]),
    )

    with pytest.raises(BootstrapBlocked, match="registry_event_manifest_mismatch"):
        bootstrap_module._validate_static_manifest()


@pytest.mark.asyncio
async def test_prepared_batch_collects_the_first_worker_certification_cycle() -> None:
    """The exact Batch exists before workers can publish member evidence."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-prepare-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )

        clock = VirtualClock()
        prepared_batch_id = await bootstrap_module.prepare_certification_batch(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
        )
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)

        results = await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
            ),
        )
        completed_batches = await _completed_batch_rows(engine)
        snapshot = await _snapshot(engine)

        assert tuple(result.event_id for result in results) == tuple(
            bootstrap_module.EVENT_ORDER
        )
        assert results[0].status == "already_warming"
        assert tuple(result.status for result in results[1:]) == ("installed",) * 5
        assert len(completed_batches) == 1
        assert completed_batches[0][0] == prepared_batch_id
        assert snapshot["active_versions"] == 6
        assert snapshot["active_scopes"] == 42
        assert snapshot["completed_certification_batches"] == 1
        assert snapshot["eligible_certification_batch_members"] == 7
        assert snapshot["tickets"] == 0
        assert snapshot["commands"] == 0
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


@pytest.mark.asyncio
async def test_six_event_batch_bootstrap_is_idempotent_and_uses_worker_boundaries() -> None:
    """Prove the production batch can reach six Active Universes from an empty DB."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-bootstrap-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )

        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        sleep = _worker_driving_sleep(
            engine=engine,
            clock=clock,
            market=market,
            certification=certification,
        )

        first = await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=sleep,
        )
        first_snapshot = await _snapshot(engine)

        second = await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=sleep,
        )
        second_snapshot = await _snapshot(engine)

        assert tuple(result.event_id for result in first) == (
            "CPM-LONG",
            "MPG-LONG",
            "MI-LONG",
            "SOR-LONG",
            "SOR-SHORT",
            "BRF2-SHORT",
        )
        assert tuple(result.event_spec_id for result in first) == (
            "event_spec:CPM-RO-001:CPM-LONG:v3",
            "event_spec:MPG-001:MPG-LONG:v3",
            "event_spec:MI-001:MI-LONG:v3",
            "event_spec:SOR-001:SOR-LONG:v4",
            "event_spec:SOR-001:SOR-SHORT:v4",
            "event_spec:BRF2-001:BRF2-SHORT:v3",
        )
        assert tuple(result.status for result in second) == (
            "already_active",
        ) * 6
        assert first_snapshot == second_snapshot == {
            "active_versions": 6,
            "warming_versions": 0,
            "current_universes": 6,
            "active_scopes": 42,
            "warming_scopes": 0,
            "active_members": tuple(INITIAL_MEMBERS),
            "active_event_spec_ids": (
                "event_spec:BRF2-001:BRF2-SHORT:v3",
                "event_spec:CPM-RO-001:CPM-LONG:v3",
                "event_spec:MI-001:MI-LONG:v3",
                "event_spec:MPG-001:MPG-LONG:v3",
                "event_spec:SOR-001:SOR-LONG:v4",
                "event_spec:SOR-001:SOR-SHORT:v4",
            ),
            "completed_certification_batches": 1,
            "eligible_certification_batch_members": 7,
            "signals": 0,
            "tickets": 0,
            "commands": 0,
        }
        assert len(
            {request.target.exchange_instrument_id for request in certification.requests}
        ) == 7
        assert market.requests
        assert certification.mutation_calls == []
        assert market.mutation_calls == []
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


@pytest.mark.asyncio
async def test_readonly_certification_recomputes_batch_manifest_from_member_rows() -> None:
    """Catches accepting seven substituted members from a stale stored digest."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-drift-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )
        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
            ),
        )
        certification_now_ms = clock.read()
        baseline = await _certify(
            database_url,
            require_flat=True,
            now_ms=certification_now_ms,
        )
        assert baseline["certification_batch_pass"] is True

        async with engine.begin() as connection:
            await connection.execute(
                sa.insert(instruments).values(
                    exchange_instrument_id="binance-usdm:AVAXUSDT:perpetual",
                    venue_id="binance-usdm",
                    asset_class="crypto",
                    venue_symbol="AVAXUSDT",
                    contract_kind="perpetual",
                    status="active",
                )
            )
            batch_id = str(
                (
                    await connection.execute(
                        sa.select(
                            instrument_certification_batches.c.certification_batch_id
                        ).where(instrument_certification_batches.c.status == "completed")
                    )
                ).scalar_one()
            )
            await connection.execute(
                sa.text(
                    "ALTER TABLE brc_instrument_certification_batch_members "
                    "DISABLE TRIGGER trg_brc_certification_batch_member_result"
                )
            )
            await connection.execute(
                sa.update(instrument_certification_batch_members)
                .where(
                    instrument_certification_batch_members.c.certification_batch_id
                    == batch_id,
                    instrument_certification_batch_members.c.exchange_instrument_id
                    == "binance-usdm:ADAUSDT:perpetual",
                )
                .values(
                    exchange_instrument_id="binance-usdm:AVAXUSDT:perpetual"
                )
            )
            await connection.execute(
                sa.text(
                    "ALTER TABLE brc_instrument_certification_batch_members "
                    "ENABLE TRIGGER trg_brc_certification_batch_member_result"
                )
            )

        drifted = await _certify(
            database_url,
            require_flat=True,
            now_ms=certification_now_ms,
        )
        batch = drifted["certification_batch"]
        assert isinstance(batch, dict)
        assert batch["member_count"] == 7
        assert batch["live_manifest_digest"] != batch["manifest_digest"]
        assert drifted["certification_batch_pass"] is False
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


@pytest.mark.asyncio
async def test_six_event_batch_uses_one_total_wait_budget() -> None:
    """Catches resetting the deployment timeout independently for every Event."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-timeout-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )

        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        drive_workers = _worker_driving_sleep(
            engine=engine,
            clock=clock,
            market=market,
            certification=certification,
        )

        async def slow_worker_progress(delay_seconds: float) -> None:
            await drive_workers(delay_seconds)
            clock.advance(20_000)

        with pytest.raises(BootstrapBlocked, match=r"warming_timeout:"):
            await bootstrap_strategy_universes(
                database_url,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                now_ms=clock.read,
                wait_timeout_ms=60_000,
                poll_interval_ms=1,
                sleep=slow_worker_progress,
            )
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


@pytest.mark.asyncio
async def test_active_manifest_refresh_replaces_an_expired_batch_without_reinstalling_universes() -> None:
    """Catches Batch renewal that changes any Active Universe or runtime scope."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-refresh-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )

        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
            ),
        )
        first_batches = await _completed_batch_rows(engine)
        assert len(first_batches) == 1
        first_market_call_count = len(market.requests)
        clock.now = first_batches[0][1] + 1
        before_refresh = await _snapshot(engine)

        refreshed_batch_id = await bootstrap_module.refresh_active_certification_batch(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
        )
        retried_batch_id = await bootstrap_module.refresh_active_certification_batch(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
        )
        after_refresh = await _snapshot(engine)

        await _certification_batch_refresh_sleep(
            engine=engine,
            clock=clock,
            certification=certification,
        )(0)
        refreshed_batches = await _completed_batch_rows(engine)
        snapshot = await _snapshot(engine)

        assert retried_batch_id == refreshed_batch_id
        for key in (
            "active_versions",
            "warming_versions",
            "current_universes",
            "active_scopes",
            "warming_scopes",
            "active_members",
            "active_event_spec_ids",
            "signals",
            "tickets",
            "commands",
        ):
            assert after_refresh[key] == before_refresh[key]
        assert len(refreshed_batches) == 2
        assert refreshed_batches[0][0] != refreshed_batch_id
        assert refreshed_batches[1][0] == refreshed_batch_id
        assert refreshed_batches[1][1] > clock.read()
        assert snapshot["active_versions"] == 6
        assert snapshot["warming_versions"] == 0
        assert snapshot["completed_certification_batches"] == 2
        assert snapshot["eligible_certification_batch_members"] == 14
        assert snapshot["tickets"] == 0
        assert snapshot["commands"] == 0
        assert len(market.requests) == first_market_call_count
        assert certification.mutation_calls == []
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


@pytest.mark.asyncio
async def test_active_manifest_refresh_rejects_member_drift_and_warming_universe() -> None:
    """Catches refreshing a Batch from any non-exact current Universe state."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    engine: AsyncEngine | None = None
    avax = "binance-usdm:AVAXUSDT:perpetual"
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        database_url = _database_url(database_name)
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-batch-refresh-block-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )

        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
            ),
        )

        async with engine.begin() as connection:
            await connection.execute(
                sa.insert(instruments).values(
                    exchange_instrument_id=avax,
                    venue_id="binance-usdm",
                    asset_class="crypto",
                    venue_symbol="AVAXUSDT",
                    contract_kind="perpetual",
                    status="active",
                )
            )
            cpm_universe_version_id = str(
                await connection.scalar(
                    sa.select(strategy_universe_current.c.universe_version_id)
                    .where(
                        strategy_universe_current.c.event_spec_id
                        == bootstrap_module.EVENT_SPEC_BY_EVENT_ID["CPM-LONG"]
                    )
                )
            )
            await connection.execute(
                sa.insert(strategy_universe_members).values(
                    universe_version_id=cpm_universe_version_id,
                    exchange_instrument_id=avax,
                )
            )

        with pytest.raises(
            BootstrapBlocked,
            match="active_universe_member_manifest_mismatch:CPM-LONG",
        ):
            await bootstrap_module.refresh_active_certification_batch(
                database_url,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                now_ms=clock.read,
            )

        async with PostgresKernelUnitOfWork(engine) as uow:
            warming = await bootstrap_module.configure_strategy_universe(
                uow,
                bootstrap_module.UniverseConfigurationRequest(
                    runtime_profile_id=RUNTIME_PROFILE_ID,
                    event_id="CPM-LONG",
                    exchange_instrument_ids=(*INITIAL_MEMBERS[1:], avax),
                    installed_at_ms=clock.advance(),
                ),
            )
        assert warming.universe is not None
        assert warming.lifecycle_state == "warming"

        with pytest.raises(BootstrapBlocked, match="warming_universe_present"):
            await bootstrap_module.refresh_active_certification_batch(
                database_url,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                now_ms=clock.read,
            )
    finally:
        if engine is not None:
            await engine.dispose()
        await _drop_database(admin, database_name)
        await admin.close()


def _worker_driving_sleep(
    *,
    engine: AsyncEngine,
    clock: VirtualClock,
    market: RecordingWarmMarket,
    certification: RecordingReadonlyCertificationSource,
) -> Callable[[float], Awaitable[None]]:
    async def sleep(_delay_seconds: float) -> None:
        del _delay_seconds
        async with engine.connect() as connection:
            warming_rows = (
                await connection.execute(
                    sa.select(
                        runtime_scopes_current.c.next_observation_due_at_ms,
                        runtime_scopes_current.c.lease_owner,
                        runtime_scopes_current.c.lease_expires_at_ms,
                    )
                    .where(runtime_scopes_current.c.lifecycle_state == "warming")
                    .order_by(runtime_scopes_current.c.runtime_scope_id)
                )
            ).all()
            warming_scope_count = len(warming_rows)
        assert warming_scope_count == len(INITIAL_MEMBERS)
        for _member in INITIAL_MEMBERS:
            certification_result = await run_reconciliation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                NoTicketVenueTruth(),
                NoTicketPositionSource(),
                _reconciliation_request(clock.advance()),
                instrument_certification_source=certification,
            )
            assert certification_result.status in {
                ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
                ReconciliationWorkerStatus.NO_WORK,
            }
        observations = []
        for _member in INITIAL_MEMBERS:
            observation_result = await run_observation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                market,
                _observation_request(clock.advance()),
            )
            observations.append(observation_result.status)
            if observation_result.status is ObservationWorkerStatus.NO_WORK:
                break
            assert observation_result.status is ObservationWorkerStatus.OBSERVED
            assert observation_result.observation_status is ObservationStatus.WARMED
        assert observations == [ObservationWorkerStatus.OBSERVED] * len(INITIAL_MEMBERS), (
            warming_rows,
            clock.read(),
        )

    return sleep


def _certification_batch_refresh_sleep(
    *,
    engine: AsyncEngine,
    clock: VirtualClock,
    certification: RecordingReadonlyCertificationSource,
) -> Callable[[float], Awaitable[None]]:
    async def sleep(_delay_seconds: float) -> None:
        del _delay_seconds
        for _member in INITIAL_MEMBERS:
            certification_result = await run_reconciliation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                NoTicketVenueTruth(),
                NoTicketPositionSource(),
                _reconciliation_request(clock.advance()),
                instrument_certification_source=certification,
            )
            assert certification_result.status in {
                ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
                ReconciliationWorkerStatus.NO_WORK,
            }

    return sleep


async def _completed_batch_rows(engine: AsyncEngine) -> tuple[tuple[str, int], ...]:
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.select(
                    instrument_certification_batches.c.certification_batch_id,
                    instrument_certification_batches.c.valid_until_ms,
                )
                .where(instrument_certification_batches.c.status == "completed")
                .order_by(instrument_certification_batches.c.started_at_ms)
            )
        ).all()
    return tuple((str(row[0]), int(row[1])) for row in rows)


def _observation_request(now_ms: int) -> ObservationWorkerRequest:
    return ObservationWorkerRequest(
        worker_id="batch-bootstrap-observation",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=SCHEMA_REVISION,
        now_ms=now_ms,
        lease_until_ms=now_ms + 30_000,
        timeout_seconds=1,
        retry_interval_ms=30_000,
    )


def _reconciliation_request(now_ms: int) -> ReconciliationWorkerRequest:
    return ReconciliationWorkerRequest(
        worker_id="batch-bootstrap-reconciliation",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=SCHEMA_REVISION,
        now_ms=now_ms,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
        certification_lease_ms=60_000,
        certification_max_wait_ms=120_000,
        certification_valid_for_ms=600_000,
        certification_eligible_check_interval_ms=300_000,
        certification_owner_action_check_interval_ms=300_000,
        certification_transient_retry_interval_ms=30_000,
    )


async def _snapshot(engine: AsyncEngine) -> dict[str, object]:
    async with engine.connect() as connection:
        active_event_spec_ids = tuple(
            str(value)
            for value in (
                await connection.execute(
                    sa.select(strategy_universe_versions.c.event_spec_id)
                    .where(
                        strategy_universe_versions.c.lifecycle_state == "active"
                    )
                    .order_by(strategy_universe_versions.c.event_spec_id)
                )
            ).scalars()
        )
        active_members = tuple(
            row[0]
            for row in (
                await connection.execute(
                    sa.text(
                        "SELECT DISTINCT member.exchange_instrument_id "
                        "FROM brc_strategy_universe_members AS member "
                        "JOIN brc_strategy_universe_versions AS version "
                        "ON version.universe_version_id = member.universe_version_id "
                        "WHERE version.lifecycle_state = 'active' "
                        "ORDER BY member.exchange_instrument_id"
                    )
                )
            ).all()
        )
        return {
            "active_versions": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        strategy_universe_versions
                    ).where(strategy_universe_versions.c.lifecycle_state == "active")
                )
                or 0
            ),
            "warming_versions": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        strategy_universe_versions
                    ).where(strategy_universe_versions.c.lifecycle_state == "warming")
                )
                or 0
            ),
            "current_universes": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(strategy_universe_current)
                )
                or 0
            ),
            "active_scopes": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        runtime_scopes_current
                    ).where(runtime_scopes_current.c.lifecycle_state == "active")
                )
                or 0
            ),
            "warming_scopes": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        runtime_scopes_current
                    ).where(runtime_scopes_current.c.lifecycle_state == "warming")
                )
                or 0
            ),
            "active_members": active_members,
            "active_event_spec_ids": active_event_spec_ids,
            "completed_certification_batches": int(
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(instrument_certification_batches)
                    .where(
                        instrument_certification_batches.c.status == "completed"
                    )
                )
                or 0
            ),
            "eligible_certification_batch_members": int(
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(instrument_certification_batch_members)
                    .where(
                        instrument_certification_batch_members.c.status == "eligible"
                    )
                )
                or 0
            ),
            "signals": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(signal_events)
                )
                or 0
            ),
            "tickets": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(trade_tickets)
                )
                or 0
            ),
            "commands": int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(exchange_commands)
                )
                or 0
            ),
        }


def _database_url(database_name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str) -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            "upgrade",
            "head",
        ),
        cwd=REPO_ROOT,
        env=os.environ | {"TRADING_KERNEL_DATABASE_URL": database_url},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


async def _drop_database(admin: asyncpg.Connection, database_name: str) -> None:
    with suppress(asyncpg.UndefinedObjectError):
        await admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            database_name,
        )
    await admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
