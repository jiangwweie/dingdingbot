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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
)
from src.trading_kernel.application.ports import RuntimeIncidentRecord
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.events import TicketIssued
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    AggregateVersionConflict,
    PostgresKernelUnitOfWork,
)
from tests.trading_kernel.unit.test_ticket import _identity, _ticket


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def kernel_engine() -> AsyncEngine:
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
async def test_reduction_commits_ticket_aggregate_event_and_command_atomically(
    kernel_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    event = TicketIssued(
        event_id="event-issued-1",
        ticket=ticket,
        sequence=1,
        occurred_at_ms=1_001,
    )
    reduction = reduce_event(None, event)

    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        await uow.commit_reduction(
            event=event,
            reduction=reduction,
            expected_version=0,
        )

    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        assert await uow.tickets.get(ticket.identity.ticket_id) == ticket
        assert await uow.aggregates.get(ticket.identity.ticket_id) == reduction.aggregate
        assert await uow.events.list_for_ticket(ticket.identity.ticket_id) == [event]
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    assert len(commands) == 1
    assert commands[0].kind is ExchangeCommandKind.ENTRY
    assert commands[0].status is ExchangeCommandStatus.PREPARED
    assert commands[0].payload.quantity == ticket.quantity


@pytest.mark.asyncio
async def test_event_uniqueness_failure_rolls_back_every_new_projection(
    kernel_engine: AsyncEngine,
) -> None:
    first_ticket = _ticket()
    first_event = TicketIssued(
        event_id="event-duplicate",
        ticket=first_ticket,
        sequence=1,
        occurred_at_ms=1_001,
    )
    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        await uow.commit_reduction(
            event=first_event,
            reduction=reduce_event(None, first_event),
            expected_version=0,
        )

    second_ticket = _ticket_for_signal("signal-2", "episode-2", position_side="short")
    duplicate_event = TicketIssued(
        event_id="event-duplicate",
        ticket=second_ticket,
        sequence=1,
        occurred_at_ms=1_002,
    )
    with pytest.raises(IntegrityError):
        async with PostgresKernelUnitOfWork(kernel_engine) as uow:
            await uow.commit_reduction(
                event=duplicate_event,
                reduction=reduce_event(None, duplicate_event),
                expected_version=0,
            )

    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        assert await uow.tickets.get(second_ticket.identity.ticket_id) is None
        assert await uow.aggregates.get(second_ticket.identity.ticket_id) is None
        assert await uow.events.list_for_ticket(second_ticket.identity.ticket_id) == []
        assert (
            await uow.exchange_commands.list_for_ticket(
                second_ticket.identity.ticket_id
            )
            == []
        )


@pytest.mark.asyncio
async def test_two_workers_enforce_optimistic_aggregate_version(
    kernel_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    event = TicketIssued(
        event_id="event-version-1",
        ticket=ticket,
        sequence=1,
        occurred_at_ms=1_001,
    )
    aggregate = reduce_event(None, event).aggregate
    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(None, event),
            expected_version=0,
        )

    update = aggregate.model_copy(update={"version": 2, "last_event_sequence": 2})

    async def save_from_worker() -> None:
        async with PostgresKernelUnitOfWork(kernel_engine) as uow:
            await uow.aggregates.save(update, expected_version=1)

    results = await asyncio.gather(
        save_from_worker(),
        save_from_worker(),
        return_exceptions=True,
    )

    assert sum(result is None for result in results) == 1
    conflicts = [
        result for result in results if isinstance(result, AggregateVersionConflict)
    ]
    assert len(conflicts) == 1

    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        current = await uow.aggregates.get(ticket.identity.ticket_id)
    assert current is not None
    assert current.version == 2


@pytest.mark.asyncio
async def test_admission_ownership_is_bounded_to_exact_account_and_instrument(
    kernel_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    event = TicketIssued(
        event_id="event-ownership-1",
        ticket=ticket,
        sequence=1,
        occurred_at_ms=1_001,
    )
    async with PostgresKernelUnitOfWork(kernel_engine) as uow:
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(None, event),
            expected_version=0,
        )
        await uow.incidents.add(
            RuntimeIncidentRecord(
                incident_id="incident:account-capacity",
                ticket_id=ticket.identity.ticket_id,
                incident_kind="external_ownership",
                status="open",
                first_blocker="external_ownership",
                entry_block_scope=EntryBlockScope.ACCOUNT_CAPACITY,
                entry_block_key=(
                    f"{ticket.identity.netting_domain.venue_id}:"
                    f"{ticket.identity.netting_domain.account_id}"
                ),
                details={},
                opened_at_ms=1_002,
            )
        )
        ownership = await uow.entry_admission.read_admission_ownership(
            venue_id=ticket.identity.netting_domain.venue_id,
            account_id=ticket.identity.netting_domain.account_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
        )

    assert ownership.owned_position_domain_keys == (
        ticket.identity.netting_domain.key(),
    )
    assert ownership.open_incident_scopes == (EntryBlockScope.ACCOUNT_CAPACITY,)


def _ticket_for_signal(
    signal_event_id: str,
    exposure_episode_id: str,
    *,
    position_side: str,
):
    original = _identity()
    domain = NettingDomain(
        venue_id=original.netting_domain.venue_id,
        account_id=original.netting_domain.account_id,
        exchange_instrument_id=original.netting_domain.exchange_instrument_id,
        position_side=position_side,
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=original.runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=original.runtime,
        netting_domain=domain,
    )
    return _ticket(identity=identity, runtime_scope_id=f"scope-{signal_event_id}")


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
