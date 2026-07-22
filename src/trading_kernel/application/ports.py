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


class OwnerPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_policy_id: str
    policy_version: int
    enabled: bool
    real_submit_enabled: bool
    max_concurrent_tickets: int
    max_gross_notional: Decimal


class AccountExposureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    gross_notional: Decimal
    gross_risk_at_stop: Decimal
    active_ticket_count: int
    projection_version: int
    updated_at_ms: int


class EntryLaneSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_id: str
    ticket_id: str | None
    signal_event_id: str | None
    status: str
    claimed_at_ms: int | None
    lease_until_ms: int | None
    claim_owner: str | None
    version: int


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


class EntryAdmissionRepository(Protocol):
    async def lock_global_lane(self) -> EntryLaneSnapshot: ...

    async def get_global_lane(self) -> EntryLaneSnapshot | None: ...

    async def get_owner_policy(
        self,
        owner_policy_id: str,
    ) -> OwnerPolicySnapshot | None: ...

    async def has_active_ticket_in_domain(self, netting_domain_key: str) -> bool: ...

    async def has_ticket_for_signal(self, signal_event_id: str) -> bool: ...

    async def get_account_exposure(
        self,
        account_id: str,
        *,
        for_update: bool = False,
    ) -> AccountExposureSnapshot | None: ...

    async def reserve_account_exposure(
        self,
        *,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        expected_version: int | None,
        updated_at_ms: int,
    ) -> None: ...

    async def claim_global_lane(
        self,
        *,
        ticket_id: str,
        signal_event_id: str,
        claim_owner: str,
        claimed_at_ms: int,
        lease_until_ms: int,
        expected_version: int,
    ) -> None: ...


class KernelUnitOfWork(Protocol):
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    incidents: IncidentRepository
    entry_admission: EntryAdmissionRepository

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
