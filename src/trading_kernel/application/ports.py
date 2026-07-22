"""Typed persistence ports owned by the trading-kernel application layer."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, JsonValue

from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.commands import ExchangeCommand
from src.trading_kernel.domain.events import TradeEvent
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.ticket import TradeTicket


class AggregateVersionConflict(RuntimeError):
    """The persisted aggregate is not the version used to compute a change."""


class UnsupportedKernelEffect(RuntimeError):
    """A reducer effect has no explicit durable materializer."""


class BudgetReservationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget_reservation_id: str
    ticket_id: str
    owner_policy_id: str
    account_id: str
    reserved_notional: Decimal
    reserved_risk: Decimal
    status: str
    created_at_ms: int
    released_at_ms: int | None = None


class RuntimeIncidentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: str
    ticket_id: str | None
    incident_kind: str
    status: str
    first_blocker: str
    details: dict[str, JsonValue]
    opened_at_ms: int
    resolved_at_ms: int | None = None


class TicketRepository(Protocol):
    async def add(self, ticket: TradeTicket) -> None: ...

    async def get(self, ticket_id: str) -> TradeTicket | None: ...


class AggregateRepository(Protocol):
    async def add(
        self,
        aggregate: TradeAggregate,
        *,
        updated_at_ms: int | None = None,
    ) -> None: ...

    async def get(self, ticket_id: str) -> TradeAggregate | None: ...

    async def get_for_update(self, ticket_id: str) -> TradeAggregate | None: ...

    async def save(
        self,
        aggregate: TradeAggregate,
        *,
        expected_version: int,
        updated_at_ms: int | None = None,
    ) -> None: ...


class EventRepository(Protocol):
    async def append(self, event: TradeEvent) -> None: ...

    async def list_for_ticket(self, ticket_id: str) -> list[TradeEvent]: ...


class ExchangeCommandRepository(Protocol):
    async def add(self, command: ExchangeCommand) -> None: ...

    async def get(self, command_id: str) -> ExchangeCommand | None: ...

    async def list_for_ticket(self, ticket_id: str) -> list[ExchangeCommand]: ...


class BudgetRepository(Protocol):
    async def add(self, reservation: BudgetReservationRecord) -> None: ...

    async def get_for_ticket(
        self,
        ticket_id: str,
    ) -> BudgetReservationRecord | None: ...

    async def release(self, ticket_id: str, *, released_at_ms: int) -> None: ...


class IncidentRepository(Protocol):
    async def add(self, incident: RuntimeIncidentRecord) -> None: ...

    async def get_open_for_ticket(
        self,
        ticket_id: str,
    ) -> RuntimeIncidentRecord | None: ...

    async def resolve(self, incident_id: str, *, resolved_at_ms: int) -> None: ...


class KernelUnitOfWork(Protocol):
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    incidents: IncidentRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    async def commit_reduction(
        self,
        *,
        event: TradeEvent,
        reduction: Reduction,
        expected_version: int,
    ) -> None: ...
