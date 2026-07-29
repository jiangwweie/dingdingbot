from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from hashlib import sha256
from typing import Literal, TypedDict
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

import src.trading_kernel.interfaces.observation_worker as observation_worker_module
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationStatus,
    advance_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.observe_strategy_scope import (
    ObservationRequest,
    ObservationStatus,
    build_warm_readiness,
    observe_strategy_scope,
)
from src.trading_kernel.application.ports import (
    LeverageTruthRequest,
    LeverageTruthSnapshot,
    VenueTruthRequest,
    WarmReadiness,
)
from src.trading_kernel.application.runtime_facts import PositionSnapshotRequest
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot
from src.trading_kernel.infrastructure.pg_models import (
    event_specs,
    exchange_commands,
    facts_current,
    readiness_current,
    runtime_scopes_current,
    signal_events,
    strategy_universe_current,
    strategy_universe_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_signal_repository import (
    PostgresSignalRepository,
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
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    ADMIN_DSN,
    SAFE_DATABASE,
    RecordingReadonlyCertificationSource,
    _database_url,
    _run_alembic,
)
from tests.trading_kernel.integration.universe_certification_support import (
    worker_request as certification_worker_request,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    BTC,
    ETH,
    NOW_MS,
    OP,
    SOL,
    flat_candles,
    mpg_long_snapshot,
    sor_snapshot,
)

RUNTIME_COMMIT = "task-8-test"
SCHEMA_REVISION: Literal["0001_trading_kernel_baseline_v2"] = (
    "0001_trading_kernel_baseline_v2"
)
CONTRACT = next(
    item
    for item in registered_strategy_contracts()
    if item.event_id == "SOR-LONG"
)
MPG_CONTRACT = next(
    item
    for item in registered_strategy_contracts()
    if item.event_id == "MPG-LONG"
)
MEMBERS = (BTC, ETH)


@pytest_asyncio.fixture
async def warming_engine(request: pytest.FixtureRequest) -> AsyncGenerator[AsyncEngine, None]:
    contract, members = getattr(request, "param", (CONTRACT, MEMBERS))
    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE "{database_name}"')
    database_url = _database_url(database_name)
    engine: AsyncEngine | None = None
    try:
        _run_alembic(database_url, "upgrade", "head")
        engine = create_async_engine(database_url)
        await _install_warming_universe(engine, contract, members)
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


class TypedMarketFake:
    def __init__(
        self,
        engine: AsyncEngine,
        responses: Mapping[
            tuple[str, str],
            tuple[ClosedCandle, ...],
        ],
    ) -> None:
        self._engine = engine
        self._responses = responses
        self.calls: list[ClosedCandleRequest] = []
        self._transaction_boundary_checked = False
        self._transaction_check_lock = asyncio.Lock()

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.calls.append(request)
        async with self._transaction_check_lock:
            if not self._transaction_boundary_checked:
                async with self._engine.connect() as connection:
                    idle_in_transaction = int(
                        (
                            await connection.exec_driver_sql(
                                "SELECT count(*) FROM pg_stat_activity "
                                "WHERE datname = current_database() "
                                "AND state = 'idle in transaction'"
                            )
                        ).scalar_one()
                    )
                assert idle_in_transaction == 0
                self._transaction_boundary_checked = True
        return self._responses.get(
            (request.exchange_instrument_id, request.timeframe),
            (),
        )


class BlockingMarketFake:
    def __init__(
        self,
        responses: Mapping[
            tuple[str, str],
            tuple[ClosedCandle, ...],
        ],
        *,
        failure: Exception | None = None,
    ) -> None:
        self._responses = responses
        self._failure = failure
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.started.set()
        await self.release.wait()
        if self._failure is not None:
            raise self._failure
        return self._responses.get(
            (request.exchange_instrument_id, request.timeframe),
            (),
        )


class NoTicketVenueTruth:
    async def lookup_command_truth(
        self, request: VenueTruthRequest
    ) -> VenueTruthSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read order truth")

    async def read_configured_leverage(
        self, request: LeverageTruthRequest
    ) -> LeverageTruthSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read leverage truth")


class NoTicketPositionSource:
    async def read_position_snapshot(
        self, request: PositionSnapshotRequest
    ) -> PositionSnapshot:
        del request
        raise AssertionError("certification-only cadence must not read position")


class WarmingProjectionState(TypedDict):
    scope: dict[str, object]
    readiness: dict[str, object]
    facts: tuple[dict[str, object], ...]


@pytest.mark.asyncio
async def test_all_warming_members_become_ready_without_signal_chain(
    warming_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_signal_add(self, signal):
        del self, signal
        raise AssertionError("warming must never call SignalRepository.add")

    monkeypatch.setattr(
        PostgresSignalRepository,
        "add",
        forbidden_signal_add,
    )
    source = _triggering_source(warming_engine, MEMBERS)
    scopes = await _warming_scopes(warming_engine)

    first = await _observe(warming_engine, source, scopes[0]["runtime_scope_id"])

    assert first.status.value == "warmed"
    assert first.signal_event_id is None
    assert await _warm_ready_count(warming_engine) == 1
    assert len(scopes) == 2

    second = await _observe(warming_engine, source, scopes[1]["runtime_scope_id"])

    assert second.status is ObservationStatus.WARMED
    assert second.signal_event_id is None
    assert await _warm_ready_count(warming_engine) == len(MEMBERS)
    assert len(source.calls) == len(MEMBERS)
    async with warming_engine.connect() as connection:
        ready_rows = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.exchange_instrument_id,
                    runtime_scopes_current.c.universe_version_id,
                    runtime_scopes_current.c.universe_semantic_digest,
                    runtime_scopes_current.c.entry_enabled,
                    runtime_scopes_current.c.warm_closed_bar_time_ms,
                    runtime_scopes_current.c.warm_readiness_digest,
                    runtime_scopes_current.c.warm_valid_until_ms,
                ).order_by(runtime_scopes_current.c.exchange_instrument_id)
            )
        ).mappings().all()
        readiness_rows = (
            await connection.execute(
                sa.select(readiness_current).order_by(
                    readiness_current.c.runtime_scope_id
                )
            )
        ).mappings().all()
        counts = {
            "signals": await connection.scalar(
                sa.select(sa.func.count()).select_from(signal_events)
            ),
            "tickets": await connection.scalar(
                sa.select(sa.func.count()).select_from(trade_tickets)
            ),
            "commands": await connection.scalar(
                sa.select(sa.func.count()).select_from(exchange_commands)
            ),
            "facts": await connection.scalar(
                sa.select(sa.func.count()).select_from(facts_current)
            ),
        }
    assert {row["exchange_instrument_id"] for row in ready_rows} == set(MEMBERS)
    assert len({row["universe_version_id"] for row in ready_rows}) == 1
    assert len({row["universe_semantic_digest"] for row in ready_rows}) == 1
    assert all(row["entry_enabled"] is False for row in ready_rows)
    assert all(row["warm_closed_bar_time_ms"] == NOW_MS for row in ready_rows)
    assert all(
        str(row["warm_readiness_digest"]).startswith("sha256:")
        for row in ready_rows
    )
    assert all(row["warm_valid_until_ms"] > NOW_MS for row in ready_rows)
    assert [row["readiness_state"] for row in readiness_rows] == [
        "warm_ready",
        "warm_ready",
    ]
    assert counts == {"signals": 0, "tickets": 0, "commands": 0, "facts": 6}


@pytest.mark.asyncio
async def test_warming_after_install_can_use_fresh_last_closed_bar(
    warming_engine: AsyncEngine,
) -> None:
    """Catches readiness time incorrectly using the pre-install bar close."""

    scope = (await _warming_scopes(warming_engine))[0]
    installed_after_close_ms = NOW_MS + 30_000
    attempted_at_ms = NOW_MS + 60_000
    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == scope["runtime_scope_id"]
            )
            .values(updated_at_ms=installed_after_close_ms)
        )

    result = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        _triggering_source(
            warming_engine,
            (scope["exchange_instrument_id"],),
        ),
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
            attempted_at_ms=attempted_at_ms,
        ),
    )

    assert result.status is ObservationStatus.WARMED
    persisted = await _persisted_scope(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert persisted["warm_closed_bar_time_ms"] == NOW_MS
    assert persisted["warm_completed_at_ms"] == attempted_at_ms
    assert persisted["updated_at_ms"] == attempted_at_ms


@pytest.mark.asyncio
async def test_warming_failure_after_install_records_attempt_time(
    warming_engine: AsyncEngine,
) -> None:
    """Catches blockers incorrectly using the pre-install bar close time."""

    scope = (await _warming_scopes(warming_engine))[0]
    installed_after_close_ms = NOW_MS + 30_000
    attempted_at_ms = NOW_MS + 60_000
    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == scope["runtime_scope_id"]
            )
            .values(updated_at_ms=installed_after_close_ms)
        )

    result = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        TypedMarketFake(warming_engine, {}),
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
            attempted_at_ms=attempted_at_ms,
        ),
    )

    assert result.status is ObservationStatus.INVALID
    persisted = await _persisted_scope(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert persisted["warm_closed_bar_time_ms"] is None
    assert persisted["updated_at_ms"] == attempted_at_ms


@pytest.mark.asyncio
async def test_last_warm_success_auto_activates_fully_certified_universe(
    warming_engine: AsyncEngine,
) -> None:
    """Catches Observation persisting complete warm facts without activation."""

    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_runtime_capabilities_current "
                "SET enabled = true "
                "WHERE capability_key = 'exchange_commands'"
            )
        )
    certification_source = RecordingReadonlyCertificationSource(
        warming_engine
    )
    for _ in MEMBERS:
        result = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(warming_engine),
            NoTicketVenueTruth(),
            NoTicketPositionSource(),
            certification_worker_request(NOW_MS).model_copy(
                update={"runtime_commit": RUNTIME_COMMIT}
            ),
            instrument_certification_source=certification_source,
        )
        assert (
            result.status
            is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
        )
    source = _triggering_source(warming_engine, MEMBERS)

    first = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        source,
        _worker_request(now_ms=NOW_MS),
    )
    async with warming_engine.connect() as connection:
        state_after_first = (
            await connection.execute(
                sa.select(
                    strategy_universe_versions.c.lifecycle_state
                )
            )
        ).scalar_one()
        pointer_after_first = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    strategy_universe_current
                )
            )
            or 0
        )

    second = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        source,
        _worker_request(now_ms=NOW_MS),
    )
    async with warming_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(strategy_universe_current)
            )
        ).mappings().one()
        active_scopes = (
            await connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.lifecycle_state == "active"
                )
                .order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
            )
        ).mappings().all()
        side_effect_counts = (
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(signal_events)
                )
                or 0
            ),
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(trade_tickets)
                )
                or 0
            ),
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        exchange_commands
                    )
                )
                or 0
            ),
        )

    assert first.status is ObservationWorkerStatus.OBSERVED
    assert first.observation_status is ObservationStatus.WARMED
    assert state_after_first == "warming"
    assert pointer_after_first == 0
    assert second.status is ObservationWorkerStatus.OBSERVED
    assert second.observation_status is ObservationStatus.WARMED
    assert current["activation_generation"] == 1
    assert len(active_scopes) == len(MEMBERS)
    assert all(scope["entry_enabled"] for scope in active_scopes)
    assert side_effect_counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_observation_and_reconciliation_activation_converge_without_deadlock(
    warming_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches scope-lock then advisory-lock inversion across existing workers."""

    _, market_source = (
        await _prepare_certified_universe_with_one_warm_scope(
            warming_engine
        )
    )
    async with warming_engine.connect() as connection:
        universe_version_id = str(
            await connection.scalar(
                sa.select(
                    strategy_universe_versions.c.universe_version_id
                )
            )
        )

    original_advance = (
        observation_worker_module.advance_strategy_universe
    )
    observation_reached_activation = asyncio.Event()
    release_observation_activation = asyncio.Event()

    async def pause_before_observation_activation(uow, request):
        observation_reached_activation.set()
        await release_observation_activation.wait()
        return await original_advance(uow, request)

    monkeypatch.setattr(
        observation_worker_module,
        "advance_strategy_universe",
        pause_before_observation_activation,
    )
    observation_task = asyncio.create_task(
        run_observation_worker_once(
            lambda: PostgresKernelUnitOfWork(warming_engine),
            market_source,
            _worker_request(now_ms=NOW_MS),
        )
    )
    await asyncio.wait_for(
        observation_reached_activation.wait(),
        timeout=5,
    )

    async def reconciliation_activation():
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            return await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=universe_version_id,
                    attempted_at_ms=NOW_MS,
                ),
            )

    reconciliation_task = asyncio.create_task(
        reconciliation_activation()
    )
    try:
        await _wait_for_advisory_lock_or_activation(
            warming_engine,
        )
    finally:
        release_observation_activation.set()

    observation_result, reconciliation_activation_result = (
        await asyncio.wait_for(
            asyncio.gather(observation_task, reconciliation_task),
            timeout=5,
        )
    )
    async with warming_engine.connect() as connection:
        current_rows = (
            await connection.execute(
                sa.select(strategy_universe_current)
            )
        ).mappings().all()
        version_state = (
            await connection.execute(
                sa.select(
                    strategy_universe_versions.c.lifecycle_state
                )
            )
        ).scalar_one()
        scope_states = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.lifecycle_state,
                    runtime_scopes_current.c.observation_enabled,
                    runtime_scopes_current.c.entry_enabled,
                    runtime_scopes_current.c.lease_owner,
                ).order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
            )
        ).all()
        side_effect_counts = (
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(signal_events)
                )
                or 0
            ),
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(trade_tickets)
                )
                or 0
            ),
            int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        exchange_commands
                    )
                )
                or 0
            ),
        )

    assert observation_result.status is ObservationWorkerStatus.OBSERVED
    assert observation_result.observation_status is ObservationStatus.WARMED
    assert reconciliation_activation_result.status in {
        UniverseActivationStatus.ACTIVATED,
        UniverseActivationStatus.ALREADY_ACTIVE,
    }
    assert len(current_rows) == 1
    assert current_rows[0]["activation_generation"] == 1
    assert version_state == "active"
    assert scope_states == [
        ("active", True, True, None),
        ("active", True, True, None),
    ]
    assert side_effect_counts == (0, 0, 0)


@pytest.mark.asyncio
async def test_observation_activation_failure_preserves_schedule_and_next_tick_recovers(
    warming_engine: AsyncEngine,
) -> None:
    """Catches activation rollback also rolling back warm claim completion."""

    certification_source, market_source = (
        await _prepare_certified_universe_with_one_warm_scope(
            warming_engine
        )
    )
    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                CREATE FUNCTION fail_task10_observation_activation()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION
                        'task 10 observation activation failure';
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                """
                CREATE TRIGGER trg_task10_observation_activation
                BEFORE INSERT ON brc_strategy_universe_current
                FOR EACH ROW EXECUTE FUNCTION
                    fail_task10_observation_activation()
                """
            )
        )

    with pytest.raises(
        DBAPIError,
        match="task 10 observation activation failure",
    ):
        await run_observation_worker_once(
            lambda: PostgresKernelUnitOfWork(warming_engine),
            market_source,
            _worker_request(now_ms=NOW_MS),
        )

    async with warming_engine.connect() as connection:
        warming_scopes = (
            await connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.lifecycle_state == "warming"
                )
                .order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
            )
        ).mappings().all()
        current_count = int(
            await connection.scalar(
                sa.select(sa.func.count()).select_from(
                    strategy_universe_current
                )
            )
            or 0
        )
    assert len(warming_scopes) == len(MEMBERS)
    assert all(
        scope["warm_closed_bar_time_ms"] == NOW_MS
        for scope in warming_scopes
    )
    assert all(scope["lease_owner"] is None for scope in warming_scopes)
    assert all(
        scope["next_observation_due_at_ms"] == NOW_MS + 900_000
        for scope in warming_scopes
    )
    assert current_count == 0

    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.text(
                "DROP TRIGGER trg_task10_observation_activation "
                "ON brc_strategy_universe_current"
            )
        )
        await connection.execute(
            sa.text(
                "DROP FUNCTION fail_task10_observation_activation()"
            )
        )
        await connection.execute(
            sa.text(
                "UPDATE brc_instrument_certification_current "
                "SET next_check_at_ms = :next_tick "
                "WHERE exchange_instrument_id = :instrument_id"
            ),
            {
                "next_tick": NOW_MS + 1,
                "instrument_id": MEMBERS[0],
            },
        )

    recovered = await run_reconciliation_worker_once(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        NoTicketVenueTruth(),
        NoTicketPositionSource(),
        certification_worker_request(NOW_MS + 1).model_copy(
            update={"runtime_commit": RUNTIME_COMMIT}
        ),
        instrument_certification_source=certification_source,
    )
    async with warming_engine.connect() as connection:
        current = (
            await connection.execute(
                sa.select(strategy_universe_current)
            )
        ).mappings().one()
        scope_states = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.lifecycle_state,
                    runtime_scopes_current.c.entry_enabled,
                    runtime_scopes_current.c.lease_owner,
                ).order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
            )
        ).all()

    assert recovered.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    assert current["activation_generation"] == 1
    assert scope_states == [
        ("active", True, None),
        ("active", True, None),
    ]


@pytest.mark.asyncio
async def test_missing_or_stale_warming_market_data_clears_prior_readiness(
    warming_engine: AsyncEngine,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    valid_source = _triggering_source(
        warming_engine,
        (scope["exchange_instrument_id"],),
    )
    first = await _observe(
        warming_engine,
        valid_source,
        scope["runtime_scope_id"],
    )
    assert first.status is ObservationStatus.WARMED
    assert await _scope_is_warm_ready(warming_engine, scope["runtime_scope_id"])

    missing = await _observe(
        warming_engine,
        TypedMarketFake(warming_engine, {}),
        scope["runtime_scope_id"],
    )
    assert missing.status is ObservationStatus.INVALID
    assert not await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )

    await _observe(
        warming_engine,
        valid_source,
        scope["runtime_scope_id"],
    )
    stale = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        valid_source,
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS + 900_000,
        ),
    )
    assert stale.status is ObservationStatus.INVALID
    assert not await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )
    async with warming_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0


@pytest.mark.parametrize(
    "warming_engine",
    [(MPG_CONTRACT, (SOL, OP))],
    indirect=True,
)
@pytest.mark.asyncio
async def test_comparative_warming_requires_market_data_for_every_member(
    warming_engine: AsyncEngine,
) -> None:
    scope = next(
        row
        for row in await _warming_scopes(warming_engine)
        if row["exchange_instrument_id"] == SOL
    )
    snapshot = mpg_long_snapshot()
    missing_peer = TypedMarketFake(
        warming_engine,
        {
            (SOL, "1h"): snapshot.candles_1h,
            (SOL, "4h"): snapshot.candles_4h,
        },
    )

    incomplete = await _observe(
        warming_engine,
        missing_peer,
        scope["runtime_scope_id"],
    )

    assert incomplete.status is ObservationStatus.INVALID
    assert not await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )
    complete = TypedMarketFake(
        warming_engine,
        {
            (SOL, "1h"): snapshot.candles_1h,
            (SOL, "4h"): snapshot.candles_4h,
            (OP, "1h"): flat_candles(9, 3_600_000),
        },
    )

    warmed = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        complete,
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
            attempted_at_ms=NOW_MS + 30_000,
        ),
    )

    assert warmed.status is ObservationStatus.WARMED
    assert await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert {
        call.exchange_instrument_id
        for call in complete.calls
        if call.timeframe == "1h"
    } == {SOL, OP}
    async with warming_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0


@pytest.mark.asyncio
async def test_warm_readiness_cannot_be_saved_for_changed_version_or_digest(
    warming_engine: AsyncEngine,
) -> None:
    scope_row = (await _warming_scopes(warming_engine))[0]
    source = _triggering_source(
        warming_engine,
        (scope_row["exchange_instrument_id"],),
    )
    result = await _observe(
        warming_engine,
        source,
        scope_row["runtime_scope_id"],
    )
    assert result.status is ObservationStatus.WARMED
    async with PostgresKernelUnitOfWork(warming_engine) as uow:
        scope = await uow.signals.get_runtime_scope(scope_row["runtime_scope_id"])
        facts = await uow.signals.get_required_facts(
            runtime_scope_id=scope_row["runtime_scope_id"],
            event_spec_id=CONTRACT.event_spec_id,
        )
    assert scope is not None
    assert facts is not None
    wrong_version_id = "universe:changed-version"
    wrong_digest = f"sha256:{sha256(b'changed-digest').hexdigest()}"
    readiness_digest = WarmReadiness.digest_for(
        runtime_scope_id=scope.runtime_scope_id,
        scope_version=scope.scope_version,
        observation_generation=scope.observation_generation,
        event_spec_id=scope.event_spec_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        universe_version_id=wrong_version_id,
        universe_semantic_digest=wrong_digest,
        fact_digest=_fact_digest(facts),
        warm_closed_bar_time_ms=NOW_MS,
        warm_valid_until_ms=min(item.valid_until_ms for item in facts),
    )
    changed = WarmReadiness(
        runtime_scope_id=scope.runtime_scope_id,
        scope_version=scope.scope_version,
        observation_generation=scope.observation_generation,
        event_spec_id=scope.event_spec_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        universe_version_id=wrong_version_id,
        universe_semantic_digest=wrong_digest,
        fact_digest=_fact_digest(facts),
        warm_closed_bar_time_ms=NOW_MS,
        warm_completed_at_ms=NOW_MS,
        warm_valid_until_ms=min(item.valid_until_ms for item in facts),
        readiness_digest=readiness_digest,
    )

    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            await uow.signals.save_warm_readiness(changed)

    async with warming_engine.connect() as connection:
        persisted = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == scope.runtime_scope_id
                )
            )
        ).mappings().one()
    assert persisted["universe_version_id"] == scope.universe_version_id
    assert persisted["universe_semantic_digest"] == scope.universe_semantic_digest
    assert persisted["warm_readiness_digest"] == scope.warm_readiness_digest


@pytest.mark.asyncio
async def test_old_warm_success_cannot_resurrect_after_later_invalid_clear(
    warming_engine: AsyncEngine,
) -> None:
    scope_row = (await _warming_scopes(warming_engine))[0]
    source = _triggering_source(
        warming_engine,
        (scope_row["exchange_instrument_id"],),
    )
    first = await _observe(
        warming_engine,
        source,
        scope_row["runtime_scope_id"],
    )
    assert first.status is ObservationStatus.WARMED
    async with PostgresKernelUnitOfWork(warming_engine) as uow:
        scope = await uow.signals.get_runtime_scope(scope_row["runtime_scope_id"])
        facts = await uow.signals.get_required_facts(
            runtime_scope_id=scope_row["runtime_scope_id"],
            event_spec_id=CONTRACT.event_spec_id,
        )
    assert scope is not None
    assert facts is not None
    old_success = build_warm_readiness(
        scope=scope,
        facts=facts,
        expected_fact_definition_ids=tuple(
            item.fact_definition_id
            for item in (*CONTRACT.required_facts, *CONTRACT.disable_facts)
        ),
        warm_closed_bar_time_ms=NOW_MS,
        warm_completed_at_ms=NOW_MS,
    )

    later_invalid = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        source,
        ObservationRequest(
            runtime_scope_id=scope.runtime_scope_id,
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS + 900_000,
        ),
    )

    assert later_invalid.status is ObservationStatus.INVALID
    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            await uow.signals.save_warm_readiness(old_success)
    persisted = await _persisted_scope(warming_engine, scope.runtime_scope_id)
    assert persisted["warm_closed_bar_time_ms"] is None
    assert persisted["warm_readiness_digest"] is None
    assert persisted["warm_valid_until_ms"] is None
    assert persisted["updated_at_ms"] == NOW_MS + 900_000


@pytest.mark.asyncio
async def test_old_warm_failure_cannot_clear_a_newer_success(
    warming_engine: AsyncEngine,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    later_ms = NOW_MS + 900_000
    later_source = _shifted_triggering_source(
        warming_engine,
        (scope["exchange_instrument_id"],),
        delta_ms=900_000,
    )

    later_success = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        later_source,
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=later_ms,
        ),
    )

    assert later_success.status is ObservationStatus.WARMED
    before = await _persisted_scope(
        warming_engine,
        scope["runtime_scope_id"],
    )
    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            await uow.signals.clear_warm_readiness(
                runtime_scope_id=scope["runtime_scope_id"],
                scope_version=scope["scope_version"],
                observation_generation=scope["observation_generation"],
                event_spec_id=scope["event_spec_id"],
                exchange_instrument_id=scope["exchange_instrument_id"],
                universe_version_id=scope["universe_version_id"],
                universe_semantic_digest=scope["universe_semantic_digest"],
                blocker="old_worker_failure",
                updated_at_ms=NOW_MS,
            )
    after = await _persisted_scope(warming_engine, scope["runtime_scope_id"])
    assert after["warm_closed_bar_time_ms"] == later_ms
    assert after["warm_readiness_digest"] == before["warm_readiness_digest"]
    assert after["warm_valid_until_ms"] == before["warm_valid_until_ms"]
    assert after["updated_at_ms"] == later_ms


@pytest.mark.asyncio
async def test_same_bar_old_success_cannot_resurrect_after_new_invalid(
    warming_engine: AsyncEngine,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    valid_source = _triggering_source(
        warming_engine,
        (scope["exchange_instrument_id"],),
    )
    assert (
        await _observe(
            warming_engine,
            valid_source,
            scope["runtime_scope_id"],
        )
    ).status is ObservationStatus.WARMED
    old_source = BlockingMarketFake(valid_source._responses)
    old_attempt = asyncio.create_task(
        _observe(
            warming_engine,
            old_source,
            scope["runtime_scope_id"],
        )
    )
    await old_source.started.wait()
    old_generation = (
        await _persisted_scope(
            warming_engine,
            scope["runtime_scope_id"],
        )
    )["observation_generation"]

    newer_invalid = await _observe(
        warming_engine,
        TypedMarketFake(warming_engine, {}),
        scope["runtime_scope_id"],
    )
    assert newer_invalid.status is ObservationStatus.INVALID
    after_newer = await _warming_projection_state(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert (
        after_newer["scope"]["observation_generation"]
        == old_generation + 1
    )
    old_source.release.set()

    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        await old_attempt
    after_old = await _warming_projection_state(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert after_old == after_newer
    assert after_old["scope"]["warm_closed_bar_time_ms"] is None
    assert after_old["readiness"]["readiness_state"] == "blocked"


@pytest.mark.asyncio
async def test_same_bar_old_failure_cannot_clear_new_success(
    warming_engine: AsyncEngine,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    old_source = BlockingMarketFake(
        {},
        failure=TimeoutError("old observation failed"),
    )
    old_attempt = asyncio.create_task(
        _observe(
            warming_engine,
            old_source,
            scope["runtime_scope_id"],
        )
    )
    await old_source.started.wait()
    old_generation = (
        await _persisted_scope(
            warming_engine,
            scope["runtime_scope_id"],
        )
    )["observation_generation"]

    newer_success = await _observe(
        warming_engine,
        _triggering_source(
            warming_engine,
            (scope["exchange_instrument_id"],),
        ),
        scope["runtime_scope_id"],
    )
    assert newer_success.status is ObservationStatus.WARMED
    after_newer = await _warming_projection_state(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert (
        after_newer["scope"]["observation_generation"]
        == old_generation + 1
    )
    old_source.release.set()

    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        await old_attempt
    after_old = await _warming_projection_state(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert after_old == after_newer
    assert after_old["scope"]["warm_closed_bar_time_ms"] == NOW_MS
    assert after_old["readiness"]["readiness_state"] == "warm_ready"


@pytest.mark.parametrize(
    "drift_kind",
    ("event", "contract", "permission"),
)
@pytest.mark.asyncio
async def test_identified_warming_scope_drift_clears_prior_readiness(
    warming_engine: AsyncEngine,
    drift_kind: str,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    first = await _observe(
        warming_engine,
        _triggering_source(
            warming_engine,
            (scope["exchange_instrument_id"],),
        ),
        scope["runtime_scope_id"],
    )
    assert first.status is ObservationStatus.WARMED

    async with warming_engine.begin() as connection:
        if drift_kind == "event":
            await connection.execute(
                sa.update(event_specs)
                .where(event_specs.c.event_spec_id == scope["event_spec_id"])
                .values(status="inactive")
            )
        elif drift_kind == "contract":
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == scope["runtime_scope_id"]
                )
                .values(strategy_version_id="sgv:contract-drift:v99")
            )
        else:
            await connection.exec_driver_sql(
                "ALTER TABLE brc_runtime_scopes_current "
                "DROP CONSTRAINT ck_brc_runtime_scopes_current_lifecycle_permissions_valid"
            )
            await connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == scope["runtime_scope_id"]
                )
                .values(entry_enabled=True)
            )
    unused_source = TypedMarketFake(warming_engine, {})

    invalid = await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        unused_source,
        ObservationRequest(
            runtime_scope_id=scope["runtime_scope_id"],
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS + 1,
        ),
    )

    assert invalid.status is ObservationStatus.INVALID
    assert unused_source.calls == []
    assert not await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )
    persisted = await _persisted_scope(
        warming_engine,
        scope["runtime_scope_id"],
    )
    assert persisted["updated_at_ms"] == NOW_MS + 1


@pytest.mark.asyncio
async def test_clear_warm_readiness_rejects_arbitrary_scope_identity(
    warming_engine: AsyncEngine,
) -> None:
    scope = (await _warming_scopes(warming_engine))[0]
    first = await _observe(
        warming_engine,
        _triggering_source(
            warming_engine,
            (scope["exchange_instrument_id"],),
        ),
        scope["runtime_scope_id"],
    )
    assert first.status is ObservationStatus.WARMED

    with pytest.raises(RuntimeError, match="warm readiness authority changed"):
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            await uow.signals.clear_warm_readiness(
                runtime_scope_id=scope["runtime_scope_id"],
                scope_version=scope["scope_version"] + 1,
                observation_generation=scope["observation_generation"],
                event_spec_id=scope["event_spec_id"],
                exchange_instrument_id=scope["exchange_instrument_id"],
                universe_version_id=scope["universe_version_id"],
                universe_semantic_digest=scope["universe_semantic_digest"],
                blocker="arbitrary_cleanup",
                updated_at_ms=NOW_MS + 1,
            )

    assert await _scope_is_warm_ready(
        warming_engine,
        scope["runtime_scope_id"],
    )


@pytest.mark.asyncio
async def test_crashed_warming_claim_is_recovered_after_lease_expiry(
    warming_engine: AsyncEngine,
) -> None:
    scopes = await _warming_scopes(warming_engine)
    crashed_scope_id = scopes[0]["runtime_scope_id"]
    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                != crashed_scope_id
            )
            .values(next_observation_due_at_ms=NOW_MS + 1_800_000)
        )
    async with PostgresKernelUnitOfWork(warming_engine) as uow:
        claim = await uow.signals.claim_next_observation_scope(
            worker_id="crashed-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    assert claim is not None
    assert claim.runtime_scope_id == crashed_scope_id
    source = _triggering_source(
        warming_engine,
        (scopes[0]["exchange_instrument_id"],),
    )

    before_expiry = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        source,
        _worker_request(now_ms=NOW_MS + 30_000),
    )
    recovered = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(warming_engine),
        source,
        _worker_request(now_ms=NOW_MS + 60_000),
    )

    assert before_expiry.status is ObservationWorkerStatus.NO_WORK
    assert recovered.status is ObservationWorkerStatus.OBSERVED
    assert recovered.runtime_scope_id == crashed_scope_id
    assert recovered.observation_status is ObservationStatus.WARMED
    assert len(source.calls) == 1
    async with warming_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(signal_events)
        ) == 0
        persisted = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == crashed_scope_id
                )
            )
        ).mappings().one()
    assert persisted["lease_owner"] is None
    assert persisted["lease_expires_at_ms"] is None
    assert persisted["warm_closed_bar_time_ms"] == NOW_MS
    assert persisted["warm_completed_at_ms"] == NOW_MS + 60_000


@pytest.mark.asyncio
async def test_expired_generation_cannot_release_reclaimed_same_worker_lease(
    warming_engine: AsyncEngine,
) -> None:
    scopes = await _warming_scopes(warming_engine)
    target_scope_id = scopes[0]["runtime_scope_id"]
    async with warming_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id != target_scope_id
            )
            .values(next_observation_due_at_ms=NOW_MS + 1_800_000)
        )
    async with PostgresKernelUnitOfWork(warming_engine) as uow:
        old_claim = await uow.signals.claim_next_observation_scope(
            worker_id="same-worker",
            now_ms=NOW_MS,
            lease_until_ms=NOW_MS + 60_000,
        )
    async with PostgresKernelUnitOfWork(warming_engine) as uow:
        new_claim = await uow.signals.claim_next_observation_scope(
            worker_id="same-worker",
            now_ms=NOW_MS + 60_000,
            lease_until_ms=NOW_MS + 120_000,
        )
    assert old_claim is not None
    assert new_claim is not None
    assert (
        new_claim.observation_generation
        == old_claim.observation_generation + 1
    )

    with pytest.raises(
        RuntimeError,
        match="observation scope lease is not owned",
    ):
        async with PostgresKernelUnitOfWork(warming_engine) as uow:
            await uow.signals.schedule_observation_scope(
                runtime_scope_id=target_scope_id,
                worker_id="same-worker",
                observation_generation=old_claim.observation_generation,
                due_at_ms=NOW_MS + 900_000,
            )

    persisted = await _persisted_scope(warming_engine, target_scope_id)
    assert persisted["observation_generation"] == (
        new_claim.observation_generation
    )
    assert persisted["lease_owner"] == "same-worker"
    assert persisted["lease_expires_at_ms"] == NOW_MS + 120_000


async def _install_warming_universe(
    engine: AsyncEngine,
    contract,
    members: tuple[str, ...],
) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(
            uow,
            RuntimeAuthoritySeedRequest(
                account_id="subaccount-warming-test",
                runtime_commit=RUNTIME_COMMIT,
                schema_revision=SCHEMA_REVISION,
                seeded_at_ms=NOW_MS - 10_000,
            ),
        )
        result = await install_strategy_universe(
            uow,
            UniverseInstallRequest(
                event_spec_id=contract.event_spec_id,
                runtime_profile_id=RUNTIME_PROFILE_ID,
                owner_policy_id=OWNER_POLICY_ID,
                exchange_instrument_ids=members,
                installed_at_ms=NOW_MS - 1_000,
            ),
        )
    assert result.universe is not None
    assert result.universe.exchange_instrument_ids == tuple(sorted(members))


def _triggering_source(
    engine: AsyncEngine,
    members: tuple[str, ...],
) -> TypedMarketFake:
    candles = sor_snapshot(side="long").candles_15m
    return TypedMarketFake(
        engine,
        {(member, "15m"): candles for member in members},
    )


def _shifted_triggering_source(
    engine: AsyncEngine,
    members: tuple[str, ...],
    *,
    delta_ms: int,
) -> TypedMarketFake:
    candles = tuple(
        candle.model_copy(
            update={
                "open_time_ms": candle.open_time_ms + delta_ms,
                "close_time_ms": candle.close_time_ms + delta_ms,
            }
        )
        for candle in sor_snapshot(side="long").candles_15m
    )
    return TypedMarketFake(
        engine,
        {(member, "15m"): candles for member in members},
    )


async def _observe(
    engine: AsyncEngine,
    source: TypedMarketFake | BlockingMarketFake,
    runtime_scope_id: str,
):
    return await observe_strategy_scope(
        lambda: PostgresKernelUnitOfWork(engine),
        source,
        ObservationRequest(
            runtime_scope_id=runtime_scope_id,
            runtime_commit=RUNTIME_COMMIT,
            schema_revision=SCHEMA_REVISION,
            trigger_candle_close_time_ms=NOW_MS,
        ),
    )


async def _warming_scopes(engine: AsyncEngine):
    async with engine.connect() as connection:
        return (
            await connection.execute(
                sa.select(runtime_scopes_current)
                .where(runtime_scopes_current.c.lifecycle_state == "warming")
                .order_by(runtime_scopes_current.c.exchange_instrument_id)
                .limit(11)
            )
        ).mappings().all()


async def _warm_ready_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return int(
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.lifecycle_state == "warming",
                    runtime_scopes_current.c.warm_closed_bar_time_ms.is_not(None),
                    runtime_scopes_current.c.warm_valid_until_ms > NOW_MS,
                )
            )
            or 0
        )


async def _scope_is_warm_ready(
    engine: AsyncEngine,
    runtime_scope_id: str,
) -> bool:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.warm_closed_bar_time_ms,
                    runtime_scopes_current.c.warm_readiness_digest,
                    runtime_scopes_current.c.warm_valid_until_ms,
                ).where(
                    runtime_scopes_current.c.runtime_scope_id == runtime_scope_id
                )
            )
        ).one()
    return all(value is not None for value in row)


async def _persisted_scope(
    engine: AsyncEngine,
    runtime_scope_id: str,
):
    async with engine.connect() as connection:
        return (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
            )
        ).mappings().one()


async def _warming_projection_state(
    engine: AsyncEngine,
    runtime_scope_id: str,
) -> WarmingProjectionState:
    async with engine.connect() as connection:
        scope = (
            await connection.execute(
                sa.select(runtime_scopes_current).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
            )
        ).mappings().one()
        readiness = (
            await connection.execute(
                sa.select(readiness_current).where(
                    readiness_current.c.runtime_scope_id == runtime_scope_id
                )
            )
        ).mappings().one()
        facts = (
            await connection.execute(
                sa.select(facts_current)
                .where(facts_current.c.runtime_scope_id == runtime_scope_id)
                .order_by(facts_current.c.fact_definition_id)
            )
        ).mappings().all()
    return {
        "scope": dict(scope),
        "readiness": dict(readiness),
        "facts": tuple(dict(row) for row in facts),
    }


def _worker_request(*, now_ms: int) -> ObservationWorkerRequest:
    return ObservationWorkerRequest(
        worker_id="warming-recovery-worker",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=SCHEMA_REVISION,
        now_ms=now_ms,
        lease_until_ms=now_ms + 30_000,
        timeout_seconds=1,
        retry_interval_ms=30_000,
    )


async def _prepare_certified_universe_with_one_warm_scope(
    engine: AsyncEngine,
) -> tuple[RecordingReadonlyCertificationSource, TypedMarketFake]:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE brc_runtime_capabilities_current "
                "SET enabled = true "
                "WHERE capability_key = 'exchange_commands'"
            )
        )
    certification_source = RecordingReadonlyCertificationSource(engine)
    for _ in MEMBERS:
        result = await run_reconciliation_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            NoTicketVenueTruth(),
            NoTicketPositionSource(),
            certification_worker_request(NOW_MS).model_copy(
                update={"runtime_commit": RUNTIME_COMMIT}
            ),
            instrument_certification_source=certification_source,
        )
        assert result.status is ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED
    market_source = _triggering_source(engine, MEMBERS)
    first = await run_observation_worker_once(
        lambda: PostgresKernelUnitOfWork(engine),
        market_source,
        _worker_request(now_ms=NOW_MS),
    )
    assert first.status is ObservationWorkerStatus.OBSERVED
    assert first.observation_status is ObservationStatus.WARMED
    return certification_source, market_source


async def _wait_for_advisory_lock_or_activation(
    engine: AsyncEngine,
) -> None:
    for _ in range(500):
        async with engine.connect() as connection:
            advisory_locks = int(
                await connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' AND granted"
                    )
                )
                or 0
            )
            current_count = int(
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(
                        strategy_universe_current
                    )
                )
                or 0
            )
        if advisory_locks > 0 or current_count > 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        "concurrent activation did not reach advisory lock"
    )


def _fact_digest(facts) -> str:
    from src.trading_kernel.domain.signal import build_signal_fact_digest

    return build_signal_fact_digest(facts)
