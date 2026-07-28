from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    observe_strategy_scope,
)
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    facts_current,
    instruments,
    readiness_current,
    runtime_capabilities_current,
    runtime_scopes_current,
    signal_events,
    signal_fact_snapshots,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
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
from tests.trading_kernel.unit.detectors.fixtures import (
    AVAX,
    BTC,
    ETH,
    NOW_MS,
    OP,
    SOL,
    SUI,
    brf2_short_snapshot,
    cpm_long_snapshot,
    flat_candles,
    mpg_long_snapshot,
    sor_snapshot,
)


class FakeMarketSource:
    def __init__(
        self,
        responses: dict[tuple[str, str], tuple[ClosedCandle, ...]],
    ) -> None:
        self._responses = responses
        self.calls: list[ClosedCandleRequest] = []

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.calls.append(request)
        return self._responses.get(
            (request.exchange_instrument_id, request.timeframe),
            (),
        )


class TimeoutMarketSource:
    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        raise TimeoutError(f"timed out: {request.exchange_instrument_id}")


@pytest.mark.asyncio
async def test_observation_worker_claims_one_due_scope_and_waits_for_next_close(
    observation_engine: AsyncEngine,
) -> None:
    await _seed_sor_scope(observation_engine)
    snapshot = sor_snapshot(side=None)
    source = FakeMarketSource(
        {
            (
                snapshot.exchange_instrument_id,
                "15m",
            ): snapshot.candles_15m
        }
    )
    request = ObservationWorkerRequest(
        worker_id="observation-worker-1",
        runtime_commit="kernel-test-head",
        schema_revision="0001_initial",
        now_ms=NOW_MS,
        lease_until_ms=NOW_MS + 30_000,
        timeout_seconds=1,
        retry_interval_ms=30_000,
    )

    first = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        source,
        request,
    )
    second = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        source,
        request,
    )

    assert first.status is ObservationWorkerStatus.OBSERVED
    assert first.runtime_scope_id == "scope-sor-eth-long"
    assert first.trigger_candle_close_time_ms == NOW_MS
    assert first.observation_status is ObservationStatus.NO_SIGNAL
    assert second.status is ObservationWorkerStatus.NO_WORK
    assert len(source.calls) == 1
    async with observation_engine.connect() as connection:
        scope = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == "scope-sor-eth-long"
                )
            )
        ).mappings().one()
    assert scope["next_observation_due_at_ms"] == NOW_MS + 900_000
    assert scope["lease_owner"] is None
    assert scope["lease_expires_at_ms"] is None


@pytest_asyncio.fixture(name="observation_engine")
async def observation_engine_fixture() -> AsyncEngine:
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
async def test_observer_ignores_open_tail_and_appends_no_signal_history(
    observation_engine: AsyncEngine,
) -> None:
    await _seed_sor_scope(observation_engine)
    base = sor_snapshot(side=None)
    future = ClosedCandle(
        open_time_ms=NOW_MS + 1,
        close_time_ms=NOW_MS + 900_000,
        open=Decimal("101"),
        high=Decimal("104"),
        low=Decimal("100"),
        close=Decimal("103"),
        volume=Decimal("100"),
    )
    source = FakeMarketSource(
        {
            (
                base.exchange_instrument_id,
                "15m",
            ): (*base.candles_15m, future)
        }
    )

    result = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        source,
        ObservationRequest(
            runtime_scope_id="scope-sor-eth-long",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )

    assert result.status is ObservationStatus.NO_SIGNAL
    assert result.signal_event_id is None
    assert len(source.calls) == 1
    assert source.calls[0].timeframe == "15m"
    assert source.calls[0].limit == 120
    async with observation_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_fact_snapshots)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(facts_current)
        ) == 3
        readiness = (
            await connection.execute(sa.select(readiness_current))
        ).mappings().one()
    assert readiness["readiness_state"] == "signal_absent"
    assert readiness["first_blocker"] == "signal_absent"


@pytest.mark.asyncio
async def test_triggered_observation_persists_one_stable_strategy_signal(
    observation_engine: AsyncEngine,
) -> None:
    await _seed_sor_scope(observation_engine)
    snapshot = sor_snapshot(side="long")
    source = FakeMarketSource(
        {
            (
                snapshot.exchange_instrument_id,
                "15m",
            ): snapshot.candles_15m
        }
    )
    request = ObservationRequest(
        runtime_scope_id="scope-sor-eth-long",
        runtime_commit="kernel-test-head",
        schema_revision="0001_initial",
        trigger_candle_close_time_ms=NOW_MS,
    )

    first = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        source,
        request,
    )
    duplicate = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        source,
        request,
    )

    assert first.status is ObservationStatus.SIGNAL_CREATED
    assert duplicate.status is ObservationStatus.DUPLICATE_SIGNAL
    assert first.signal_event_id == duplicate.signal_event_id
    assert first.signal_event_id is not None
    async with PostgresKernelUnitOfWork(observation_engine) as uow:
        signal = await uow.signals.get(first.signal_event_id)
        facts = await uow.signals.get_fact_snapshots(first.signal_event_id)
        readiness = await uow.signals.get_readiness("scope-sor-eth-long")
    assert signal is not None
    assert signal.facts == facts
    assert signal.occurred_at_ms == NOW_MS
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    async with observation_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 1
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_fact_snapshots)
        ) == 3
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_tickets)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands)
        ) == 0


@pytest.mark.asyncio
async def test_market_timeout_fails_closed_as_observation_unavailable(
    observation_engine: AsyncEngine,
) -> None:
    await _seed_sor_scope(observation_engine)

    result = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(observation_engine),
        TimeoutMarketSource(),
        ObservationRequest(
            runtime_scope_id="scope-sor-eth-long",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )

    assert result.status is ObservationStatus.INVALID
    assert result.detector_reason == "market_snapshot_unavailable"
    async with observation_engine.connect() as connection:
        readiness = (
            await connection.execute(sa.select(readiness_current))
        ).mappings().one()
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0
    assert readiness["readiness_state"] == "blocked"
    assert readiness["first_blocker"] == "observation_unavailable"


@pytest.mark.asyncio
async def test_all_six_registered_events_produce_signals_through_observation(
    observation_engine: AsyncEngine,
) -> None:
    await _seed_six_scopes(observation_engine)
    cpm = cpm_long_snapshot()
    mpg = mpg_long_snapshot()
    brf2 = brf2_short_snapshot()
    sor_long = sor_snapshot(side="long").model_copy(
        update={"exchange_instrument_id": AVAX}
    )
    sor_short = sor_snapshot(side="short").model_copy(
        update={"exchange_instrument_id": BTC}
    )
    peer_1h = flat_candles(13, 3_600_000)
    source = FakeMarketSource(
        {
            (ETH, "1h"): cpm.candles_1h,
            (ETH, "4h"): cpm.candles_4h,
            (SOL, "1h"): mpg.candles_1h,
            (SOL, "4h"): mpg.candles_4h,
            (OP, "1h"): peer_1h,
            (AVAX, "1h"): peer_1h,
            (SUI, "1h"): peer_1h,
            (BTC, "1h"): brf2.candles_1h,
            (BTC, "4h"): brf2.candles_4h,
            (AVAX, "15m"): sor_long.candles_15m,
            (BTC, "15m"): sor_short.candles_15m,
        }
    )
    scope_ids = (
        "scope-cpm-eth-long",
        "scope-mpg-sol-long",
        "scope-mi-sol-long",
        "scope-sor-avax-long",
        "scope-sor-btc-short",
        "scope-brf2-btc-short",
    )

    results = []
    for scope_id in scope_ids:
        results.append(
            await observe_strategy_scope(
                lambda: PostgresKernelUnitOfWork(observation_engine),
                source,
                ObservationRequest(
                    runtime_scope_id=scope_id,
                    runtime_commit="kernel-test-head",
                    schema_revision="0001_initial",
                    trigger_candle_close_time_ms=NOW_MS,
                ),
            )
        )

    assert [item.status for item in results] == [
        ObservationStatus.SIGNAL_CREATED,
    ] * 6
    assert len({item.signal_event_id for item in results}) == 6
    async with observation_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 6
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_fact_snapshots)
        ) == 19
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(facts_current)
        ) == 19


async def _seed_sor_scope(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=NOW_MS - 1)
    event_spec_id = "event_spec:SOR-001:SOR-LONG:v2"
    universe_version_id, universe_digest = _universe_identity(event_spec_id)
    async with engine.begin() as connection:
        await _seed_active_universe(
            connection,
            strategy_group_id="SOR-001",
            event_spec_id=event_spec_id,
            universe_version_id=universe_version_id,
            universe_digest=universe_digest,
            members=(ETH,),
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="scope-sor-eth-long",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v2",
                event_spec_id=event_spec_id,
                runtime_profile_id="profile-observation-only",
                owner_policy_id="policy-observation-only",
                exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
                position_side="long",
                universe_version_id=universe_version_id,
                universe_semantic_digest=universe_digest,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=1,
                warm_ready_at_ms=NOW_MS - 1,
                warm_readiness_digest=universe_digest,
                warm_valid_until_ms=NOW_MS + 1,
                updated_at_ms=NOW_MS - 1,
            )
        )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_initial",
                certification={},
                updated_at_ms=NOW_MS - 1,
            )
        )


async def _seed_six_scopes(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=NOW_MS - 1)
    rows = (
        (
            "scope-cpm-eth-long",
            "CPM-RO-001",
            "sgv:CPM-RO-001:v2",
            "event_spec:CPM-RO-001:CPM-LONG:v2",
            ETH,
            "long",
            (ETH,),
        ),
        (
            "scope-mpg-sol-long",
            "MPG-001",
            "sgv:MPG-001:v2",
            "event_spec:MPG-001:MPG-LONG:v2",
            SOL,
            "long",
            (SOL, OP, AVAX, SUI),
        ),
        (
            "scope-mi-sol-long",
            "MI-001",
            "sgv:MI-001:v2",
            "event_spec:MI-001:MI-LONG:v2",
            SOL,
            "long",
            (SOL, OP, AVAX, SUI),
        ),
        (
            "scope-sor-avax-long",
            "SOR-001",
            "sgv:SOR-001:v2",
            "event_spec:SOR-001:SOR-LONG:v2",
            AVAX,
            "long",
            (AVAX,),
        ),
        (
            "scope-sor-btc-short",
            "SOR-001",
            "sgv:SOR-001:v2",
            "event_spec:SOR-001:SOR-SHORT:v2",
            BTC,
            "short",
            (BTC,),
        ),
        (
            "scope-brf2-btc-short",
            "BRF2-001",
            "sgv:BRF2-001:v2",
            "event_spec:BRF2-001:BRF2-SHORT:v2",
            BTC,
            "short",
            (BTC,),
        ),
    )
    async with engine.begin() as connection:
        for (
            runtime_scope_id,
            strategy_group_id,
            strategy_version_id,
            event_spec_id,
            exchange_instrument_id,
            position_side,
            members,
        ) in rows:
            universe_version_id, universe_digest = _universe_identity(event_spec_id)
            await _seed_active_universe(
                connection,
                strategy_group_id=strategy_group_id,
                event_spec_id=event_spec_id,
                universe_version_id=universe_version_id,
                universe_digest=universe_digest,
                members=members,
            )
            await connection.execute(
                sa.insert(runtime_scopes_current).values(
                    runtime_scope_id=runtime_scope_id,
                    strategy_group_id=strategy_group_id,
                    strategy_version_id=strategy_version_id,
                    event_spec_id=event_spec_id,
                    runtime_profile_id="profile-observation-only",
                    owner_policy_id="policy-observation-only",
                    exchange_instrument_id=exchange_instrument_id,
                    position_side=position_side,
                    universe_version_id=universe_version_id,
                    universe_semantic_digest=universe_digest,
                    lifecycle_state="active",
                    observation_enabled=True,
                    entry_enabled=True,
                    scope_version=1,
                    warm_ready_at_ms=NOW_MS - 1,
                    warm_readiness_digest=universe_digest,
                    warm_valid_until_ms=NOW_MS + 1,
                    updated_at_ms=NOW_MS - 1,
                )
            )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_initial",
                certification={},
                updated_at_ms=NOW_MS - 1,
            )
        )


def _universe_identity(event_spec_id: str) -> tuple[str, str]:
    return (
        f"universe:test:{event_spec_id}",
        f"sha256:{sha256(event_spec_id.encode()).hexdigest()}",
    )


async def _seed_active_universe(
    connection,
    *,
    strategy_group_id: str,
    event_spec_id: str,
    universe_version_id: str,
    universe_digest: str,
    members: tuple[str, ...],
) -> None:
    for member in members:
        await connection.execute(
            pg_insert(instruments)
            .values(
                exchange_instrument_id=member,
                venue_id="binance-usdm",
                asset_class="crypto",
                venue_symbol=member.split(":")[1],
                contract_kind="perpetual",
                status="active",
            )
            .on_conflict_do_nothing(
                index_elements=[instruments.c.exchange_instrument_id]
            )
        )
    await connection.execute(
        sa.insert(strategy_universe_versions).values(
            universe_version_id=universe_version_id,
            strategy_group_id=strategy_group_id,
            event_spec_id=event_spec_id,
            universe_version=1,
            semantic_digest=universe_digest,
            lifecycle_state="active",
            installed_at_ms=NOW_MS - 1,
            activated_at_ms=NOW_MS - 1,
        )
    )
    await connection.execute(
        sa.insert(strategy_universe_members),
        [
            {
                "universe_version_id": universe_version_id,
                "exchange_instrument_id": member,
            }
            for member in members
        ],
    )
    await connection.execute(
        sa.insert(strategy_universe_current).values(
            event_spec_id=event_spec_id,
            universe_version_id=universe_version_id,
            semantic_digest=universe_digest,
            lifecycle_state="active",
            activation_generation=1,
            activated_at_ms=NOW_MS - 1,
        )
    )
