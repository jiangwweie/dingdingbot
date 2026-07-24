"""Typed persistence ports owned by the trading-kernel application layer."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
import re
from types import TracebackType
from typing import Callable, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.arbitration import EntryCandidate
from src.trading_kernel.domain.capacity import CapacityClaim
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.entry_admission_snapshot import AdmissionOwnership
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    CommandPayload,
    SetLeverageCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.events import TradeEvent
from src.trading_kernel.domain.exit_policy import ExitPolicy
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.signal import SignalFactSnapshot, StrategySignal
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    RegistrySeedResult,
)
from src.trading_kernel.domain.ticket import TradeTicket
from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot


class AggregateVersionConflict(RuntimeError):
    """The persisted aggregate is not the version used to compute a change."""


class UnsupportedKernelEffect(RuntimeError):
    """A reducer effect has no explicit durable materializer."""


class BudgetReservationRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget_reservation_id: str
    ticket_id: str
    owner_policy_id: str
    venue_id: str
    account_id: str
    reserved_notional: Decimal
    reserved_risk: Decimal
    reserved_margin: Decimal
    planned_stop_risk_budget: Decimal
    risk_reservation_basis: str
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
    entry_block_scope: EntryBlockScope
    entry_block_key: str | None
    details: dict[str, JsonValue]
    opened_at_ms: int
    resolved_at_ms: int | None = None

    @model_validator(mode="after")
    def _validate_entry_block_identity(self) -> "RuntimeIncidentRecord":
        if self.entry_block_scope is EntryBlockScope.NONE:
            if self.entry_block_key is not None:
                raise ValueError("non-blocking Incident must not carry a block key")
            return self
        if self.entry_block_scope is EntryBlockScope.RUNTIME:
            if self.entry_block_key != "global":
                raise ValueError("runtime Incident must use the global block key")
            return self
        if not self.entry_block_key:
            raise ValueError("scoped Incident requires a canonical block key")
        return self


class TradeReviewRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str
    ticket_id: str
    outcome: str
    metrics: dict[str, JsonValue]
    decision_impact: dict[str, JsonValue]
    created_at_ms: int


class MonitorOwnerStatus(StrEnum):
    NOT_ENABLED = "not_enabled"
    RUNNING = "running"
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
    new_entry_submit_enabled: bool
    priority_rank: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    min_liquidation_distance_to_stop_distance_ratio: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal


class AccountExposureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
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


class ObservationScopeClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    timeframe: Literal["15m", "1h"]
    trigger_candle_close_time_ms: int


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

    venue_id: str
    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    exchange_max_leverage: int
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
    observed_at_ms: int
    valid_until_ms: int
    projection_version: int


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

    async def release_active_netting_domain(
        self,
        ticket_id: str,
        *,
        netting_domain_key: str,
    ) -> None: ...

    async def has_other_instrument_ticket_in_window(
        self,
        *,
        ticket_id: str,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
        entry_time_ms: int,
        exit_time_ms: int,
    ) -> bool: ...


class AggregateRepository(Protocol):
    async def add(
        self,
        aggregate: TradeAggregate,
        *,
        updated_at_ms: int | None = None,
    ) -> None: ...

    async def get(self, ticket_id: str) -> TradeAggregate | None: ...

    async def get_for_update(self, ticket_id: str) -> TradeAggregate | None: ...

    async def get_next_for_statuses(
        self,
        statuses: tuple[AggregateStatus, ...],
        *,
        work_kind: Literal["lifecycle", "reconciliation"] | None = None,
        now_ms: int | None = None,
    ) -> TradeAggregate | None: ...

    async def schedule_next_check(
        self,
        ticket_id: str,
        *,
        work_kind: Literal["lifecycle", "reconciliation"],
        due_at_ms: int,
    ) -> None: ...

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
        command_kinds: tuple[ExchangeCommandKind, ...] = (),
    ) -> ExchangeCommand | None: ...

    async def record_result(
        self,
        *,
        command_id: str,
        worker_id: str,
        result: ExchangeCommandResult,
    ) -> None: ...

    async def record_leverage_result(
        self,
        *,
        command_id: str,
        worker_id: str,
        result: SetLeverageCommandResult,
    ) -> None: ...

    async def mark_claimed_superseded(
        self,
        *,
        command_id: str,
        worker_id: str,
        observed_at_ms: int,
        reason: str,
    ) -> None: ...

    async def get_one_expired_claim(
        self,
        *,
        now_ms: int,
        ticket_id: str | None = None,
        command_kinds: tuple[ExchangeCommandKind, ...] = (),
    ) -> ExchangeCommand | None: ...

    async def get_one_unknown(self) -> ExchangeCommand | None: ...

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

    async def reconcile_unknown_submitted(
        self,
        *,
        command_id: str,
        exchange_order_id: str,
        observed_at_ms: int,
    ) -> None: ...

    async def reconcile_unknown_leverage_confirmed(
        self,
        *,
        command_id: str,
        result: SetLeverageCommandResult,
    ) -> None: ...

    async def reconcile_unknown_absent(
        self,
        *,
        command_id: str,
        observed_at_ms: int,
        reason: str,
    ) -> None: ...


class BudgetRepository(Protocol):
    async def add(self, reservation: BudgetReservationRecord) -> None: ...

    async def get_for_ticket(
        self,
        ticket_id: str,
    ) -> BudgetReservationRecord | None: ...

    async def release(self, ticket_id: str, *, released_at_ms: int) -> None: ...


class CapacityClaimRepository(Protocol):
    async def add(self, claim: CapacityClaim) -> None: ...

    async def get(self, capacity_claim_id: str) -> CapacityClaim | None: ...

    async def get_for_signal(self, signal_event_id: str) -> CapacityClaim | None: ...

    async def get_for_ticket(self, ticket_id: str) -> CapacityClaim | None: ...


class IncidentRepository(Protocol):
    async def add(self, incident: RuntimeIncidentRecord) -> None: ...

    async def get_open_for_ticket(
        self,
        ticket_id: str,
    ) -> RuntimeIncidentRecord | None: ...

    async def get_open_for_ticket_kind(
        self,
        ticket_id: str,
        incident_kind: str,
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

    async def read_admission_ownership(
        self,
        *,
        venue_id: str,
        account_id: str,
        exchange_instrument_id: str,
    ) -> AdmissionOwnership: ...

    async def get_account_exposure(
        self,
        venue_id: str,
        account_id: str,
        *,
        for_update: bool = False,
    ) -> AccountExposureSnapshot | None: ...

    async def reserve_account_exposure(
        self,
        *,
        venue_id: str,
        account_id: str,
        notional: Decimal,
        risk_at_stop: Decimal,
        expected_version: int | None,
        updated_at_ms: int,
    ) -> None: ...

    async def release_account_exposure(
        self,
        *,
        venue_id: str,
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
    async def add(self, signal: StrategySignal) -> bool: ...

    async def get(self, signal_event_id: str) -> StrategySignal | None: ...

    async def get_fact_snapshots(
        self,
        signal_event_id: str,
    ) -> tuple[SignalFactSnapshot, ...]: ...

    async def upsert_current_facts(
        self,
        *,
        runtime_scope_id: str,
        facts: tuple[SignalFactSnapshot, ...],
    ) -> tuple[SignalFactSnapshot, ...]: ...

    async def get_next_ready(
        self,
        *,
        now_ms: int,
    ) -> StrategySignal | None: ...

    async def get_next_stale_ready(
        self,
        *,
        now_ms: int,
    ) -> StrategySignal | None: ...

    async def list_ready_candidates(
        self,
        *,
        now_ms: int,
        limit: int,
    ) -> tuple[EntryCandidate, ...]: ...

    async def claim_next_observation_scope(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ObservationScopeClaim | None: ...

    async def schedule_observation_scope(
        self,
        *,
        runtime_scope_id: str,
        worker_id: str,
        due_at_ms: int,
    ) -> None: ...

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
        *,
        for_update: bool = False,
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
        venue_id: str,
        exchange_instrument_id: str,
    ) -> InstrumentRulesSnapshot | None: ...

    async def upsert_instrument_rules(
        self,
        *,
        venue_id: str,
        exchange_instrument_id: str,
        quantity_step: Decimal,
        price_tick: Decimal,
        min_quantity: Decimal,
        min_notional: Decimal,
        exchange_max_leverage: int,
        maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...],
        maintenance_margin_brackets_digest: str,
        observed_at_ms: int,
        valid_until_ms: int,
    ) -> InstrumentRulesSnapshot: ...

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

    async def get_exit_policy(self, event_spec_id: str) -> ExitPolicy | None: ...


class VenueCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    kind: ExchangeCommandKind
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    venue_client_order_id: str | None
    payload: CommandPayload
    deadline_at_ms: int


class VenueSetLeverageRequest(BaseModel):
    """The exact durable non-order mutation sent to one venue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    payload: SetLeverageCommandPayload
    deadline_at_ms: int


class LeverageTruthRequest(BaseModel):
    """Exact-instrument readonly truth used after a leverage mutation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    desired_leverage: int
    observed_at_ms: int


class LeverageTruthSnapshot(BaseModel):
    """One bounded exact-instrument leverage/flatness observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_configured_leverage: int
    long_position_quantity: Decimal
    short_position_quantity: Decimal
    regular_open_order_ids: tuple[str, ...]
    conditional_open_order_ids: tuple[str, ...]
    observed_at_ms: int

    @model_validator(mode="after")
    def _validate_exact_truth(self) -> "LeverageTruthSnapshot":
        if (
            isinstance(self.exchange_configured_leverage, bool)
            or not isinstance(self.exchange_configured_leverage, int)
            or self.exchange_configured_leverage <= 0
        ):
            raise ValueError("configured leverage must be a positive integer")
        if self.long_position_quantity < 0 or self.short_position_quantity < 0:
            raise ValueError("leverage truth quantities must be nonnegative")
        if self.observed_at_ms <= 0:
            raise ValueError("leverage truth observation time must be positive")
        return self


class VenueMutationRejected(RuntimeError):
    """A venue-authoritative non-order mutation rejection."""


class VenueMutationFailure(RuntimeError):
    """A sanitized non-order venue failure whose outcome remains unresolved."""

    _REASON = re.compile(r"^exchange_code_-?[0-9]{1,6}$")

    def __init__(self, reason: str) -> None:
        if self._REASON.fullmatch(reason) is None:
            raise ValueError("venue mutation failure reason is not sanitized")
        self.reason = reason
        super().__init__(reason)


class VenuePort(Protocol):
    async def execute(
        self,
        request: VenueCommandRequest,
    ) -> ExchangeCommandResult: ...

    async def set_leverage(
        self,
        request: VenueSetLeverageRequest,
    ) -> SetLeverageCommandResult: ...


class VenueTruthRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    command_id: str
    kind: ExchangeCommandKind
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    venue_client_order_id: str
    payload: CommandPayload
    observed_at_ms: int


class VenueTruthPort(Protocol):
    async def lookup_command_truth(
        self,
        request: VenueTruthRequest,
    ) -> VenueTruthSnapshot: ...

    async def read_configured_leverage(
        self,
        request: LeverageTruthRequest,
    ) -> LeverageTruthSnapshot: ...


UnitOfWorkFactory = Callable[[], "KernelUnitOfWork"]


class KernelUnitOfWork(Protocol):
    tickets: TicketRepository
    aggregates: AggregateRepository
    events: EventRepository
    exchange_commands: ExchangeCommandRepository
    budgets: BudgetRepository
    capacity_claims: CapacityClaimRepository
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
