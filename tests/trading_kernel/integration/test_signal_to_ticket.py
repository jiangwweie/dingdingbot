from __future__ import annotations

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
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.infrastructure.pg_models import (
    facts_current,
    instrument_rules_current,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    signal_fact_snapshots,
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
async def test_ingest_persists_signal_and_fact_lineage_without_ticket_terms(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
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

    assert result.status is IngestSignalStatus.CANDIDATE_READY
    assert result.signal_event_id == signal.signal_event_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        persisted = await uow.signals.get(signal.signal_event_id)
        persisted_facts = await uow.signals.get_fact_snapshots(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)

    assert persisted == signal
    assert persisted_facts == signal.facts
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    assert readiness.first_blocker is None
    assert readiness.signal_event_id == signal.signal_event_id
    assert readiness.fact_summary == {
        "fact_count": len(signal.facts),
        "fact_digest": signal.fact_digest,
    }

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_002),
        )

    assert selected.status is SelectEntryCandidateStatus.SELECTED
    assert selected.candidate is not None
    assert selected.candidate.signal.signal_event_id == signal.signal_event_id
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        assert await uow.capacity_claims.get_for_signal(signal.signal_event_id) is None
        assert not await uow.entry_admission.has_ticket_for_signal(
            signal.signal_event_id
        )
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    assert readiness.first_blocker is None


@pytest.mark.asyncio
async def test_signal_ingest_does_not_consume_action_time_capital_authority(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(owner_policy_current).values(
                enabled=False,
                real_submit_enabled=False,
            )
        )
        await connection.execute(
            sa.update(runtime_profiles).values(position_mode="one_way")
        )
        await connection.execute(sa.delete(instrument_rules_current))

    signal = _signal(signal_event_id="signal-no-capital-authority")
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

    assert result.status is IngestSignalStatus.CANDIDATE_READY
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.signals.get(signal.signal_event_id) == signal


@pytest.mark.asyncio
async def test_duplicate_strategy_signal_is_exactly_idempotent(
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

    assert first.status is IngestSignalStatus.CANDIDATE_READY
    assert duplicate.status is IngestSignalStatus.DUPLICATE_SIGNAL
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        facts = await uow.signals.get_fact_snapshots(signal.signal_event_id)
    async with issue_engine.connect() as connection:
        fact_row_count = await connection.scalar(
            sa.select(sa.func.count())
            .select_from(signal_fact_snapshots)
            .where(
                signal_fact_snapshots.c.signal_event_id
                == signal.signal_event_id
            )
        )

    assert readiness is not None
    assert readiness.projection_version == 1
    assert facts == signal.facts
    assert fact_row_count == len(signal.facts)


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("stale", IngestSignalStatus.SIGNAL_INVALID_OR_STALE),
        ("scope-version", IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH),
        ("side", IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH),
        ("scope-disabled", IngestSignalStatus.SCOPE_OR_POLICY_MISMATCH),
        ("commit", IngestSignalStatus.SCHEMA_IDENTITY_MISMATCH),
        ("fact-value", IngestSignalStatus.SIGNAL_INVALID_OR_STALE),
        ("fact-stale", IngestSignalStatus.SIGNAL_INVALID_OR_STALE),
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
        signal = _signal(
            signal_event_id="signal-side",
            runtime_scope_id="scope-sor-btc-long",
            position_side="short",
        )
    elif case == "scope-disabled":
        async with issue_engine.begin() as connection:
            await connection.execute(
                sa.update(runtime_scopes_current).values(enabled=False)
            )
    elif case == "commit":
        runtime_commit = "wrong-commit"
    elif case == "fact-value":
        async with issue_engine.begin() as connection:
            await connection.execute(
                sa.update(facts_current)
                .where(
                    facts_current.c.fact_definition_id
                    == "fact:breakout_confirmed:v1"
                )
                .values(value=False, satisfied=False)
            )
    elif case == "fact-stale":
        async with issue_engine.begin() as connection:
            await connection.execute(
                sa.update(facts_current).values(valid_until_ms=1_001)
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
        assert await uow.signals.get_readiness(signal.runtime_scope_id) is None


@pytest.mark.asyncio
async def test_expired_candidate_is_terminally_blocked(
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
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                action_time_facts=_action_time_facts(signal.signal_event_id),
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                now_ms=signal.expires_at_ms,
            ),
        )

    assert result.status is IssueTicketStatus.SIGNAL_INVALID_OR_STALE
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "signal_invalid_or_stale"


@pytest.mark.asyncio
async def test_no_candidate_returns_explicit_idle_result(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_001),
        )

    assert result.status is SelectEntryCandidateStatus.NO_CANDIDATE
    assert result.candidate is None


def _signal(
    *,
    signal_event_id: str = "signal-live-1",
    runtime_scope_id: str = "scope-sor-btc-long",
    position_side: str = "long",
    exchange_instrument_id: str = "binance-usdm:BTCUSDT:perpetual",
    occurred_at_ms: int = 1_000,
) -> StrategySignal:
    event_spec_id = (
        "event_spec:SOR-001:SOR-LONG:v2"
        if position_side == "long"
        else "event_spec:SOR-001:SOR-SHORT:v2"
    )
    facts = _signal_facts(position_side=position_side)
    return StrategySignal(
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
        observed_at_ms=occurred_at_ms + 1,
        expires_at_ms=10_000,
        facts=facts,
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
                capability_key="strategy_signal_ingest",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision="0001_initial",
                certification={},
                updated_at_ms=1_000,
            )
        )


def _signal_facts(*, position_side: str) -> tuple[SignalFactSnapshot, ...]:
    if position_side == "long":
        values: tuple[tuple[str, str, object, bool], ...] = (
            ("fact:opening_range_defined:v1", "condition", True, True),
            ("fact:breakout_confirmed:v1", "condition", True, True),
            (
                "fact:opening_range_low_reference:v1",
                "protection_reference",
                "9900.0",
                True,
            ),
        )
    else:
        values = (
            ("fact:opening_range_defined:v1", "condition", True, True),
            ("fact:breakdown_confirmed:v1", "condition", True, True),
            (
                "fact:opening_range_high_reference:v1",
                "protection_reference",
                "10100.0",
                True,
            ),
        )
    return tuple(
        SignalFactSnapshot(
            fact_definition_id=fact_definition_id,
            role=role,
            value=value,
            satisfied=satisfied,
            observed_at_ms=1_000,
            valid_until_ms=10_000,
            projection_version=1,
        )
        for fact_definition_id, role, value, satisfied in values
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


def _action_time_facts(signal_event_id: str) -> ActionTimeFacts:
    return ActionTimeFacts(
        signal_event_id=signal_event_id,
        runtime_scope_id="scope-sor-btc-long",
        venue_id="binance-usdm",
        account_id="subaccount-main",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal("10000"),
        account_equity=Decimal("1000"),
        available_margin=Decimal("1000"),
        netting_domain_position_qty=Decimal("0"),
        netting_domain_open_order_count=0,
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )
