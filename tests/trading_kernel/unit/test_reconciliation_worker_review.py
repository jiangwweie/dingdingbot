from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.runtime_facts import ReviewEconomicsRequest
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.events import (
    EntryFilled,
    ExternalFlatDetected,
    TicketIssued,
)
from src.trading_kernel.domain.post_fill_risk import (
    PostFillRiskRequest,
    assess_post_fill_risk,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.unit.test_ticket import _ticket


class _AggregateRepository:
    def __init__(self, aggregate: TradeAggregate) -> None:
        self.aggregate = aggregate
        self.scheduled_due_at_ms: int | None = None

    async def get_next_for_statuses(self, statuses, **kwargs):
        del kwargs
        return self.aggregate if self.aggregate.status in statuses else None

    async def schedule_next_check(self, ticket_id, *, work_kind, due_at_ms):
        assert ticket_id == self.aggregate.identity.ticket_id
        assert work_kind == "reconciliation"
        self.scheduled_due_at_ms = due_at_ms


class _CommandRepository:
    def __init__(self, commands: list[ExchangeCommand]) -> None:
        self.commands = commands

    async def get_one_unknown(self):
        return None

    async def list_for_ticket(self, ticket_id):
        assert ticket_id == self.commands[0].ticket_identity.ticket_id
        return self.commands


class _EventRepository:
    def __init__(self, events) -> None:
        self.events = events

    async def list_for_ticket(self, ticket_id):
        assert ticket_id == self.events[0].ticket.identity.ticket_id
        return self.events


class _TicketRepository:
    def __init__(self, *, overlap: bool) -> None:
        self.overlap = overlap

    async def has_other_instrument_ticket_in_window(self, **kwargs):
        del kwargs
        return self.overlap


class _FakeUnitOfWork:
    def __init__(self, state: "_WorkerState") -> None:
        self.aggregates = state.aggregates
        self.exchange_commands = state.commands
        self.events = state.events
        self.tickets = state.tickets

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback


class _WorkerState:
    def __init__(self, *, overlap: bool) -> None:
        ticket = _ticket()
        self.aggregate = TradeAggregate(
            identity=ticket.identity,
            ticket=ticket,
            status=AggregateStatus.REVIEW_PENDING,
            version=5,
            last_event_sequence=5,
            entry_lane_held=False,
            position_qty=Decimal("0"),
            average_fill_price=Decimal("60000"),
        )
        self.aggregates = _AggregateRepository(self.aggregate)
        self.commands = _CommandRepository(
            [
                _command(ticket, ExchangeCommandKind.ENTRY, reduce_only=False),
                _command(ticket, ExchangeCommandKind.EXIT, reduce_only=True),
            ]
        )
        self.events = _EventRepository(
            [
                TicketIssued(
                    event_id="event-1",
                    sequence=1,
                    occurred_at_ms=1_000,
                    ticket=ticket,
                ),
                EntryFilled(
                    event_id="event-2",
                    ticket_id=ticket.identity.ticket_id,
                    sequence=2,
                    occurred_at_ms=1_100,
                    filled_qty=ticket.quantity,
                    average_fill_price=Decimal("60000"),
                    post_fill_risk=assess_post_fill_risk(
                        PostFillRiskRequest(
                            position_side=ticket.identity.netting_domain.position_side,
                            filled_quantity=ticket.quantity,
                            average_fill_price=Decimal("60000"),
                            initial_stop_price=ticket.initial_stop_price,
                            planned_stop_risk_budget=ticket.planned_stop_risk_budget,
                            post_fill_stop_risk_limit=ticket.post_fill_stop_risk_limit,
                            current_liquidation_price=Decimal("57000"),
                            min_liquidation_distance_to_stop_distance_ratio=(
                                ticket.min_liquidation_distance_to_stop_distance_ratio
                            ),
                        )
                    ),
                ),
                ExternalFlatDetected(
                    event_id="event-3",
                    ticket_id=ticket.identity.ticket_id,
                    sequence=3,
                    occurred_at_ms=3_000,
                ),
            ]
        )
        self.tickets = _TicketRepository(overlap=overlap)

    def factory(self):
        return _FakeUnitOfWork(self)


class _FailingEconomicsSource:
    def __init__(self) -> None:
        self.requests: list[ReviewEconomicsRequest] = []

    async def read_review_economics(self, request: ReviewEconomicsRequest):
        self.requests.append(request)
        raise RuntimeError("fills incomplete")


@pytest.mark.asyncio
async def test_review_worker_does_not_write_a_thin_review_when_facts_are_missing() -> None:
    state = _WorkerState(overlap=False)
    source = _FailingEconomicsSource()

    result = await run_reconciliation_worker_once(
        state.factory,
        object(),
        object(),
        _request(),
        review_economics_source=source,
    )

    assert result.status is ReconciliationWorkerStatus.FACTS_UNAVAILABLE
    assert result.detail == "review_economics:RuntimeError"
    assert state.aggregates.scheduled_due_at_ms == 7_000
    assert len(source.requests) == 1


@pytest.mark.asyncio
async def test_review_worker_disables_funding_attribution_when_ticket_windows_overlap() -> None:
    state = _WorkerState(overlap=True)
    source = _FailingEconomicsSource()

    await run_reconciliation_worker_once(
        state.factory,
        object(),
        object(),
        _request(),
        review_economics_source=source,
    )

    assert source.requests[0].funding_attribution_exact is False


def _request() -> ReconciliationWorkerRequest:
    return ReconciliationWorkerRequest(
        worker_id="reconciliation-worker-test",
        now_ms=5_000,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
    )


def _command(ticket, kind: ExchangeCommandKind, *, reduce_only: bool) -> ExchangeCommand:
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=kind,
        generation=1,
    )
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=kind,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side="sell" if reduce_only else "buy",
            quantity=ticket.quantity,
            order_type="market",
            reduce_only=reduce_only,
            required_configured_leverage=(
                ticket.selected_leverage
                if kind is ExchangeCommandKind.ENTRY
                else None
            ),
            leverage_verification_digest=(
                ticket.decision_digest()
                if kind is ExchangeCommandKind.ENTRY
                else None
            ),
        ),
        status=ExchangeCommandStatus.ACCEPTED,
        created_at_ms=1_000 if not reduce_only else 2_000,
        deadline_at_ms=31_000 if not reduce_only else 32_000,
    )
