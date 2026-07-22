"""One short PostgreSQL transaction per trading-kernel state reduction."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from src.trading_kernel.application.ports import (
    AggregateVersionConflict,
    UnsupportedKernelEffect,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.effects import PrepareEntryCommand
from src.trading_kernel.domain.events import TicketIssued, TradeEvent
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.ticket import EntryOrderType
from src.trading_kernel.infrastructure.pg_repositories import (
    PostgresAggregateRepository,
    PostgresBudgetRepository,
    PostgresEventRepository,
    PostgresEntryAdmissionRepository,
    PostgresExchangeCommandRepository,
    PostgresIncidentRepository,
    PostgresTicketRepository,
)


__all__ = ["AggregateVersionConflict", "PostgresKernelUnitOfWork"]


class PostgresKernelUnitOfWork:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._transaction: AsyncTransaction | None = None

    async def __aenter__(self) -> "PostgresKernelUnitOfWork":
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        self._connection = await self._engine.connect()
        self._transaction = await self._connection.begin()
        self.tickets = PostgresTicketRepository(self._connection)
        self.aggregates = PostgresAggregateRepository(self._connection)
        self.events = PostgresEventRepository(self._connection)
        self.exchange_commands = PostgresExchangeCommandRepository(self._connection)
        self.budgets = PostgresBudgetRepository(self._connection)
        self.incidents = PostgresIncidentRepository(self._connection)
        self.entry_admission = PostgresEntryAdmissionRepository(self._connection)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        transaction = self._require_transaction()
        connection = self._require_connection()
        try:
            if exc_type is None:
                await transaction.commit()
            else:
                await transaction.rollback()
        finally:
            await connection.close()
            self._transaction = None
            self._connection = None

    async def commit_reduction(
        self,
        *,
        event: TradeEvent,
        reduction: Reduction,
        expected_version: int,
    ) -> None:
        self._require_connection()
        aggregate = reduction.aggregate
        ticket_id = aggregate.identity.ticket_id
        current = await self.aggregates.get_for_update(ticket_id)

        if expected_version == 0:
            if current is not None:
                raise AggregateVersionConflict("Ticket aggregate already exists")
            if not isinstance(event, TicketIssued):
                raise AggregateVersionConflict("new aggregate requires TicketIssued")
            if aggregate.version != 1 or aggregate.last_event_sequence != 1:
                raise AggregateVersionConflict("new aggregate must start at one")
            await self.tickets.add(aggregate.ticket)
            await self.aggregates.add(
                aggregate,
                updated_at_ms=event.occurred_at_ms,
            )
        else:
            if current is None:
                raise AggregateVersionConflict("aggregate does not exist")
            await self.aggregates.save(
                aggregate,
                expected_version=expected_version,
                updated_at_ms=event.occurred_at_ms,
            )

        if event.sequence != aggregate.last_event_sequence:
            raise AggregateVersionConflict("event sequence differs from reduction")
        if _event_ticket_id(event) != ticket_id:
            raise AggregateVersionConflict("event Ticket differs from reduction")

        await self.events.append(event)
        for effect in reduction.effects:
            if isinstance(effect, PrepareEntryCommand):
                await self.exchange_commands.add(
                    _entry_command(effect, occurred_at_ms=event.occurred_at_ms)
                )
                continue
            raise UnsupportedKernelEffect(
                f"no durable materializer for {type(effect).__name__}"
            )

    def _require_connection(self) -> AsyncConnection:
        if self._connection is None:
            raise RuntimeError("unit of work must be entered before use")
        return self._connection

    def _require_transaction(self) -> AsyncTransaction:
        if self._transaction is None:
            raise RuntimeError("unit of work transaction is not active")
        return self._transaction


def _entry_command(
    effect: PrepareEntryCommand,
    *,
    occurred_at_ms: int,
) -> ExchangeCommand:
    ticket = effect.ticket
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    side = "buy" if ticket.identity.netting_domain.position_side == "long" else "sell"
    order_type = "market" if ticket.entry_order_type is EntryOrderType.MARKET else "limit"
    return ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side=side,
            quantity=ticket.quantity,
            order_type=order_type,
            reduce_only=False,
            limit_price=ticket.entry_limit_price,
        ),
        status=ExchangeCommandStatus.PREPARED,
        created_at_ms=occurred_at_ms,
        deadline_at_ms=ticket.expires_at_ms,
    )


def _event_ticket_id(event: TradeEvent) -> str:
    if isinstance(event, TicketIssued):
        return event.ticket.identity.ticket_id
    return event.ticket_id
