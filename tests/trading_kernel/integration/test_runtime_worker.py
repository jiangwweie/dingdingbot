from __future__ import annotations

import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.ingest_signal import (
    IngestSignalRequest,
    IngestSignalStatus,
    ingest_signal,
)
from src.trading_kernel.application.issue_ticket import (
    IssueTicketRequest,
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.runtime import (
    MonitorOwnerStatus,
    RuntimeActionStatus,
    RuntimeTickRequest,
    derive_monitor_state,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    monitor_current,
    monitor_events,
    owner_policy_current,
    runtime_profiles,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.interfaces.readonly_api import get_monitor_state
from src.trading_kernel.interfaces.worker import run_worker_once
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.integration.test_signal_to_ticket import (
    _seed_runtime_authority,
    _signal,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def runtime_engine() -> AsyncEngine:
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


class AcceptingVenue:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="venue-entry-1",
        )


class NoCallVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        raise AssertionError(f"venue must not be called for {request.command_id}")


class SlowVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        await asyncio.sleep(0.1)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="late-order",
        )


def test_runtime_tick_requires_exact_code_and_schema_identity() -> None:
    with pytest.raises(ValidationError):
        RuntimeTickRequest(
            monitor_key="strategy:SOR-001",
            owner_policy_id="policy-main",
            worker_id="runtime-worker-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_worker_issues_ready_signal_and_dispatches_entry_in_one_tick(
    runtime_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(runtime_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
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

    venue = AcceptingVenue()
    result = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        venue,
        RuntimeTickRequest(
            monitor_key="strategy:SOR-001",
            owner_policy_id="policy-main",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            worker_id="runtime-worker-signal",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )

    assert result.issued_ticket_id is not None
    assert result.action_status is RuntimeActionStatus.ACCEPTED
    assert result.command_id is not None
    assert venue.calls == 1
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        ticket = await uow.tickets.get(result.issued_ticket_id)
        aggregate = await uow.aggregates.get(result.issued_ticket_id)
    assert ticket is not None
    assert ticket.identity.signal_event_id == signal.signal_event_id
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED


@pytest.mark.asyncio
async def test_schema_blocked_readiness_projects_and_retains_temporarily_unavailable(
    runtime_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(runtime_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
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
    request = RuntimeTickRequest(
        monitor_key="strategy:SOR-001",
        owner_policy_id="policy-main",
        runtime_commit="wrong-runtime-head",
        schema_revision="0001_initial",
        worker_id="runtime-worker-schema-blocked",
        now_ms=1_100,
        lease_until_ms=6_100,
        timeout_seconds=1,
    )

    first = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        NoCallVenue(),
        request,
    )
    repeated = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        NoCallVenue(),
        request.model_copy(update={"now_ms": 1_200, "lease_until_ms": 6_200}),
    )

    assert first.action_status is RuntimeActionStatus.NO_COMMAND
    assert first.monitor.owner_status.value == "temporarily_unavailable"
    assert repeated.monitor.owner_status.value == "temporarily_unavailable"
    assert repeated.monitor.projection_version == first.monitor.projection_version


@pytest.mark.asyncio
async def test_account_mode_blocked_readiness_requires_intervention(
    runtime_engine: AsyncEngine,
) -> None:
    await _seed_runtime_authority(runtime_engine)
    signal = _signal()
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
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
    async with runtime_engine.begin() as connection:
        await connection.execute(
            sa.update(runtime_profiles).values(position_mode="one_way")
        )

    result = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        NoCallVenue(),
        RuntimeTickRequest(
            monitor_key="strategy:SOR-001",
            owner_policy_id="policy-main",
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            worker_id="runtime-worker-account-mode",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )

    assert result.action_status is RuntimeActionStatus.NO_COMMAND
    assert result.monitor.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
    assert result.monitor.intervention == "需要介入"


@pytest.mark.asyncio
async def test_one_worker_invocation_processes_one_command_without_history_scan(
    runtime_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(runtime_engine, enabled=True)
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        issued = await issue_ticket(
            uow,
            IssueTicketRequest(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="issuer-1",
            ),
        )
    assert issued.status is IssueTicketStatus.ISSUED

    statements: list[str] = []

    def capture_sql(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(" ".join(statement.lower().split()))

    event.listen(runtime_engine.sync_engine, "before_cursor_execute", capture_sql)
    venue = AcceptingVenue()
    try:
        result = await run_worker_once(
            lambda: PostgresKernelUnitOfWork(runtime_engine),
            venue,
            RuntimeTickRequest(
                monitor_key="strategy:SOR-001",
                owner_policy_id=ticket.owner_policy_id,
                runtime_commit="kernel-test-head",
                schema_revision="0001_initial",
                ticket_id=ticket.identity.ticket_id,
                worker_id="runtime-worker-1",
                now_ms=1_100,
                lease_until_ms=6_100,
                timeout_seconds=1,
            ),
        )
    finally:
        event.remove(runtime_engine.sync_engine, "before_cursor_execute", capture_sql)

    assert result.action_status is RuntimeActionStatus.ACCEPTED
    assert result.monitor.owner_status is MonitorOwnerStatus.PROCESSING
    assert venue.calls == 1
    assert not any(
        statement.startswith("select") and "brc_trade_events" in statement
        for statement in statements
    )

    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        monitor = await get_monitor_state(uow, "strategy:SOR-001")
    assert monitor is not None
    assert monitor.owner_status is MonitorOwnerStatus.PROCESSING
    assert monitor.ticket_id == ticket.identity.ticket_id


@pytest.mark.asyncio
async def test_ticket_scoped_worker_never_claims_another_ticket_command(
    runtime_engine: AsyncEngine,
) -> None:
    first_ticket = _ticket()
    second_ticket = _ticket_for_side(
        first_ticket,
        side="short",
        signal_event_id="signal-short-1",
        exposure_episode_id="episode-short-1",
    )
    await _seed_policy(runtime_engine, enabled=True)
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        first = TicketIssued(
            event_id="event:first:1",
            ticket=first_ticket,
            sequence=1,
            occurred_at_ms=1_001,
        )
        await uow.commit_reduction(
            event=first,
            reduction=reduce_event(None, first),
            expected_version=0,
        )
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        second = TicketIssued(
            event_id="event:second:1",
            ticket=second_ticket,
            sequence=1,
            occurred_at_ms=1_002,
        )
        await uow.commit_reduction(
            event=second,
            reduction=reduce_event(None, second),
            expected_version=0,
        )

    venue = AcceptingVenue()
    result = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        venue,
        RuntimeTickRequest(
            monitor_key="strategy:SOR-001:short",
            owner_policy_id=second_ticket.owner_policy_id,
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            ticket_id=second_ticket.identity.ticket_id,
            worker_id="runtime-worker-short",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )

    assert result.monitor.ticket_id == second_ticket.identity.ticket_id
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        first_commands = await uow.exchange_commands.list_for_ticket(
            first_ticket.identity.ticket_id
        )
        second_commands = await uow.exchange_commands.list_for_ticket(
            second_ticket.identity.ticket_id
        )
    assert first_commands[0].status is ExchangeCommandStatus.PREPARED
    assert second_commands[0].status is ExchangeCommandStatus.ACCEPTED


@pytest.mark.asyncio
async def test_unknown_command_outcome_projects_owner_intervention_state(
    runtime_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(runtime_engine, enabled=True)
    async with PostgresKernelUnitOfWork(runtime_engine) as uow:
        issued = await issue_ticket(
            uow,
            IssueTicketRequest(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="issuer-1",
            ),
        )
    assert issued.status is IssueTicketStatus.ISSUED

    result = await run_worker_once(
        lambda: PostgresKernelUnitOfWork(runtime_engine),
        SlowVenue(),
        RuntimeTickRequest(
            monitor_key="strategy:SOR-001",
            owner_policy_id=ticket.owner_policy_id,
            runtime_commit="kernel-test-head",
            schema_revision="0001_initial",
            ticket_id=ticket.identity.ticket_id,
            worker_id="runtime-worker-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=0.01,
        ),
    )

    assert result.action_status is RuntimeActionStatus.OUTCOME_UNKNOWN
    assert result.monitor.owner_status is MonitorOwnerStatus.NEEDS_INTERVENTION
    assert result.monitor.incident_id is not None
    assert result.monitor.intervention == "需要介入"


@pytest.mark.asyncio
async def test_no_signal_tick_writes_no_files_and_only_material_monitor_transition(
    runtime_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_policy(runtime_engine, enabled=True)
    monkeypatch.chdir(tmp_path)
    statements: list[str] = []

    def capture_sql(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        normalized = " ".join(statement.lower().split())
        if normalized.startswith(("insert", "update", "delete")):
            statements.append(normalized)

    event.listen(runtime_engine.sync_engine, "before_cursor_execute", capture_sql)
    request = RuntimeTickRequest(
        monitor_key="strategy:SOR-001",
        owner_policy_id="policy-main",
        runtime_commit="kernel-test-head",
        schema_revision="0001_initial",
        ticket_id=None,
        worker_id="runtime-worker-1",
        now_ms=1_100,
        lease_until_ms=6_100,
        timeout_seconds=1,
    )
    try:
        first = await run_worker_once(
            lambda: PostgresKernelUnitOfWork(runtime_engine),
            NoCallVenue(),
            request,
        )
        first_write_count = len(statements)
        statements.clear()
        repeated = await run_worker_once(
            lambda: PostgresKernelUnitOfWork(runtime_engine),
            NoCallVenue(),
            request.model_copy(
                update={
                    "now_ms": 1_200,
                    "lease_until_ms": 6_200,
                }
            ),
        )
    finally:
        event.remove(runtime_engine.sync_engine, "before_cursor_execute", capture_sql)

    assert first.action_status is RuntimeActionStatus.NO_COMMAND
    assert first.monitor.owner_status is MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY
    assert repeated.action_status is RuntimeActionStatus.NO_COMMAND
    assert repeated.monitor.projection_version == first.monitor.projection_version
    assert first_write_count == 2
    assert statements == []
    assert list(tmp_path.rglob("*")) == []
    async with runtime_engine.connect() as connection:
        current_count = await connection.scalar(
            sa.select(sa.func.count()).select_from(monitor_current)
        )
        event_count = await connection.scalar(
            sa.select(sa.func.count()).select_from(monitor_events)
        )
    assert current_count == 1
    assert event_count == 1


@pytest.mark.parametrize(
    ("policy_enabled", "aggregate_status", "incident_id", "expected"),
    [
        (True, None, None, MonitorOwnerStatus.WAITING_FOR_OPPORTUNITY),
        (False, None, None, MonitorOwnerStatus.PAUSED),
        (True, AggregateStatus.ENTRY_PENDING, None, MonitorOwnerStatus.PROCESSING),
        (
            True,
            AggregateStatus.ENTRY_PENDING,
            "incident-1",
            MonitorOwnerStatus.NEEDS_INTERVENTION,
        ),
        (True, AggregateStatus.TERMINAL, None, MonitorOwnerStatus.COMPLETED),
    ],
)
def test_monitor_projection_uses_small_owner_product_state_vocabulary(
    policy_enabled: bool,
    aggregate_status: AggregateStatus | None,
    incident_id: str | None,
    expected: MonitorOwnerStatus,
) -> None:
    ticket = _ticket()
    aggregate = None
    if aggregate_status is not None:
        aggregate = reduce_event(
            None,
            TicketIssued(
                event_id="event-1",
                ticket=ticket,
                sequence=1,
                occurred_at_ms=1_001,
            ),
        ).aggregate.model_copy(update={"status": aggregate_status})

    monitor = derive_monitor_state(
        monitor_key="strategy:SOR-001",
        policy_enabled=policy_enabled,
        aggregate=aggregate,
        incident_id=incident_id,
        ticket_id=None if aggregate is None else ticket.identity.ticket_id,
        updated_at_ms=2_000,
    )

    assert monitor.owner_status is expected
    assert monitor.intervention == (
        "需要介入" if expected is MonitorOwnerStatus.NEEDS_INTERVENTION else "无需操作"
    )


def test_worker_cli_exposes_explicit_one_shot_dependency_boundary(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "trading_kernel" / "run_worker_once.py"),
            "--help",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--venue-factory" in result.stdout
    assert "--database-url" in result.stdout
    assert list(tmp_path.rglob("*")) == []


async def _seed_policy(engine: AsyncEngine, *, enabled: bool) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=enabled,
                real_submit_enabled=enabled,
                max_concurrent_tickets=2,
                max_gross_notional="1000",
                scope={},
                updated_at_ms=1_000,
            )
        )


def _ticket_for_side(
    base_ticket,
    *,
    side: str,
    signal_event_id: str,
    exposure_episode_id: str,
):
    domain = base_ticket.identity.netting_domain.model_copy(
        update={"position_side": side}
    )
    identity = base_ticket.identity.model_copy(
        update={
            "ticket_id": build_ticket_id(
                signal_event_id=signal_event_id,
                runtime=base_ticket.identity.runtime,
                netting_domain=domain,
            ),
            "signal_event_id": signal_event_id,
            "exposure_episode_id": exposure_episode_id,
            "netting_domain": domain,
        }
    )
    return base_ticket.model_copy(
        update={
            "identity": identity,
            "runtime_scope_id": f"scope-{side}",
        }
    )


def _database_url(database_name: str) -> str:
    if SAFE_DATABASE.fullmatch(database_name) is None:
        raise ValueError("unsafe kernel test database name")
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base.replace('postgresql://', 'postgresql+asyncpg://', 1)}/{database_name}"


def _run_alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "TRADING_KERNEL_DATABASE_URL": database_url}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]
