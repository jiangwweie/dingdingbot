"""Pure Generic Dynamic Selection period, staleness, and close-proof contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.exposure_episode import LockedObservationCursor

_HOUR_MS = 60 * 60 * 1000


class DynamicMembershipState(StrEnum):
    ACTIVE = "ACTIVE"
    GRACE = "GRACE"
    SELECTION_STALE_PAUSED = "SELECTION_STALE_PAUSED"


class GenericSelectionPeriod(BaseModel):
    """One new-strategy selection period; SOR keeps its dedicated session clock."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_cutoff_at_ms: int
    cadence_hours: int
    scheduled_effective_at_ms: int
    period_expires_at_ms: int

    @model_validator(mode="after")
    def _validate_period(self) -> GenericSelectionPeriod:
        cadence_ms = _cadence_ms(self.cadence_hours)
        if (
            self.feature_cutoff_at_ms <= 0
            or self.feature_cutoff_at_ms % cadence_ms != 0
            or self.scheduled_effective_at_ms != self.feature_cutoff_at_ms + _HOUR_MS
            or self.period_expires_at_ms != self.scheduled_effective_at_ms + cadence_ms
        ):
            raise ValueError("Generic Selection period timing is invalid")
        return self


def missed_closes_at_gap_fence(*, period: GenericSelectionPeriod,
    fenced_at_ms: int) -> tuple[int, ...]:
    """Exact elapsed close boundaries, never inferred Detector or P&L outcomes."""
    period = GenericSelectionPeriod.model_validate(period.model_dump())
    if not period.scheduled_effective_at_ms <= fenced_at_ms < period.period_expires_at_ms:
        raise ValueError("gap fence is outside its Selection period")
    latest = fenced_at_ms//_HOUR_MS*_HOUR_MS
    return tuple(range(period.scheduled_effective_at_ms,
        min(latest,period.period_expires_at_ms-_HOUR_MS)+1,_HOUR_MS))


HourlyRecoveryReason = Literal[
    "AUTHORITY_GAP", "MATERIALIZATION_FAILURE", "MATERIALIZATION_TIMEOUT",
    "FAILED_RECOVERY", "STALE_SOURCE", "VACUUM_INTERRUPTION",
    "UNPROVEN_CRASH_CONTINUITY", "COMPARISON_PROVENANCE_LOST",
]


class HourlyRecoveryClosePlan(BaseModel):
    """Fail-closed recovery clock plan, never an Entry grant or arming proof."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    recovery_id: str
    recovery_revision: int
    reason: HourlyRecoveryReason
    period: GenericSelectionPeriod
    evaluated_at_ms: int
    status: Literal["FUTURE_CLOSE_REBASE_REQUIRED", "NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY"]
    first_eligible_close_time_ms: int | None
    episode_rebase_required: Literal[True] = True

    @model_validator(mode="after")
    def _validate_recovery_clock(self) -> HourlyRecoveryClosePlan:
        if not self.recovery_id.strip() or len(self.recovery_id)>160 or self.recovery_revision<=0:
            raise ValueError("recovery requires durable identity and revision")
        if self.evaluated_at_ms<self.period.feature_cutoff_at_ms:
            raise ValueError("recovery cannot plan beyond the adjacent eligible period")
        # An hourly failure loses its current close. Planning the adjacent
        # period before its boundary avoids permanently losing every hour.
        # This is a plan, not a grant or permission to refresh membership age.
        first = max(self.period.scheduled_effective_at_ms,(self.evaluated_at_ms//_HOUR_MS+1)*_HOUR_MS)
        if first>=self.period.period_expires_at_ms:
            if self.status!="NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY" or self.first_eligible_close_time_ms is not None:
                raise ValueError("recovery cannot invent an eligible close before expiry")
        elif self.status!="FUTURE_CLOSE_REBASE_REQUIRED" or self.first_eligible_close_time_ms!=first:
            raise ValueError("recovery requires the next strictly future close")
        return self


def plan_hourly_recovery_close(*, recovery_id: str, recovery_revision: int, reason: HourlyRecoveryReason,
                              period: GenericSelectionPeriod, evaluated_at_ms: int) -> HourlyRecoveryClosePlan:
    first = max(period.scheduled_effective_at_ms,(evaluated_at_ms//_HOUR_MS+1)*_HOUR_MS)
    eligible = first<period.period_expires_at_ms
    return HourlyRecoveryClosePlan(recovery_id=recovery_id,recovery_revision=recovery_revision,reason=reason,
        period=period,evaluated_at_ms=evaluated_at_ms,
        status="FUTURE_CLOSE_REBASE_REQUIRED" if eligible else "NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY",
        first_eligible_close_time_ms=first if eligible else None)


def require_hourly_recovery_commit(plan: HourlyRecoveryClosePlan, *, committed_at_ms: int) -> None:
    """Caller must use fresh commit-time facts and persist recovery rebase atomically."""
    plan = HourlyRecoveryClosePlan.model_validate(plan.model_dump())
    if plan.status=="NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY":
        raise ValueError("NO_ELIGIBLE_CLOSE_BEFORE_EXPIRY")
    first = plan.first_eligible_close_time_ms
    if first is None or not plan.evaluated_at_ms<=committed_at_ms<first<plan.period.period_expires_at_ms:
        raise ValueError("recovery commit crossed its future-close boundary; replan required")


class DynamicMembershipFreshness(BaseModel):
    """Immutable membership source age and its finite Dynamic continuity budget."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_snapshot_id: str
    source_member_set_digest: str
    source_snapshot_cutoff_at_ms: int
    source_snapshot_effective_at_ms: int
    cadence_hours: int
    membership_valid_until_ms: int
    consecutive_missed_periods: int
    state: DynamicMembershipState

    @field_validator("source_snapshot_id", mode="before")
    @classmethod
    def _require_snapshot_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Dynamic membership freshness requires Snapshot identity")
        return normalized

    @field_validator("source_member_set_digest")
    @classmethod
    def _require_member_digest(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if (
            not normalized.startswith("sha256:")
            or len(normalized) != 71
            or normalized != normalized.lower()
        ):
            raise ValueError("Dynamic membership freshness requires canonical digest")
        try:
            int(normalized[7:], 16)
        except ValueError as exc:
            raise ValueError(
                "Dynamic membership freshness requires canonical digest"
            ) from exc
        return normalized

    @model_validator(mode="after")
    def _validate_freshness(self) -> DynamicMembershipFreshness:
        cadence_ms = _cadence_ms(self.cadence_hours)
        if (
            self.source_snapshot_cutoff_at_ms <= 0
            or self.source_snapshot_cutoff_at_ms % cadence_ms != 0
            or self.source_snapshot_effective_at_ms
            != self.source_snapshot_cutoff_at_ms + _HOUR_MS
            or self.membership_valid_until_ms
            != self.source_snapshot_effective_at_ms + 2 * cadence_ms
            or self.consecutive_missed_periods < 0
        ):
            raise ValueError("Dynamic membership freshness timing is invalid")
        if self.state is DynamicMembershipState.ACTIVE:
            if self.consecutive_missed_periods != 0:
                raise ValueError(
                    "active Dynamic membership cannot have a missed period"
                )
        elif self.state is DynamicMembershipState.GRACE:
            if self.consecutive_missed_periods != 1:
                raise ValueError("Dynamic grace requires exactly one missed period")
        elif self.consecutive_missed_periods < 2:
            raise ValueError("stale Dynamic membership requires two missed periods")
        return self

    def allows_new_entry_at(self, now_ms: int) -> bool:
        """Apply the absolute deadline even when no Coordinator heartbeat runs."""

        return (
            self.source_snapshot_effective_at_ms
            <= now_ms
            < self.membership_valid_until_ms
            and self.state is not DynamicMembershipState.SELECTION_STALE_PAUSED
        )


class CurrentFinalCloseGrantProof(BaseModel):
    """Proof for a fresh, unconsumed current close after a precommitted selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_snapshot_id: str
    selection_committed_at_ms: int
    source_snapshot_cutoff_at_ms: int
    period: GenericSelectionPeriod
    current_final_close_time_ms: int
    authority_granted_at_ms: int
    observation_cursors: tuple[LockedObservationCursor, ...]

    @field_validator("selection_snapshot_id", mode="before")
    @classmethod
    def _require_snapshot_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("current-close proof requires Snapshot identity")
        return normalized

    @model_validator(mode="after")
    def _validate_current_close_proof(self) -> CurrentFinalCloseGrantProof:
        if (
            self.source_snapshot_cutoff_at_ms != self.period.feature_cutoff_at_ms
            or self.selection_committed_at_ms < self.source_snapshot_cutoff_at_ms
            or self.current_final_close_time_ms % _HOUR_MS != 0
            or self.current_final_close_time_ms
            != self.authority_granted_at_ms // _HOUR_MS * _HOUR_MS
        ):
            raise ValueError(
                "current-close proof source or latest-close identity differs"
            )
        members = tuple(c.exchange_instrument_id for c in self.observation_cursors)
        if not 1 <= len(members) <= 16 or tuple(sorted(set(members))) != members:
            raise ValueError("current-close proof requires complete canonical Observation cursors")
        if len({c.episode_domain_key for c in self.observation_cursors}) != len(members):
            raise ValueError("current-close proof requires unique Episode keys")
        if any(c.last_observed_at_ms is not None and c.last_observed_at_ms >= self.current_final_close_time_ms
               for c in self.observation_cursors):
            raise ValueError("current-close proof cannot reuse a consumed close")
        if not (
            self.period.scheduled_effective_at_ms
            <= self.current_final_close_time_ms
            < self.period.period_expires_at_ms
        ):
            raise ValueError("current-close proof is outside its Selection period")
        if (
            self.source_snapshot_cutoff_at_ms
            > self.current_final_close_time_ms - _HOUR_MS
        ):
            raise ValueError(
                "current-close proof requires precommitted Selection cutoff"
            )
        if self.selection_committed_at_ms >= self.current_final_close_time_ms:
            raise ValueError("current-close proof requires precommitted Snapshot")
        if not (
            self.current_final_close_time_ms
            < self.authority_granted_at_ms
            < self.period.period_expires_at_ms
        ):
            raise ValueError("current-close authority grant timing is invalid")
        return self


class GenericContinuityCloseProof(BaseModel):
    """The previous exact set, not a new Selection result, owns this close."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proof_kind: Literal["PRE_FENCE_CONTINUITY_CURRENT_CLOSE"] = "PRE_FENCE_CONTINUITY_CURRENT_CLOSE"
    source_selection_authority_id: str
    source_snapshot_id: str
    origin_recovery_authority_id: str | None = None
    period: GenericSelectionPeriod
    current_final_close_time_ms: int
    authority_granted_at_ms: int
    observation_cursors: tuple[LockedObservationCursor, ...]

    @field_validator("source_selection_authority_id", "source_snapshot_id", "origin_recovery_authority_id")
    @classmethod
    def _bounded_identity(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value!=value.strip() or len(value)>160):
            raise ValueError("Continuity requires an exact bounded source identity")
        return value

    @model_validator(mode="after")
    def _shape(self) -> GenericContinuityCloseProof:
        close = self.current_final_close_time_ms
        if close<=0 or close%_HOUR_MS or close!=self.authority_granted_at_ms//_HOUR_MS*_HOUR_MS or (
            not self.period.scheduled_effective_at_ms==close<self.authority_granted_at_ms<self.period.period_expires_at_ms):
            raise ValueError("Continuity must grant only the latest unconsumed current close")
        if not self.source_selection_authority_id or not self.source_snapshot_id:
            raise ValueError("Continuity requires a source Authority and Snapshot")
        members = tuple(cursor.exchange_instrument_id for cursor in self.observation_cursors)
        if not 1<=len(members)<=16 or members!=tuple(sorted(set(members))) or (
            len({cursor.episode_domain_key for cursor in self.observation_cursors})!=len(members)
            or any(cursor.last_observed_at_ms is not None and cursor.last_observed_at_ms>=close
                for cursor in self.observation_cursors)):
            raise ValueError("Continuity requires exact unconsumed member coverage")
        return self


def require_current_close_commit(proof: CurrentFinalCloseGrantProof, *, committed_at_ms: int) -> None:
    """Recheck NORMAL close at the final transaction boundary; never reclassify a gap."""
    proof = CurrentFinalCloseGrantProof.model_validate(proof.model_dump())
    if committed_at_ms < proof.authority_granted_at_ms:
        raise ValueError("current-close commit clock moved backwards")
    if committed_at_ms >= proof.period.period_expires_at_ms or committed_at_ms//_HOUR_MS*_HOUR_MS != proof.current_final_close_time_ms:
        raise ValueError("current-close commit crossed its proof boundary")


def require_generic_continuity_commit(proof: GenericContinuityCloseProof, *, committed_at_ms: int) -> None:
    proof = GenericContinuityCloseProof.model_validate(proof.model_dump())
    if committed_at_ms<proof.authority_granted_at_ms or committed_at_ms>=proof.period.period_expires_at_ms or (
        committed_at_ms//_HOUR_MS*_HOUR_MS!=proof.current_final_close_time_ms):
        raise ValueError("Continuity commit crossed its current-close boundary")


def build_generic_selection_period(
    *,
    feature_cutoff_at_ms: int,
    cadence_hours: int,
) -> GenericSelectionPeriod:
    cadence_ms = _cadence_ms(cadence_hours)
    return GenericSelectionPeriod(
        feature_cutoff_at_ms=feature_cutoff_at_ms,
        cadence_hours=cadence_hours,
        scheduled_effective_at_ms=feature_cutoff_at_ms + _HOUR_MS,
        period_expires_at_ms=feature_cutoff_at_ms + _HOUR_MS + cadence_ms,
    )


def build_dynamic_membership_freshness(
    *,
    source_snapshot_id: str,
    source_member_set_digest: str,
    period: GenericSelectionPeriod,
) -> DynamicMembershipFreshness:
    return DynamicMembershipFreshness(
        source_snapshot_id=source_snapshot_id,
        source_member_set_digest=source_member_set_digest,
        source_snapshot_cutoff_at_ms=period.feature_cutoff_at_ms,
        source_snapshot_effective_at_ms=period.scheduled_effective_at_ms,
        cadence_hours=period.cadence_hours,
        membership_valid_until_ms=(
            period.scheduled_effective_at_ms + 2 * _cadence_ms(period.cadence_hours)
        ),
        consecutive_missed_periods=0,
        state=DynamicMembershipState.ACTIVE,
    )


def record_dynamic_selection_miss(
    *,
    current: DynamicMembershipFreshness,
    missed_period: GenericSelectionPeriod,
) -> DynamicMembershipFreshness:
    """Record one due period with no usable Snapshot without rolling source age."""

    if missed_period.cadence_hours != current.cadence_hours:
        raise ValueError("Dynamic Selection miss cadence differs")
    missed = (
        missed_period.scheduled_effective_at_ms
        - current.source_snapshot_effective_at_ms
    ) // _cadence_ms(current.cadence_hours)
    if missed <= 0:
        raise ValueError("Dynamic Selection miss must follow its source period")
    if missed <= current.consecutive_missed_periods:
        return current
    return current.model_copy(
        update={
            "consecutive_missed_periods": missed,
            "state": (
                DynamicMembershipState.GRACE
                if missed == 1
                else DynamicMembershipState.SELECTION_STALE_PAUSED
            ),
        }
    )


def confirm_dynamic_membership_snapshot(
    *,
    current: DynamicMembershipFreshness,
    source_snapshot_id: str,
    source_member_set_digest: str,
    period: GenericSelectionPeriod,
    confirmed_at_ms: int,
) -> DynamicMembershipFreshness:
    """Reset age only after a due Snapshot confirms the actual membership."""

    if period.cadence_hours != current.cadence_hours:
        raise ValueError("Dynamic membership confirmation cadence differs")
    if period.feature_cutoff_at_ms < current.source_snapshot_cutoff_at_ms:
        raise ValueError("Dynamic membership confirmation cannot move backwards")
    if period.feature_cutoff_at_ms == current.source_snapshot_cutoff_at_ms:
        if (
            source_snapshot_id != current.source_snapshot_id
            or source_member_set_digest != current.source_member_set_digest
        ):
            raise ValueError("same period membership identity differs")
        return current
    if not (
        period.scheduled_effective_at_ms
        <= confirmed_at_ms
        < period.period_expires_at_ms
    ):
        raise ValueError(
            "Dynamic membership Snapshot is not yet effective or is expired"
        )
    return build_dynamic_membership_freshness(
        source_snapshot_id=source_snapshot_id,
        source_member_set_digest=source_member_set_digest,
        period=period,
    )


def build_current_final_close_grant_proof(
    *,
    selection_snapshot_id: str,
    selection_committed_at_ms: int,
    source_snapshot_cutoff_at_ms: int,
    period: GenericSelectionPeriod,
    current_final_close_time_ms: int,
    authority_granted_at_ms: int,
    observation_cursors: tuple[LockedObservationCursor, ...],
) -> CurrentFinalCloseGrantProof:
    return CurrentFinalCloseGrantProof(
        selection_snapshot_id=selection_snapshot_id,
        selection_committed_at_ms=selection_committed_at_ms,
        source_snapshot_cutoff_at_ms=source_snapshot_cutoff_at_ms,
        period=period,
        current_final_close_time_ms=current_final_close_time_ms,
        authority_granted_at_ms=authority_granted_at_ms,
        observation_cursors=observation_cursors,
    )


def _cadence_ms(cadence_hours: int) -> int:
    if cadence_hours not in {1, 4}:
        raise ValueError("Generic Selection cadence must be 1h or 4h")
    return cadence_hours * _HOUR_MS
