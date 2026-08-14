from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import AsyncGenerator
from decimal import Decimal
from pathlib import Path
from typing import Literal
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
from src.trading_kernel.application.ports import (
    VenueCommandRequest,
    VenueSetLeverageRequest,
)
from src.trading_kernel.application.reconcile_ticket import (
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    ExchangeCommandResult,
    ExchangeCommandStatus,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.identities import NettingDomain, TicketIdentity
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    positions_current,
    runtime_capabilities_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.integration.test_command_dispatch import (
    _commit_passed_post_fill_stress_if_pending,
    _ticket,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    _seed_ticket_runtime_scope,
)
from tests.trading_kernel.support.capacity_claims import (
    make_issue_request as _issue_request,
)
from tests.trading_kernel.support.dispatch_venues import PreflightFacts

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def certification_engine() -> AsyncGenerator[AsyncEngine, None]:
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

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult:
        return SetLeverageCommandResult(
            exchange_configured_leverage=request.payload.desired_leverage,
            leverage_verified_at_ms=2_000,
            leverage_verification_digest="sha256:" + "4" * 64,
        )


@pytest.mark.asyncio
async def test_two_serial_entries_become_concurrent_protected_long_short_positions(
    certification_engine: AsyncEngine,
) -> None:
    await _seed_policy(certification_engine)
    venue = MultiPositionVenue()
    long_ticket = _ticket()
    short_ticket = _ticket_for_domain(
        long_ticket,
        signal_event_id="signal-2",
        exposure_episode_id="episode-2",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="short",
        runtime_scope_id="scope-sor-btc-short",
        runtime=long_ticket.identity.runtime.model_copy(
            update={"event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4"}
        ),
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


@pytest.mark.asyncio
async def test_three_serial_tickets_protect_independent_domains_and_fence_refusals(
    certification_engine: AsyncEngine,
) -> None:
    await _seed_policy(certification_engine)
    venue = MultiPositionVenue()
    btc_long = _ticket()
    btc_short = _ticket_for_domain(
        btc_long,
        signal_event_id="signal-btc-short",
        exposure_episode_id="episode-btc-short",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="short",
        runtime_scope_id="scope-sor-btc-short",
        runtime=btc_long.identity.runtime.model_copy(
            update={"event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4"}
        ),
    )
    cpm_runtime = btc_long.identity.runtime.model_copy(
        update={
            "strategy_group_id": "CPM-RO-001",
            "strategy_version_id": "sgv:CPM-RO-001:v3",
            "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v3",
        }
    )
    eth_long = _ticket_for_domain(
        btc_long,
        signal_event_id="signal-eth-long",
        exposure_episode_id="episode-eth-long",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        position_side="long",
        runtime_scope_id="scope-cpm-eth-long",
        runtime=cpm_runtime,
    )

    for index, ticket in enumerate((btc_long, btc_short, eth_long), start=1):
        issued_at_ms = 1_000 + index * 1_000
        await _issue(
            certification_engine,
            ticket,
            f"issuer-{index}",
            issued_at_ms,
        )
        await _protect(
            certification_engine,
            venue,
            ticket,
            entry_now_ms=issued_at_ms + 100,
            fill_observed_at_ms=issued_at_ms + 200,
            stop_now_ms=issued_at_ms + 300,
        )

    mi_runtime = eth_long.identity.runtime.model_copy(
        update={
            "strategy_group_id": "MI-001",
            "strategy_version_id": "sgv:MI-001:v3",
            "event_spec_id": "event_spec:MI-001:MI-LONG:v3",
        }
    )
    same_direction = _ticket_for_domain(
        eth_long,
        signal_event_id="signal-eth-mi-long",
        exposure_episode_id="episode-eth-mi-long",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        position_side="long",
        runtime_scope_id="scope-mi-eth-long",
        runtime=mi_runtime,
    )
    brf_runtime = eth_long.identity.runtime.model_copy(
        update={
            "strategy_group_id": "BRF2-001",
            "strategy_version_id": "sgv:BRF2-001:v3",
            "event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v3",
        }
    )
    fourth_ticket = _ticket_for_domain(
        eth_long,
        signal_event_id="signal-eth-short",
        exposure_episode_id="episode-eth-short",
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
        position_side="short",
        runtime_scope_id="scope-brf-eth-short",
        runtime=brf_runtime,
    )
    venue_call_count = len(venue.calls)

    same_direction_result = await _attempt_issue(
        certification_engine,
        same_direction,
        claim_owner="issuer-same-direction",
        now_ms=5_100,
    )
    fourth_result = await _attempt_issue(
        certification_engine,
        fourth_ticket,
        claim_owner="issuer-fourth",
        now_ms=5_200,
    )

    async with PostgresKernelUnitOfWork(certification_engine) as uow:
        aggregates = [
            await uow.aggregates.get(ticket.identity.ticket_id)
            for ticket in (btc_long, btc_short, eth_long)
        ]
        commands = [
            await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
            for ticket in (btc_long, btc_short, eth_long)
        ]
        lane = await uow.entry_admission.get_global_lane()
        exposure = await uow.entry_admission.get_account_exposure(
            btc_long.identity.netting_domain.venue_id,
            btc_long.identity.netting_domain.account_id,
        )
        rejected_tickets = [
            await uow.tickets.get(ticket.identity.ticket_id)
            for ticket in (same_direction, fourth_ticket)
        ]

    assert all(
        aggregate is not None and aggregate.status is AggregateStatus.POSITION_PROTECTED
        for aggregate in aggregates
    )
    assert {
        ticket.identity.netting_domain.key()
        for ticket in (btc_long, btc_short, eth_long)
    } == {
        btc_long.identity.netting_domain.key(),
        btc_short.identity.netting_domain.key(),
        eth_long.identity.netting_domain.key(),
    }
    assert all(
        {command.kind.value for command in ticket_commands}
        == {"entry", "initial_stop", "take_profit"}
        and len(ticket_commands) == 3
        and [
            command.generation
            for command in ticket_commands
            if command.kind.value == "entry"
        ]
        == [1]
        for ticket_commands in commands
    )
    assert same_direction_result.status is IssueTicketStatus.ACTIVE_NETTING_DOMAIN
    assert fourth_result.status is IssueTicketStatus.BUDGET_EXHAUSTED
    assert rejected_tickets == [None, None]
    assert len(venue.calls) == venue_call_count
    assert lane is not None and lane.status == "idle"
    assert exposure is not None and exposure.active_ticket_count == 3


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


async def _attempt_issue(
    engine: AsyncEngine,
    ticket,
    *,
    claim_owner: str,
    now_ms: int,
):
    await _seed_ticket_runtime_scope(engine, ticket)
    async with PostgresKernelUnitOfWork(engine) as uow:
        return await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=now_ms,
                claim_owner=claim_owner,
            ),
        )


async def _protect(
    engine: AsyncEngine,
    venue: MultiPositionVenue,
    ticket,
    *,
    entry_now_ms: int,
    fill_observed_at_ms: int,
    stop_now_ms: int,
) -> None:
    entry = await _dispatch(
        engine,
        venue,
        ticket.identity.ticket_id,
        entry_now_ms,
        entry=True,
    )
    assert entry.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(engine) as uow:
        fill = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=Decimal(60000),
                    venue_reported_liquidation_price=Decimal(0),
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
    *,
    entry: bool = False,
):
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=f"worker-{ticket_id}-{now_ms}",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
            runtime_commit="kernel-test-head" if entry else None,
            schema_revision=(
                CURRENT_SCHEMA_REVISION if entry else None
            ),
            admission_snapshot_validity_ms=1_000 if entry else None,
        ),
        entry_facts_source=PreflightFacts() if entry else None,
    )
    await _commit_passed_post_fill_stress_if_pending(engine, ticket_id)
    return result


def _ticket_for_domain(
    template,
    *,
    signal_event_id: str,
    exposure_episode_id: str,
    exchange_instrument_id: str,
    position_side: Literal["long", "short"],
    runtime_scope_id: str,
    runtime=None,
):
    runtime = template.identity.runtime if runtime is None else runtime
    domain = NettingDomain(
        venue_id=template.identity.netting_domain.venue_id,
        account_id=template.identity.netting_domain.account_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=position_side,
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=signal_event_id,
            runtime=runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=exposure_episode_id,
        signal_event_id=signal_event_id,
        runtime=runtime,
        netting_domain=domain,
    )
    terms = {
        "identity": identity,
        "runtime_scope_id": runtime_scope_id,
        "fact_digest": "sha256:" + "3" * 64,
    }
    if runtime.strategy_group_id == "SOR-001":
        terms.update(exposure_family="opening_range", family_ticket_limit=2)
    elif runtime.strategy_group_id == "BRF2-001":
        terms.update(exposure_family="rally_failure_short", family_ticket_limit=1)
    else:
        terms.update(exposure_family="long_continuation", family_ticket_limit=1)
    if runtime.event_spec_id != template.identity.runtime.event_spec_id:
        terms.update(
            {
                "universe_version_id": (
                    f"universe:test:{runtime.event_spec_id}"
                ),
                "universe_semantic_digest": "sha256:" + "b" * 64,
            }
        )
    if position_side == "short":
        terms.update(
            {
                "initial_stop_price": Decimal(61000),
                "take_profit_prices": (Decimal(58000),),
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
                max_strategy_group_concurrent_tickets=None,
                family_ticket_limits={
                    "long_continuation": 1,
                    "opening_range": 2,
                    "rally_failure_short": 1,
                },
                max_ticket_stop_risk_fraction="0.02",
                max_gross_stop_risk_fraction="0.06",
                max_ticket_initial_margin_fraction="0.30",
                max_gross_initial_margin_utilization="0.90",
                directional_stop_risk_limit_fraction="0.04",
                min_materialization_ratio="0.50",
                max_leverage=10,
                supported_margin_mode="cross",
                post_stop_stress_multiple="2.0",
                max_post_fill_stop_risk_overrun_fraction="0.10",
                scope={
                    "event_runtime_profiles": [
                        {
                            "event_spec_id": event_spec_id,
                            "runtime_profile_id": "tiny-live-v1",
                        }
                        for event_spec_id in (
                            "event_spec:BRF2-001:BRF2-SHORT:v3",
                            "event_spec:CPM-RO-001:CPM-LONG:v3",
                            "event_spec:MI-001:MI-LONG:v3",
                            "event_spec:SOR-001:SOR-LONG:v4",
                            "event_spec:SOR-001:SOR-SHORT:v4",
                        )
                    ]
                },
                updated_at_ms=1_000,
            )
        )
        await connection.execute(
            sa.insert(runtime_capabilities_current).values(
                capability_key="exchange_commands",
                enabled=True,
                certified_commit="kernel-test-head",
                schema_revision=CURRENT_SCHEMA_REVISION,
                certification={},
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
