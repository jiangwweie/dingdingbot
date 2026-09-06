"""Pure Generic Dynamic Selection period, staleness, and close-proof contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
            raise ValueError("Dynamic membership freshness requires canonical digest") from exc
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
                raise ValueError("active Dynamic membership cannot have a missed period")
        elif self.state is DynamicMembershipState.GRACE:
            if self.consecutive_missed_periods != 1:
                raise ValueError("Dynamic grace requires exactly one missed period")
        elif self.consecutive_missed_periods < 2:
            raise ValueError("stale Dynamic membership requires two missed periods")
        return self

    def allows_new_entry_at(self, now_ms: int) -> bool:
        """Apply the absolute deadline even when no Coordinator heartbeat runs."""

        return now_ms < self.membership_valid_until_ms


class CurrentFinalCloseGrantProof(BaseModel):
    """Proof for a fresh, unconsumed current close after a precommitted selection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_snapshot_id: str
    selection_committed_at_ms: int
    source_snapshot_cutoff_at_ms: int
    period: GenericSelectionPeriod
    current_final_close_time_ms: int
    authority_granted_at_ms: int
    observation_cursor_version: int

    @field_validator("selection_snapshot_id", mode="before")
    @classmethod
    def _require_snapshot_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("current-close proof requires Snapshot identity")
        return normalized

    @model_validator(mode="after")
    def _validate_current_close_proof(self) -> CurrentFinalCloseGrantProof:
        if self.observation_cursor_version <= 0:
            raise ValueError("current-close proof requires locked Observation cursor")
        if not (
            self.period.scheduled_effective_at_ms
            <= self.current_final_close_time_ms
            < self.period.period_expires_at_ms
        ):
            raise ValueError("current-close proof is outside its Selection period")
        if self.source_snapshot_cutoff_at_ms > self.current_final_close_time_ms - _HOUR_MS:
            raise ValueError("current-close proof requires precommitted Selection cutoff")
        if self.selection_committed_at_ms >= self.current_final_close_time_ms:
            raise ValueError("current-close proof requires precommitted Snapshot")
        if not (
            self.current_final_close_time_ms
            < self.authority_granted_at_ms
            < self.period.period_expires_at_ms
        ):
            raise ValueError("current-close authority grant timing is invalid")
        return self


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

    _require_next_period(current=current, period=missed_period)
    missed = current.consecutive_missed_periods + 1
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
    if not (
        period.scheduled_effective_at_ms
        <= confirmed_at_ms
        < period.period_expires_at_ms
    ):
        raise ValueError("Dynamic membership Snapshot is not yet effective or is expired")
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
    observation_cursor_version: int,
) -> CurrentFinalCloseGrantProof:
    return CurrentFinalCloseGrantProof(
        selection_snapshot_id=selection_snapshot_id,
        selection_committed_at_ms=selection_committed_at_ms,
        source_snapshot_cutoff_at_ms=source_snapshot_cutoff_at_ms,
        period=period,
        current_final_close_time_ms=current_final_close_time_ms,
        authority_granted_at_ms=authority_granted_at_ms,
        observation_cursor_version=observation_cursor_version,
    )


def _cadence_ms(cadence_hours: int) -> int:
    if cadence_hours not in {1, 4}:
        raise ValueError("Generic Selection cadence must be 1h or 4h")
    return cadence_hours * _HOUR_MS


def _require_next_period(
    *,
    current: DynamicMembershipFreshness,
    period: GenericSelectionPeriod,
) -> None:
    if period.cadence_hours != current.cadence_hours:
        raise ValueError("Dynamic Selection miss cadence differs")
    expected_effective = current.source_snapshot_effective_at_ms + (
        _cadence_ms(current.cadence_hours)
        * (current.consecutive_missed_periods + 1)
    )
    if period.scheduled_effective_at_ms != expected_effective:
        raise ValueError("Dynamic Selection miss period is not the next due period")
