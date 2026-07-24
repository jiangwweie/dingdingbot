from __future__ import annotations

import os
from decimal import Decimal
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
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
)
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    positions_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.integration.test_issue_ticket import (
    _issue_request,
    _seed_ticket_runtime_scope,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


def _safe_liquidation_price(ticket, average_fill_price: Decimal) -> Decimal:
    liquidation_distance = (
        abs(average_fill_price - ticket.initial_stop_price)
        * ticket.min_liquidation_distance_to_stop_distance_ratio
    )
    return (
        ticket.initial_stop_price - liquidation_distance
        if ticket.identity.netting_domain.position_side == "long"
        else ticket.initial_stop_price + liquidation_distance
    )


@pytest_asyncio.fixture
async def certification_engine() -> AsyncEngine:
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


class MultiPositionVenue:
    def __init__(self) -> None:
        self.calls: list[VenueCommandRequest] = []

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls.append(request)
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000 + len(self.calls),
            exchange_order_id=(
                f"venue-{request.kind.value}-{request.position_side}-{len(self.calls)}"
            ),
        )


@pytest.mark.asyncio
async def test_two_serial_entries_become_concurrent_protected_long_short_positions(
    certification_engine: AsyncEngine,
) -> None:
    await _seed_policy(certification_engine)
    venue = MultiPositionVenue()
    long_ticket = _ticket()
    short_ticket = _ticket_for_side(
        long_ticket,
        signal_event_id="signal-2",
        exposure_episode_id="episode-2",
        position_side="short",
    )

    await _issue(certification_engine, long_ticket, "issuer-long", 1_001)
    await _protect(
        certification_engine,
        venue,
        long_ticket,
        entry_now_ms=1_100,
        fill_observed_at_ms=1_200,
        stop_now_ms=1_300,
    )

    await _issue(certification_engine, short_ticket, "issuer-short", 1_400)
    await _protect(
        certification_engine,
        venue,
        short_ticket,
        entry_now_ms=1_500,
        fill_observed_at_ms=1_600,
        stop_now_ms=1_700,
    )

    async with PostgresKernelUnitOfWork(certification_engine) as uow:
        long_aggregate = await uow.aggregates.get(long_ticket.identity.ticket_id)
        short_aggregate = await uow.aggregates.get(short_ticket.identity.ticket_id)
        long_commands = await uow.exchange_commands.list_for_ticket(
            long_ticket.identity.ticket_id
        )
        short_commands = await uow.exchange_commands.list_for_ticket(
            short_ticket.identity.ticket_id
        )
        long_budget = await uow.budgets.get_for_ticket(long_ticket.identity.ticket_id)
        short_budget = await uow.budgets.get_for_ticket(short_ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            long_ticket.identity.netting_domain.venue_id,
            long_ticket.identity.netting_domain.account_id
        )
    async with certification_engine.connect() as connection:
        position_rows = (
            await connection.execute(
                sa.select(positions_current).order_by(
                    positions_current.c.position_side
                )
            )
        ).mappings().all()

    assert long_aggregate is not None
    assert short_aggregate is not None
    assert long_aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert short_aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert long_aggregate.identity.netting_domain.position_side == "long"
    assert short_aggregate.identity.netting_domain.position_side == "short"
    assert long_aggregate.initial_stop_exchange_order_id != (
        short_aggregate.initial_stop_exchange_order_id
    )
    assert [command.kind.value for command in long_commands] == [
        "entry",
        "initial_stop",
        "take_profit",
    ]
    assert [command.kind.value for command in short_commands] == [
        "entry",
        "initial_stop",
        "take_profit",
    ]
    assert long_budget is not None and long_budget.status == "active"
    assert short_budget is not None and short_budget.status == "active"
    assert lane is not None and lane.status == "idle"
    assert exposure is not None
    assert exposure.active_ticket_count == 2
    assert exposure.gross_notional == long_ticket.notional + short_ticket.notional
    assert [(row["position_side"], row["quantity"]) for row in position_rows] == [
        ("long", long_ticket.quantity),
        ("short", short_ticket.quantity),
    ]
    assert [call.position_side for call in venue.calls] == [
        "long",
        "long",
        "long",
        "short",
        "short",
        "short",
    ]


async def _issue(
    engine: AsyncEngine,
    ticket,
    claim_owner: str,
    now_ms: int,
) -> None:
    await _seed_ticket_runtime_scope(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=now_ms,
                claim_owner=claim_owner,
            ),
        )
    assert result.status is IssueTicketStatus.ISSUED


async def _protect(
    engine: AsyncEngine,
    venue: MultiPositionVenue,
    ticket,
    *,
    entry_now_ms: int,
    fill_observed_at_ms: int,
    stop_now_ms: int,
) -> None:
    entry = await _dispatch(engine, venue, ticket.identity.ticket_id, entry_now_ms)
    assert entry.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        fill = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    liquidation_price=_safe_liquidation_price(
                        ticket, Decimal("60000")
                    ),
                    observed_at_ms=fill_observed_at_ms,
                ),
            ),
        )
    assert fill.status is ReconcileTicketStatus.ENTRY_FILL_RECORDED
    stop = await _dispatch(engine, venue, ticket.identity.ticket_id, stop_now_ms)
    assert stop.status is DispatchCommandStatus.ACCEPTED
    take_profit = await _dispatch(
        engine,
        venue,
        ticket.identity.ticket_id,
        stop_now_ms + 1,
    )
    assert take_profit.status is DispatchCommandStatus.ACCEPTED


async def _dispatch(
    engine: AsyncEngine,
    venue: MultiPositionVenue,
    ticket_id: str,
    now_ms: int,
):
    return await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=f"worker-{ticket_id}-{now_ms}",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
        ),
    )


def _ticket_for_side(
    template,
    *,
    signal_event_id: str,
    exposure_episode_id: str,
    position_side: str,
):
    domain = NettingDomain(
        venue_id=template.identity.netting_domain.venue_id,
        account_id=template.identity.netting_domain.account_id,
        exchange_instrument_id=(
            template.identity.netting_domain.exchange_instrument_id
        ),
        position_side=position_side,
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=template.identity.runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=template.identity.runtime,
        netting_domain=domain,
    )
    terms = {
        "identity": identity,
        "runtime_scope_id": "scope-sor-btc-short",
        "fact_digest": "sha256:" + "3" * 64,
    }
    if position_side == "short":
        terms.update(
            {
                "initial_stop_price": Decimal("61000"),
                "take_profit_prices": (Decimal("58000"),),
                "projected_liquidation_price": Decimal("63000"),
            }
        )
    return template.model_copy(update=terms)


async def _seed_policy(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_current).values(
                owner_policy_id="policy-main",
                policy_version=7,
                enabled=True,
                new_entry_submit_enabled=True,
                priority_rank=1,
                max_concurrent_tickets=3,
                planned_stop_risk_fraction="0.03",
                max_initial_margin_utilization="0.90",
                max_leverage=10,
                supported_margin_mode="cross",
                min_liquidation_distance_to_stop_distance_ratio="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={},
                updated_at_ms=1_000,
            )
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
