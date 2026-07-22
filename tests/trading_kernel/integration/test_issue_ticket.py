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

from src.trading_kernel.application.issue_ticket import (
    IssueTicketRequest,
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.domain.capacity import freeze_capacity_claim
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    entry_lane_current,
    owner_policy_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.test_ticket import _identity, _ticket


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def issue_engine() -> AsyncEngine:
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
async def test_issue_ticket_claims_global_lane_and_reserves_budget_atomically(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="worker-1",
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    assert result.ticket_id == ticket.identity.ticket_id

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        persisted = await uow.tickets.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.account_id
        )

    assert persisted == ticket
    assert reservation is not None
    assert reservation.reserved_notional == ticket.notional
    assert reservation.reserved_risk == ticket.risk_at_stop
    assert lane is not None
    assert lane.ticket_id == ticket.identity.ticket_id
    assert exposure is not None
    assert exposure.gross_notional == ticket.notional
    assert exposure.active_ticket_count == 1


@pytest.mark.asyncio
async def test_occupied_global_lane_serializes_two_different_tickets(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-2", "episode-2", position_side="short")

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        issued = await issue_ticket(
            uow,
            _issue_request(ticket=first, now_ms=1_001, claim_owner="worker-1"),
        )
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        blocked = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_002, claim_owner="worker-2"),
        )

    assert issued.status is IssueTicketStatus.ISSUED
    assert blocked.status is IssueTicketStatus.ENTRY_LANE_OCCUPIED


@pytest.mark.asyncio
async def test_expired_action_time_facts_cannot_issue_ticket(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    ticket = _ticket(expires_at_ms=2_000)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=2_000, claim_owner="worker-1"),
        )

    assert result.status is IssueTicketStatus.FACTS_EXPIRED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        assert await uow.tickets.get(ticket.identity.ticket_id) is None
        assert await uow.budgets.get_for_ticket(ticket.identity.ticket_id) is None


@pytest.mark.asyncio
async def test_missing_or_stale_owner_policy_blocks_ticket(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        missing = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )

    await _seed_policy(issue_engine, policy_version=8)
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        stale = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_002, claim_owner="worker-1"),
        )

    assert missing.status is IssueTicketStatus.POLICY_MISSING_OR_STALE
    assert stale.status is IssueTicketStatus.POLICY_MISSING_OR_STALE


@pytest.mark.asyncio
async def test_policy_and_budget_limits_fail_closed(
    issue_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(issue_engine, enabled=False)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        disabled = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )
    assert disabled.status is IssueTicketStatus.POLICY_DISABLED

    async with issue_engine.begin() as connection:
        await connection.execute(sa.delete(owner_policy_current))
    await _seed_policy(issue_engine, max_gross_notional="50")
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        exhausted = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_002, claim_owner="worker-1"),
        )
    assert exhausted.status is IssueTicketStatus.BUDGET_EXHAUSTED


@pytest.mark.asyncio
async def test_active_netting_domain_blocks_a_new_exposure_episode(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-2", "episode-2", position_side="long")
    await _issue_and_release_lane(issue_engine, first)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_010, claim_owner="worker-2"),
        )

    assert result.status is IssueTicketStatus.ACTIVE_NETTING_DOMAIN


@pytest.mark.asyncio
async def test_long_and_short_are_independent_default_netting_domains(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    long_ticket = _ticket()
    short_ticket = _ticket_for_signal(
        "signal-2",
        "episode-2",
        position_side="short",
    )
    await _issue_and_release_lane(issue_engine, long_ticket)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=short_ticket,
                now_ms=1_010,
                claim_owner="worker-short",
            ),
        )

    assert result.status is IssueTicketStatus.ISSUED
    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        exposure = await uow.entry_admission.get_account_exposure(
            long_ticket.identity.netting_domain.account_id
        )
    assert exposure is not None
    assert exposure.active_ticket_count == 2


@pytest.mark.asyncio
async def test_one_signal_cannot_create_a_second_ticket_identity(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    first = _ticket()
    second = _ticket_for_signal("signal-1", "episode-2", position_side="short")
    await _issue_and_release_lane(issue_engine, first)

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=second, now_ms=1_010, claim_owner="worker-2"),
        )

    assert result.status is IssueTicketStatus.DUPLICATE_SIGNAL


@pytest.mark.asyncio
async def test_two_worker_race_has_exactly_one_global_entry_winner(
    issue_engine: AsyncEngine,
) -> None:
    await _seed_policy(issue_engine)
    long_ticket = _ticket()
    short_ticket = _ticket_for_signal(
        "signal-2",
        "episode-2",
        position_side="short",
    )

    async def attempt(ticket, worker: str):
        async with PostgresKernelUnitOfWork(issue_engine) as uow:
            return await issue_ticket(
                uow,
                _issue_request(ticket=ticket, now_ms=1_001, claim_owner=worker),
            )

    results = await asyncio.gather(
        attempt(long_ticket, "worker-long"),
        attempt(short_ticket, "worker-short"),
    )

    assert sorted(result.status for result in results) == sorted(
        [IssueTicketStatus.ISSUED, IssueTicketStatus.ENTRY_LANE_OCCUPIED]
    )

    async with PostgresKernelUnitOfWork(issue_engine) as uow:
        persisted = [
            await uow.tickets.get(long_ticket.identity.ticket_id),
            await uow.tickets.get(short_ticket.identity.ticket_id),
        ]
    assert sum(ticket is not None for ticket in persisted) == 1


async def _seed_policy(
    engine: AsyncEngine,
    *,
    policy_version: int = 7,
    enabled: bool = True,
    real_submit_enabled: bool = True,
    max_gross_notional: str = "1000",
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=policy_version,
                enabled=enabled,
                real_submit_enabled=real_submit_enabled,
                max_concurrent_tickets=2,
                max_gross_notional=max_gross_notional,
                target_leverage="5",
                scope={},
                updated_at_ms=1_000,
            )
        )


async def _issue_and_release_lane(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="worker-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(entry_lane_current).values(
                ticket_id=None,
                signal_event_id=None,
                status="idle",
                claimed_at_ms=None,
                lease_until_ms=None,
                claim_owner=None,
                version=entry_lane_current.c.version + 1,
            )
        )


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
    return _ticket(identity=identity, runtime_scope_id=f"scope-{position_side}")


def _issue_request(*, ticket, now_ms: int, claim_owner: str) -> IssueTicketRequest:
    return IssueTicketRequest(
        capacity_claim=freeze_capacity_claim(
            ticket_identity=ticket.identity,
            owner_policy_id=ticket.owner_policy_id,
            owner_policy_version=ticket.owner_policy_version,
            runtime_scope_id=ticket.runtime_scope_id,
            runtime_scope_version=ticket.runtime_scope_version,
            fact_digest=ticket.fact_digest,
            action_facts_digest="sha256:" + "2" * 64,
            instrument_rules_projection_version=1,
            created_at_ms=ticket.created_at_ms,
            expires_at_ms=ticket.expires_at_ms,
            entry_reference_price=ticket.entry_reference_price,
            quantity=ticket.quantity,
            notional=ticket.notional,
            leverage=ticket.leverage,
            risk_at_stop=ticket.risk_at_stop,
            entry_order_type=ticket.entry_order_type,
            entry_limit_price=ticket.entry_limit_price,
            initial_stop_price=ticket.initial_stop_price,
            take_profit_prices=ticket.take_profit_prices,
        ),
        now_ms=now_ms,
        claim_owner=claim_owner,
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
