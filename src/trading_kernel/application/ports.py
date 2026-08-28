"""Typed persistence ports owned by the trading-kernel application layer."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from types import TracebackType
from typing import TYPE_CHECKING, Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    field_validator,
    model_validator,
)

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
)
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    UniverseActivationResult,
)
from src.trading_kernel.application.install_strategy_universe import (
    GenerationUniverseTarget,
    UniverseCurrent,
    UniverseInstallContext,
    UniverseInstallRequest,
    UniverseInstallResult,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeProjectionFailure,
    ComparativeProjectionOutcome,
    ComparativeUniverseProjection,
)
from src.trading_kernel.application.read_strategy_universe_status import (
    StrategyUniverseStatusRequest,
    StrategyUniverseStatusResult,
)
from src.trading_kernel.application.reconciliation_scheduler import (
    ReconciliationActionCandidate,
)
from src.trading_kernel.application.runtime import RuntimeReleaseCompatibilityFact
from src.trading_kernel.domain.admission_decision import AdmissionDecision
from src.trading_kernel.domain.aggregate import AggregateStatus, TradeAggregate
from src.trading_kernel.domain.arbitration import EntryCandidate
from src.trading_kernel.domain.capacity import CapacityClaim, FamilyTicketLimits
from src.trading_kernel.domain.commands import (
    CommandPayload,
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandResult,
    SetLeverageCommandPayload,
    SetLeverageCommandResult,
)
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.entry_admission_snapshot import AdmissionOwnership
from src.trading_kernel.domain.events import TradeEvent
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    EventExitBinding,
    EventExitBindingEvent,
    ExitProfile,
    ExitProfileRecord,
)
from src.trading_kernel.domain.exposure_episode import ExposureEpisodeState
from src.trading_kernel.domain.incident_blocking import EntryBlockScope
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertification,
)
from src.trading_kernel.domain.instrument_selection import (
    SelectionAttemptOutcome,
    SelectionComputation,
    SelectionJobClaim,
    SelectionJobFailure,
    SelectionPeriod,
    SelectionSnapshot,
    SorDynamicSelectionSpecV0,
)
from src.trading_kernel.domain.order_attribution import TicketOrderReference
from src.trading_kernel.domain.owner_control import (
    OwnerAuthorization,
    OwnerControlOperation,
    StrategyEntryControl,
)
from src.trading_kernel.domain.owner_policy import OwnerPolicyScope
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductSessionSnapshot,
)
from src.trading_kernel.domain.reducer import Reduction
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAudit,
    AuthorityGapScopeResult,
    CurrentSelectionAuthority,
    MaterializationGeneration,
    MaterializationGenerationLeaseClaim,
    MaterializationTarget,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    SelectionSnapshotDisposition,
)
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeClaim,
    ShadowOutcomeProjection,
    ShadowOutcomeSpec,
)
from src.trading_kernel.domain.signal import SignalFactSnapshot, StrategySignal
from src.trading_kernel.domain.strategy_entry_vacuum import StrategyEntryVacuum
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    RegistrySeedResult,
)
from src.trading_kernel.domain.ticket import TradeTicket
from src.trading_kernel.domain.venue_truth import VenueTruthSnapshot

if TYPE_CHECKING:
    from src.trading_kernel.application.certification_batch import (
        CertificationBatchSnapshot,
        StartCertificationBatchRequest,
    )


class AggregateVersionConflict(RuntimeError):
    """The persisted aggregate is not the version used to compute a change."""


class ExitProfileAuthorityConflict(RuntimeError):
    """ExitProfile authority changed or current facts block the mutation."""


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
    def _validate_entry_block_identity(self) -> RuntimeIncidentRecord:
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
    revision: int = 1
    supersedes_review_id: str | None = None
    outcome: str
    metrics: dict[str, JsonValue]
    decision_impact: dict[str, JsonValue]
    created_at_ms: int

    @field_validator("review_id", "ticket_id", mode="before")
    @classmethod
    def _require_review_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Review identities must be non-blank")
        return normalized

    @field_validator("supersedes_review_id", mode="before")
    @classmethod
    def _normalize_supersedes_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_revision_chain(self) -> TradeReviewRecord:
        if self.revision <= 0:
            raise ValueError("Review revision must be positive")
        if self.revision == 1 and self.supersedes_review_id is not None:
            raise ValueError("initial Review must not supersede another Review")
        if self.revision > 1 and self.supersedes_review_id is None:
            raise ValueError("later Review revision must supersede its predecessor")
        if self.review_id == self.supersedes_review_id:
            raise ValueError("Review revision cannot supersede itself")
        return self


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
    family_ticket_limits: FamilyTicketLimits
    max_ticket_stop_risk_fraction: Decimal
    max_gross_stop_risk_fraction: Decimal
    max_ticket_initial_margin_fraction: Decimal
    max_gross_initial_margin_utilization: Decimal
    directional_stop_risk_limit_fraction: Decimal
    min_materialization_ratio: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    post_stop_stress_multiple: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal
    scope: OwnerPolicyScope | None = None


class AccountExposureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    gross_notional: Decimal
    gross_risk_at_stop: Decimal
    current_reserved_margin: Decimal
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
    universe_version_id: str
    universe_semantic_digest: str
    lifecycle_state: Literal["warming", "active", "retired", "abandoned"]
    observation_enabled: bool
    entry_enabled: bool
    scope_version: int
    observation_generation: int
    warm_closed_bar_time_ms: int | None = None
    warm_completed_at_ms: int | None = None
    warm_readiness_digest: str | None = None
    warm_valid_until_ms: int | None = None

    @field_validator("observation_generation")
    @classmethod
    def _require_nonnegative_generation(cls, value: int) -> int:
        if value < 0:
            raise ValueError("observation generation must be nonnegative")
        return value


class WarmReadiness(BaseModel):
    """One scope's immutable, Universe-bound market-readiness proof."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    scope_version: int
    observation_generation: int
    event_spec_id: str
    exchange_instrument_id: str
    universe_version_id: str
    universe_semantic_digest: str
    fact_digest: str
    warm_closed_bar_time_ms: int
    warm_completed_at_ms: int
    warm_valid_until_ms: int
    readiness_digest: str

    @classmethod
    def digest_for(
        cls,
        *,
        runtime_scope_id: str,
        scope_version: int,
        observation_generation: int,
        event_spec_id: str,
        exchange_instrument_id: str,
        universe_version_id: str,
        universe_semantic_digest: str,
        fact_digest: str,
        warm_closed_bar_time_ms: int,
        warm_valid_until_ms: int,
    ) -> str:
        canonical = json.dumps(
            {
                "event_spec_id": event_spec_id,
                "exchange_instrument_id": exchange_instrument_id,
                "fact_digest": fact_digest,
                "warm_closed_bar_time_ms": warm_closed_bar_time_ms,
                "runtime_scope_id": runtime_scope_id,
                "scope_version": scope_version,
                "observation_generation": observation_generation,
                "universe_semantic_digest": universe_semantic_digest,
                "universe_version_id": universe_version_id,
                "warm_valid_until_ms": warm_valid_until_ms,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return f"sha256:{sha256(canonical).hexdigest()}"

    @model_validator(mode="after")
    def _validate_readiness(self) -> WarmReadiness:
        identities = (
            self.runtime_scope_id,
            self.event_spec_id,
            self.exchange_instrument_id,
            self.universe_version_id,
        )
        if any(not value.strip() for value in identities):
            raise ValueError("warm readiness identities must be non-blank")
        digests = (
            self.universe_semantic_digest,
            self.fact_digest,
            self.readiness_digest,
        )
        if any(re.fullmatch(r"sha256:[0-9a-f]{64}", item) is None for item in digests):
            raise ValueError("warm readiness digests must be exact sha256 identities")
        if (
            self.scope_version <= 0
            or self.observation_generation <= 0
            or self.warm_closed_bar_time_ms <= 0
            or self.warm_completed_at_ms < self.warm_closed_bar_time_ms
            or self.warm_valid_until_ms <= self.warm_completed_at_ms
        ):
            raise ValueError("warm readiness version and time window are invalid")
        expected = self.digest_for(
            runtime_scope_id=self.runtime_scope_id,
            scope_version=self.scope_version,
            observation_generation=self.observation_generation,
            event_spec_id=self.event_spec_id,
            exchange_instrument_id=self.exchange_instrument_id,
            universe_version_id=self.universe_version_id,
            universe_semantic_digest=self.universe_semantic_digest,
            fact_digest=self.fact_digest,
            warm_closed_bar_time_ms=self.warm_closed_bar_time_ms,
            warm_valid_until_ms=self.warm_valid_until_ms,
        )
        if self.readiness_digest != expected:
            raise ValueError("warm readiness digest differs from bound inputs")
        return self


class ActiveStrategyUniverseSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    exchange_instrument_id: str


class ActiveStrategyUniverseMembershipSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    exchange_instrument_ids: tuple[str, ...]


class ObservationUniverseMembershipSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    universe_version_id: str
    semantic_digest: str
    lifecycle_state: Literal["warming", "active"]
    exchange_instrument_ids: tuple[str, ...]


class ObservationScopeClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    timeframe: Literal["15m", "1h"]
    trigger_candle_close_time_ms: int
    observation_generation: int

    @field_validator("observation_generation")
    @classmethod
    def _require_positive_generation(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("observation claim generation must be positive")
        return value


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
    notional_coefficient: Decimal
    notional_coefficient_certified: bool
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

    async def list_active_ticket_ids(
        self,
        *,
        venue_id: str,
        account_id: str,
        limit: int,
    ) -> tuple[str, ...]: ...

    async def get_next_for_statuses(
        self,
        statuses: tuple[AggregateStatus, ...],
        *,
        work_kind: Literal["lifecycle", "reconciliation"] | None = None,
        now_ms: int | None = None,
    ) -> TradeAggregate | None: ...

    async def claim_next_critical_reconciliation_work(
        self,
        *,
        now_ms: int,
    ) -> TradeAggregate | None: ...

    async def claim_next_routine_reconciliation_work(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> TradeAggregate | None: ...

    async def peek_next_routine_reconciliation_action(
        self,
        *,
        now_ms: int,
    ) -> ReconciliationActionCandidate | None: ...

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

    async def list_order_references(
        self,
        ticket_id: str,
    ) -> tuple[TicketOrderReference, ...]: ...

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

    async def mark_prepared_superseded(
        self,
        *,
        command_id: str,
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

    async def get_latest_for_account(
        self,
        *,
        venue_id: str,
        account_id: str,
    ) -> CapacityClaim | None: ...


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

    async def resolve_all_open_for_ticket(
        self,
        ticket_id: str,
        *,
        resolved_at_ms: int,
        resolved_by_event_id: str,
    ) -> None: ...


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

    async def get(self, review_id: str) -> TradeReviewRecord | None: ...

    async def get_for_ticket(self, ticket_id: str) -> TradeReviewRecord | None: ...


class MonitorRepository(Protocol):
    async def get(self, monitor_key: str) -> MonitorStateRecord | None: ...

    async def save_if_changed(
        self,
        state: MonitorStateRecord,
    ) -> MonitorStateRecord: ...


class OwnerControlRepository(Protocol):
    async def get_strategy_control(
        self,
        strategy_group_id: str,
        *,
        for_update: bool = False,
    ) -> StrategyEntryControl | None: ...

    async def list_strategy_controls(self) -> tuple[StrategyEntryControl, ...]: ...

    async def add_authorization(self, authorization: OwnerAuthorization) -> None: ...

    async def get_authorization_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> OwnerAuthorization | None: ...

    async def save_strategy_control(
        self,
        *,
        current: StrategyEntryControl,
        authorization_id: str,
        operation: Literal["pause", "resume"],
        payload: dict[str, JsonValue],
    ) -> None: ...

    async def set_global_entry_enabled(
        self,
        *,
        owner_policy_id: str,
        expected_version: int,
        enabled: bool,
        authorization_id: str,
        reason: str,
        updated_at_ms: int,
    ) -> OwnerPolicySnapshot: ...

    async def get_global_entry_resume_blocker(
        self,
        *,
        owner_policy_id: str,
    ) -> str | None: ...

    async def add_operation(self, operation: OwnerControlOperation) -> None: ...

    async def get_operation(
        self,
        authorization_id: str,
        *,
        for_update: bool = False,
    ) -> OwnerControlOperation | None: ...

    async def get_actionable_operation(
        self,
        *,
        now_ms: int,
        for_update: bool = False,
    ) -> OwnerControlOperation | None: ...

    async def get_progressable_operation(
        self,
        *,
        for_update: bool = False,
    ) -> OwnerControlOperation | None: ...

    async def get_latest_operation(self) -> OwnerControlOperation | None: ...

    async def get_latest_nonterminal_operation(
        self,
    ) -> OwnerControlOperation | None: ...

    async def list_recent_operations(
        self,
        *,
        limit: int,
    ) -> tuple[OwnerControlOperation, ...]: ...

    async def save_operation(
        self,
        operation: OwnerControlOperation,
        *,
        event_payload: dict[str, JsonValue],
    ) -> None: ...

    async def list_recent_events(
        self,
        *,
        limit: int,
    ) -> tuple[dict[str, JsonValue], ...]: ...


class EntryAdmissionRepository(Protocol):
    async def lock_global_lane(self) -> EntryLaneSnapshot: ...

    async def get_global_lane(self) -> EntryLaneSnapshot | None: ...

    async def get_owner_policy(
        self,
        owner_policy_id: str,
    ) -> OwnerPolicySnapshot | None: ...

    async def has_active_ticket_in_domain(self, netting_domain_key: str) -> bool: ...

    async def has_ticket_for_signal(self, signal_event_id: str) -> bool: ...

    async def count_active_family_tickets(
        self,
        *,
        venue_id: str,
        account_id: str,
        exposure_family: str,
    ) -> int: ...

    async def sum_active_directional_stop_risk(
        self,
        *,
        venue_id: str,
        account_id: str,
        position_side: Literal["long", "short"],
    ) -> Decimal: ...

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
        reserved_margin: Decimal,
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
        reserved_margin: Decimal,
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

    async def lock_exposure_episode(
        self,
        episode_domain_key: str,
    ) -> ExposureEpisodeState | None: ...

    async def save_exposure_episode(
        self,
        state: ExposureEpisodeState,
        *,
        expected_version: int,
    ) -> None: ...

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

    async def claim_observation_generation(
        self,
        runtime_scope_id: str,
    ) -> RuntimeScopeSnapshot | None: ...

    async def schedule_observation_scope(
        self,
        *,
        runtime_scope_id: str,
        worker_id: str,
        observation_generation: int,
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

    async def save_warm_readiness(
        self,
        readiness: WarmReadiness,
    ) -> None: ...

    async def clear_warm_readiness(
        self,
        *,
        runtime_scope_id: str,
        scope_version: int,
        observation_generation: int,
        event_spec_id: str,
        exchange_instrument_id: str,
        universe_version_id: str,
        universe_semantic_digest: str,
        blocker: str,
        updated_at_ms: int,
    ) -> None: ...
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

    async def get_active_universe_member(
        self,
        *,
        event_spec_id: str,
        exchange_instrument_id: str,
        for_update: bool = False,
    ) -> ActiveStrategyUniverseSnapshot | None: ...

    async def get_active_universe_members(
        self,
        *,
        event_spec_id: str,
    ) -> ActiveStrategyUniverseMembershipSnapshot | None: ...

    async def get_observation_universe_members(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
    ) -> ObservationUniverseMembershipSnapshot | None: ...

    async def get_runtime_profile(
        self,
        runtime_profile_id: str,
    ) -> RuntimeProfileSnapshot | None: ...

    async def get_instrument(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentSnapshot | None: ...

    async def get_product_session(
        self,
        exchange_instrument_id: str,
    ) -> ProductSessionSnapshot | None: ...

    async def get_product_profile(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentProductProfile | None: ...

    async def upsert_product_sessions(
        self,
        snapshots: tuple[ProductSessionSnapshot, ...],
    ) -> int: ...

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
        notional_coefficient: Decimal,
        notional_coefficient_certified: bool,
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

    async def get_selection_authority_chain(
        self,
        *,
        selection_spec_id: str,
        birth_selection_authority_id: str,
        current_selection_authority_id: str,
        max_depth: int,
    ) -> tuple[SelectionSessionAuthority, ...]: ...

    async def selection_authority_was_interrupted(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        owner_policy_id: str,
        after_ms: int,
        through_ms: int,
    ) -> bool: ...

    async def is_strategy_trigger_suppressed(
        self,
        *,
        event_spec_id: str,
        exchange_instrument_id: str,
        session_reference: str,
    ) -> bool: ...

    async def selection_generation_matches_pair(
        self,
        *,
        materialization_generation_id: str,
        long_universe_version_id: str,
        short_universe_version_id: str,
    ) -> bool: ...


class AdmissionDecisionRepository(Protocol):
    async def add(self, decision: AdmissionDecision) -> None: ...

    async def get_for_signal(
        self,
        signal_event_id: str,
    ) -> AdmissionDecision | None: ...

    async def list_recent(
        self,
        *,
        limit: int,
    ) -> tuple[AdmissionDecision, ...]: ...


class ShadowOutcomeRepository(Protocol):
    async def add_pending(self, spec: ShadowOutcomeSpec) -> None: ...

    async def claim_one_due(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ShadowOutcomeClaim | None: ...

    async def complete(
        self,
        *,
        claim: ShadowOutcomeClaim,
        projection: ShadowOutcomeProjection,
        completed_at_ms: int,
    ) -> None: ...

    async def mark_unavailable(
        self,
        *,
        claim: ShadowOutcomeClaim,
        reason: str,
        completed_at_ms: int,
    ) -> None: ...

    async def release_expired_claim(
        self,
        *,
        claim: ShadowOutcomeClaim,
    ) -> None: ...


class StrategyRegistryRepository(Protocol):
    async def seed_exact(
        self,
        contracts: tuple[RegisteredStrategyContract, ...],
        *,
        registry_semantic_hash: str,
        seeded_at_ms: int,
        include_product_compatibility: bool = True,
        include_exit_profile_authority: bool = True,
        compatible_source_registry_semantic_hash: str | None = None,
    ) -> RegistrySeedResult: ...

    async def list_current_event_ids(self) -> tuple[str, ...]: ...

class StrategyUniverseRepository(Protocol):
    async def resolve_install_context(
        self,
        *,
        runtime_profile_id: str,
        event_id: str,
    ) -> UniverseInstallContext: ...

    async def install(
        self,
        request: UniverseInstallRequest,
    ) -> UniverseInstallResult: ...

    async def get_current(
        self,
        event_spec_id: str,
    ) -> UniverseCurrent | None: ...

    async def get_members(
        self,
        universe_version_id: str,
    ) -> tuple[str, ...]: ...

    async def read_status(
        self,
        request: StrategyUniverseStatusRequest,
    ) -> StrategyUniverseStatusResult: ...

    async def try_activate(
        self,
        request: UniverseActivationRequest,
    ) -> UniverseActivationResult: ...

    async def get_generation_universe_targets(
        self,
        materialization_generation_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[GenerationUniverseTarget, ...]: ...

    async def abandon(
        self,
        request: AbandonStrategyUniverseRequest,
    ) -> None: ...

    async def get_comparative_projection(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        closed_bar_time_ms: int,
        member_set_digest: str,
    ) -> ComparativeProjectionOutcome | None: ...

    async def save_comparative_projection(
        self,
        projection: ComparativeUniverseProjection,
    ) -> ComparativeUniverseProjection: ...

    async def save_comparative_projection_failure(
        self,
        failure: ComparativeProjectionFailure,
    ) -> ComparativeProjectionOutcome: ...

    async def claim_due_instrument_certification(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
        overdue_before_ms: int | None = None,
    ) -> InstrumentCertificationTarget | None: ...

    async def peek_next_due_instrument_certification_action(
        self,
        *,
        now_ms: int,
    ) -> ReconciliationActionCandidate | None: ...

    async def save_instrument_certification(
        self,
        *,
        target: InstrumentCertificationTarget,
        certification: InstrumentCertification,
        product_rules_digest: str | None,
        configured_leverage: int | None,
        margin_mode: str | None,
        position_mode: str | None,
        next_check_at_ms: int,
    ) -> None: ...

    async def start_certification_batch(
        self,
        *,
        request: StartCertificationBatchRequest,
        manifest_digest: str,
    ) -> CertificationBatchSnapshot: ...


class SelectionJobRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_job_id: str
    selection_spec_id: str
    session_start_ms: int
    scheduled_at_ms: int
    feature_cutoff_at_ms: int
    state: Literal[
        "DUE",
        "CLAIMED",
        "SNAPSHOT_READY",
        "SOURCE_FAILED",
        "COMPUTE_FAILED",
    ]
    selection_snapshot_id: str | None
    first_blocker: str | None
    attempt_count: int
    next_retry_at_ms: int | None
    lease_owner: str | None
    lease_expires_at_ms: int | None
    projection_version: int
    updated_at_ms: int

    @model_validator(mode="after")
    def _validate_job(self) -> SelectionJobRecord:
        expected_id = f"selection-job:{self.selection_spec_id}:{self.session_start_ms}"
        if self.selection_job_id != expected_id:
            raise ValueError("Selection Job identity is not canonical")
        if self.attempt_count < 0 or self.projection_version <= 0:
            raise ValueError("Selection Job counters are invalid")
        if self.state == "CLAIMED":
            if self.lease_owner is None or self.lease_expires_at_ms is None:
                raise ValueError("claimed Selection Job requires lease ownership")
        elif self.lease_owner is not None or self.lease_expires_at_ms is not None:
            raise ValueError("unclaimed Selection Job cannot retain a lease")
        if self.state == "SNAPSHOT_READY":
            if self.selection_snapshot_id is None or self.first_blocker is not None:
                raise ValueError("ready Selection Job requires only its Snapshot")
        elif self.selection_snapshot_id is not None:
            raise ValueError("non-ready Selection Job cannot reference a Snapshot")
        if self.state in {"SOURCE_FAILED", "COMPUTE_FAILED"}:
            if self.first_blocker is None:
                raise ValueError("failed Selection Job requires its first blocker")
        elif self.first_blocker is not None:
            raise ValueError("non-failed Selection Job cannot claim a blocker")
        return self


class InstrumentSelectionRepository(Protocol):
    @classmethod
    def lease_namespace(
        cls,
        lease_kind: Literal["selection", "materialization", "observation"],
    ) -> str: ...

    async def get_active_spec(
        self,
        selection_spec_id: str,
    ) -> SorDynamicSelectionSpecV0: ...

    async def claim_selection_job(
        self,
        *,
        spec: SorDynamicSelectionSpecV0,
        period: SelectionPeriod,
        worker_id: str,
        now_ms: int,
        lease_duration_ms: int,
    ) -> SelectionJobClaim | SelectionJobFailure | SelectionSnapshot: ...

    async def complete_selection_snapshot(
        self,
        *,
        claim: SelectionJobClaim,
        computation: SelectionComputation,
        completed_at_ms: int,
    ) -> None: ...

    async def complete_selection_failure(
        self,
        *,
        claim: SelectionJobClaim,
        outcome: SelectionAttemptOutcome,
        reason_code: str,
        source_member_count: int,
        source_digest: str | None,
        completed_at_ms: int,
    ) -> None: ...

    async def get_selection_job(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
    ) -> SelectionJobRecord | None: ...

    async def add_authority_and_set_current(
        self,
        authority: SelectionSessionAuthority,
        *,
        expected_current_version: int | None,
    ) -> None: ...

    async def get_current_authority(
        self,
        selection_spec_id: str,
        *,
        for_update: bool = False,
    ) -> SelectionSessionAuthority | None: ...

    async def get_current_authority_projection(
        self,
        selection_spec_id: str,
        *,
        for_update: bool = False,
    ) -> CurrentSelectionAuthority | None: ...

    async def get_selection_control(
        self,
        strategy_group_id: str,
        *,
        for_update: bool = False,
    ) -> SelectionControl | None: ...

    async def activate_pending_selection_mode(
        self,
        *,
        strategy_group_id: str,
        expected_control_version: int,
        expected_pending_mode: SelectionMode,
        activated_at_ms: int,
    ) -> SelectionControl: ...

    async def stage_pending_selection_mode(
        self,
        *,
        strategy_group_id: str,
        expected_control_version: int,
        expected_current_mode: SelectionMode,
        pending_mode: SelectionMode,
        effective_session_start_ms: int,
        authorization_id: str,
        updated_at_ms: int,
    ) -> SelectionControl | None: ...

    async def get_snapshot_disposition(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        for_update: bool = False,
    ) -> SelectionSnapshotDisposition | None: ...

    async def add_pending_materialization_generation(
        self,
        generation: MaterializationGeneration,
        *,
        targets: tuple[MaterializationTarget, ...],
    ) -> None: ...

    async def get_materialization_generation_for_snapshot(
        self,
        selection_snapshot_id: str,
        *,
        for_update: bool = False,
    ) -> MaterializationGeneration | None: ...

    async def get_materialization_generation_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
    ) -> MaterializationGeneration | None: ...

    async def mark_materialization_generation_desired(
        self,
        materialization_generation_id: str,
        *,
        expected_projection_version: int,
        desired_at_ms: int,
    ) -> MaterializationGeneration: ...

    async def mark_materialization_generation_abandoned(
        self,
        materialization_generation_id: str,
        *,
        expected_projection_version: int,
        reason_code: str,
        abandoned_at_ms: int,
    ) -> MaterializationGeneration: ...

    async def supersede_generation_and_retarget_vacuum(
        self,
        *,
        previous_generation: MaterializationGeneration,
        replacement_generation: MaterializationGeneration,
        replacement_targets: tuple[MaterializationTarget, ...],
        vacuum: StrategyEntryVacuum,
        superseded_at_ms: int,
    ) -> MaterializationGeneration: ...

    async def supersede_generation_and_resolve_valid_empty(
        self,
        *,
        previous_generation: MaterializationGeneration,
        snapshot: SelectionSnapshot,
        vacuum: StrategyEntryVacuum,
        superseded_at_ms: int,
    ) -> None: ...

    async def mark_generation_fallback_previous_pending(
        self,
        *,
        generation: MaterializationGeneration,
        vacuum: StrategyEntryVacuum,
        reason_code: str,
        marked_at_ms: int,
    ) -> StrategyEntryVacuum: ...

    async def abandon_generation_for_owner_pause(
        self,
        *,
        generation: MaterializationGeneration,
        vacuum: StrategyEntryVacuum,
        paused_at_ms: int,
    ) -> MaterializationGeneration: ...

    async def get_materialization_generation(
        self,
        materialization_generation_id: str,
        *,
        for_update: bool = False,
    ) -> MaterializationGeneration | None: ...

    async def get_current_nonterminal_materialization_generation(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        for_update: bool = False,
    ) -> MaterializationGeneration | None: ...

    async def claim_materialization_generation(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        worker_id: str,
        now_ms: int,
        lease_duration_ms: int,
    ) -> MaterializationGenerationLeaseClaim: ...

    async def release_materialization_generation_lease(
        self,
        *,
        materialization_generation_id: str,
        worker_id: str,
    ) -> None: ...

    async def open_generation_entry_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        expected_generation_version: int,
    ) -> None: ...

    async def get_current_entry_vacuum(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        for_update: bool = False,
    ) -> StrategyEntryVacuum | None: ...

    async def list_entry_vacuums_for_period(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ) -> tuple[StrategyEntryVacuum, ...]: ...

    async def open_valid_empty_intent_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        selection_snapshot_id: str,
    ) -> None: ...

    async def open_owner_paused_entry_vacuum(
        self,
        vacuum: StrategyEntryVacuum,
    ) -> StrategyEntryVacuum: ...

    async def mark_entry_vacuum_draining(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        started_at_ms: int,
    ) -> StrategyEntryVacuum: ...

    async def get_next_entry_vacuum_ticket(
        self,
        *,
        strategy_group_id: str,
    ) -> str | None: ...

    async def entry_vacuum_has_drain_blockers(
        self,
        *,
        strategy_group_id: str,
    ) -> bool: ...

    async def mark_entry_vacuum_drained(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        target_state: Literal["RECONFIGURING", "VALID_EMPTY"],
        drained_at_ms: int,
    ) -> StrategyEntryVacuum: ...

    async def mark_owner_pause_vacuum_drained(
        self,
        vacuum: StrategyEntryVacuum,
        *,
        drained_at_ms: int,
    ) -> StrategyEntryVacuum: ...

    async def add_pending_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
    ) -> None: ...

    async def get_authority_gap_audit(
        self,
        authority_gap_audit_id: str,
        *,
        for_update: bool = False,
    ) -> AuthorityGapAudit | None: ...

    async def list_authority_gap_audits_for_period(
        self,
        *,
        selection_spec_id: str,
        session_start_ms: int,
        limit: int,
    ) -> tuple[AuthorityGapAudit, ...]: ...

    async def add_runtime_release_compatibility_fact(
        self,
        fact: RuntimeReleaseCompatibilityFact,
    ) -> None: ...

    async def get_runtime_release_compatibility_fact(
        self,
        release_compatibility_id: str,
    ) -> RuntimeReleaseCompatibilityFact | None: ...

    async def complete_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
        *,
        results: tuple[AuthorityGapScopeResult, ...],
        completed_at_ms: int,
    ) -> None: ...

    async def fail_authority_gap_audit(
        self,
        audit: AuthorityGapAudit,
        *,
        failed_at_ms: int,
    ) -> None: ...


class ExitProfileAuthorityRepository(Protocol):
    async def acquire_authority_write_lock(self) -> None: ...

    async def get_current_binding(
        self,
        event_spec_id: str,
        *,
        for_update: bool = False,
    ) -> CurrentEventExitBinding | None: ...

    async def get_binding(self, exit_binding_id: str) -> EventExitBinding | None: ...

    async def get_profile(
        self,
        *,
        exit_profile_id: str,
        semantic_hash: str,
    ) -> ExitProfileRecord | None: ...

    async def switch_current_binding(
        self,
        *,
        expected_current: CurrentEventExitBinding,
        new_binding: EventExitBinding,
        owner_authorization_id: str,
        reason: str,
        switched_at_ms: int,
    ) -> CurrentEventExitBinding: ...

    async def retire_profile(
        self,
        *,
        profile: ExitProfile,
        retired_at_ms: int,
    ) -> ExitProfileRecord: ...

    async def retire_current_bindings_for_events(
        self,
        *,
        event_spec_ids: tuple[str, ...],
        reason: str,
        retired_at_ms: int,
    ) -> None: ...

    async def list_profiles(self, *, limit: int) -> tuple[ExitProfileRecord, ...]: ...

    async def list_current_bindings(
        self,
        *,
        event_spec_id: str | None,
        limit: int,
    ) -> tuple[CurrentEventExitBinding, ...]: ...

    async def list_binding_events(
        self,
        *,
        event_spec_id: str | None,
        limit: int,
    ) -> tuple[EventExitBindingEvent, ...]: ...


class InstrumentCertificationTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    venue_id: str
    account_id: str
    universe_version_id: str
    exchange_instrument_id: str
    lease_owner: str
    lease_expires_at_ms: int

    @model_validator(mode="after")
    def _validate_target(self) -> InstrumentCertificationTarget:
        for value in (
            self.runtime_profile_id,
            self.venue_id,
            self.account_id,
            self.universe_version_id,
            self.exchange_instrument_id,
            self.lease_owner,
        ):
            if not str(value or "").strip():
                raise ValueError("certification target identities must be non-blank")
        if self.lease_expires_at_ms <= 0:
            raise ValueError("certification lease expiry must be positive")
        return self


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
    def _validate_exact_truth(self) -> LeverageTruthSnapshot:
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
    owner_controls: OwnerControlRepository
    entry_admission: EntryAdmissionRepository
    admission_decisions: AdmissionDecisionRepository
    shadow_outcomes: ShadowOutcomeRepository
    signals: SignalRepository
    strategy_registry: StrategyRegistryRepository
    strategy_universes: StrategyUniverseRepository
    instrument_selection: InstrumentSelectionRepository
    exit_profiles: ExitProfileAuthorityRepository

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
