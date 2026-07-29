from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.order_attribution import OrderNamespace, OrderRole
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.pg_models import exchange_commands
from tests.trading_kernel.integration import test_command_dispatch as dispatch_fixture
from tests.trading_kernel.unit.test_ticket import _ticket


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
            stop_price=Decimal("59000"),
        ),
    )

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


@pytest.mark.asyncio
async def test_repository_reads_accepted_historical_limit_order_reference(
    order_attribution_engine,
) -> None:
    ticket = _ticket()
    tp1 = _command(
        ticket=ticket,
        command_id="command:tp1",
        kind=ExchangeCommandKind.TAKE_PROFIT,
        payload=OrderCommandPayload(
            side="sell",
            quantity=Decimal("0.005"),
            order_type="limit",
            limit_price=Decimal("62000"),
            time_in_force="GTC",
            reduce_only=True,
        ),
    )
    async with PostgresKernelUnitOfWork(order_attribution_engine) as uow:
        await uow.tickets.add(ticket)
        await uow.exchange_commands.add(tp1)
        claimed = await uow.exchange_commands.claim_one_prepared(
            worker_id="test-worker",
            now_ms=1_100,
            lease_until_ms=2_000,
            ticket_id=ticket.identity.ticket_id,
        )
        assert claimed is not None
        await uow.exchange_commands.record_result(
            command_id=tp1.command_id,
            worker_id="test-worker",
            result=ExchangeCommandResult(
                status=ExchangeCommandStatus.ACCEPTED,
                observed_at_ms=1_200,
                exchange_order_id="2001",
            ),
        )

    async with order_attribution_engine.begin() as connection:
        await connection.execute(
            sa.update(exchange_commands)
            .where(exchange_commands.c.command_id == tp1.command_id)
            .values(
                request_payload={
                    "side": "sell",
                    "quantity": "0.005",
                    "order_type": "limit",
                    "stop_price": None,
                    "limit_price": "62000",
                    "reduce_only": True,
                    "source_watermark_ms": None,
                    "replaces_exchange_order_id": None,
                    "leverage_verification_digest": None,
                    "required_configured_leverage": None,
                }
            )
        )

    async with PostgresKernelUnitOfWork(order_attribution_engine) as uow:
        references = await uow.exchange_commands.list_order_references(
            ticket.identity.ticket_id
        )

    assert len(references) == 1
    assert references[0].namespace is OrderNamespace.REGULAR
    assert references[0].submitted_exchange_order_id == "2001"


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
