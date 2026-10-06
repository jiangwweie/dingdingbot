"""Pure time-bounded Selection Authority identities and compatibility rules."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.trading_kernel.domain.dynamic_selection_timing import (
    CurrentFinalCloseGrantProof,
    DynamicMembershipFreshness,
    DynamicMembershipState,
    GenericSelectionPeriod,
    HourlyRecoveryClosePlan,
    require_hourly_recovery_commit,
)
from src.trading_kernel.domain.exposure_episode import (
    LockedObservationCursor,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.instrument_selection import (
    DAY_MS,
    HOUR_MS,
    INTERVAL_MS,
    SelectionSnapshot,
)
from src.trading_kernel.domain.strategy_universe import StrategyUniverseSourceKind


class AuthorityOutcome(StrEnum):
    PRE_FENCE_CONTINUITY = "PRE_FENCE_CONTINUITY"
    ACTIVE_NEW = "ACTIVE_NEW"
    NO_CHANGE = "NO_CHANGE"
    FALLBACK_PREVIOUS = "FALLBACK_PREVIOUS"
    VALID_EMPTY = "VALID_EMPTY"
    OWNER_PAUSED_NOT_MATERIALIZED = "OWNER_PAUSED_NOT_MATERIALIZED"


class ContinuitySourceKind(StrEnum):
    SELECTION_AUTHORITY = "SELECTION_AUTHORITY"
    STATIC_BASELINE = "STATIC_BASELINE"
    AUTHORITY_GAP_AUDIT = "AUTHORITY_GAP_AUDIT"
    NONE = "NONE"


class SelectionMode(StrEnum):
    DISABLED = "disabled"
    STATIC_BASELINE = "static_baseline"
    DYNAMIC_SELECTION = "dynamic_selection"


class AuthorityGrantProofKind(StrEnum):
    CONTINUOUS_ELIGIBLE_CLOSES = "CONTINUOUS_ELIGIBLE_CLOSES"
    AUDITED_AUTHORITY_GAP = "AUDITED_AUTHORITY_GAP"


class AuthorityGapAuditKind(StrEnum):
    LATE_PRE_FENCE_CONTINUITY = "LATE_PRE_FENCE_CONTINUITY"
    LATE_NO_CHANGE = "LATE_NO_CHANGE"
    ENTRY_VACUUM = "ENTRY_VACUUM"
    OWNER_PAUSE = "OWNER_PAUSE"


class AuthorityGapAuditState(StrEnum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AuthorityGapScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    exchange_instrument_id: str

    @field_validator("event_spec_id", "exchange_instrument_id", mode="before")
    @classmethod
    def _require_scope_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority Gap Audit scope identity must be non-blank")
        return normalized


class AuthorityGapScopeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: AuthorityGapScope
    session_reference: str
    first_natural_trigger_at_ms: int | None

    @field_validator("session_reference", mode="before")
    @classmethod
    def _require_session_reference(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority Gap Audit result requires session reference")
        return normalized

    @field_validator("first_natural_trigger_at_ms")
    @classmethod
    def _require_optional_positive_trigger(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Authority Gap Audit trigger time must be positive")
        return value

    @property
    def trigger_consumed(self) -> bool:
        return self.first_natural_trigger_at_ms is not None


class StrategyTriggerSuppression(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger_suppression_id: str
    authority_gap_audit_id: str
    entry_vacuum_id: str | None
    materialization_generation_id: str | None
    event_spec_id: str
    exchange_instrument_id: str
    session_reference: str
    first_natural_trigger_at_ms: int
    reason_code: Literal["TRIGGER_DURING_AUTHORITY_GAP"] = (
        "TRIGGER_DURING_AUTHORITY_GAP"
    )
    detector_semantic_digest: str
    created_at_ms: int

    @field_validator(
        "trigger_suppression_id",
        "authority_gap_audit_id",
        "event_spec_id",
        "exchange_instrument_id",
        "session_reference",
        mode="before",
    )
    @classmethod
    def _require_suppression_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("trigger suppression identity must be non-blank")
        return normalized

    @field_validator("entry_vacuum_id", "materialization_generation_id", mode="before")
    @classmethod
    def _normalize_optional_suppression_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("detector_semantic_digest")
    @classmethod
    def _require_detector_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_suppression_time(self) -> StrategyTriggerSuppression:
        if self.first_natural_trigger_at_ms <= 0 or self.created_at_ms <= 0:
            raise ValueError("trigger suppression times must be positive")
        return self


class AuthorityGapAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_gap_audit_id: str
    selection_spec_id: str
    session_start_ms: int
    gap_kind: AuthorityGapAuditKind
    source_entry_vacuum_id: str | None
    source_generation_id: str | None
    proposed_authority_outcome: AuthorityOutcome
    unauthorized_from_close_time_ms: int
    audited_through_close_time_ms: int | None
    first_eligible_close_time_ms: int | None
    audit_scope_digest: str | None
    audit_result_digest: str | None
    detector_semantic_digest: str
    state: AuthorityGapAuditState
    first_blocker: str | None
    projection_version: int

    @field_validator("authority_gap_audit_id", "selection_spec_id", mode="before")
    @classmethod
    def _require_audit_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority Gap Audit identity must be non-blank")
        return normalized

    @field_validator(
        "source_entry_vacuum_id",
        "source_generation_id",
        "first_blocker",
        mode="before",
    )
    @classmethod
    def _normalize_optional_audit_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator(
        "audit_scope_digest",
        "audit_result_digest",
        "detector_semantic_digest",
    )
    @classmethod
    def _require_optional_audit_digest(cls, value: str | None) -> str | None:
        return None if value is None else _require_sha256(value)

    @model_validator(mode="after")
    def _validate_gap_audit(self) -> AuthorityGapAudit:
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("Authority Gap Audit session must be exact 00:00 UTC")
        if (
            self.unauthorized_from_close_time_ms % INTERVAL_MS != 0
            or self.unauthorized_from_close_time_ms
            < self.session_start_ms + 5 * INTERVAL_MS
        ):
            raise ValueError("Authority Gap Audit must start at an eligible close")
        if self.projection_version <= 0:
            raise ValueError("Authority Gap Audit projection version must be positive")
        if self.state is AuthorityGapAuditState.PENDING:
            if any(
                value is not None
                for value in (
                    self.audited_through_close_time_ms,
                    self.first_eligible_close_time_ms,
                    self.audit_scope_digest,
                    self.audit_result_digest,
                    self.first_blocker,
                )
            ):
                raise ValueError("pending Authority Gap Audit cannot claim results")
            return self
        if self.state is AuthorityGapAuditState.FAILED:
            if self.first_blocker is None:
                raise ValueError("failed Authority Gap Audit requires blocker")
            return self
        if (
            self.audited_through_close_time_ms is None
            or self.first_eligible_close_time_ms is None
            or self.audit_scope_digest is None
            or self.audit_result_digest is None
            or self.first_blocker is not None
        ):
            raise ValueError("complete Authority Gap Audit requires exact result proof")
        if (
            self.audited_through_close_time_ms % INTERVAL_MS != 0
            or self.first_eligible_close_time_ms % INTERVAL_MS != 0
            or self.first_eligible_close_time_ms
            != self.audited_through_close_time_ms + INTERVAL_MS
            or self.audited_through_close_time_ms
            < self.unauthorized_from_close_time_ms
        ):
            raise ValueError("Authority Gap Audit close window is not canonical")
        return self


class SelectionControl(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    selection_spec_id: str
    selection_mode: SelectionMode
    pending_selection_mode: SelectionMode | None
    pending_effective_period_anchor_ms: int | None
    pending_authorization_id: str | None
    control_version: int
    rollback_baseline_id: str | None
    updated_at_ms: int
    selection_epoch_id: str | None = None

    @field_validator("strategy_group_id", "selection_spec_id", mode="before")
    @classmethod
    def _require_control_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection Control identity must be non-blank")
        return normalized

    @field_validator(
        "pending_authorization_id",
        "rollback_baseline_id",
        mode="before",
    )
    @classmethod
    def _normalize_optional_control_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_selection_control(self) -> SelectionControl:
        pending_values = (
            self.pending_selection_mode,
            self.pending_effective_period_anchor_ms,
            self.pending_authorization_id,
        )
        if any(value is None for value in pending_values) != all(
            value is None for value in pending_values
        ):
            raise ValueError("Selection Control pending transition shape is incomplete")
        if self.control_version <= 0 or self.updated_at_ms <= 0:
            raise ValueError("Selection Control version and time must be positive")
        cadence = DAY_MS if self.strategy_group_id == "SOR-001" else generic_selection_spec(self.strategy_group_id).cadence_hours * HOUR_MS
        if (
            self.pending_effective_period_anchor_ms is not None
            and self.pending_effective_period_anchor_ms % cadence != 0
        ):
            raise ValueError("pending Selection mode must target exact UTC period")
        if self.strategy_group_id == "SOR-001":
            if self.selection_epoch_id is not None:
                raise ValueError("SOR Control keeps frozen Session identity")
        elif self.selection_mode is SelectionMode.DYNAMIC_SELECTION or self.pending_selection_mode is SelectionMode.DYNAMIC_SELECTION:
            if not self.selection_epoch_id or not self.selection_epoch_id.strip() or self.selection_epoch_id == "sor-v0":
                raise ValueError("Generic Dynamic Control requires explicit epoch")
        elif self.selection_epoch_id is not None:
            raise ValueError("Static Generic Control cannot retain Dynamic epoch")
        return self


class SelectionSnapshotDisposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: SelectionSnapshot
    selected_members: tuple[str, ...]
    selected_member_set_digest: str

    @field_validator("selected_member_set_digest")
    @classmethod
    def _require_selected_set_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_snapshot_disposition(self) -> SelectionSnapshotDisposition:
        if (
            tuple(sorted(self.selected_members)) != self.selected_members
            or len(self.selected_members) != len(set(self.selected_members))
            or len(self.selected_members) != self.snapshot.selected_count
            or self.selected_member_set_digest
            != selected_member_set_digest(self.selected_members)
        ):
            raise ValueError("Snapshot selected-member disposition is not canonical")
        return self


class MaterializationGenerationState(StrEnum):
    PENDING = "PENDING"
    DESIRED = "DESIRED"
    DRAINING_ENTRY = "DRAINING_ENTRY"
    MATERIALIZING = "MATERIALIZING"
    STAGED = "STAGED"
    ACTIVE = "ACTIVE"
    FALLBACK_PREVIOUS = "FALLBACK_PREVIOUS"
    SUPERSEDED = "SUPERSEDED"
    ABANDONED = "ABANDONED"
    FAILED_CLOSED = "FAILED_CLOSED"


class MaterializationGenerationClaimStatus(StrEnum):
    NO_GENERATION = "NO_GENERATION"
    CLAIMED = "CLAIMED"
    LEASE_HELD = "LEASE_HELD"


class MaterializationTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    position_side: Literal["long", "short"]
    expected_member_set_digest: str
    materialization_order: int

    @field_validator("event_spec_id", mode="before")
    @classmethod
    def _require_target_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Materialization target EventSpec must be non-blank")
        return normalized

    @field_validator("expected_member_set_digest")
    @classmethod
    def _require_target_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_target_order(self) -> MaterializationTarget:
        expected = 1 if self.position_side == "long" else 2
        if self.materialization_order != expected:
            raise ValueError("Materialization target order must be LONG then SHORT")
        return self


class MaterializationGeneration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    materialization_generation_id: str
    selection_spec_id: str
    strategy_group_id: str
    strategy_version_id: str
    selection_mode: SelectionMode
    selection_snapshot_id: str | None
    rollback_baseline_id: str | None
    session_start_ms: int | None
    previous_long_universe_version_id: str
    previous_short_universe_version_id: str
    desired_member_count: int
    semantic_digest: str
    lifecycle_state: MaterializationGenerationState
    fallback_reason_code: str | None
    projection_version: int
    created_at_ms: int
    desired_at_ms: int | None

    @field_validator(
        "materialization_generation_id",
        "selection_spec_id",
        "strategy_group_id",
        "strategy_version_id",
        "previous_long_universe_version_id",
        "previous_short_universe_version_id",
        mode="before",
    )
    @classmethod
    def _require_generation_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Materialization Generation identity must be non-blank")
        return normalized

    @field_validator(
        "selection_snapshot_id",
        "rollback_baseline_id",
        "fallback_reason_code",
        mode="before",
    )
    @classmethod
    def _normalize_optional_generation_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("semantic_digest")
    @classmethod
    def _require_generation_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_generation(self) -> MaterializationGeneration:
        if self.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
            raise ValueError("DS-04 Generation requires dynamic_selection mode")
        if (
            self.previous_long_universe_version_id
            == self.previous_short_universe_version_id
        ):
            raise ValueError("Generation previous LONG/SHORT pair must be distinct")
        if (
            self.selection_snapshot_id is None
            or self.rollback_baseline_id is not None
            or self.session_start_ms is None
            or self.session_start_ms % DAY_MS != 0
            or not 1 <= self.desired_member_count <= 7
        ):
            raise ValueError("Dynamic Generation source identity is incomplete")
        if self.projection_version <= 0 or self.created_at_ms <= 0:
            raise ValueError("Generation version and creation time must be positive")
        if self.lifecycle_state is MaterializationGenerationState.PENDING:
            if self.desired_at_ms is not None:
                raise ValueError("pending Generation cannot claim desired time")
        elif (
            self.lifecycle_state is MaterializationGenerationState.DESIRED
            and (
                self.desired_at_ms is None
                or self.desired_at_ms < self.created_at_ms
            )
        ):
            raise ValueError("desired Generation requires valid desired time")
        return self


class MaterializationGenerationLeaseClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: MaterializationGenerationClaimStatus
    generation: MaterializationGeneration | None = None
    lease_owner: str | None = None
    lease_expires_at_ms: int | None = None

    @field_validator("lease_owner", mode="before")
    @classmethod
    def _normalize_claim_owner(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_claim(self) -> MaterializationGenerationLeaseClaim:
        claimed = self.status is MaterializationGenerationClaimStatus.CLAIMED
        if claimed and (
            self.generation is None
            or self.lease_owner is None
            or self.lease_expires_at_ms is None
        ):
            raise ValueError("claimed materialization lease requires exact ownership")
        if self.status is MaterializationGenerationClaimStatus.NO_GENERATION and any(
            value is not None
            for value in (
                self.generation,
                self.lease_owner,
                self.lease_expires_at_ms,
            )
        ):
            raise ValueError("absent materialization generation cannot claim lease facts")
        if self.status is MaterializationGenerationClaimStatus.LEASE_HELD and (
            self.generation is None
            or self.lease_owner is None
            or self.lease_expires_at_ms is None
        ):
            raise ValueError("held materialization lease requires current ownership")
        if self.lease_expires_at_ms is not None and self.lease_expires_at_ms <= 0:
            raise ValueError("materialization lease expiry must be positive")
        return self


class AuthorityGrantProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: AuthorityGrantProofKind
    predecessor_authority_id: str | None
    authority_gap_audit_id: str | None

    @field_validator("predecessor_authority_id", "authority_gap_audit_id", mode="before")
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_proof(self) -> AuthorityGrantProof:
        if self.kind is AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES:
            if self.predecessor_authority_id is None:
                raise ValueError("continuous proof requires predecessor Authority")
            if self.authority_gap_audit_id is not None:
                raise ValueError("continuous proof forbids Authority Gap Audit")
            return self
        if self.authority_gap_audit_id is None:
            raise ValueError("audited proof requires gap audit")
        if self.predecessor_authority_id is not None:
            raise ValueError("audited proof forbids continuous predecessor")
        return self


class UniverseAuthorityPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    long_universe_version_id: str
    short_universe_version_id: str

    @field_validator("long_universe_version_id", "short_universe_version_id", mode="before")
    @classmethod
    def _require_universe_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority requires exact LONG and SHORT Universe identities")
        return normalized

    @model_validator(mode="after")
    def _require_distinct_pair(self) -> UniverseAuthorityPair:
        if self.long_universe_version_id == self.short_universe_version_id:
            raise ValueError("Authority LONG and SHORT Universes must be distinct")
        return self


class AuthorityEventSetError(ValueError):
    """An EventUniverseSet cannot represent the required authority shape."""


class AuthorityEventGrantState(StrEnum):
    ACTIVE = "ACTIVE"
    EMPTY = "EMPTY"


class AuthorityEventRequirement(BaseModel):
    """One Event/side that a SelectionSpec requires an Authority to represent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    position_side: Literal["long", "short"]

    @field_validator("event_spec_id", mode="before")
    @classmethod
    def _require_event_spec(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority Event requirement requires EventSpec identity")
        return normalized


class AuthorityEventBinding(BaseModel):
    """One explicit ACTIVE or EMPTY grant for a required Event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    position_side: Literal["long", "short"]
    grant_state: AuthorityEventGrantState
    universe_version_id: str | None
    member_set_digest: str

    @field_validator("event_spec_id", mode="before")
    @classmethod
    def _require_event_spec(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Authority Event binding requires EventSpec identity")
        return normalized

    @field_validator("universe_version_id", mode="before")
    @classmethod
    def _normalize_universe_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("member_set_digest")
    @classmethod
    def _require_member_set_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @model_validator(mode="after")
    def _validate_binding(self) -> AuthorityEventBinding:
        empty_digest = selected_member_set_digest(())
        if self.grant_state is AuthorityEventGrantState.ACTIVE:
            if self.universe_version_id is None:
                raise ValueError("ACTIVE Event binding requires Universe identity")
            if self.member_set_digest == empty_digest:
                raise ValueError("ACTIVE Event binding forbids empty digest")
        elif (
            self.universe_version_id is not None
            or self.member_set_digest != empty_digest
        ):
            raise ValueError("EMPTY Event binding requires NULL Universe and empty digest")
        return self

    @classmethod
    def empty(
        cls,
        *,
        event_spec_id: str,
        position_side: Literal["long", "short"],
    ) -> AuthorityEventBinding:
        return cls(
            event_spec_id=event_spec_id,
            position_side=position_side,
            grant_state=AuthorityEventGrantState.EMPTY,
            universe_version_id=None,
            member_set_digest=selected_member_set_digest(()),
        )


class EventUniverseSet(BaseModel):
    """Complete ordered Event authority shape for a Generic SelectionSpec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bindings: tuple[AuthorityEventBinding, ...]

    @model_validator(mode="after")
    def _validate_event_set(self) -> EventUniverseSet:
        if not self.bindings:
            raise ValueError("EventUniverseSet requires at least one Event binding")
        identities = tuple(
            (item.event_spec_id, item.position_side) for item in self.bindings
        )
        if len(identities) != len(set(identities)):
            raise ValueError("EventUniverseSet bindings must be unique")
        states = {item.grant_state for item in self.bindings}
        if len(states) != 1:
            raise ValueError("EventUniverseSet bindings must be all ACTIVE or all EMPTY")
        return self

    @property
    def is_trading(self) -> bool:
        return self.bindings[0].grant_state is AuthorityEventGrantState.ACTIVE

    def binding_for(self, event_spec_id: str) -> AuthorityEventBinding:
        for binding in self.bindings:
            if binding.event_spec_id == event_spec_id:
                return binding
        raise KeyError(event_spec_id)


def build_event_universe_set(
    *,
    requirements: tuple[AuthorityEventRequirement, ...],
    bindings: tuple[AuthorityEventBinding, ...],
) -> EventUniverseSet:
    """Build a complete Spec Event shape without dummy or missing Event rows."""

    if not requirements:
        raise AuthorityEventSetError("Authority Event requirements must be nonempty")
    requirement_ids = tuple(
        (item.event_spec_id, item.position_side) for item in requirements
    )
    if len(requirement_ids) != len(set(requirement_ids)):
        raise AuthorityEventSetError("Authority Event requirements must be unique")
    bindings_by_identity = {
        (item.event_spec_id, item.position_side): item for item in bindings
    }
    if len(bindings_by_identity) != len(bindings):
        raise AuthorityEventSetError("Authority Event bindings must be unique")
    if set(bindings_by_identity) != set(requirement_ids):
        raise AuthorityEventSetError(
            "Authority Event bindings differ from required Spec Event shape"
        )
    try:
        return EventUniverseSet(
            bindings=tuple(bindings_by_identity[identity] for identity in requirement_ids)
        )
    except ValueError as exc:
        raise AuthorityEventSetError(str(exc)) from exc


_DYNAMIC_UNIVERSE_MEMBER_LIMITS: dict[tuple[str, str], int] = {
    ("SOR-001", "event_spec:SOR-001:SOR-LONG:v4"): 7,
    ("SOR-001", "event_spec:SOR-001:SOR-SHORT:v4"): 7,
    ("CPM-RO-001", "event_spec:CPM-RO-001:CPM-LONG:v3"): 16,
    ("MPG-001", "event_spec:MPG-001:MPG-LONG:v3"): 16,
    ("MI-001", "event_spec:MI-001:MI-LONG:v3"): 16,
    ("BRF2-001", "event_spec:BRF2-001:BRF2-SHORT:v3"): 16,
}


class TrustedUniverseMembershipPolicy(BaseModel):
    """Trusted source/Event policy; callers never supply a numeric limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: StrategyUniverseSourceKind
    strategy_group_id: str
    event_spec_id: str

    @field_validator("strategy_group_id", "event_spec_id", mode="before")
    @classmethod
    def _require_policy_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Universe membership policy identity must be non-blank")
        return normalized

    @property
    def member_limit(self) -> int:
        if self.source_kind in {
            StrategyUniverseSourceKind.MANUAL,
            StrategyUniverseSourceKind.STATIC_BASELINE,
        }:
            return 10
        limit = _DYNAMIC_UNIVERSE_MEMBER_LIMITS.get(
            (self.strategy_group_id, self.event_spec_id)
        )
        if limit is None:
            raise AuthorityEventSetError("Dynamic Universe policy is not installed")
        return limit

    def require_member_count(self, member_count: int) -> None:
        if not 1 <= member_count <= self.member_limit:
            raise AuthorityEventSetError(
                f"Universe member limit is {self.member_limit}, got {member_count}"
            )


def trusted_universe_membership_policy(
    *,
    source_kind: StrategyUniverseSourceKind,
    strategy_group_id: str,
    event_spec_id: str,
) -> TrustedUniverseMembershipPolicy:
    """Return the fixed trusted policy for a source/Event authority tuple."""

    return TrustedUniverseMembershipPolicy(
        source_kind=source_kind,
        strategy_group_id=strategy_group_id,
        event_spec_id=event_spec_id,
    )


class GenericSelectionAuthority(BaseModel):
    """Normal/empty Generic authority contract; persistence remains the shared chain.

    Recovery and continuity must supply their own typed proofs, not masquerade
    as normal ACTIVE_NEW/NO_CHANGE grants.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_authority_id: str
    selection_spec_id: str
    strategy_group_id: str
    selection_epoch_id: str
    selection_mode: Literal["dynamic_selection"] = "dynamic_selection"
    selection_snapshot_id: str
    materialization_generation_id: str | None = None
    authority_sequence: int = Field(gt=0)
    owner_control_version: int = Field(gt=0)
    selection_control_version: int = Field(gt=0)
    activation_authorization_id: str | None = None
    period: GenericSelectionPeriod
    authority_outcome: Literal["ACTIVE_NEW", "NO_CHANGE", "VALID_EMPTY"]
    event_binding: AuthorityEventBinding
    current_close_proof: CurrentFinalCloseGrantProof | None
    membership_freshness: DynamicMembershipFreshness | None
    comparison_universe_id: str | None = None
    comparison_transition_revision: int | None = None
    effective_from_ms: int
    created_at_ms: int

    @field_validator("selection_authority_id", "selection_spec_id", "strategy_group_id", "selection_epoch_id", "selection_snapshot_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not value.strip() or len(value)>160:
            raise ValueError("Generic Authority requires bounded identity")
        return value.strip()

    @field_validator("materialization_generation_id", "comparison_universe_id", "activation_authorization_id")
    @classmethod
    def _optional_identity(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip() or len(value)>160):
            raise ValueError("Generic Authority optional identity is invalid")
        return value

    @property
    def blocks_new_entry(self) -> bool:
        return self.authority_outcome == "VALID_EMPTY"

    @property
    def allows_existing_ticket_lifecycle(self) -> bool:
        return True

    @property
    def rewrites_existing_lineage(self) -> bool:
        return False

    @property
    def expires_at_ms(self) -> int:
        return self.period.period_expires_at_ms

    @property
    def first_eligible_close_time_ms(self) -> int | None:
        return None if self.current_close_proof is None else self.current_close_proof.current_final_close_time_ms

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def _validate_generic_authority(self) -> GenericSelectionAuthority:
        spec = generic_selection_spec(self.strategy_group_id)
        if self.selection_spec_id != spec.selection_spec_id or self.period.cadence_hours != spec.cadence_hours:
            raise ValueError("Generic Authority Spec/period differs")
        if (self.event_binding.event_spec_id,self.event_binding.position_side) != (spec.event_spec_id,spec.position_side):
            raise ValueError("Generic Authority Event binding differs")
        if not self.period.scheduled_effective_at_ms <= self.effective_from_ms < self.period.period_expires_at_ms or self.created_at_ms != self.effective_from_ms:
            raise ValueError("Generic Authority must freeze its actual commit boundary")
        if (self.comparison_universe_id is None) != (self.comparison_transition_revision is None):
            raise ValueError("Generic Authority comparison identity is incomplete")
        comparative = self.strategy_group_id in {"MPG-001", "MI-001"}
        if not comparative and self.comparison_universe_id is not None:
            raise ValueError("non-comparative Authority forbids comparison identity")
        if self.comparison_transition_revision is not None and self.comparison_transition_revision < 0:
            raise ValueError("Generic comparison revision is invalid")
        if self.blocks_new_entry:
            if self.materialization_generation_id is not None:
                raise ValueError("VALID_EMPTY forbids a materialization Generation")
            if self.event_binding.grant_state is not AuthorityEventGrantState.EMPTY or self.current_close_proof is not None or self.membership_freshness is not None:
                raise ValueError("VALID_EMPTY forbids positive trading proof")
            return self
        if self.event_binding.grant_state is not AuthorityEventGrantState.ACTIVE:
            raise ValueError("normal Generic Authority requires ACTIVE Event")
        if self.authority_outcome == "NO_CHANGE" and self.materialization_generation_id is not None:
            raise ValueError("NO_CHANGE forbids a materialization Generation")
        if self.authority_outcome == "ACTIVE_NEW" and (
            self.materialization_generation_id is None or not self.materialization_generation_id.strip()
            or len(self.materialization_generation_id)>160
        ):
            raise ValueError("ACTIVE_NEW requires its materialization Generation")
        if comparative and (self.comparison_universe_id != "comparison:"+_semantic_digest({"exchange_instrument_ids":spec.candidate_ids})[7:]
            or self.comparison_transition_revision is None or self.comparison_transition_revision <= 0):
            raise ValueError("Generic trading comparison requires fixed24 and positive revision")
        proof = self.current_close_proof
        fresh = self.membership_freshness
        if proof is None or proof.period != self.period or proof.selection_snapshot_id != self.selection_snapshot_id or proof.authority_granted_at_ms != self.effective_from_ms:
            raise ValueError("Generic Authority current-close proof differs")
        covered_members = tuple(cursor.exchange_instrument_id for cursor in proof.observation_cursors)
        if selected_member_set_digest(covered_members) != self.event_binding.member_set_digest or (
            not set(covered_members).issubset(spec.candidate_ids) or len(covered_members)>spec.retain_rank):
            raise ValueError("Generic Authority cursor coverage differs from selected members")
        if any(cursor.episode_domain_key != build_episode_domain_key(event_spec_id=spec.event_spec_id,
            exchange_instrument_id=cursor.exchange_instrument_id,position_side=spec.position_side) for cursor in proof.observation_cursors):
            raise ValueError("Generic Authority cursor Event identity differs")
        if fresh is None or fresh.state is not DynamicMembershipState.ACTIVE or fresh.consecutive_missed_periods != 0 or (
            fresh.source_snapshot_id != self.selection_snapshot_id
            or fresh.source_member_set_digest != self.event_binding.member_set_digest
            or fresh.source_snapshot_cutoff_at_ms != self.period.feature_cutoff_at_ms
            or fresh.source_snapshot_effective_at_ms != self.period.scheduled_effective_at_ms
            or fresh.cadence_hours != self.period.cadence_hours
        ):
            raise ValueError("Generic Authority source freshness differs")
        return self


def generic_authority_entry_rejection(*, authority: GenericSelectionAuthority,
    selection_spec_id: str, selection_epoch_id: str | None, selection_control_version: int,
    owner_control_version: int, event_spec_id: str, position_side: str, universe_version_id: str,
    birth_selection_authority_id: str | None, allow_current_as_birth: bool,
    observed_close_time_ms: int, now_ms: int) -> str | None:
    """Pure exact-birth normal grant check; callers also prove current DB facts."""
    authority = GenericSelectionAuthority.model_validate(authority.model_dump())
    if (authority.selection_spec_id != selection_spec_id or authority.selection_epoch_id != selection_epoch_id
        or authority.selection_control_version != selection_control_version or authority.owner_control_version != owner_control_version):
        return "selection_authority_control_changed"
    if not authority.effective_from_ms <= now_ms < authority.expires_at_ms:
        return "selection_authority_missing_or_expired"
    if authority.blocks_new_entry:
        return "selection_valid_empty"
    binding = authority.event_binding
    if (binding.event_spec_id,binding.position_side,binding.universe_version_id) != (event_spec_id,position_side,universe_version_id):
        return "selection_authority_universe_changed"
    if birth_selection_authority_id != authority.selection_authority_id and not (
        birth_selection_authority_id is None and allow_current_as_birth):
        return "selection_birth_authority_changed"
    if (authority.first_eligible_close_time_ms is None
        or observed_close_time_ms % HOUR_MS != 0
        or observed_close_time_ms < authority.first_eligible_close_time_ms
        or observed_close_time_ms != now_ms//HOUR_MS*HOUR_MS
        or observed_close_time_ms >= authority.expires_at_ms):
        return "selection_authority_close_ineligible"
    if authority.membership_freshness is None or not authority.membership_freshness.allows_new_entry_at(now_ms):
        return "selection_membership_stale"
    return None


class GenericRecoveryGrantProof(BaseModel):
    """Recovery evidence only, not a current pointer or a production grant.

    PostgreSQL must bind these references to actual current Owner/Control,
    Vacuum, previous Universe and source Authority before accepting a grant.
    Static form is the failed first Dynamic activation transition only.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    proof_kind: Literal["FUTURE_CLOSE_REBASE_REQUIRED"] = "FUTURE_CLOSE_REBASE_REQUIRED"
    authority_outcome: Literal["FALLBACK_PREVIOUS", "ACTIVE_NEW"] = "FALLBACK_PREVIOUS"
    target_snapshot_id: str | None = None
    selection_spec_id: str
    strategy_group_id: str
    selection_epoch_id: str
    selection_mode: Literal["dynamic_selection", "static_baseline"]
    source_entry_vacuum_id: str
    vacuum_fenced_at_ms: int = Field(gt=0)
    materialization_generation_id: str | None
    source_selection_authority_id: str | None
    failed_activation_authorization_id: str | None
    owner_control_version: int = Field(gt=0)
    selection_control_version: int = Field(gt=0)
    event_binding: AuthorityEventBinding
    recovery_close_plan: HourlyRecoveryClosePlan
    membership_freshness: DynamicMembershipFreshness | None
    comparison_universe_id: str | None
    comparison_transition_revision: int | None
    observation_cursors: tuple[LockedObservationCursor, ...]
    committed_at_ms: int = Field(gt=0)
    episode_rebase_required: Literal[True] = True

    @field_validator("selection_spec_id", "strategy_group_id", "selection_epoch_id", "source_entry_vacuum_id", "target_snapshot_id",
        "materialization_generation_id", "source_selection_authority_id", "failed_activation_authorization_id", "comparison_universe_id")
    @classmethod
    def _canonical_reference(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip() or len(value)>160):
            raise ValueError("recovery proof requires canonical bounded references")
        return value

    @property
    def first_eligible_close_time_ms(self) -> int:
        first = self.recovery_close_plan.first_eligible_close_time_ms
        if first is None:
            raise ValueError("NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY is not a grant")
        return first

    @property
    def effective_from_ms(self) -> int:
        return max(self.committed_at_ms,self.recovery_close_plan.period.scheduled_effective_at_ms)

    @property
    def expires_at_ms(self) -> int:
        period_end = self.recovery_close_plan.period.period_expires_at_ms
        return period_end if self.membership_freshness is None else min(period_end,self.membership_freshness.membership_valid_until_ms)

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(self.model_dump(mode="json"))

    @model_validator(mode="after")
    def _validate_recovery_proof(self) -> GenericRecoveryGrantProof:
        spec = generic_selection_spec(self.strategy_group_id)
        plan = self.recovery_close_plan
        if self.selection_spec_id != spec.selection_spec_id or self.selection_epoch_id == "sor-v0" or plan.period.cadence_hours != spec.cadence_hours:
            raise ValueError("recovery Spec, epoch or cadence differs")
        require_hourly_recovery_commit(plan,committed_at_ms=self.committed_at_ms)
        if self.vacuum_fenced_at_ms > plan.evaluated_at_ms:
            raise ValueError("recovery cannot precede its Vacuum fence")
        if plan.reason in {"MATERIALIZATION_FAILURE","MATERIALIZATION_TIMEOUT"} and self.materialization_generation_id is None:
            raise ValueError("materialization recovery requires its Generation")
        binding = self.event_binding
        if binding.grant_state is not AuthorityEventGrantState.ACTIVE or (
            binding.event_spec_id,binding.position_side)!=(spec.event_spec_id,spec.position_side):
            raise ValueError("recovery requires the exact previous active Event")
        members = tuple(cursor.exchange_instrument_id for cursor in self.observation_cursors)
        static = self.selection_mode == "static_baseline"
        if not 1<=len(members)<=(10 if static else spec.retain_rank) or tuple(sorted(set(members)))!=members or (
            selected_member_set_digest(members)!=binding.member_set_digest or (not static and not set(members).issubset(spec.candidate_ids))):
            raise ValueError("recovery member coverage differs")
        for cursor in self.observation_cursors:
            LockedObservationCursor.model_validate(cursor.model_dump())
            if cursor.episode_domain_key!=build_episode_domain_key(event_spec_id=spec.event_spec_id,
                exchange_instrument_id=cursor.exchange_instrument_id,position_side=spec.position_side) or (
                cursor.last_observed_at_ms is not None and cursor.last_observed_at_ms>self.committed_at_ms):
                raise ValueError("recovery cursor scope or time differs")
        if self.authority_outcome == "ACTIVE_NEW":
            fresh = self.membership_freshness
            if static or self.target_snapshot_id is None or fresh is None or self.source_selection_authority_id is None or (
                self.materialization_generation_id is None or self.failed_activation_authorization_id is not None):
                raise ValueError("recovered activation requires exact Dynamic target and source Authority")
            fresh = DynamicMembershipFreshness.model_validate(fresh.model_dump())
            missed = (plan.period.scheduled_effective_at_ms-fresh.source_snapshot_effective_at_ms)//(spec.cadence_hours*HOUR_MS)
            if self.target_snapshot_id!=fresh.source_snapshot_id or fresh.source_member_set_digest!=binding.member_set_digest or (
                fresh.cadence_hours!=spec.cadence_hours or fresh.source_snapshot_effective_at_ms>self.committed_at_ms
                or missed not in {0,1} or fresh.consecutive_missed_periods!=missed
                or fresh.state is not (DynamicMembershipState.ACTIVE if missed==0 else DynamicMembershipState.GRACE)
                or not fresh.allows_new_entry_at(self.first_eligible_close_time_ms)):
                raise ValueError("recovered activation Snapshot freshness differs")
        elif static:
            if self.target_snapshot_id is not None:
                raise ValueError("Static fallback cannot claim a new target Snapshot")
            if self.membership_freshness is not None or self.source_selection_authority_id is not None or (
                self.failed_activation_authorization_id is None or self.materialization_generation_id is None):
                raise ValueError("first Static fallback requires failed activation provenance, not Dynamic freshness")
        else:
            if self.target_snapshot_id is not None:
                raise ValueError("fallback cannot claim a new target Snapshot")
            fresh = self.membership_freshness
            if fresh is None or self.source_selection_authority_id is None or self.failed_activation_authorization_id is not None:
                raise ValueError("Dynamic recovery requires existing source Authority and freshness")
            fresh = DynamicMembershipFreshness.model_validate(fresh.model_dump())
            missed = (plan.period.scheduled_effective_at_ms-fresh.source_snapshot_effective_at_ms)//(spec.cadence_hours*HOUR_MS)
            expected_state = DynamicMembershipState.ACTIVE if missed==0 else DynamicMembershipState.GRACE
            if fresh.source_member_set_digest!=binding.member_set_digest or fresh.cadence_hours!=spec.cadence_hours or (
                fresh.source_snapshot_effective_at_ms>self.committed_at_ms or missed not in {0,1}
                or fresh.consecutive_missed_periods!=missed or fresh.state is not expected_state
                or not fresh.allows_new_entry_at(self.first_eligible_close_time_ms)):
                raise ValueError("recovery freshness cannot refresh or exceed the original deadline")
        if not self.effective_from_ms<=self.first_eligible_close_time_ms<self.expires_at_ms:
            raise ValueError("recovery deadline leaves no eligible close")
        if self.strategy_group_id in {"MPG-001","MI-001"}:
            expected = _semantic_digest({"exchange_instrument_ids":members if static else spec.candidate_ids})
            if self.comparison_universe_id!="comparison:"+expected[7:] or self.comparison_transition_revision is None or self.comparison_transition_revision<(0 if static else 1):
                raise ValueError("recovery comparison must preserve the previous semantic identity")
        elif self.comparison_universe_id is not None or self.comparison_transition_revision is not None:
            raise ValueError("non-comparative recovery forbids comparison identity")
        return self


class GenericRecoveryAuthority(BaseModel):
    """Prepared immutable recovery identity; only a committed current row grants.

    Kept distinct from normal/empty authority so recovery can never acquire a
    current-close grant merely through normal model decoding.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    selection_authority_id: str
    authority_sequence: int = Field(gt=0)
    authority_outcome: Literal["FALLBACK_PREVIOUS", "ACTIVE_NEW"] = "FALLBACK_PREVIOUS"
    recovery_proof: GenericRecoveryGrantProof

    @classmethod
    def build(cls, *, proof: GenericRecoveryGrantProof, authority_sequence: int) -> GenericRecoveryAuthority:
        proof = GenericRecoveryGrantProof.model_validate(proof.model_dump())
        return cls(selection_authority_id=cls._identity(proof,authority_sequence),
            authority_sequence=authority_sequence,authority_outcome=proof.authority_outcome,recovery_proof=proof)

    @staticmethod
    def _identity(proof: GenericRecoveryGrantProof, sequence: int) -> str:
        return "authority:recovery:"+_semantic_digest({"proof_digest":proof.semantic_digest,"authority_sequence":sequence})[7:]

    @model_validator(mode="after")
    def _validate_identity(self) -> GenericRecoveryAuthority:
        proof = GenericRecoveryGrantProof.model_validate(self.recovery_proof.model_dump())
        if self.selection_authority_id!=self._identity(proof,self.authority_sequence) or self.authority_outcome!=proof.authority_outcome:
            raise ValueError("Recovery Authority identity differs from its frozen proof and sequence")
        return self

    @property
    def selection_spec_id(self) -> str:
        return self.recovery_proof.selection_spec_id

    @property
    def strategy_group_id(self) -> str:
        return self.recovery_proof.strategy_group_id

    @property
    def selection_epoch_id(self) -> str:
        return self.recovery_proof.selection_epoch_id

    @property
    def selection_control_version(self) -> int:
        return self.recovery_proof.selection_control_version

    @property
    def owner_control_version(self) -> int:
        return self.recovery_proof.owner_control_version

    @property
    def period(self) -> GenericSelectionPeriod:
        return self.recovery_proof.recovery_close_plan.period

    @property
    def materialization_generation_id(self) -> str | None:
        return self.recovery_proof.materialization_generation_id

    @property
    def comparison_universe_id(self) -> str | None:
        return self.recovery_proof.comparison_universe_id

    @property
    def comparison_transition_revision(self) -> int | None:
        return self.recovery_proof.comparison_transition_revision

    @property
    def blocks_new_entry(self) -> bool:
        return False

    @property
    def selection_mode(self) -> Literal["dynamic_selection", "static_baseline"]:
        return self.recovery_proof.selection_mode

    @property
    def selection_snapshot_id(self) -> str | None:
        if self.recovery_proof.authority_outcome == "ACTIVE_NEW":
            return self.recovery_proof.target_snapshot_id
        fresh = self.recovery_proof.membership_freshness
        return None if fresh is None else fresh.source_snapshot_id

    @property
    def event_binding(self) -> AuthorityEventBinding:
        return self.recovery_proof.event_binding

    @property
    def created_at_ms(self) -> int:
        return self.recovery_proof.committed_at_ms

    @property
    def effective_from_ms(self) -> int:
        return self.recovery_proof.effective_from_ms

    @property
    def first_eligible_close_time_ms(self) -> int:
        return self.recovery_proof.first_eligible_close_time_ms

    @property
    def expires_at_ms(self) -> int:
        return self.recovery_proof.expires_at_ms

    @property
    def allows_existing_ticket_lifecycle(self) -> bool:
        return True

    @property
    def rewrites_existing_lineage(self) -> bool:
        return False

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(self.model_dump(mode="json"))


def generic_recovery_entry_rejection(*, authority: GenericRecoveryAuthority,
    selection_spec_id: str, selection_epoch_id: str | None, selection_mode: str,
    selection_control_version: int, owner_control_version: int,
    event_spec_id: str, position_side: str, universe_version_id: str, exchange_instrument_id: str,
    birth_selection_authority_id: str | None, allow_current_as_birth: bool,
    observed_close_time_ms: int, now_ms: int) -> str | None:
    """Exact recovery eligibility only; caller must also enforce rebase and DB facts."""
    authority = GenericRecoveryAuthority.model_validate(authority.model_dump())
    proof = authority.recovery_proof
    # Failed first activation clears the pending Dynamic epoch on Control while
    # retaining that attempted epoch in immutable transition evidence.
    expected_epoch = None if proof.selection_mode=="static_baseline" else proof.selection_epoch_id
    if (selection_spec_id!=proof.selection_spec_id or selection_mode!=proof.selection_mode
        or selection_epoch_id!=expected_epoch or selection_control_version!=proof.selection_control_version
        or owner_control_version!=proof.owner_control_version):
        return "selection_recovery_control_changed"
    binding = proof.event_binding
    if (event_spec_id,position_side,universe_version_id)!=(binding.event_spec_id,binding.position_side,binding.universe_version_id) or (
        exchange_instrument_id not in {cursor.exchange_instrument_id for cursor in proof.observation_cursors}):
        return "selection_recovery_scope_changed"
    if birth_selection_authority_id!=authority.selection_authority_id and not (birth_selection_authority_id is None and allow_current_as_birth):
        return "selection_recovery_birth_changed"
    if not authority.effective_from_ms<=now_ms<authority.expires_at_ms:
        return "selection_recovery_not_effective"
    if observed_close_time_ms%HOUR_MS or not authority.first_eligible_close_time_ms<=observed_close_time_ms<=now_ms or observed_close_time_ms>=authority.expires_at_ms:
        return "selection_recovery_close_ineligible"
    if proof.membership_freshness is not None and not proof.membership_freshness.allows_new_entry_at(now_ms):
        return "selection_membership_stale"
    return None


class CurrentGenericSelectionAuthority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authority: GenericSelectionAuthority | GenericRecoveryAuthority
    projection_version: int = Field(gt=0)


class SelectionSessionAuthority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_authority_id: str
    selection_spec_id: str
    session_start_ms: int
    decision_boundary_ms: int
    authority_sequence: int
    selection_mode: SelectionMode
    selection_snapshot_id: str | None
    continued_from_selection_authority_id: str | None
    continuity_source_kind: ContinuitySourceKind
    authority_gap_audit_id: str | None
    materialization_generation_id: str | None
    owner_control_version: int
    authority_outcome: AuthorityOutcome
    authorized_pair: UniverseAuthorityPair | None
    grant_proof: AuthorityGrantProof | None
    effective_from_ms: int
    first_eligible_close_time_ms: int | None
    expires_at_ms: int
    reason_code: str
    created_at_ms: int

    @field_validator("selection_authority_id", "selection_spec_id", "reason_code", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Selection Authority identity and reason must be non-blank")
        return normalized

    @field_validator(
        "selection_snapshot_id",
        "continued_from_selection_authority_id",
        "authority_gap_audit_id",
        "materialization_generation_id",
        mode="before",
    )
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @property
    def blocks_new_entry(self) -> bool:
        return self.authority_outcome in {
            AuthorityOutcome.VALID_EMPTY,
            AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED,
        }

    @property
    def allows_existing_ticket_lifecycle(self) -> bool:
        return True

    @property
    def rewrites_existing_lineage(self) -> bool:
        return False

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(
            self.model_dump(
                mode="json",
            )
        )

    @model_validator(mode="after")
    def _validate_authority(self) -> SelectionSessionAuthority:
        self._validate_period_and_time()
        if self.authority_sequence <= 0 or self.owner_control_version <= 0:
            raise ValueError("Authority sequence and Owner control version must be positive")
        self._validate_outcome_shape()
        if self.authority_outcome in _TRADING_OUTCOMES:
            self._validate_trading_grant()
        else:
            self._validate_non_trading_outcome()
        return self

    def _validate_period_and_time(self) -> None:
        if self.session_start_ms <= 0 or self.session_start_ms % DAY_MS != 0:
            raise ValueError("Authority session identity must be exact 00:00 UTC")
        if self.decision_boundary_ms != self.session_start_ms + HOUR_MS:
            raise ValueError("Authority period must start at the 01:00 UTC decision boundary")
        if self.expires_at_ms != self.session_start_ms + DAY_MS + HOUR_MS:
            raise ValueError("Authority must expire at the next decision boundary")
        if not self.decision_boundary_ms <= self.effective_from_ms < self.expires_at_ms:
            raise ValueError("Authority effective time cannot precede its decision boundary")
        if not self.effective_from_ms <= self.created_at_ms < self.expires_at_ms:
            raise ValueError("Authority creation time must be within its effective period")

    def _validate_trading_grant(self) -> None:
        if self.authorized_pair is None:
            raise ValueError("trading Authority requires exact LONG and SHORT Universe pair")
        if self.grant_proof is None:
            raise ValueError("trading Authority requires one grant proof")
        if self.first_eligible_close_time_ms is None:
            raise ValueError("trading Authority requires first eligible close")
        if self.first_eligible_close_time_ms % INTERVAL_MS != 0:
            raise ValueError("first eligible close must be canonical 15m close")
        if self.first_eligible_close_time_ms < self.session_start_ms + 5 * INTERVAL_MS:
            raise ValueError("first eligible close cannot precede SOR eligibility")
        if not self.created_at_ms < self.first_eligible_close_time_ms < self.expires_at_ms:
            raise ValueError("first eligible close must be a future close within Authority period")
        if self.grant_proof.kind is AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES:
            if self.authority_gap_audit_id is not None:
                raise ValueError("continuous Authority cannot reference a Gap Audit")
            if self.continuity_source_kind is ContinuitySourceKind.SELECTION_AUTHORITY:
                if (
                    self.grant_proof.predecessor_authority_id
                    != self.continued_from_selection_authority_id
                ):
                    raise ValueError(
                        "continuous Authority proof must match predecessor lineage"
                    )
            elif self.continuity_source_kind is ContinuitySourceKind.STATIC_BASELINE:
                if self.continued_from_selection_authority_id is not None:
                    raise ValueError(
                        "Static continuity cannot invent Selection Authority predecessor"
                    )
            else:
                raise ValueError("continuous Authority proof must match predecessor lineage")
        else:
            if (
                self.authority_gap_audit_id is None
                or self.grant_proof.authority_gap_audit_id
                != self.authority_gap_audit_id
            ):
                raise ValueError("audited Authority proof must match exact Gap Audit")
            if (
                self.authority_outcome is not AuthorityOutcome.FALLBACK_PREVIOUS
                or self.continuity_source_kind is not ContinuitySourceKind.STATIC_BASELINE
            ) and self.continuity_source_kind is not ContinuitySourceKind.AUTHORITY_GAP_AUDIT:
                raise ValueError("audited Authority requires AUTHORITY_GAP_AUDIT source")

    def _validate_non_trading_outcome(self) -> None:
        if self.authorized_pair is not None:
            raise ValueError("non-trading outcome forbids Universe pair")
        if self.grant_proof is not None:
            raise ValueError("non-trading outcome forbids grant proof")
        if self.first_eligible_close_time_ms is not None:
            raise ValueError("non-trading outcome forbids first eligible close")
        if self.continuity_source_kind is not ContinuitySourceKind.NONE:
            raise ValueError("non-trading outcome requires NONE continuity source")
        if self.authority_gap_audit_id is not None:
            raise ValueError("non-trading outcome cannot grant through Gap Audit")

    def _validate_outcome_shape(self) -> None:
        if self.authority_outcome is AuthorityOutcome.PRE_FENCE_CONTINUITY:
            if self.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
                raise ValueError("PRE_FENCE_CONTINUITY requires dynamic_selection mode")
            if self.materialization_generation_id is not None:
                raise ValueError("PRE_FENCE_CONTINUITY cannot own a Generation")
            if self.continuity_source_kind not in {
                ContinuitySourceKind.SELECTION_AUTHORITY,
                ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
            }:
                raise ValueError("PRE_FENCE_CONTINUITY requires Dynamic continuity lineage")
        elif self.authority_outcome is AuthorityOutcome.ACTIVE_NEW:
            if self.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
                raise ValueError("ACTIVE_NEW requires dynamic_selection mode")
            if self.selection_snapshot_id is None or self.materialization_generation_id is None:
                raise ValueError("ACTIVE_NEW requires Snapshot and Generation")
            if (
                self.grant_proof is None
                or self.grant_proof.kind is not AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP
            ):
                raise ValueError("ACTIVE_NEW requires audited post-Vacuum grant proof")
        elif self.authority_outcome is AuthorityOutcome.NO_CHANGE:
            if self.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
                raise ValueError("NO_CHANGE requires dynamic_selection mode")
            if self.selection_snapshot_id is None:
                raise ValueError("NO_CHANGE requires current Selection Snapshot")
            if self.materialization_generation_id is not None:
                raise ValueError("NO_CHANGE cannot own a new Generation")
        elif self.authority_outcome is AuthorityOutcome.FALLBACK_PREVIOUS:
            if (
                self.selection_snapshot_id is None
                or self.materialization_generation_id is None
                or self.authority_gap_audit_id is None
                or self.grant_proof is None
                or self.grant_proof.kind is not AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP
            ):
                raise ValueError("fallback requires generation and audited gap proof")
            if self.continuity_source_kind is ContinuitySourceKind.STATIC_BASELINE:
                if self.selection_mode is not SelectionMode.STATIC_BASELINE:
                    raise ValueError("first Static fallback must keep static_baseline mode")
                if self.continued_from_selection_authority_id is not None:
                    raise ValueError("first Static fallback cannot invent Dynamic predecessor")
            elif (
                self.selection_mode is not SelectionMode.DYNAMIC_SELECTION
                or self.continuity_source_kind is not ContinuitySourceKind.AUTHORITY_GAP_AUDIT
            ):
                raise ValueError("Dynamic fallback requires audited Dynamic authority")
        elif self.authority_outcome is AuthorityOutcome.VALID_EMPTY:
            if self.selection_mode is not SelectionMode.DYNAMIC_SELECTION:
                raise ValueError("VALID_EMPTY requires dynamic_selection mode")
            if self.selection_snapshot_id is None:
                raise ValueError("VALID_EMPTY requires exact zero-member Snapshot")
            if self.materialization_generation_id is not None:
                raise ValueError("VALID_EMPTY cannot create a Generation")
        elif self.authority_outcome is AuthorityOutcome.OWNER_PAUSED_NOT_MATERIALIZED:
            if self.materialization_generation_id is not None:
                raise ValueError("Owner Pause cannot materialize a Generation")


class CurrentSelectionAuthority(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authority: SelectionSessionAuthority
    projection_version: int

    @field_validator("projection_version")
    @classmethod
    def _require_current_projection_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("current Selection Authority version must be positive")
        return value


_TRADING_OUTCOMES = frozenset(
    {
        AuthorityOutcome.PRE_FENCE_CONTINUITY,
        AuthorityOutcome.ACTIVE_NEW,
        AuthorityOutcome.NO_CHANGE,
        AuthorityOutcome.FALLBACK_PREVIOUS,
    }
)


def authority_successor_is_compatible(
    *,
    birth: SelectionSessionAuthority,
    successor: SelectionSessionAuthority,
    vacuum_opened: bool,
    owner_control_continuous: bool,
    global_policy_continuous: bool,
    eligible_close_coverage_continuous: bool,
) -> bool:
    """Return whether a Signal birth Authority may use one continuity successor."""

    if (
        vacuum_opened
        or not owner_control_continuous
        or not global_policy_continuous
        or not eligible_close_coverage_continuous
    ):
        return False
    if birth.authority_outcome is not AuthorityOutcome.PRE_FENCE_CONTINUITY:
        return False
    if successor.authority_outcome not in {
        AuthorityOutcome.PRE_FENCE_CONTINUITY,
        AuthorityOutcome.NO_CHANGE,
    }:
        return False
    return not (
        birth.selection_spec_id != successor.selection_spec_id
        or birth.session_start_ms != successor.session_start_ms
        or birth.decision_boundary_ms != successor.decision_boundary_ms
        or birth.expires_at_ms != successor.expires_at_ms
        or birth.selection_mode is not successor.selection_mode
        or birth.owner_control_version != successor.owner_control_version
        or birth.authorized_pair != successor.authorized_pair
        or successor.authority_sequence != birth.authority_sequence + 1
        or successor.continued_from_selection_authority_id
        != birth.selection_authority_id
        or successor.grant_proof is None
        or successor.grant_proof.kind
        is not AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES
        or successor.grant_proof.predecessor_authority_id
        != birth.selection_authority_id
        or successor.authority_gap_audit_id is not None
        or successor.first_eligible_close_time_ms is None
        or birth.first_eligible_close_time_ms is None
        or successor.first_eligible_close_time_ms
        < birth.first_eligible_close_time_ms
    )


def selection_authority_allows_new_entry(
    authority: SelectionSessionAuthority,
    *,
    now_ms: int,
    observed_close_time_ms: int,
    scoped_vacuum_open: bool,
) -> bool:
    """Apply the time-bounded grant and higher-priority negative Vacuum fence."""

    return bool(
        authority.authority_outcome in _TRADING_OUTCOMES
        and not scoped_vacuum_open
        and authority.effective_from_ms <= now_ms < authority.expires_at_ms
        and authority.first_eligible_close_time_ms is not None
        and observed_close_time_ms >= authority.first_eligible_close_time_ms
    )


def _semantic_digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def selected_member_set_digest(members: tuple[str, ...]) -> str:
    canonical = tuple(sorted(members))
    if canonical != members or len(canonical) != len(set(canonical)):
        raise ValueError("selected member set must be canonical and unique")
    return _semantic_digest({"selected_exchange_instrument_ids": canonical})


def _require_sha256(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized.startswith("sha256:") or len(normalized) != 71:
        raise ValueError("digest must be canonical sha256")
    try:
        int(normalized[7:], 16)
    except ValueError as exc:
        raise ValueError("digest must be canonical sha256") from exc
    if normalized != normalized.lower():
        raise ValueError("digest must be canonical sha256")
    return normalized


def next_canonical_eligible_close(*, session_start_ms: int, now_ms: int) -> int:
    """Return the first canonical SOR close strictly after the current instant."""

    if session_start_ms <= 0 or session_start_ms % DAY_MS != 0:
        raise ValueError("SOR session must be exact 00:00 UTC")
    first_close = session_start_ms + 5 * INTERVAL_MS
    if now_ms < first_close:
        return first_close
    intervals = (now_ms - session_start_ms) // INTERVAL_MS + 1
    return session_start_ms + intervals * INTERVAL_MS


def build_pending_authority_gap_audit(
    *,
    authority_gap_audit_id: str,
    selection_spec_id: str,
    session_start_ms: int,
    gap_kind: AuthorityGapAuditKind,
    proposed_authority_outcome: AuthorityOutcome | str,
    unauthorized_from_close_time_ms: int,
    detector_semantic_digest: str,
    created_at_ms: int,
    source_entry_vacuum_id: str | None = None,
    source_generation_id: str | None = None,
) -> AuthorityGapAudit:
    if created_at_ms <= 0:
        raise ValueError("Authority Gap Audit creation time must be positive")
    return AuthorityGapAudit(
        authority_gap_audit_id=authority_gap_audit_id,
        selection_spec_id=selection_spec_id,
        session_start_ms=session_start_ms,
        gap_kind=gap_kind,
        source_entry_vacuum_id=source_entry_vacuum_id,
        source_generation_id=source_generation_id,
        proposed_authority_outcome=AuthorityOutcome(proposed_authority_outcome),
        unauthorized_from_close_time_ms=unauthorized_from_close_time_ms,
        audited_through_close_time_ms=None,
        first_eligible_close_time_ms=None,
        audit_scope_digest=None,
        audit_result_digest=None,
        detector_semantic_digest=detector_semantic_digest,
        state=AuthorityGapAuditState.PENDING,
        first_blocker=None,
        projection_version=1,
    )


def complete_authority_gap_audit(
    audit: AuthorityGapAudit,
    *,
    audited_through_close_time_ms: int,
    scopes: tuple[AuthorityGapScope, ...],
    results: tuple[AuthorityGapScopeResult, ...],
) -> AuthorityGapAudit:
    if audit.state is not AuthorityGapAuditState.PENDING:
        raise ValueError("only pending Authority Gap Audit may complete")
    canonical_scopes = tuple(
        sorted(scopes, key=lambda item: (item.event_spec_id, item.exchange_instrument_id))
    )
    canonical_results = tuple(
        sorted(
            results,
            key=lambda item: (
                item.scope.event_spec_id,
                item.scope.exchange_instrument_id,
            ),
        )
    )
    if not canonical_scopes or tuple(item.scope for item in canonical_results) != canonical_scopes:
        raise ValueError("Authority Gap Audit requires one result for every exact scope")
    if any(
        item.first_natural_trigger_at_ms is not None
        and not (
            audit.unauthorized_from_close_time_ms
            <= item.first_natural_trigger_at_ms
            <= audited_through_close_time_ms
        )
        for item in canonical_results
    ):
        raise ValueError("Authority Gap Audit trigger falls outside audited window")
    scope_digest = _semantic_digest(
        [item.model_dump(mode="json") for item in canonical_scopes]
    )
    result_digest = _semantic_digest(
        [item.model_dump(mode="json") for item in canonical_results]
    )
    values = audit.model_dump()
    values.update(
        {
            "audited_through_close_time_ms": audited_through_close_time_ms,
            "first_eligible_close_time_ms": (
                audited_through_close_time_ms + INTERVAL_MS
            ),
            "audit_scope_digest": scope_digest,
            "audit_result_digest": result_digest,
            "state": AuthorityGapAuditState.COMPLETE,
            "projection_version": audit.projection_version + 1,
        }
    )
    return AuthorityGapAudit.model_validate(values)


def fail_authority_gap_audit(
    audit: AuthorityGapAudit,
    *,
    first_blocker: str,
) -> AuthorityGapAudit:
    normalized = first_blocker.strip()
    if audit.state is not AuthorityGapAuditState.PENDING or not normalized:
        raise ValueError("pending Authority Gap Audit requires non-blank failure")
    values = audit.model_dump()
    values.update(
        {
            "state": AuthorityGapAuditState.FAILED,
            "first_blocker": normalized,
            "projection_version": audit.projection_version + 1,
        }
    )
    return AuthorityGapAudit.model_validate(values)
