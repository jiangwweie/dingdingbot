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
from src.trading_kernel.application.issue_ticket import IssueTicketStatus, issue_ticket
from src.trading_kernel.application.ports import VenueCommandRequest
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ExitTicketStatus,
    ReconcileTicketRequest,
    ReconcileTicketStatus,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.application.settle_ticket import (
    RecordTradeReviewRequest,
    SettleTicketRequest,
    SettleTicketStatus,
    record_trade_review,
    settle_ticket,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.position import PositionSnapshot, VenueOrderSnapshot
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.infrastructure.pg_models import owner_policy_current
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.integration.test_issue_ticket import _issue_request


REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_DSN = os.getenv(
    "BRC_TEST_POSTGRES_ADMIN_URL",
    "postgresql://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres",
)
SAFE_DATABASE = re.compile(r"^brc_kernel_test_[a-f0-9]{12}$")


@pytest_asyncio.fixture
async def lifecycle_engine() -> AsyncEngine:
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


class LifecycleVenue:
    def __init__(self) -> None:
        self._last_observed_at_ms = 0

    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        order_ids = {
            ExchangeCommandKind.ENTRY: "entry-order-1",
            ExchangeCommandKind.INITIAL_STOP: "stop-order-1",
            ExchangeCommandKind.TAKE_PROFIT: "tp-order-1",
            ExchangeCommandKind.EXIT: "exit-order-1",
        }
        if request.kind is ExchangeCommandKind.CANCEL_ORDER:
            assert isinstance(request.payload, CancelCommandPayload)
            exchange_order_id = request.payload.exchange_order_id
        else:
            exchange_order_id = order_ids[request.kind]
        candidate_observed_at_ms = request.deadline_at_ms - 29_998
        self._last_observed_at_ms = max(
            self._last_observed_at_ms + 1,
            candidate_observed_at_ms,
        )
        return ExchangeCommandResult(
            status=ExchangeCommandStatus.ACCEPTED,
            observed_at_ms=self._last_observed_at_ms,
            exchange_order_id=exchange_order_id,
        )


class ExitTimeoutVenue(LifecycleVenue):
    async def execute(self, request: VenueCommandRequest) -> ExchangeCommandResult:
        if request.kind is ExchangeCommandKind.EXIT:
            await asyncio.sleep(0.1)
        return await super().execute(request)


@pytest.mark.asyncio
async def test_one_ticket_reaches_protected_exit_settlement_and_terminal_review(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    venue = LifecycleVenue()

    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-entry", 1_100)
    ).status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        filled = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    open_orders=(),
                    observed_at_ms=2_100,
                ),
            ),
        )
    assert filled.status is ReconcileTicketStatus.ENTRY_FILL_RECORDED

    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-stop", 2_200)
    ).status is DispatchCommandStatus.ACCEPTED
    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-tp1", 2_250)
    ).status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        protected = await uow.aggregates.get(ticket.identity.ticket_id)
        lane = await uow.entry_admission.get_global_lane()
    assert protected is not None
    assert protected.status is AggregateStatus.POSITION_PROTECTED
    assert protected.initial_stop_exchange_order_id == "stop-order-1"
    assert lane is not None and lane.status == "idle"

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        exit_result = await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    assert exit_result.status is ExitTicketStatus.REQUESTED

    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-exit", 3_100)
    ).status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        flat = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="tp-order-1",
                            venue_client_order_id="brc-owned-tp1",
                            position_side="long",
                            reduce_only=True,
                        ),
                        VenueOrderSnapshot(
                            exchange_order_id="stop-order-1",
                            venue_client_order_id="brc-owned-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_200,
                ),
            ),
        )
    assert flat.status is ReconcileTicketStatus.POSITION_FLAT_RECORDED

    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-cancel-tp1", 3_300)
    ).status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        stop_cleanup = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="stop-order-1",
                            venue_client_order_id="brc-owned-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_350,
                ),
            ),
        )
    assert stop_cleanup.status is ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
    assert (
        await _dispatch(lifecycle_engine, venue, "dispatch-cancel-stop", 3_375)
    ).status is DispatchCommandStatus.ACCEPTED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        reservation_before_match = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        exposure_before_match = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.account_id
        )
    assert reservation_before_match is not None
    assert reservation_before_match.status == "active"
    assert exposure_before_match is not None
    assert exposure_before_match.active_ticket_count == 1

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        matched = await reconcile_ticket(
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
    assert matched.status is ReconcileTicketStatus.MATCHED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        reservation_after_match = await uow.budgets.get_for_ticket(
            ticket.identity.ticket_id
        )
        exposure_after_match = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.account_id
        )
    assert reservation_after_match is not None
    assert reservation_after_match.status == "released"
    assert exposure_after_match is not None
    assert exposure_after_match.active_ticket_count == 0

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        settled = await settle_ticket(
            uow,
            SettleTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                settled_at_ms=3_500,
            ),
        )
    assert settled.status is SettleTicketStatus.BUDGET_SETTLED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        reviewed = await record_trade_review(
            uow,
            RecordTradeReviewRequest(
                ticket_id=ticket.identity.ticket_id,
                review_id="review-1",
                outcome="closed",
                metrics={"realized_pnl": "1.25"},
                decision_impact={"strategy_action": "keep"},
                recorded_at_ms=3_600,
            ),
        )
    assert reviewed.status is SettleTicketStatus.REVIEW_RECORDED

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        persisted_ticket = await uow.tickets.get(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
        exposure = await uow.entry_admission.get_account_exposure(
            ticket.identity.netting_domain.account_id
        )
        review = await uow.reviews.get_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    assert aggregate is not None and aggregate.status is AggregateStatus.TERMINAL
    assert persisted_ticket is not None and persisted_ticket.status.value == "terminal"
    assert reservation is not None and reservation.status == "released"
    assert exposure is not None and exposure.active_ticket_count == 0
    assert review is not None and review.review_id == "review-1"
    assert [command.kind for command in commands] == [
        ExchangeCommandKind.ENTRY,
        ExchangeCommandKind.INITIAL_STOP,
        ExchangeCommandKind.TAKE_PROFIT,
        ExchangeCommandKind.EXIT,
        ExchangeCommandKind.CANCEL_ORDER,
        ExchangeCommandKind.CANCEL_ORDER,
    ]


@pytest.mark.asyncio
async def test_external_flat_opens_incident_and_enters_owned_protection_cleanup(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = LifecycleVenue()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    await _dispatch(lifecycle_engine, venue, "dispatch-entry", 1_100)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    open_orders=(),
                    observed_at_ms=2_100,
                ),
            ),
        )
    await _dispatch(lifecycle_engine, venue, "dispatch-stop", 2_200)
    await _dispatch(lifecycle_engine, venue, "dispatch-tp1", 2_250)

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="tp-order-1",
                            venue_client_order_id="brc-owned-tp1",
                            position_side="long",
                            reduce_only=True,
                        ),
                        VenueOrderSnapshot(
                            exchange_order_id="stop-order-1",
                            venue_client_order_id="brc-owned-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=2_300,
                ),
            ),
        )

    assert result.status is ReconcileTicketStatus.EXTERNAL_FLAT_INCIDENT
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.RECONCILIATION_PENDING
    assert incident is not None and incident.incident_kind == "external_flat"
    assert commands[-1].kind is ExchangeCommandKind.CANCEL_ORDER
    assert reservation is not None and reservation.status == "active"

    assert (
        await _dispatch(lifecycle_engine, venue, "cancel-external-flat-tp1", 2_400)
    ).status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        stop_cleanup = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="stop-order-1",
                            venue_client_order_id="brc-owned-stop",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=2_500,
                ),
            ),
        )
    assert stop_cleanup.status is ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
    assert (
        await _dispatch(lifecycle_engine, venue, "cancel-external-flat-stop", 2_600)
    ).status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        matched = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=2_700,
                ),
            ),
        )
        incident_after_match = await uow.incidents.get_open_for_ticket(
            ticket.identity.ticket_id
        )

    assert matched.status is ReconcileTicketStatus.MATCHED
    assert incident_after_match is None


@pytest.mark.asyncio
async def test_exit_timeout_is_conserved_as_unknown_and_never_redispatched(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = ExitTimeoutVenue()
    await _seed_policy(lifecycle_engine)
    await _issue(lifecycle_engine, ticket)
    await _dispatch(lifecycle_engine, venue, "dispatch-entry", 1_100)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
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
    await _dispatch(lifecycle_engine, venue, "dispatch-stop", 2_200)
    await _dispatch(lifecycle_engine, venue, "dispatch-tp1", 2_250)
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )

    result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(lifecycle_engine),
        venue,
        DispatchCommandRequest(
            worker_id="dispatch-exit",
            now_ms=3_100,
            lease_until_ms=8_100,
            timeout_seconds=0.01,
        ),
    )

    assert result.status is DispatchCommandStatus.OUTCOME_UNKNOWN
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
    assert aggregate is not None
    assert aggregate.status is AggregateStatus.EXIT_OUTCOME_UNKNOWN
    assert incident is not None and incident.incident_kind == "exit_outcome_unknown"
    assert commands[-1].status is ExchangeCommandStatus.OUTCOME_UNKNOWN

    repeated = await _dispatch(lifecycle_engine, venue, "dispatch-repeat", 9_000)
    assert repeated.status is DispatchCommandStatus.NO_COMMAND


@pytest.mark.asyncio
async def test_owned_orphan_order_creates_new_exact_cancel_generation(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = LifecycleVenue()
    await _seed_policy(lifecycle_engine)
    await _reach_reconciliation_pending_after_cancel(
        lifecycle_engine,
        venue,
        ticket,
    )

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="owned-orphan-1",
                            venue_client_order_id="brc-owned-orphan",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_400,
                ),
            ),
        )

    assert result.status is ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    orphan_cancel = commands[-1]
    assert orphan_cancel.kind is ExchangeCommandKind.CANCEL_ORDER
    assert orphan_cancel.generation == 3
    assert isinstance(orphan_cancel.payload, CancelCommandPayload)
    assert orphan_cancel.payload.exchange_order_id == "owned-orphan-1"
    assert reservation is not None and reservation.status == "active"

    dispatched = await _dispatch(
        lifecycle_engine,
        venue,
        "dispatch-owned-orphan",
        3_500,
    )
    assert dispatched.status is DispatchCommandStatus.ACCEPTED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        still_present = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="owned-orphan-1",
                            venue_client_order_id="brc-owned-orphan",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_550,
                ),
            ),
        )
        commands_after_accept = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )
    assert still_present.status is ReconcileTicketStatus.PROTECTION_RESIDUE
    assert len(commands_after_accept) == 7

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
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
    assert matched.status is ReconcileTicketStatus.MATCHED
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert reservation is not None and reservation.status == "released"


@pytest.mark.asyncio
async def test_unowned_open_order_opens_incident_without_creating_cancel(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = LifecycleVenue()
    await _seed_policy(lifecycle_engine)
    await _reach_reconciliation_pending_after_cancel(
        lifecycle_engine,
        venue,
        ticket,
    )

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="manual-order-1",
                            venue_client_order_id="manual-order",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_400,
                ),
            ),
        )

    assert result.status is ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        repeated = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="manual-order-1",
                            venue_client_order_id="manual-order",
                            position_side="long",
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_450,
                ),
            ),
        )
    assert repeated.status is ReconcileTicketStatus.UNOWNED_ORDER_INCIDENT
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        incident = await uow.incidents.get_open_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)
    assert incident is not None and incident.incident_kind == "unowned_open_order"
    assert len(commands) == 6
    assert len(events) == 12
    assert reservation is not None and reservation.status == "active"


@pytest.mark.asyncio
async def test_protection_residue_blocks_match_without_duplicate_cancel(
    lifecycle_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    venue = LifecycleVenue()
    await _seed_policy(lifecycle_engine)
    await _reach_reconciliation_pending_after_cancel(
        lifecycle_engine,
        venue,
        ticket,
        dispatch_cancel=False,
    )

    snapshot = PositionSnapshot(
        netting_domain=ticket.identity.netting_domain,
        quantity="0",
        average_entry_price=None,
        open_orders=(
            VenueOrderSnapshot(
                exchange_order_id="stop-order-1",
                venue_client_order_id="brc-owned-stop",
                position_side="long",
                reduce_only=True,
            ),
        ),
        observed_at_ms=3_250,
    )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        first = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=snapshot,
            ),
        )
    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        second = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=snapshot.model_copy(update={"observed_at_ms": 3_260}),
            ),
        )
        commands = await uow.exchange_commands.list_for_ticket(ticket.identity.ticket_id)
        reservation = await uow.budgets.get_for_ticket(ticket.identity.ticket_id)

    assert first.status is ReconcileTicketStatus.PROTECTION_RESIDUE
    assert second.status is ReconcileTicketStatus.PROTECTION_RESIDUE
    assert len(commands) == 5
    assert commands[-1].kind is ExchangeCommandKind.CANCEL_ORDER
    assert commands[-1].status is ExchangeCommandStatus.PREPARED
    assert reservation is not None and reservation.status == "active"


@pytest.mark.asyncio
async def test_same_instrument_long_and_short_tickets_are_isolated(
    lifecycle_engine: AsyncEngine,
) -> None:
    long_ticket = _ticket()
    short_ticket = _ticket_for_side(
        long_ticket,
        side="short",
        signal_event_id="signal-short-1",
        exposure_episode_id="episode-short-1",
    )
    venue = LifecycleVenue()
    await _seed_policy(lifecycle_engine)

    await _protect_ticket(
        lifecycle_engine,
        venue,
        long_ticket,
        worker_prefix="long",
        dispatch_at_ms=1_100,
        observed_at_ms=2_100,
    )
    await _protect_ticket(
        lifecycle_engine,
        venue,
        short_ticket,
        worker_prefix="short",
        dispatch_at_ms=2_300,
        observed_at_ms=2_400,
    )

    async with PostgresKernelUnitOfWork(lifecycle_engine) as uow:
        long_aggregate = await uow.aggregates.get(long_ticket.identity.ticket_id)
        short_aggregate = await uow.aggregates.get(short_ticket.identity.ticket_id)
        long_position = await uow.positions.get(
            long_ticket.identity.netting_domain.key()
        )
        short_position = await uow.positions.get(
            short_ticket.identity.netting_domain.key()
        )
        long_commands = await uow.exchange_commands.list_for_ticket(
            long_ticket.identity.ticket_id
        )
        short_commands = await uow.exchange_commands.list_for_ticket(
            short_ticket.identity.ticket_id
        )
        exposure = await uow.entry_admission.get_account_exposure(
            long_ticket.identity.netting_domain.account_id
        )

    assert long_aggregate is not None
    assert long_aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert short_aggregate is not None
    assert short_aggregate.status is AggregateStatus.POSITION_PROTECTED
    assert long_position is not None and long_position.quantity == long_ticket.quantity
    assert short_position is not None and short_position.quantity == short_ticket.quantity
    assert exposure is not None and exposure.active_ticket_count == 2

    long_entry, long_stop, long_tp1 = long_commands
    short_entry, short_stop, short_tp1 = short_commands
    assert isinstance(long_entry.payload, OrderCommandPayload)
    assert isinstance(long_stop.payload, OrderCommandPayload)
    assert isinstance(long_tp1.payload, OrderCommandPayload)
    assert isinstance(short_entry.payload, OrderCommandPayload)
    assert isinstance(short_stop.payload, OrderCommandPayload)
    assert isinstance(short_tp1.payload, OrderCommandPayload)
    assert (
        long_entry.payload.side,
        long_stop.payload.side,
        long_tp1.payload.side,
    ) == ("buy", "sell", "sell")
    assert (
        short_entry.payload.side,
        short_stop.payload.side,
        short_tp1.payload.side,
    ) == ("sell", "buy", "buy")


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
                target_leverage="5",
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


async def _protect_ticket(
    engine: AsyncEngine,
    venue: LifecycleVenue,
    ticket,
    *,
    worker_prefix: str,
    dispatch_at_ms: int,
    observed_at_ms: int,
) -> None:
    await _issue(engine, ticket)
    await _dispatch(
        engine,
        venue,
        f"{worker_prefix}-entry",
        dispatch_at_ms,
    )
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price="60000",
                    observed_at_ms=observed_at_ms,
                ),
            ),
        )
    assert result.status is ReconcileTicketStatus.ENTRY_FILL_RECORDED
    protected = await _dispatch(
        engine,
        venue,
        f"{worker_prefix}-stop",
        observed_at_ms + 100,
    )
    assert protected.status is DispatchCommandStatus.ACCEPTED
    tp1 = await _dispatch(
        engine,
        venue,
        f"{worker_prefix}-tp1",
        observed_at_ms + 150,
    )
    assert tp1.status is DispatchCommandStatus.ACCEPTED


async def _reach_reconciliation_pending_after_cancel(
    engine: AsyncEngine,
    venue: LifecycleVenue,
    ticket,
    *,
    dispatch_cancel: bool = True,
) -> None:
    await _issue(engine, ticket)
    await _dispatch(engine, venue, "dispatch-entry", 1_100)
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
    await _dispatch(engine, venue, "dispatch-stop", 2_200)
    await _dispatch(engine, venue, "dispatch-tp1", 2_250)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_000,
            ),
        )
    await _dispatch(engine, venue, "dispatch-exit", 3_100)
    async with PostgresKernelUnitOfWork(engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity="0",
                    average_entry_price=None,
                    open_orders=(
                        VenueOrderSnapshot(
                            exchange_order_id="tp-order-1",
                            venue_client_order_id="brc-owned-tp1",
                            position_side=ticket.identity.netting_domain.position_side,
                            reduce_only=True,
                        ),
                        VenueOrderSnapshot(
                            exchange_order_id="stop-order-1",
                            venue_client_order_id="brc-owned-stop",
                            position_side=ticket.identity.netting_domain.position_side,
                            reduce_only=True,
                        ),
                    ),
                    observed_at_ms=3_200,
                ),
            ),
        )
    if dispatch_cancel:
        await _dispatch(engine, venue, "dispatch-cancel-tp1", 3_300)
        async with PostgresKernelUnitOfWork(engine) as uow:
            stop_cleanup = await reconcile_ticket(
                uow,
                ReconcileTicketRequest(
                    ticket_id=ticket.identity.ticket_id,
                    snapshot=PositionSnapshot(
                        netting_domain=ticket.identity.netting_domain,
                        quantity="0",
                        average_entry_price=None,
                        open_orders=(
                            VenueOrderSnapshot(
                                exchange_order_id="stop-order-1",
                                venue_client_order_id="brc-owned-stop",
                                position_side=(
                                    ticket.identity.netting_domain.position_side
                                ),
                                reduce_only=True,
                            ),
                        ),
                        observed_at_ms=3_350,
                    ),
                ),
            )
        assert (
            stop_cleanup.status
            is ReconcileTicketStatus.OWNED_ORPHAN_CANCEL_REQUESTED
        )
        await _dispatch(engine, venue, "dispatch-cancel-stop", 3_375)


async def _issue(engine: AsyncEngine, ticket) -> None:
    async with PostgresKernelUnitOfWork(engine) as uow:
        result = await issue_ticket(
            uow,
            _issue_request(ticket=ticket, now_ms=1_001, claim_owner="issuer-1"),
        )
    assert result.status is IssueTicketStatus.ISSUED


async def _dispatch(
    engine: AsyncEngine,
    venue: LifecycleVenue,
    worker_id: str,
    now_ms: int,
):
    return await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=worker_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
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
