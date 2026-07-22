from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
)
from src.trading_kernel.application.issue_ready_signal import (
    IssueReadySignalRequest,
    issue_ready_signal,
)
from src.trading_kernel.application.issue_ticket import IssueTicketStatus
from src.trading_kernel.domain.signal import (
    ActionableSignal,
    SignalFactSnapshot,
    SignalTicketTerms,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.ticket import EntryOrderType
from src.trading_kernel.infrastructure.pg_models import (
    facts_current,
    instrument_rules_current,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


@pytest_asyncio.fixture(name="issue_engine")
async def signal_engine() -> AsyncEngine:
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
async def test_typed_signal_persists_readiness_and_issues_one_frozen_ticket(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )

    assert ingested.status is IngestSignalStatus.TICKET_READY
    assert ingested.signal_event_id == signal.signal_event_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        issued = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )

    assert issued.status is IssueTicketStatus.ISSUED
    assert issued.ticket_id is not None

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ticket = await uow.tickets.get(issued.ticket_id)
        persisted_signal = await uow.signals.get(signal.signal_event_id)
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)

    assert persisted_signal == signal
    assert readiness is not None
    assert readiness.readiness_state == "ticket_issued"
    assert readiness.signal_event_id == signal.signal_event_id
    assert ticket is not None
    assert ticket.identity.signal_event_id == signal.signal_event_id
    assert ticket.identity.runtime.strategy_group_id == signal.strategy_group_id
    assert ticket.identity.runtime.strategy_version_id == signal.strategy_version_id
    assert ticket.identity.runtime.event_spec_id == signal.event_spec_id
    assert ticket.identity.netting_domain.position_side == signal.position_side
    assert ticket.runtime_scope_id == signal.runtime_scope_id
    assert ticket.runtime_scope_version == signal.runtime_scope_version
    assert ticket.fact_digest == signal.fact_digest
    assert ticket.quantity == signal.terms.quantity
    assert ticket.initial_stop_price == signal.terms.initial_stop_price


@pytest.mark.asyncio
async def test_signal_from_non_independent_position_mode_is_rejected_before_persist(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_profiles).values(position_mode="one_way")
        )
    signal = _signal()

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )

    assert result.status.value == "account_mode_invalid"
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.signals.get(signal.signal_event_id) is None
        assert await uow.signals.get_readiness(signal.runtime_scope_id) is None


@pytest.mark.asyncio
async def test_wrong_fact_digest_is_rejected_before_signal_persistence(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal().model_copy(update={"fact_digest": "sha256:" + "0" * 64})

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )

    assert result.status is IngestSignalStatus.SIGNAL_INVALID_OR_STALE
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.signals.get(signal.signal_event_id) is None


@pytest.mark.asyncio
async def test_missing_or_stale_required_fact_rejects_signal(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    await _seed_required_fact(issue_engine, valid_until_ms=1_500)
    signal = _signal()

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_600,
            ),
        )

    assert result.status is IngestSignalStatus.SIGNAL_INVALID_OR_STALE
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.signals.get(signal.signal_event_id) is None


@pytest.mark.asyncio
async def test_duplicate_typed_signal_is_idempotently_rejected(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    request = IngestSignalRequest(
        signal=signal,
        runtime_commit="kernel-test-head",
        schema_revision="0001_initial",
        now_ms=1_001,
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        first = await ingest_signal(uow, request)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        duplicate = await ingest_signal(uow, request)

    assert first.status is IngestSignalStatus.TICKET_READY
    assert duplicate.status.value == "duplicate_signal"
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert readiness is not None
    assert readiness.projection_version == 1


@pytest.mark.asyncio
async def test_three_ready_signals_issue_serially_into_three_concurrent_domains(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    await _seed_additional_scope(
        issue_engine,
        runtime_scope_id="scope-sor-btc-short",
        event_spec_id="event_spec:SOR-001:SOR-SHORT:v2",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="short",
    )
    await _seed_additional_scope(
        issue_engine,
        runtime_scope_id="scope-sor-eth-long",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        position_side="long",
    )
    signals = (
        _signal(signal_event_id="signal-1", occurred_at_ms=1_000),
        _signal(
            signal_event_id="signal-2",
            runtime_scope_id="scope-sor-btc-short",
            position_side="short",
            occurred_at_ms=1_001,
        ),
        _signal(
            signal_event_id="signal-3",
            runtime_scope_id="scope-sor-eth-long",
            exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
            occurred_at_ms=1_002,
        ),
    )
    for signal in signals:
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            result = await ingest_signal(
                uow,
                IngestSignalRequest(
                    signal=signal,
                    runtime_commit="kernel-test-head",
                    schema_revision="0001_initial",
                    now_ms=1_003,
                ),
            )
        assert result.status is IngestSignalStatus.TICKET_READY

    ticket_ids: list[str] = []
    for index in range(3):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            issued = await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    claim_owner=f"signal-worker-{index}",
                    runtime_commit="kernel-test-head",
                    schema_revision="0001_initial",
                    now_ms=1_010 + index,
                ),
            )
        assert issued.status is IssueTicketStatus.ISSUED
        assert issued.ticket_id is not None
        ticket_ids.append(issued.ticket_id)
        if index < 2:
            if index == 0:
                async with PostgresKernelUnitOfWork(issue_engine) as uow:
                    blocked = await issue_ready_signal(
                        uow,
                        IssueReadySignalRequest(
                            claim_owner="signal-worker-blocked",
                            runtime_commit="kernel-test-head",
                            schema_revision="0001_initial",
                            now_ms=1_020,
                        ),
                    )
                assert blocked.status is IssueTicketStatus.ENTRY_LANE_OCCUPIED
                async with PostgresKernelUnitOfWork(issue_engine) as uow:
                    pending = await uow.signals.get_readiness(
                        "scope-sor-btc-short"
                    )
                assert pending is not None
                assert pending.readiness_state == "ticket_ready"
            async with PostgresKernelUnitOfWork(issue_engine) as uow:
                await uow.entry_admission.release_global_lane(
                    ticket_id=issued.ticket_id
                )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        tickets = [await uow.tickets.get(ticket_id) for ticket_id in ticket_ids]
        exposure = await uow.entry_admission.get_account_exposure("subaccount-main")

    assert all(ticket is not None for ticket in tickets)
    assert len({ticket.identity.netting_domain.key() for ticket in tickets if ticket}) == 3
    assert exposure is not None
    assert exposure.active_ticket_count == 3


@pytest.mark.asyncio
async def test_budget_is_revalidated_at_issue_and_persisted_as_first_blocker(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.TICKET_READY
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current).values(max_gross_notional=Decimal("50"))
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.BUDGET_EXHAUSTED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        assert await uow.signals.get(signal.signal_event_id) == signal
        assert not await uow.entry_admission.has_ticket_for_signal(
            signal.signal_event_id
        )
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "budget_exhausted"


@pytest.mark.asyncio
async def test_policy_disabled_after_ingest_returns_exact_issue_blocker(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.TICKET_READY
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current).values(
                enabled=False,
                real_submit_enabled=False,
            )
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_002,
            ),
        )

    assert result.status.value == "scope_or_policy_mismatch"
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "scope_or_policy_mismatch"


@pytest.mark.asyncio
async def test_expired_queued_signal_is_terminally_blocked_not_left_ticket_ready(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.TICKET_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=signal.expires_at_ms,
            ),
        )

    assert result.status.value == "signal_invalid_or_stale"
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "signal_invalid_or_stale"


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stale", IngestSignalStatus.SIGNAL_INVALID_OR_STALE),
        ("scope-version", IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH),
        ("side", IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH),
        ("commit", IngestSignalStatus.SCHEMA_IDENTITY_MISMATCH),
        ("precision", IngestSignalStatus.INSTRUMENT_RULES_INVALID),
    ],
)
@pytest.mark.asyncio
async def test_signal_authority_matrix_fails_before_persistence(
    issue_engine: AsyncEngine,
    case: str,
    expected: IngestSignalStatus,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id=f"signal-{case}")
    runtime_commit = "kernel-test-head"
    now_ms = 1_001
    if case == "stale":
        now_ms = signal.expires_at_ms
    elif case == "scope-version":
        signal = signal.model_copy(update={"runtime_scope_version": 99})
    elif case == "side":
        signal = _signal(signal_event_id="signal-side", position_side="short")
    elif case == "commit":
        runtime_commit = "wrong-commit"
    elif case == "precision":
        signal = signal.model_copy(
            update={
                "terms": signal.terms.model_copy(
                    update={"quantity": Decimal("0.0105")}
                )
            }
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit=runtime_commit,
                schema_revision="0001_initial",
                now_ms=now_ms,
            ),
        )

    assert result.status is expected
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.signals.get(signal.signal_event_id) is None


@pytest.mark.asyncio
async def test_no_ready_signal_returns_explicit_idle_result(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                claim_owner="signal-worker-idle",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )

    assert result.status is IssueTicketStatus.NO_READY_SIGNAL
    assert result.ticket_id is None


@pytest.mark.asyncio
async def test_two_signal_workers_create_exactly_one_ticket_for_one_ready_signal(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.TICKET_READY

    async def attempt(worker: str):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            return await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    claim_owner=worker,
                    runtime_commit="kernel-test-head",
                    schema_revision="0001_initial",
                    now_ms=1_002,
                ),
            )

    results = await asyncio.gather(attempt("worker-a"), attempt("worker-b"))

    assert sorted(result.status.value for result in results) == [
        "issued",
        "no_ready_signal",
    ]
    issued = next(result for result in results if result.ticket_id is not None)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert issued.ticket_id is not None
        assert await uow.tickets.get(issued.ticket_id) is not None
        exposure = await uow.entry_admission.get_account_exposure("subaccount-main")
    assert exposure is not None
    assert exposure.active_ticket_count == 1


def _signal(
    *,
    signal_event_id: str = "signal-live-1",
    runtime_scope_id: str = "scope-sor-btc-long",
    position_side: str = "long",
    exchange_instrument_id: str = "binance-usdm:BTCUSDT:perpetual",
    occurred_at_ms: int = 1_000,
) -> ActionableSignal:
    event_spec_id = (
        "event_spec:SOR-001:SOR-LONG:v2"
        if position_side == "long"
        else "event_spec:SOR-001:SOR-SHORT:v2"
    )
    facts = _signal_facts(position_side=position_side)
    return ActionableSignal(
        signal_event_id=signal_event_id,
        runtime_scope_id=runtime_scope_id,
        runtime_scope_version=4,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v2",
        event_spec_id=event_spec_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
        fact_digest=build_signal_fact_digest(facts),
        occurred_at_ms=occurred_at_ms,
        expires_at_ms=10_000,
        terms=SignalTicketTerms(
            quantity=Decimal("0.010"),
            notional=Decimal("100"),
            leverage=Decimal("5"),
            risk_at_stop=Decimal("2.5"),
            entry_order_type=EntryOrderType.MARKET,
            initial_stop_price=Decimal("9900.0"),
            take_profit_prices=(Decimal("10500.0"),),
        ),
    )


async def _seed_runtime_authority(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)

    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(instrument_rules_current).values(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.1"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal("5"),
                session_and_settlement={},
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                real_submit_enabled=True,
                max_concurrent_tickets=8,
                max_gross_notional=Decimal("1000"),
                scope={},
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(runtime_profiles).values(
                runtime_profile_id="tiny-live-v1",
                venue_id="binance-usdm",
                account_id="subaccount-main",
                environment="live",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="scope-sor-btc-long",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v2",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                enabled=True,
                scope_version=4,
                updated_at_ms=1_000,
            )
        )
        await _insert_scope_facts(
            connection,
            runtime_scope_id="scope-sor-btc-long",
            position_side="long",
        )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="signal_to_ticket",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_initial",
                certification={},
                updated_at_ms=1_000,
            )
        )


async def _seed_additional_scope(
    engine: AsyncEngine,
    *,
    runtime_scope_id: str,
    event_spec_id: str,
    exchange_instrument_id: str,
    position_side: str,
) -> None:
    async with engine.begin() as connection:
        rules_exist = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(instrument_rules_current)
            .where(
                instrument_rules_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
        )
        if not rules_exist:
            await connection.execute(
                sa.insert(instrument_rules_current).values(
                    exchange_instrument_id=exchange_instrument_id,
                    quantity_step=Decimal("0.001"),
                    price_tick=Decimal("0.1"),
                    min_quantity=Decimal("0.001"),
                    min_notional=Decimal("5"),
                    session_and_settlement={},
                    observed_at_ms=1_000,
                    valid_until_ms=10_000,
                    projection_version=1,
                )
            )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id=runtime_scope_id,
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v2",
                event_spec_id=event_spec_id,
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_id=exchange_instrument_id,
                position_side=position_side,
                enabled=True,
                scope_version=4,
                updated_at_ms=1_000,
            )
        )
        await _insert_scope_facts(
            connection,
            runtime_scope_id=runtime_scope_id,
            position_side=position_side,
        )


async def _seed_required_fact(
    engine: AsyncEngine,
    *,
    valid_until_ms: int,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(facts_current)
            .where(
                facts_current.c.runtime_scope_id == "scope-sor-btc-long",
                facts_current.c.fact_definition_id
                == "fact:opening_range_defined:v1",
            )
            .values(valid_until_ms=valid_until_ms)
        )


def _signal_facts(*, position_side: str) -> tuple[SignalFactSnapshot, ...]:
    if position_side == "long":
        values: tuple[tuple[str, object], ...] = (
            ("fact:opening_range_defined:v1", True),
            ("fact:breakout_confirmed:v1", True),
            ("fact:opening_range_low_reference:v1", "9900.0"),
        )
    else:
        values = (
            ("fact:opening_range_defined:v1", True),
            ("fact:breakdown_confirmed:v1", True),
            ("fact:opening_range_high_reference:v1", "10100.0"),
        )
    return tuple(
        SignalFactSnapshot(
            fact_definition_id=fact_definition_id,
            value=value,
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=10_000,
            projection_version=1,
        )
        for fact_definition_id, value in values
    )


async def _insert_scope_facts(
    connection: AsyncConnection,
    *,
    runtime_scope_id: str,
    position_side: str,
) -> None:
    for fact in _signal_facts(position_side=position_side):
        await connection.execute(
            sa.insert(facts_current).values(
                fact_current_id=(
                    f"fact-current:{runtime_scope_id}:{fact.fact_definition_id}"
                ),
                runtime_scope_id=runtime_scope_id,
                fact_definition_id=fact.fact_definition_id,
                value=fact.value,
                satisfied=fact.satisfied,
                observed_at_ms=fact.observed_at_ms,
                valid_until_ms=fact.valid_until_ms,
                projection_version=fact.projection_version,
            )
        )
