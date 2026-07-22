"""Typed persistence ports owned by the trading-kernel application layer."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from types import TracebackType
from typing import Callable, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, JsonValue

from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    CommandPayload,
)
from src.trading_kernel.domain.events import TradeEvent
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.signal import ActionableSignal, SignalFactSnapshot
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    RegistrySeedResult,
)
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


class TradeReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str
    ticket_id: str
    outcome: str
    metrics: dict[str, JsonValue]
    decision_impact: dict[str, JsonValue]
    created_at_ms: int


class MonitorOwnerStatus(StrEnum):
    WAITING_FOR_OPPORTUNITY = "waiting_for_opportunity"
    PROCESSING = "processing"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    NEEDS_INTERVENTION = "needs_intervention"
    PAUSED = "paused"
    COMPLETED = "completed"


class MonitorStateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    monitor_key: str
    owner_status: MonitorOwnerStatus
    summary: str
    intervention: str
    ticket_id: str | None = None
    incident_id: str | None = None
    updated_at_ms: int
    projection_version: int = 0


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


class StrategyGroupSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    active_version_id: str | None
    status: str


class StrategyVersionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_version_id: str
    strategy_group_id: str
    status: str


class EventSpecSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    strategy_version_id: str
    position_side: Literal["long", "short"]
    entry_order_type: str
    status: str


class RuntimeScopeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    runtime_profile_id: str
    owner_policy_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    enabled: bool
    scope_version: int


class RuntimeProfileSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    venue_id: str
    account_id: str
    environment: str
    position_mode: str
    status: str


class InstrumentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    venue_id: str
    status: str


class InstrumentRulesSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    valid_until_ms: int


class RuntimeCapabilitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_key: str
    enabled: bool
    certified_commit: str
    schema_revision: str


class ReadinessSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    readiness_state: str
    first_blocker: str | None
    signal_event_id: str | None
    fact_summary: dict[str, JsonValue]
    updated_at_ms: int
    projection_version: int


class TicketRepository(Protocol):
    async def add(self, ticket: TradeTicket) -> None: ...

    async def get(self, ticket_id: str) -> TradeTicket | None: ...

    async def mark_terminal(
        self,
        ticket_id: str,
        *,
        status: str,
        terminal_at_ms: int,
    ) -> None: ...


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

    async def next_generation(
        self,
        *,
        ticket_id: str,
        kind: ExchangeCommandKind,
    ) -> int: ...

    async def claim_one_prepared(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
        ticket_id: str | None = None,
    ) -> ExchangeCommand | None: ...

    async def record_result(
        self,
        *,
        command_id: str,
        worker_id: str,
        result: ExchangeCommandResult,
    ) -> None: ...

    async def get_one_expired_claim(
        self,
        *,
        now_ms: int,
        ticket_id: str | None = None,
    ) -> ExchangeCommand | None: ...

    async def record_expired_claim_unknown(
        self,
        *,
        command_id: str,
        result: ExchangeCommandResult,
    ) -> None: ...

    async def mark_cancel_reconciled_absent(
        self,
        *,
        ticket_id: str,
        exchange_order_id: str,
        observed_at_ms: int,
    ) -> None: ...


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


class PositionRepository(Protocol):
    async def upsert(
        self,
        *,
        ticket_id: str,
        snapshot: PositionSnapshot,
    ) -> None: ...

    async def get(self, netting_domain_key: str) -> PositionSnapshot | None: ...


class ReviewRepository(Protocol):
    async def add(self, review: TradeReviewRecord) -> None: ...

    async def get_for_ticket(self, ticket_id: str) -> TradeReviewRecord | None: ...


class MonitorRepository(Protocol):
    async def get(self, monitor_key: str) -> MonitorStateRecord | None: ...

    async def save_if_changed(
        self,
        state: MonitorStateRecord,
    ) -> MonitorStateRecord: ...


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

    async def release_account_exposure(
        self,
        *,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
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

    async def release_global_lane(self, *, ticket_id: str) -> None: ...


class SignalRepository(Protocol):
    async def add(self, signal: ActionableSignal) -> bool: ...

    async def get(self, signal_event_id: str) -> ActionableSignal | None: ...

    async def get_next_ready(
        self,
        *,
        now_ms: int,
    ) -> ActionableSignal | None: ...

    async def get_next_stale_ready(
        self,
        *,
        now_ms: int,
    ) -> ActionableSignal | None: ...

    async def get_readiness(
        self,
        runtime_scope_id: str,
    ) -> ReadinessSnapshot | None: ...

    async def save_readiness(
        self,
        *,
        runtime_scope_id: str,
        readiness_state: str,
        first_blocker: str | None,
        signal_event_id: str | None,
        fact_summary: dict[str, JsonValue],
        updated_at_ms: int,
    ) -> ReadinessSnapshot: ...

    async def get_strategy_group(
        self,
        strategy_group_id: str,
    ) -> StrategyGroupSnapshot | None: ...

    async def get_strategy_version(
        self,
        strategy_version_id: str,
    ) -> StrategyVersionSnapshot | None: ...

    async def get_event_spec(
        self,
        event_spec_id: str,
    ) -> EventSpecSnapshot | None: ...

    async def get_runtime_scope(
        self,
        runtime_scope_id: str,
    ) -> RuntimeScopeSnapshot | None: ...

    async def get_runtime_profile(
        self,
        runtime_profile_id: str,
    ) -> RuntimeProfileSnapshot | None: ...

    async def get_instrument(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentSnapshot | None: ...

    async def get_instrument_rules(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentRulesSnapshot | None: ...

    async def get_runtime_capability(
        self,
        capability_key: str,
    ) -> RuntimeCapabilitySnapshot | None: ...

    async def get_required_facts(
        self,
        *,
        runtime_scope_id: str,
        event_spec_id: str,
    ) -> tuple[SignalFactSnapshot, ...] | None: ...


class StrategyRegistryRepository(Protocol):
    async def seed_exact(
        self,
        contracts: tuple[RegisteredStrategyContract, ...],
        *,
        registry_semantic_hash: str,
        seeded_at_ms: int,
    ) -> RegistrySeedResult: ...

    async def list_current_event_ids(self) -> tuple[str, ...]: ...


class VenueCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    kind: ExchangeCommandKind
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    venue_client_order_id: str
    payload: CommandPayload
    deadline_at_ms: int


class VenuePort(Protocol):
    async def execute(
        self,
        request: VenueCommandRequest,
    ) -> ExchangeCommandResult: ...


UnitOfWorkFactory = Callable[[], "KernelUnitOfWork"]


class KernelUnitOfWork(Protocol):
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    incidents: IncidentRepository
    positions: PositionRepository
    reviews: ReviewRepository
    monitors: MonitorRepository
    entry_admission: EntryAdmissionRepository
    signals: SignalRepository
    strategy_registry: StrategyRegistryRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit_reduction(
        self,
        *,
        event: TradeEvent,
        reduction: Reduction,
        expected_version: int,
    ) -> None: ...
