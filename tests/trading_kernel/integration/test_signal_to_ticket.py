from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal
from types import SimpleNamespace
from typing import Literal
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

import src.trading_kernel.application.issue_ready_signal as issue_ready_signal_module
from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
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
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    InstrumentRulesFacts,
    InstrumentRulesRequest,
    ProductSessionRequest,
)
from src.trading_kernel.application.select_entry_candidate import (
    SelectEntryCandidateRequest,
    SelectEntryCandidateStatus,
    select_entry_candidate,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import (
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductSessionSnapshot,
    product_compatibility_for,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)
from src.trading_kernel.domain.strategy_universe import build_strategy_universe
from src.trading_kernel.infrastructure.pg_models import (
    budget_reservations,
    capacity_claims,
    exchange_commands,
    facts_current,
    instrument_certification_current,
    instrument_product_current,
    instrument_product_profiles,
    instrument_rules_current,
    instruments,
    owner_authorizations,
    owner_policy_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    signal_fact_snapshots,
    strategy_entry_control_events,
    strategy_entry_controls_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresAdmissionDecisionRepository,
    PostgresEntryAdmissionRepository,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)
from src.trading_kernel.interfaces.entry_worker import (
    EntryWorkerRequest,
    EntryWorkerStatus,
    run_entry_worker_once,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    ADMIN_DSN,
    SAFE_DATABASE,
    _database_url,
    _run_alembic,
)


@pytest_asyncio.fixture(name="issue_engine")
async def signal_engine() -> AsyncGenerator[AsyncEngine, None]:
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
                schema_revision=CURRENT_SCHEMA_REVISION,
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
                new_entry_submit_enabled=False,
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
                schema_revision=CURRENT_SCHEMA_REVISION,
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
        schema_revision=CURRENT_SCHEMA_REVISION,
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
                sa.delete(strategy_universe_current).where(
                    strategy_universe_current.c.event_spec_id
                    == "event_spec:SOR-001:SOR-LONG:v4"
                )
            )
            await connection.execute(
                sa.update(runtime_scopes_current).values(
                    lifecycle_state="retired",
                    observation_enabled=False,
                    entry_enabled=False,
                )
            )
            await connection.execute(
                sa.update(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.universe_version_id
                    == "universe:sor-long:4"
                )
                .values(lifecycle_state="retired", retired_at_ms=1_001)
            )
    elif case == "commit":
        runtime_commit = "wrong-commit"
    elif case == "fact-value":
        async with issue_engine.begin() as connection:
            await connection.execute(
                sa.update(facts_current)
                .where(
                    facts_current.c.fact_definition_id
                    == "fact:breakout_edge_crossed_v3:v3"
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
                schema_revision=CURRENT_SCHEMA_REVISION,
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
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=_admission_snapshot(),
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
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
async def test_candidate_selection_repairs_expired_ready_projection(
    issue_engine: AsyncEngine,
) -> None:
    """Catches expired Signals remaining visible as current candidate-ready state."""

    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-expired-projection")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        selected = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=signal.expires_at_ms),
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)

    assert selected.status is SelectEntryCandidateStatus.NO_CANDIDATE
    assert selected.candidate is None
    assert readiness is not None
    assert readiness.signal_event_id == signal.signal_event_id
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "signal_invalid_or_stale"


@pytest.mark.asyncio
async def test_issues_ticket_with_finite_terminal_bracket_in_stress_range(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal()
    snapshot = _admission_snapshot()
    risk_values = snapshot.account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )
    risk_values["configured_leverage"] = 5
    snapshot = snapshot.model_copy(
        update={
            "account_risk_snapshot": AccountRiskSnapshot.create(**risk_values)
        }
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=snapshot,
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert result.ticket_id is not None
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        claim = await uow.capacity_claims.get_for_signal(signal.signal_event_id)
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert claim is not None
    assert decision is not None
    assert decision.decision_status.value == "admitted"
    assert decision.capacity_claim_id == claim.capacity_claim_id
    assert decision.ticket_id == result.ticket_id
    assert readiness is not None
    assert readiness.readiness_state == "processing"
    assert readiness.first_blocker is None


@pytest.mark.asyncio
async def test_capacity_rejection_records_one_decision_and_no_trading_authority(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-budget-rejected")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    exhausted_account = AccountRiskSnapshot.create(
        **{
            **_admission_snapshot().account_risk_snapshot.model_dump(
                mode="python",
                exclude={"snapshot_digest"},
            ),
            "available_margin": Decimal(0),
            "configured_leverage": 5,
        }
    )
    exhausted_snapshot = EntryAdmissionSnapshot(
        account_risk_snapshot=exhausted_account,
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=exhausted_snapshot,
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.BUDGET_EXHAUSTED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert decision is not None
    assert decision.decision_status.value == "rejected"
    assert decision.first_blocker == "budget_exhausted"
    assert decision.capacity_claim_id is None
    assert decision.ticket_id is None
    assert readiness is not None
    assert readiness.first_blocker == "budget_exhausted"
    async with issue_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(capacity_claims)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_tickets)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands)
        ) == 0


@pytest.mark.asyncio
async def test_product_identity_drift_records_causal_decision_without_trading_authority(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-product-rejected")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    product_profile = InstrumentProductProfile(
        exchange_instrument_id=signal.exchange_instrument_id,
        product_family="tradfi_equity_perpetual",
        asset_class="equity",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        entry_session_policy="regular_only",
        status="active",
        max_entry_spread_bps=Decimal(20),
        max_mark_index_deviation_bps=Decimal(50),
    )
    product_snapshot = ProductSessionSnapshot(
        exchange_instrument_id=signal.exchange_instrument_id,
        product_family="tradfi_equity_perpetual",
        product_status="active",
        session_state="regular",
        regular_session_open_ms=900,
        regular_session_close_ms=2_000,
        mark_price=Decimal(10000),
        index_price=Decimal(10000),
        best_bid=Decimal(9980),
        best_ask=Decimal(10020),
        best_bid_quantity=Decimal(1),
        best_ask_quantity=Decimal(1),
        corporate_event_status="clear",
        observed_at_ms=1_000,
        valid_until_ms=10_000,
        source_ref="test:product-rejection",
    )
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_product_profiles)
            .where(
                instrument_product_profiles.c.exchange_instrument_id
                == signal.exchange_instrument_id
            )
            .values(
                **product_profile.model_dump(mode="python"),
                semantic_digest=product_profile.semantic_digest,
                updated_at_ms=1_001,
            )
        )
        await connection.execute(
            sa.insert(instrument_product_current).values(
                **product_snapshot.model_dump(
                    mode="python",
                    exclude={"product_family"},
                ),
                projection_version=1,
            )
        )

    snapshot = _admission_snapshot()
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=snapshot,
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.PRODUCT_ENTRY_BLOCKED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert decision is not None
    assert decision.decision_status.value == "rejected"
    assert decision.first_blocker == "product_entry_blocked"
    assert decision.binding_constraint == "identity_mismatch"
    assert decision.entry_admission_snapshot_digest == snapshot.digest()
    assert decision.capacity_claim_id is None
    assert decision.ticket_id is None
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "product_entry_blocked"
    async with issue_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(capacity_claims)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_tickets)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands)
        ) == 0


@pytest.mark.asyncio
async def test_tradfi_signal_issues_ticket_and_durable_entry_command(
    issue_engine: AsyncEngine,
) -> None:
    signal, snapshot = await _seed_tradfi_live_authority(issue_engine)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=snapshot,
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert result.ticket_id is not None
    async with issue_engine.connect() as connection:
        command = (
            await connection.execute(
                sa.select(exchange_commands).where(
                    exchange_commands.c.ticket_id == result.ticket_id
                )
            )
        ).mappings().one()
    assert command["command_kind"] == "entry"
    assert command["status"] == "prepared"


@pytest.mark.asyncio
async def test_tradfi_dispatch_rejects_mismatched_product_family_before_venue(
    issue_engine: AsyncEngine,
) -> None:
    signal, snapshot = await _seed_tradfi_live_authority(issue_engine)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        issued = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=snapshot,
                claim_owner="signal-worker-1",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )
    assert issued.status is IssueTicketStatus.ISSUED
    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_050,
            )
        )
    venue = _CountingEntryVenue()

    dispatched = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(issue_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            ticket_id=issued.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=_MismatchedTradFiProductFacts(),
    )

    assert dispatched.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with issue_engine.connect() as connection:
        command = (
            await connection.execute(
                sa.select(exchange_commands).where(
                    exchange_commands.c.command_id == dispatched.command_id
                )
            )
        ).mappings().one()
    assert command["status"] == "rejected"
    assert command["result_payload"]["reason"] == (
        "dispatch_preflight:product_entry_blocked"
    )


@pytest.mark.asyncio
async def test_tradfi_entry_worker_rejects_mismatched_product_family_before_ticket(
    issue_engine: AsyncEngine,
) -> None:
    signal, _snapshot = await _seed_tradfi_live_authority(issue_engine)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY
    async with issue_engine.connect() as connection:
        product_before = (
            await connection.execute(
                sa.select(instrument_product_current).where(
                    instrument_product_current.c.exchange_instrument_id
                    == signal.exchange_instrument_id
                )
            )
        ).mappings().one()
    venue = _CountingEntryVenue()

    result = await run_entry_worker_once(
        lambda: PostgresKernelUnitOfWork(issue_engine),
        venue,
        _MismatchedTradFiProductFacts(),
        EntryWorkerRequest(
            worker_id="entry-worker",
            runtime_commit="kernel-test-head",
            schema_revision=CURRENT_SCHEMA_REVISION,
            now_ms=1_002,
            lease_until_ms=6_002,
            timeout_seconds=1,
            admission_snapshot_validity_ms=1_000,
        ),
    )

    assert result.status is EntryWorkerStatus.ISSUE_REFUSED
    assert result.issue_status is IssueTicketStatus.PRODUCT_ENTRY_BLOCKED
    assert result.ticket_id is None
    assert result.command_id is None
    assert venue.calls == 0
    async with issue_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(trade_tickets)
        ) == 0
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(exchange_commands)
        ) == 0
        product_after = (
            await connection.execute(
                sa.select(instrument_product_current).where(
                    instrument_product_current.c.exchange_instrument_id
                    == signal.exchange_instrument_id
                )
            )
        ).mappings().one()
    assert dict(product_after) == dict(product_before)


@pytest.mark.asyncio
async def test_adm_003_reprocessing_signal_keeps_one_final_decision(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-adm-003")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    account = AccountRiskSnapshot.create(
        **{
            **_admission_snapshot().account_risk_snapshot.model_dump(
                mode="python",
                exclude={"snapshot_digest"},
            ),
            "available_margin": Decimal(0),
            "configured_leverage": 5,
        }
    )
    snapshot = EntryAdmissionSnapshot(
        account_risk_snapshot=account,
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )
    request = IssueReadySignalRequest(
        signal_event_id=signal.signal_event_id,
        admission_snapshot=snapshot,
        claim_owner="signal-worker-adm-003",
        runtime_commit="kernel-test-head",
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=1_002,
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        first = await issue_ready_signal(uow, request)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        second = await issue_ready_signal(uow, request)

    assert first.status is IssueTicketStatus.BUDGET_EXHAUSTED
    assert second.status is IssueTicketStatus.NO_READY_SIGNAL
    async with issue_engine.connect() as connection:
        assert await connection.scalar(
            sa.text(
                "SELECT count(*) FROM brc_admission_decisions "
                "WHERE signal_event_id = :signal_event_id"
            ),
            {"signal_event_id": signal.signal_event_id},
        ) == 1


@pytest.mark.asyncio
async def test_adm_008_action_time_policy_mismatch_commits_decision_and_readiness(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-adm-008")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    risk_values = _admission_snapshot().account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )
    risk_values["configured_leverage"] = 10
    mismatch_snapshot = _admission_snapshot().model_copy(
        update={"account_risk_snapshot": AccountRiskSnapshot.create(**risk_values)}
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ready_signal(
            uow,
            IssueReadySignalRequest(
                signal_event_id=signal.signal_event_id,
                admission_snapshot=mismatch_snapshot,
                claim_owner="signal-worker-adm-008",
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_002,
            ),
        )

    assert result.status is IssueTicketStatus.SIGNAL_INVALID_OR_STALE
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert decision is not None
    assert decision.first_blocker == "signal_invalid_or_stale"
    assert readiness is not None
    assert readiness.readiness_state == "blocked"
    assert readiness.first_blocker == "signal_invalid_or_stale"


@pytest.mark.asyncio
async def test_adm_008_decision_failure_rolls_back_mismatch_readiness(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-adm-008-rollback")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    risk_values = _admission_snapshot().account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )
    risk_values["configured_leverage"] = 10
    mismatch_snapshot = _admission_snapshot().model_copy(
        update={"account_risk_snapshot": AccountRiskSnapshot.create(**risk_values)}
    )

    async def fail_add(*args, **kwargs) -> None:
        del args, kwargs
        raise RuntimeError("injected ADM-008 Decision failure")

    monkeypatch.setattr(PostgresAdmissionDecisionRepository, "add", fail_add)
    with pytest.raises(RuntimeError, match="ADM-008"):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    signal_event_id=signal.signal_event_id,
                    admission_snapshot=mismatch_snapshot,
                    claim_owner="signal-worker-adm-008",
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    now_ms=1_002,
                ),
            )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
    assert decision is None
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    assert readiness.first_blocker is None


@pytest.mark.asyncio
async def test_cap_014_unknown_registry_family_fails_closed_without_claim(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-cap-014")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    monkeypatch.setattr(
        issue_ready_signal_module,
        "strategy_contract_for",
        lambda event_spec_id: SimpleNamespace(
            event_spec_id=event_spec_id,
            exposure_family="unknown_family",
        ),
    )

    with pytest.raises(ValueError, match="Exposure Family"):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    signal_event_id=signal.signal_event_id,
                    admission_snapshot=_admission_snapshot(),
                    claim_owner="signal-worker-cap-014",
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    now_ms=1_002,
                ),
            )

    async with issue_engine.connect() as connection:
        assert await connection.scalar(
            sa.select(sa.func.count()).select_from(capacity_claims)
        ) == 0


@pytest.mark.asyncio
async def test_locked_family_rejection_records_decision_without_claim_or_ticket(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-locked-family-rejected")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    original_count = PostgresEntryAdmissionRepository.count_active_family_tickets
    family_count_calls = 0

    async def count_family_at_lock(*args, **kwargs) -> int:
        nonlocal family_count_calls
        family_count_calls += 1
        if family_count_calls == 1:
            return 0
        return 2

    monkeypatch.setattr(
        PostgresEntryAdmissionRepository,
        "count_active_family_tickets",
        count_family_at_lock,
    )
    risk_values = _admission_snapshot().account_risk_snapshot.model_dump(
        mode="python",
        exclude={"snapshot_digest"},
    )
    risk_values["configured_leverage"] = 5
    admission_snapshot = _admission_snapshot().model_copy(
        update={"account_risk_snapshot": AccountRiskSnapshot.create(**risk_values)}
    )
    try:
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            result = await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    signal_event_id=signal.signal_event_id,
                    admission_snapshot=admission_snapshot,
                    claim_owner="signal-worker-1",
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    now_ms=1_002,
                ),
            )
    finally:
        monkeypatch.setattr(
            PostgresEntryAdmissionRepository,
            "count_active_family_tickets",
            original_count,
        )

    assert result.status is IssueTicketStatus.EXPOSURE_FAMILY_CAPACITY_EXHAUSTED
    assert family_count_calls == 2
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
    assert decision is not None
    assert decision.decision_status.value == "rejected"
    assert decision.first_blocker == "exposure_family_capacity_exhausted"
    assert decision.binding_constraint == "exposure_family_capacity_exhausted"
    assert decision.capacity_claim_id is None
    assert decision.ticket_id is None
    async with issue_engine.connect() as connection:
        for table in (
            capacity_claims,
            trade_tickets,
            budget_reservations,
            exchange_commands,
        ):
            assert await connection.scalar(
                sa.select(sa.func.count()).select_from(table)
            ) == 0


@pytest.mark.asyncio
async def test_decision_insert_failure_rolls_back_ticket_and_command(
    issue_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-decision-rollback")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async def fail_add(*args, **kwargs) -> None:
        del args, kwargs
        raise RuntimeError("injected AdmissionDecision failure")

    monkeypatch.setattr(PostgresAdmissionDecisionRepository, "add", fail_add)
    with pytest.raises(RuntimeError, match="injected AdmissionDecision"):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            await issue_ready_signal(
                uow,
                IssueReadySignalRequest(
                    signal_event_id=signal.signal_event_id,
                    admission_snapshot=_admission_snapshot(),
                    claim_owner="signal-worker-1",
                    runtime_commit="kernel-test-head",
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    now_ms=1_002,
                ),
            )

    async with issue_engine.connect() as connection:
        for table in (
            capacity_claims,
            trade_tickets,
            budget_reservations,
            exchange_commands,
        ):
            assert await connection.scalar(
                sa.select(sa.func.count()).select_from(table)
            ) == 0
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)
        decision = await uow.admission_decisions.get_for_signal(
            signal.signal_event_id
        )
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    assert decision is None


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


@pytest.mark.asyncio
async def test_stale_certification_pauses_candidate_until_same_signal_recovers(
    issue_engine: AsyncEngine,
) -> None:
    """Catches candidate arbitration ignoring current instrument eligibility."""

    await _seed_runtime_authority(issue_engine)
    signal = _signal(signal_event_id="signal-certification-recovery")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        ingested = await ingest_signal(
            uow,
            IngestSignalRequest(
                signal=signal,
                runtime_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                now_ms=1_001,
            ),
        )
    assert ingested.status is IngestSignalStatus.CANDIDATE_READY

    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_certification_current)
            .where(
                instrument_certification_current.c.runtime_profile_id
                == "tiny-live-v1",
                instrument_certification_current.c.exchange_instrument_id
                == signal.exchange_instrument_id,
            )
            .values(
                observed_at_ms=900,
                valid_until_ms=1_002,
                next_check_at_ms=1_002,
                projection_version=1,
            )
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        stale = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_002),
        )
    assert stale.status is SelectEntryCandidateStatus.NO_CANDIDATE

    async with issue_engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_certification_current).values(
                observed_at_ms=1_002,
                valid_until_ms=10_000,
                next_check_at_ms=5_000,
                projection_version=2,
            )
        )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        recovered = await select_entry_candidate(
            uow,
            SelectEntryCandidateRequest(now_ms=1_003),
        )
        readiness = await uow.signals.get_readiness(signal.runtime_scope_id)

    assert recovered.status is SelectEntryCandidateStatus.SELECTED
    assert recovered.candidate is not None
    assert recovered.candidate.signal.signal_event_id == signal.signal_event_id
    assert readiness is not None
    assert readiness.readiness_state == "candidate_ready"
    assert readiness.first_blocker is None


def _signal(
    *,
    signal_event_id: str = "signal-live-1",
    runtime_scope_id: str = "scope-sor-btc-long",
    position_side: Literal["long", "short"] = "long",
    exchange_instrument_id: str = "binance-usdm:BTCUSDT:perpetual",
    occurred_at_ms: int = 1_000,
) -> StrategySignal:
    event_spec_id = (
        "event_spec:SOR-001:SOR-LONG:v4"
        if position_side == "long"
        else "event_spec:SOR-001:SOR-SHORT:v4"
    )
    facts = _signal_facts(position_side=position_side)
    return StrategySignal(
        signal_event_id=signal_event_id,
        exposure_episode_id=f"episode:{signal_event_id}",
        runtime_scope_id=runtime_scope_id,
        runtime_scope_version=4,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_id=event_spec_id,
        universe_version_id="universe:sor-long:4",
        universe_semantic_digest="sha256:" + "a" * 64,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
        fact_digest=build_signal_fact_digest(facts),
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=occurred_at_ms + 1,
        expires_at_ms=10_000,
        facts=facts,
    )


def _maintenance_brackets() -> tuple[MaintenanceMarginBracket, ...]:
    return (
        MaintenanceMarginBracket(
            bracket_id="test:1",
            notional_floor=Decimal(0),
            notional_cap=Decimal(20_000),
            maintenance_margin_rate=Decimal("0.005"),
            maintenance_amount=Decimal(0),
        ),
    )


async def _seed_runtime_authority(engine: AsyncEngine) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_strategy_registry(uow, seeded_at_ms=1_000)

    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_authorizations).values(
                authorization_id="owner-authorization:seed:SOR-001",
                purpose="strategy_resume",
                owner_identity="system-seed",
                authentication_strength="session",
                request_digest="sha256:" + "0" * 64,
                target_scope={"seed": True},
                idempotency_key="owner-request:seed:SOR-001",
                authorized_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_control_events).values(
                strategy_entry_control_event_id=(
                    "strategy-control-event:seed:SOR-001"
                ),
                strategy_group_id="SOR-001",
                control_version=1,
                operation="resume",
                target_state="enabled",
                authorization_id="owner-authorization:seed:SOR-001",
                reason="seed_enabled",
                payload={},
                created_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_controls_current).values(
                strategy_group_id="SOR-001",
                entry_state="enabled",
                control_version=1,
                last_event_id="strategy-control-event:seed:SOR-001",
                reason="seed_enabled",
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(instruments).values(
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                venue_id="binance-usdm",
                asset_class="crypto",
                venue_symbol="BTCUSDT",
                contract_kind="perpetual",
                status="active",
            )
        )
        product_profile = InstrumentProductProfile(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            product_family="crypto_perpetual",
            asset_class="crypto",
            contract_type="PERPETUAL",
            underlying_type="CRYPTO",
            margin_asset="USDT",
            entry_session_policy="continuous",
            status="candidate",
        )
        await connection.execute(
            sa.insert(instrument_product_profiles).values(
                **product_profile.model_dump(mode="python"),
                semantic_digest=product_profile.semantic_digest,
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id="universe:sor-long:4",
                strategy_group_id="SOR-001",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version=4,
                semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                installed_at_ms=900,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members).values(
                universe_version_id="universe:sor-long:4",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                universe_version_id="universe:sor-long:4",
                semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            sa.insert(instrument_rules_current).values(
                venue_id="binance-usdm",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.1"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),
                exchange_max_leverage=10,
                maintenance_margin_brackets=[
                    item.model_dump(mode="json") for item in _maintenance_brackets()
                ],
                maintenance_margin_brackets_digest=canonical_digest(
                    _maintenance_brackets()
                ),
                notional_coefficient=Decimal(1),
                notional_coefficient_certified=True,
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
                new_entry_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=8,
                max_strategy_group_concurrent_tickets=2,
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction=Decimal("0.02"),
                max_gross_stop_risk_fraction=Decimal("0.06"),
                max_ticket_initial_margin_fraction=Decimal("0.30"),
                max_gross_initial_margin_utilization=Decimal("0.90"),
                directional_stop_risk_limit_fraction=Decimal("0.04"),
                min_materialization_ratio=Decimal("0.50"),
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple=Decimal("2.0"),
                max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": (
                                "event_spec:SOR-001:SOR-LONG:v4"
                            ),
                            "runtime_profile_id": "tiny-live-v1",
                        },
                        {
                            "event_spec_id": (
                                "event_spec:SOR-001:SOR-SHORT:v4"
                            ),
                            "runtime_profile_id": "tiny-live-v1",
                        },
                    ]
                },
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
            sa.insert(instrument_certification_current).values(
                runtime_profile_id="tiny-live-v1",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                status="eligible",
                blocker_code=None,
                facts_digest="sha256:" + "c" * 64,
                product_rules_digest="sha256:" + "d" * 64,
                configured_leverage=5,
                margin_mode="cross",
                position_mode="independent_sides",
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                next_check_at_ms=5_000,
                lease_owner=None,
                lease_expires_at_ms=None,
                lease_universe_version_id=None,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id="scope-sor-btc-long",
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                event_spec_id="event_spec:SOR-001:SOR-LONG:v4",
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
                position_side="long",
                universe_version_id="universe:sor-long:4",
                universe_semantic_digest="sha256:" + "a" * 64,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=4,
                warm_closed_bar_time_ms=900,
                warm_completed_at_ms=900,
                warm_readiness_digest="sha256:" + "a" * 64,
                warm_valid_until_ms=10_000,
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
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
                updated_at_ms=1_000,
            )
        )


async def _seed_tradfi_live_authority(
    engine: AsyncEngine,
) -> tuple[StrategySignal, EntryAdmissionSnapshot]:
    await _seed_runtime_authority(engine)
    event_spec_id = "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1"
    strategy_group_id = "SOR-US-EQ-PERP-001"
    strategy_version_id = "sgv:SOR-US-EQ-PERP-001:v1"
    runtime_profile_id = "tradfi-equity-usdm-v1"
    runtime_scope_id = "scope-sor-us-aapl-long"
    exchange_instrument_id = "binance-usdm:AAPLUSDT:perpetual"
    universe = build_strategy_universe(
        universe_version_id="universe:sor-us-aapl-long:1",
        strategy_group_id=strategy_group_id,
        event_spec_id=event_spec_id,
        universe_version=1,
        exchange_instrument_ids=(exchange_instrument_id,),
        installed_at_ms=900,
    )
    compatibility = product_compatibility_for(event_spec_id)
    product_profile = InstrumentProductProfile(
        exchange_instrument_id=exchange_instrument_id,
        product_family=compatibility.product_family,
        asset_class=compatibility.asset_class,
        contract_type=compatibility.contract_type,
        underlying_type=compatibility.underlying_type,
        margin_asset=compatibility.margin_asset,
        entry_session_policy="regular_only",
        status="active",
        max_entry_spread_bps=Decimal(20),
        max_mark_index_deviation_bps=Decimal(50),
    )
    product_snapshot = ProductSessionSnapshot(
        exchange_instrument_id=exchange_instrument_id,
        product_family="tradfi_equity_perpetual",
        product_status="active",
        session_state="regular",
        regular_session_open_ms=900,
        regular_session_close_ms=9_000,
        mark_price=Decimal(100),
        index_price=Decimal(100),
        best_bid=Decimal("99.95"),
        best_ask=Decimal("100.05"),
        best_bid_quantity=Decimal(10),
        best_ask_quantity=Decimal(10),
        corporate_event_status="unavailable",
        observed_at_ms=1_000,
        valid_until_ms=10_000,
        source_ref="test:tradfi-live-authority",
    )
    signal_facts = _tradfi_signal_facts()
    signal = StrategySignal(
        signal_event_id="signal-tradfi-live-1",
        exposure_episode_id="episode:signal-tradfi-live-1",
        runtime_scope_id=runtime_scope_id,
        runtime_scope_version=1,
        strategy_group_id=strategy_group_id,
        strategy_version_id=strategy_version_id,
        event_spec_id=event_spec_id,
        universe_version_id=universe.universe_version_id,
        universe_semantic_digest=universe.semantic_digest,
        exchange_instrument_id=exchange_instrument_id,
        position_side="long",
        fact_digest=build_signal_fact_digest(signal_facts),
        occurred_at_ms=1_000,
        observed_at_ms=1_001,
        expires_at_ms=10_000,
        facts=signal_facts,
    )
    admission_snapshot = EntryAdmissionSnapshot(
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id=exchange_instrument_id,
            mark_price=Decimal(100),
            configured_leverage=5,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=1_001,
            valid_until_ms=10_000,
        ),
        best_bid_price=Decimal("99.95"),
        best_ask_price=Decimal("100.05"),
        open_orders=(),
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )

    async with engine.begin() as connection:
        policy_scope = {
            "event_runtime_profiles": [
                {
                    "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": event_spec_id,
                    "runtime_profile_id": runtime_profile_id,
                },
            ]
        }
        await connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == "policy-main")
            .values(scope=policy_scope)
        )
        await connection.execute(
            sa.insert(owner_authorizations).values(
                authorization_id=(
                    "owner-authorization:seed:SOR-US-EQ-PERP-001"
                ),
                purpose="strategy_resume",
                owner_identity="system-seed",
                authentication_strength="session",
                request_digest="sha256:" + "1" * 64,
                target_scope={"seed": True},
                idempotency_key=(
                    "owner-request:seed:SOR-US-EQ-PERP-001"
                ),
                authorized_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_control_events).values(
                strategy_entry_control_event_id=(
                    "strategy-control-event:seed:SOR-US-EQ-PERP-001"
                ),
                strategy_group_id=strategy_group_id,
                control_version=1,
                operation="resume",
                target_state="enabled",
                authorization_id=(
                    "owner-authorization:seed:SOR-US-EQ-PERP-001"
                ),
                reason="seed_enabled",
                payload={},
                created_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(strategy_entry_controls_current).values(
                strategy_group_id=strategy_group_id,
                entry_state="enabled",
                control_version=1,
                last_event_id=(
                    "strategy-control-event:seed:SOR-US-EQ-PERP-001"
                ),
                reason="seed_enabled",
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(instruments).values(
                exchange_instrument_id=exchange_instrument_id,
                venue_id="binance-usdm",
                asset_class="equity",
                venue_symbol="AAPLUSDT",
                contract_kind="perpetual",
                status="active",
            )
        )
        await connection.execute(
            sa.update(instrument_product_profiles)
            .where(
                instrument_product_profiles.c.exchange_instrument_id
                == exchange_instrument_id
            )
            .values(
                **product_profile.model_dump(mode="python"),
                semantic_digest=product_profile.semantic_digest,
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.update(instrument_product_current)
            .where(
                instrument_product_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
            .values(
                **product_snapshot.model_dump(
                    mode="python",
                    exclude={"product_family"},
                ),
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id=universe.universe_version_id,
                strategy_group_id=strategy_group_id,
                event_spec_id=event_spec_id,
                universe_version=universe.universe_version,
                semantic_digest=universe.semantic_digest,
                lifecycle_state="active",
                installed_at_ms=universe.installed_at_ms,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members).values(
                universe_version_id=universe.universe_version_id,
                exchange_instrument_id=exchange_instrument_id,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_current).values(
                event_spec_id=event_spec_id,
                universe_version_id=universe.universe_version_id,
                semantic_digest=universe.semantic_digest,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=950,
            )
        )
        await connection.execute(
            sa.insert(instrument_rules_current).values(
                venue_id="binance-usdm",
                exchange_instrument_id=exchange_instrument_id,
                quantity_step=Decimal("0.001"),
                price_tick=Decimal("0.01"),
                min_quantity=Decimal("0.001"),
                min_notional=Decimal(5),
                exchange_max_leverage=10,
                maintenance_margin_brackets=[
                    item.model_dump(mode="json")
                    for item in _maintenance_brackets()
                ],
                maintenance_margin_brackets_digest=canonical_digest(
                    _maintenance_brackets()
                ),
                notional_coefficient=Decimal(1),
                notional_coefficient_certified=True,
                session_and_settlement={"entry_session_policy": "regular_only"},
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(runtime_profiles).values(
                runtime_profile_id=runtime_profile_id,
                venue_id="binance-usdm",
                account_id="subaccount-main",
                environment="live",
                position_mode="independent_sides",
                status="active",
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(instrument_certification_current).values(
                runtime_profile_id=runtime_profile_id,
                exchange_instrument_id=exchange_instrument_id,
                status="eligible",
                blocker_code=None,
                facts_digest="sha256:" + "e" * 64,
                product_rules_digest="sha256:" + "f" * 64,
                configured_leverage=5,
                margin_mode="cross",
                position_mode="independent_sides",
                observed_at_ms=1_000,
                valid_until_ms=10_000,
                next_check_at_ms=5_000,
                lease_owner=None,
                lease_expires_at_ms=None,
                lease_universe_version_id=None,
                projection_version=1,
            )
        )
        await connection.execute(
            sa.insert(runtime_scopes_current).values(
                runtime_scope_id=runtime_scope_id,
                strategy_group_id=strategy_group_id,
                strategy_version_id=strategy_version_id,
                event_spec_id=event_spec_id,
                runtime_profile_id=runtime_profile_id,
                owner_policy_id="policy-main",
                exchange_instrument_id=exchange_instrument_id,
                position_side="long",
                universe_version_id=universe.universe_version_id,
                universe_semantic_digest=universe.semantic_digest,
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=1,
                warm_closed_bar_time_ms=900,
                warm_completed_at_ms=900,
                warm_readiness_digest=universe.semantic_digest,
                warm_valid_until_ms=10_000,
                updated_at_ms=1_000,
            )
        )
        for fact in signal_facts:
            await connection.execute(
                sa.insert(facts_current).values(
                    fact_current_id=(
                        f"fact-current:{runtime_scope_id}:"
                        f"{fact.fact_definition_id}"
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
    return signal, admission_snapshot


def _tradfi_signal_facts() -> tuple[SignalFactSnapshot, ...]:
    values: tuple[
        tuple[
            str,
            Literal[
                "condition",
                "protection_reference",
                "identity_reference",
                "lifecycle_reference",
                "disable",
            ],
            JsonValue,
            bool,
        ],
        ...,
    ] = (
        ("fact:regular_session_confirmed_us_v1:v1", "condition", True, True),
        ("fact:opening_range_defined_us_v1:v1", "condition", True, True),
        ("fact:breakout_edge_crossed_us_v1:v1", "condition", True, True),
        (
            "fact:opening_range_high_reference_us_v1:v1",
            "lifecycle_reference",
            "100.00",
            True,
        ),
        (
            "fact:initial_stop_reference_us_v1:v1",
            "protection_reference",
            "98.00",
            True,
        ),
        (
            "fact:regular_session_open_ms_us_v1:v1",
            "identity_reference",
            "900",
            True,
        ),
        (
            "fact:session_exit_deadline_ms_us_v1:v1",
            "lifecycle_reference",
            "8100",
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


class _CountingEntryVenue:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self,
        request: VenueCommandRequest,
    ) -> ExchangeCommandResult:
        self.calls += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=1_100,
            exchange_order_id="unexpected-entry-order",
        )


class _MismatchedTradFiProductFacts:
    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        return EntryAdmissionSnapshot(
            account_risk_snapshot=AccountRiskSnapshot.create(
                venue_id=request.venue_id,
                account_id=request.account_id,
                account_risk_mode="standard_usdm_single_asset",
                settlement_asset="USDT",
                position_mode="independent_sides",
                margin_mode="cross",
                exchange_instrument_id=request.exchange_instrument_id,
                mark_price=Decimal(100),
                configured_leverage=5,
                total_wallet_balance=Decimal(1000),
                total_margin_balance=Decimal(1000),
                total_initial_margin=Decimal(0),
                total_maintenance_margin=Decimal(0),
                available_margin=Decimal(1000),
                account_positions=(),
                observed_at_ms=request.observed_at_ms,
                valid_until_ms=request.observed_at_ms + request.valid_for_ms,
            ),
            best_bid_price=Decimal("99.95"),
            best_ask_price=Decimal("100.05"),
            open_orders=(),
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts:
        return InstrumentRulesFacts(
            exchange_instrument_id=request.exchange_instrument_id,
            quantity_step=Decimal("0.001"),
            price_tick=Decimal("0.01"),
            min_quantity=Decimal("0.001"),
            min_notional=Decimal(5),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_maintenance_brackets(),
            maintenance_margin_brackets_digest=canonical_digest(
                _maintenance_brackets()
            ),
            notional_coefficient=Decimal(1),
            notional_coefficient_certified=True,
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + request.valid_for_ms,
        )

    async def read_product_session(
        self,
        request: ProductSessionRequest,
    ) -> ProductSessionSnapshot:
        return ProductSessionSnapshot(
            exchange_instrument_id=request.exchange_instrument_id,
            product_family="crypto_perpetual",
            product_status="active",
            session_state="regular",
            regular_session_open_ms=900,
            regular_session_close_ms=9_000,
            mark_price=Decimal(100),
            index_price=Decimal(100),
            best_bid=Decimal("99.95"),
            best_ask=Decimal("100.05"),
            best_bid_quantity=Decimal(10),
            best_ask_quantity=Decimal(10),
            corporate_event_status="clear",
            observed_at_ms=request.observed_at_ms,
            valid_until_ms=request.observed_at_ms + 1_000,
            source_ref="test:mismatched-product-family",
        )


def _signal_facts(
    *, position_side: Literal["long", "short"]
) -> tuple[SignalFactSnapshot, ...]:
    if position_side == "long":
        values: tuple[
            tuple[
                str,
                Literal[
                    "condition",
                    "protection_reference",
                    "identity_reference",
                    "lifecycle_reference",
                    "disable",
                ],
                JsonValue,
                bool,
            ],
            ...,
        ] = (
            ("fact:opening_range_defined_v3:v3", "condition", True, True),
            ("fact:breakout_edge_crossed_v3:v3", "condition", True, True),
            (
                "fact:opening_range_high_reference_v3:v3",
                "lifecycle_reference",
                "10050.0",
                True,
            ),
            (
                "fact:opening_range_low_reference_v3:v3",
                "protection_reference",
                "9900.0",
                True,
            ),
            (
                "fact:session_start_ms_v3:v3",
                "identity_reference",
                "1000",
                True,
            ),
            (
                "fact:session_end_ms_v3:v3",
                "lifecycle_reference",
                "86401000",
                True,
            ),
        )
    else:
        values = (
            ("fact:opening_range_defined_v3:v3", "condition", True, True),
            ("fact:breakdown_edge_crossed_v3:v3", "condition", True, True),
            (
                "fact:opening_range_low_reference_v3:v3",
                "lifecycle_reference",
                "9950.0",
                True,
            ),
            (
                "fact:opening_range_high_reference_v3:v3",
                "protection_reference",
                "10100.0",
                True,
            ),
            (
                "fact:session_start_ms_v3:v3",
                "identity_reference",
                "1000",
                True,
            ),
            (
                "fact:session_end_ms_v3:v3",
                "lifecycle_reference",
                "86401000",
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
    position_side: Literal["long", "short"],
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


def _admission_snapshot() -> EntryAdmissionSnapshot:
    return EntryAdmissionSnapshot(
        account_risk_snapshot=AccountRiskSnapshot.create(
            venue_id="binance-usdm",
            account_id="subaccount-main",
            account_risk_mode="standard_usdm_single_asset",
            settlement_asset="USDT",
            position_mode="independent_sides",
            margin_mode="cross",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            mark_price=Decimal(10000),
            configured_leverage=1,
            total_wallet_balance=Decimal(1000),
            total_margin_balance=Decimal(1000),
            total_initial_margin=Decimal(0),
            total_maintenance_margin=Decimal(0),
            available_margin=Decimal(1000),
            account_positions=(),
            observed_at_ms=1_001,
            valid_until_ms=10_000,
        ),
        best_bid_price=Decimal("9999.9"),
        best_ask_price=Decimal(10000),
        open_orders=(),
        observed_at_ms=1_001,
        valid_until_ms=10_000,
    )
