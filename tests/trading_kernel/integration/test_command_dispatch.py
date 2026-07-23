from __future__ import annotations

import asyncio
from decimal import Decimal
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
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.events import TakeProfitFilled
from src.trading_kernel.domain.reducer import reduce_event
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.integration.test_issue_ticket import _issue_request


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
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
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


class KindAwareAcceptingVenue:
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        exchange_order_id = (
            request.payload.exchange_order_id
            if isinstance(request.payload, CancelCommandPayload)
            else f"venue-{request.kind.value}-1"
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=2_000,
            exchange_order_id=exchange_order_id,
        )


class CountingKindAwareAcceptingVenue(KindAwareAcceptingVenue):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        self.calls += 1
        return await super().execute(request)


@pytest.mark.asyncio
async def test_prepared_command_is_superseded_before_venue_write_when_state_moves_on(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        assert aggregate.status is AggregateStatus.TP1_PENDING
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal("0"),
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id=str(
                                aggregate.initial_stop_exchange_order_id
                            ),
                            venue_client_order_id="brc-initial-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=2_300,
                ),
            ),
        )

    venue = CountingKindAwareAcceptingVenue()
    superseded = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_400,
            lease_until_ms=7_400,
            timeout_seconds=1,
        ),
    )

    assert superseded.status is DispatchCommandStatus.SUPERSEDED
    assert venue.calls == 0
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    tp1 = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.TAKE_PROFIT
    )
    assert tp1.status is ExchangeCommandStatus.SUPERSEDED

    cleanup = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_500,
            lease_until_ms=7_500,
            timeout_seconds=1,
        ),
    )
    assert cleanup.status is DispatchCommandStatus.ACCEPTED
    assert venue.calls == 1


@pytest.mark.asyncio
async def test_tp1_and_replacement_commands_reach_protected_runner(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    venue = KindAwareAcceptingVenue()

    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.POSITION_PROTECTED
    tp1 = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.TAKE_PROFIT
    )
    assert isinstance(tp1.payload, OrderCommandPayload)
    assert tp1.payload.order_type == "limit"
    assert tp1.payload.reduce_only is True
    assert tp1.payload.quantity == ticket.take_profit_quantities[0]
    assert tp1.payload.limit_price == ticket.take_profit_prices[0]

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        event = TakeProfitFilled(
            event_id=f"event:{ticket.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_300,
            filled_qty=ticket.take_profit_quantities[0],
            average_fill_price=ticket.take_profit_prices[0],
            runner_floor_price=Decimal("60010"),
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )

    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, venue, ticket.identity.ticket_id)

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_PROTECTED
    assert aggregate.position_qty == ticket.quantity - ticket.take_profit_quantities[0]
    replacement = next(
        command
        for command in commands
        if command.kind is ExchangeCommandKind.REPLACE_PROTECTION
    )
    assert isinstance(replacement.payload, OrderCommandPayload)
    assert replacement.payload.order_type == "stop_market"
    assert replacement.payload.stop_price == Decimal("60010")
    assert replacement.payload.replaces_exchange_order_id == "venue-initial_stop-1"
    assert replacement.payload.source_watermark_ms == 2_300


@pytest.mark.asyncio
async def test_tp1_rejection_is_persisted_without_losing_initial_protection(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="tp1-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_300,
            lease_until_ms=7_300,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.TP1_REJECTED
    assert aggregate.active_stop_exchange_order_id == "venue-initial_stop-1"
    assert incident is not None and incident.incident_kind == "take_profit_rejected"


@pytest.mark.asyncio
async def test_replacement_rejection_preserves_the_prior_active_stop(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = KindAwareAcceptingVenue()
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    await _dispatch_for_ticket(dispatch_engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        assert aggregate is not None
        event = TakeProfitFilled(
            event_id=f"event:{ticket.identity.ticket_id}:{aggregate.last_event_sequence + 1}",
            ticket_id=ticket.identity.ticket_id,
            sequence=aggregate.last_event_sequence + 1,
            occurred_at_ms=2_300,
            filled_qty=ticket.take_profit_quantities[0],
            average_fill_price=ticket.take_profit_prices[0],
            runner_floor_price=Decimal("60010"),
        )
        await uow.commit_reduction(
            event=event,
            reduction=reduce_event(aggregate, event),
            expected_version=aggregate.version,
        )
    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="replacement-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=2_400,
            lease_until_ms=7_400,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RUNNER_REPLACEMENT_REJECTED
    assert aggregate.active_stop_exchange_order_id == "venue-initial_stop-1"
    assert incident is not None
    assert incident.incident_kind == "protection_replacement_rejected"


async def _dispatch_for_ticket(
    engine: AsyncEngine,
    venue,
    ticket_id: str,
) -> None:
    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id="lifecycle-dispatcher",
            ticket_id=ticket_id,
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    assert result.status is DispatchCommandStatus.ACCEPTED


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
            ticket.identity.netting_domain.venue_id,
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


@pytest.mark.asyncio
async def test_initial_stop_rejection_is_persisted_and_prepares_controlled_exit(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        AcceptingVenue(dispatch_engine),
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )

    assert result.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.EXIT_PENDING
    assert aggregate.entry_lane_held is True
    assert {command.kind.value: command.status for command in commands} == {
        "entry": ExchangeCommandStatus.ACCEPTED,
        "initial_stop": ExchangeCommandStatus.REJECTED,
        "exit": ExchangeCommandStatus.PREPARED,
    }
    assert incident is not None
    assert incident.incident_kind == "initial_stop_rejected"
    assert lane is not None and lane.status == "claimed"


@pytest.mark.asyncio
async def test_initial_stop_timeout_waits_for_truth_without_duplicate_exit(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        AcceptingVenue(dispatch_engine),
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
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

    assert (
        aggregate is not None
        and aggregate.status is AggregateStatus.INITIAL_STOP_OUTCOME_UNKNOWN
    )
    assert [
        command.status
        for command in commands
        if command.kind.value == "initial_stop"
    ] == [ExchangeCommandStatus.OUTCOME_UNKNOWN]
    assert [command.kind.value for command in commands].count("initial_stop") == 1
    assert all(command.kind.value != "exit" for command in commands)
    assert incident is not None
    assert incident.incident_kind == "initial_stop_outcome_unknown"


@pytest.mark.asyncio
async def test_exit_rejection_is_persisted_and_explicit_retry_uses_new_generation(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _issue(dispatch_engine, ticket)
    accepting = AcceptingVenue(dispatch_engine)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        accepting,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        accepting,
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    await _dispatch_for_ticket(
        dispatch_engine,
        accepting,
        ticket.identity.ticket_id,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )

    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="exit-dispatcher",
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=1,
        ),
    )
    assert rejected.status is DispatchCommandStatus.REJECTED

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None and aggregate.status is AggregateStatus.EXIT_REJECTED
    assert incident is not None and incident.incident_kind == "exit_rejected"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="recover_exit_rejection",
                requested_at_ms=3_200,
            ),
        )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    exit_commands = [
        command for command in commands if command.kind.value == "exit"
    ]
    assert [command.generation for command in exit_commands] == [1, 2]
    assert [command.status for command in exit_commands] == [
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.PREPARED,
    ]


@pytest.mark.asyncio
async def test_cancel_rejection_is_persisted_and_blocks_settlement(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    accepting = AcceptingVenue(dispatch_engine)
    await _reach_cancel_pending(dispatch_engine, ticket, accepting)

    rejected = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        RejectingVenue(),
        DispatchCommandRequest(
            worker_id="cancel-dispatcher",
            now_ms=3_300,
            lease_until_ms=8_300,
            timeout_seconds=1,
        ),
    )

    assert rejected.status is DispatchCommandStatus.REJECTED
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CANCEL_REJECTED
    assert aggregate.pending_cancel_exchange_order_id == "venue-take_profit-1"
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert len(cancel_commands) == 1
    assert cancel_commands[0].status is ExchangeCommandStatus.REJECTED
    assert incident is not None and incident.incident_kind == "cancel_order_rejected"
    assert reservation is not None and reservation.status == "active"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        retry_requested = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="venue-take_profit-1",
                            venue_client_order_id="brc-owned-tp1",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_400,
                ),
            ),
        )
    assert retry_requested.status.value == "owned_orphan_cancel_requested"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert [command.generation for command in cancel_commands] == [1, 2]
    assert [command.status for command in cancel_commands] == [
        ExchangeCommandStatus.REJECTED,
        ExchangeCommandStatus.PREPARED,
    ]


@pytest.mark.asyncio
async def test_cancel_timeout_is_conserved_without_retry_and_blocks_settlement(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _reach_cancel_pending(
        dispatch_engine,
        ticket,
        AcceptingVenue(dispatch_engine),
    )

    unknown = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        SlowVenue(),
        DispatchCommandRequest(
            worker_id="cancel-dispatcher",
            now_ms=3_300,
            lease_until_ms=8_300,
            timeout_seconds=0.01,
        ),
    )

    assert unknown.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.CANCEL_OUTCOME_UNKNOWN
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert len(cancel_commands) == 1
    assert cancel_commands[0].status is ExchangeCommandStatus.OUTCOME_UNKNOWN
    assert incident is not None
    assert incident.incident_kind == "cancel_order_outcome_unknown"
    assert reservation is not None and reservation.status == "active"

    repeated = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        CountingVenue(),
        DispatchCommandRequest(
            worker_id="repeat-dispatcher",
            now_ms=8_500,
            lease_until_ms=13_500,
            timeout_seconds=1,
        ),
    )
    assert repeated.status is DispatchCommandStatus.NO_COMMAND

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        blocked = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_400,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert blocked.status.value == "cancel_absence_recorded"
    assert reservation is not None and reservation.status == "active"
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert aggregate.pending_cancel_exchange_order_id is None
    cancel_commands = [
        command for command in commands if command.kind.value == "cancel_order"
    ]
    assert cancel_commands[0].status is ExchangeCommandStatus.RECONCILED_ABSENT

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        stop_absence = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_500,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert stop_absence.status.value == "cancel_absence_recorded"
    assert reservation is not None and reservation.status == "active"

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_600,
                ),
            ),
        )
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert matched.status.value == "matched"
    assert reservation is not None and reservation.status == "released"


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


async def _issue(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="issuer-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED


async def _reach_cancel_pending(
    engine: AsyncEngine,
    ticket,
    accepting: AcceptingVenue,
) -> None:
    await _issue(engine, ticket)
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=2_100,
                ),
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="stop-dispatcher",
            now_ms=2_200,
            lease_until_ms=7_200,
            timeout_seconds=1,
        ),
    )
    await _dispatch_for_ticket(engine, accepting, ticket.identity.ticket_id)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        accepting,
        DispatchCommandRequest(
            worker_id="exit-dispatcher",
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=1,
        ),
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    observed_at_ms=3_200,
                ),
            ),
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
