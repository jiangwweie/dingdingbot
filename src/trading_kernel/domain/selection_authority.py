"""Pure time-bounded Selection Authority identities and compatibility rules."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_validator,
)

from src.trading_kernel.domain.instrument_selection import DAY_MS, HOUR_MS, INTERVAL_MS


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
        or successor.first_eligible_close_time_ms
        != birth.first_eligible_close_time_ms
    )


def _semantic_digest(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"
