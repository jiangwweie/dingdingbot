from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.order_attribution import OrderNamespace, OrderRole
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.integration.test_issue_ticket import (
    _seed_ticket_runtime_scope,
)
from tests.trading_kernel.support.tickets import make_ticket as _ticket

order_attribution_engine = dispatch_fixture.dispatch_engine


@pytest.mark.asyncio
async def test_repository_builds_exact_regular_and_conditional_order_references(
    order_attribution_engine,
) -> None:
    ticket = _ticket()
    entry = _command(
        ticket=ticket,
        command_id="command:entry",
        kind=ExchangeCommandKind.ENTRY,
        payload=OrderCommandPayload(
            side="buy",
            quantity=Decimal("0.01"),
            order_type="market",
            reduce_only=False,
            required_configured_leverage=5,
            leverage_verification_digest="sha256:" + "1" * 64,
        ),
    )
    stop = _command(
        ticket=ticket,
        command_id="command:stop",
        kind=ExchangeCommandKind.INITIAL_STOP,
        payload=OrderCommandPayload(
            side="sell",
            quantity=Decimal("0.01"),
            order_type="stop_market",
            reduce_only=True,
            stop_price=Decimal(59000),
        ),
    )

    await _seed_ticket_runtime_scope(order_attribution_engine, ticket)
    async with PostgresKernelUnitOfWork(order_attribution_engine) as uow:
        await uow.tickets.add(ticket)
        for command, exchange_order_id in ((entry, "1001"), (stop, "9001")):
            await uow.exchange_commands.add(command)
            claimed = await uow.exchange_commands.claim_one_prepared(
                worker_id="test-worker",
                now_ms=1_100,
                lease_until_ms=2_000,
                ticket_id=ticket.identity.ticket_id,
            )
            assert claimed is not None
            await uow.exchange_commands.record_result(
                command_id=command.command_id,
                worker_id="test-worker",
                result=ExchangeCommandResult(
                    status=ExchangeCommandStatus.ACCEPTED,
                    observed_at_ms=1_200,
                    exchange_order_id=exchange_order_id,
                ),
            )

    async with PostgresKernelUnitOfWork(order_attribution_engine) as uow:
        references = await uow.exchange_commands.list_order_references(
            ticket.identity.ticket_id
        )

    assert [(item.command_id, item.namespace, item.role) for item in references] == [
        ("command:entry", OrderNamespace.REGULAR, OrderRole.ENTRY),
        ("command:stop", OrderNamespace.CONDITIONAL, OrderRole.EXIT),
    ]
    assert [item.submitted_exchange_order_id for item in references] == ["1001", "9001"]


def _command(*, ticket, command_id: str, kind: ExchangeCommandKind, payload) -> ExchangeCommand:
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=kind,
        generation=1,
        idempotency_key=f"idempotency:{command_id}",
        venue_client_order_id=f"brc-{command_id.split(':', 1)[1]}",
        payload=payload,
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=1_000,
        deadline_at_ms=10_000,
    )
