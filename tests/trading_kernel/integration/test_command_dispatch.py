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
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import (
    IssueTicketRequest,
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.test_ticket import _ticket


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def dispatch_engine() -> AsyncEngine:
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
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self.saw_committed_claim = False

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        async with PostgresKernelUnitOfWork(self._engine) as uow:
            command = await uow.exchange_commands.get(request.command_id)
        self.saw_committed_claim = (
            command is not None and command.status is ExchangeCommandStatus.CLAIMED
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="venue-entry-1",
        )


class RejectingVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.REJECTED,
            observed_at_ms=2_000,
            reason="insufficient_margin",
        )


class SlowVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        await asyncio.sleep(0.1)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="late-order",
        )


class CountingVenue:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id="unexpected-order",
        )


@pytest.mark.asyncio
async def test_dispatch_claims_then_calls_venue_outside_transaction_and_records_acceptance(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = AcceptingVenue(dispatch_engine)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.ACCEPTED
    assert venue.saw_committed_claim is True

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)

    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.ACCEPTED
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_ACCEPTED
    assert aggregate.entry_exchange_order_id == "venue-entry-1"
    assert len(events) == 2

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=2_100,
            lease_until_ms=7_100,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_authoritative_entry_rejection_releases_lane_and_budget_without_retry(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.account_id
        )
        persisted_ticket = await uow.tickets.get(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_REJECTED
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.REJECTED
    assert reservation is not None and reservation.status == "released"
    assert lane is not None and lane.status == "idle"
    assert exposure is not None and exposure.active_ticket_count == 0
    assert persisted_ticket is not None
    assert persisted_ticket.status.value == "entry_rejected"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=2_100,
            lease_until_ms=7_100,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_timeout_becomes_unknown_outcome_incident_and_is_never_redispatched(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-1",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=0.01,
        ),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert len(commands) == 1
    assert commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None
    assert incident.incident_kind == "entry_outcome_unknown"
    assert reservation is not None and reservation.status == "active"
    assert lane is not None and lane.status == "claimed"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="dispatcher-2",
            now_ms=7_000,
            lease_until_ms=12_000,
            timeout_seconds=0.01,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_restart_conserves_expired_claim_as_unknown_without_redispatch(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        claimed = await uow.exchange_commands.claim_one_prepared(
            worker_id="crashed-worker",
            now_ms=1_100,
            lease_until_ms=1_200,
        )
    assert claimed is not None

    venue = CountingVenue()
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="restart-worker",
            now_ms=1_300,
            lease_until_ms=6_300,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    assert venue.calls == 0

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.ENTRY_OUTCOME_UNKNOWN
    assert commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None


async def _seed_policy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                real_submit_enabled=True,
                max_concurrent_tickets=2,
                max_gross_notional="1000",
                scope={},
                updated_at_ms=1_000,
            )
        )


async def _issue(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            IssueTicketRequest(ticket=ticket, now_ms=1_001, claim_owner="issuer-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED


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
