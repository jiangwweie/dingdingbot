"""Recovery arming barrier on the existing Episode key; not a second Episode chain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.detector import DetectorStatus

HOUR_MS = 3600000


class AuthorityRecoveryCheckpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    episode_domain_key: str
    recovery_id: str
    recovery_revision: int
    effective_from_ms: int
    first_eligible_close_time_ms: int
    state: Literal["REBASE_REQUIRED", "ARMED"]
    armed_at_close_time_ms: int | None
    last_observed_close_time_ms: int
    last_detector_status: DetectorStatus
    projection_version: int

    @model_validator(mode="after")
    def _shape(self) -> AuthorityRecoveryCheckpoint:
        if any(not value.strip() or value!=value.strip() or len(value)>160 for value in (self.episode_domain_key,self.recovery_id)):
            raise ValueError("recovery checkpoint identity is invalid")
        if self.recovery_revision<=0 or self.projection_version<=0:
            raise ValueError("recovery checkpoint versions must be positive")
        if not 0<self.effective_from_ms<self.first_eligible_close_time_ms<=self.last_observed_close_time_ms:
            raise ValueError("recovery checkpoint cannot consume a past close")
        if self.first_eligible_close_time_ms%HOUR_MS or self.last_observed_close_time_ms%HOUR_MS:
            raise ValueError("recovery checkpoint requires hourly close boundaries")
        if self.last_detector_status is DetectorStatus.INVALID:
            raise ValueError("invalid Detector input cannot advance recovery")
        if self.state=="REBASE_REQUIRED":
            if self.armed_at_close_time_ms is not None or self.last_detector_status is not DetectorStatus.TRIGGERED:
                raise ValueError("unarmed recovery checkpoint has contradictory state")
        elif self.armed_at_close_time_ms is None or not self.first_eligible_close_time_ms<=self.armed_at_close_time_ms<=self.last_observed_close_time_ms or self.armed_at_close_time_ms%HOUR_MS:
            raise ValueError("armed recovery checkpoint requires a legal arming close")
        if self.state=="ARMED" and self.last_detector_status is DetectorStatus.TRIGGERED and self.last_observed_close_time_ms==self.armed_at_close_time_ms:
            raise ValueError("trigger close cannot itself prove recovery arming")
        return self


class AuthorityRecoveryRebaseTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    checkpoint: AuthorityRecoveryCheckpoint
    allow_episode_advance: bool
    suppression_reason: Literal["RECOVERY_REBASE_REQUIRED", "RECOVERY_CLOSE_ALREADY_OBSERVED"] | None


def advance_authority_recovery_rebase(*, current: AuthorityRecoveryCheckpoint | None,
    episode_domain_key: str,recovery_id: str,recovery_revision: int,effective_from_ms: int,
    first_eligible_close_time_ms: int,observed_close_time_ms: int,detector_status: DetectorStatus,
) -> AuthorityRecoveryRebaseTransition:
    """Caller supplies authorized Observation only, then applies the ordinary Episode reducer.

    This gate never mints an Episode ID, mutates a comparison revision or grants
    trading authority. Owner/epoch/freshness/current Authority checks remain mandatory.
    """
    if current is not None:
        current = AuthorityRecoveryCheckpoint.model_validate(current.model_dump())
        if current.episode_domain_key!=episode_domain_key or recovery_revision<current.recovery_revision:
            raise ValueError("recovery checkpoint scope or revision is stale")
        if recovery_revision==current.recovery_revision and (
            recovery_id!=current.recovery_id or effective_from_ms!=current.effective_from_ms
            or first_eligible_close_time_ms!=current.first_eligible_close_time_ms
        ):
            raise ValueError("same recovery revision has contradictory identity")
        if observed_close_time_ms<current.last_observed_close_time_ms:
            raise ValueError("recovery Observation cannot move backwards")
        if observed_close_time_ms==current.last_observed_close_time_ms:
            if recovery_revision!=current.recovery_revision or detector_status is not current.last_detector_status:
                raise ValueError("recovery cannot reuse a consumed close with changed input")
            return AuthorityRecoveryRebaseTransition(checkpoint=current,allow_episode_advance=False,
                suppression_reason="RECOVERY_CLOSE_ALREADY_OBSERVED")
    if detector_status is DetectorStatus.INVALID:
        raise ValueError("invalid Detector input cannot advance recovery")
    changed = current is None or recovery_revision!=current.recovery_revision
    armed = None if changed or current is None else current.armed_at_close_time_ms
    if armed is None and detector_status is DetectorStatus.NOT_TRIGGERED:
        armed = observed_close_time_ms
    checkpoint = AuthorityRecoveryCheckpoint(episode_domain_key=episode_domain_key,recovery_id=recovery_id,recovery_revision=recovery_revision,
        effective_from_ms=effective_from_ms,first_eligible_close_time_ms=first_eligible_close_time_ms,
        state="ARMED" if armed is not None else "REBASE_REQUIRED",armed_at_close_time_ms=armed,
        last_observed_close_time_ms=observed_close_time_ms,last_detector_status=detector_status,
        projection_version=1 if current is None else current.projection_version+1)
    return AuthorityRecoveryRebaseTransition(checkpoint=checkpoint,allow_episode_advance=armed is not None,
        suppression_reason=None if armed is not None else "RECOVERY_REBASE_REQUIRED")
