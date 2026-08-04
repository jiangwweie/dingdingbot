"""PostgreSQL persistence coverage for Controlled Exit."""

from __future__ import annotations

from src.trading_kernel.application.controlled_exit import (
    ControlledExitAuthorization,
    ControlledExitRequest,
    request_controlled_exits,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from src.trading_kernel.domain.commands import ExchangeCommandKind, OrderCommandPayload
from src.trading_kernel.domain.events import ExitRequested
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_ticket_lifecycle_maintenance import (
    _reach_position_protected,
    _registered_sor_long_ticket,
)

controlled_exit_engine = dispatch_fixture.dispatch_engine


async def test_deployment_drain_persists_one_exit_request_and_reduce_only_command(
    controlled_exit_engine,
) -> None:
    ticket = _registered_sor_long_ticket()
    await _reach_position_protected(controlled_exit_engine, ticket)
    authorization = ControlledExitAuthorization(
        purpose="deployment_drain",
        authorization_id="deploy-20260804-01",
        target_commit="a" * 40,
    )
    request = ControlledExitRequest(
        authorization=authorization,
        runtime_profile_id=ticket.identity.runtime.runtime_profile_id,
        venue_id=ticket.identity.netting_domain.venue_id,
        account_id=ticket.identity.netting_domain.account_id,
        max_active_tickets=3,
        requested_at_ms=3_000,
    )

    first = await request_controlled_exits(
        lambda: PostgresKernelUnitOfWork(controlled_exit_engine),
        request,
    )
    second = await request_controlled_exits(
        lambda: PostgresKernelUnitOfWork(controlled_exit_engine),
        request,
    )

    assert first.requested_ticket_ids == (ticket.identity.ticket_id,)
    assert second.requested_ticket_ids == ()
    assert second.in_progress_ticket_ids == (ticket.identity.ticket_id,)

    async with PostgresKernelUnitOfWork(controlled_exit_engine) as uow:
        aggregate = await uow.aggregates.get(ticket.identity.ticket_id)
        events = await uow.events.list_for_ticket(ticket.identity.ticket_id)
        commands = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    assert aggregate is not None
    assert aggregate.status is AggregateStatus.EXIT_PENDING
    exit_events = [event for event in events if isinstance(event, ExitRequested)]
    assert len(exit_events) == 1
    assert exit_events[0].reason == authorization.reason
    exit_commands = [
        command for command in commands if command.kind is ExchangeCommandKind.EXIT
    ]
    assert len(exit_commands) == 1
    assert isinstance(exit_commands[0].payload, OrderCommandPayload)
    assert exit_commands[0].payload.reduce_only is True
    assert exit_commands[0].payload.quantity == ticket.quantity
