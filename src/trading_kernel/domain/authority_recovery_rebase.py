"""Recovery arming barrier on the existing Episode key; not a second Episode chain."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.comparison_universe import ComparisonUniverseBinding
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    ComparisonBindingEpisodeCheckpoint,
    ComparisonBindingEpisodeState,
    ExposureEpisodeState,
    ExposureEpisodeTransition,
    advance_comparison_bound_exposure_episode,
    advance_exposure_episode,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract

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
    last_observed_close_time_ms: int | None
    last_detector_status: DetectorStatus | None
    projection_version: int

    @model_validator(mode="after")
    def _shape(self) -> AuthorityRecoveryCheckpoint:
        if any(not value.strip() or value!=value.strip() or len(value)>160 for value in (self.episode_domain_key,self.recovery_id)):
            raise ValueError("recovery checkpoint identity is invalid")
        if self.recovery_revision<=0 or self.projection_version<=0:
            raise ValueError("recovery checkpoint versions must be positive")
        if not 0<self.effective_from_ms<self.first_eligible_close_time_ms:
            raise ValueError("recovery checkpoint cannot consume a past close")
        last = self.last_observed_close_time_ms
        if self.first_eligible_close_time_ms%HOUR_MS or (last is not None and (last<=0 or last%HOUR_MS)):
            raise ValueError("recovery checkpoint requires hourly close boundaries")
        if last is None or last<self.first_eligible_close_time_ms:
            if self.state!="REBASE_REQUIRED" or self.armed_at_close_time_ms is not None or self.last_detector_status is not None or (
                last is not None and last>self.effective_from_ms):
                raise ValueError("pending recovery cannot fabricate an observation or an arm")
            return self
        if self.last_detector_status is None:
            raise ValueError("observed recovery requires Detector status")
        if self.last_detector_status is DetectorStatus.INVALID:
            raise ValueError("invalid Detector input cannot advance recovery")
        if self.state=="REBASE_REQUIRED":
            if self.armed_at_close_time_ms is not None or self.last_detector_status is not DetectorStatus.TRIGGERED:
                raise ValueError("unarmed recovery checkpoint has contradictory state")
        elif self.armed_at_close_time_ms is None or not self.first_eligible_close_time_ms<=self.armed_at_close_time_ms<=last or self.armed_at_close_time_ms%HOUR_MS:
            raise ValueError("armed recovery checkpoint requires a legal arming close")
        if self.state=="ARMED" and self.last_detector_status is DetectorStatus.TRIGGERED and self.last_observed_close_time_ms==self.armed_at_close_time_ms:
            raise ValueError("trigger close cannot itself prove recovery arming")
        return self


class AuthorityRecoveryRebaseTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    checkpoint: AuthorityRecoveryCheckpoint
    allow_episode_advance: bool
    suppression_reason: Literal["RECOVERY_REBASE_REQUIRED", "RECOVERY_CLOSE_ALREADY_OBSERVED"] | None


def begin_authority_recovery_rebase(*, current: AuthorityRecoveryCheckpoint | None,
    episode_domain_key: str, recovery_id: str, recovery_revision: int, effective_from_ms: int,
    first_eligible_close_time_ms: int, latest_consumed_close_time_ms: int | None,
) -> AuthorityRecoveryCheckpoint:
    """Freeze a pending barrier without inventing a Detector result or close.

    Preserve the actual consumed-close high-water mark across revisions. It is
    not an Observation under the new recovery, so Detector status stays absent.
    An idempotent repeat must not disarm a checkpoint that already progressed.
    """
    if latest_consumed_close_time_ms is not None and (latest_consumed_close_time_ms<=0 or latest_consumed_close_time_ms%HOUR_MS):
        raise ValueError("recovery initialization cursor must be a positive hourly close")
    if current is not None:
        current = AuthorityRecoveryCheckpoint.model_validate(current.model_dump())
        if current.episode_domain_key!=episode_domain_key or recovery_revision<current.recovery_revision:
            raise ValueError("recovery initialization scope or revision is stale")
        if effective_from_ms<current.effective_from_ms:
            raise ValueError("recovery initialization time cannot move backwards")
        if recovery_revision==current.recovery_revision:
            if (current.recovery_id,current.effective_from_ms,current.first_eligible_close_time_ms)!=(recovery_id,effective_from_ms,first_eligible_close_time_ms):
                raise ValueError("recovery initialization identity changed")
            return current
    consumed = [value for value in (latest_consumed_close_time_ms,None if current is None else current.last_observed_close_time_ms) if value is not None]
    return AuthorityRecoveryCheckpoint(episode_domain_key=episode_domain_key,recovery_id=recovery_id,
        recovery_revision=recovery_revision,effective_from_ms=effective_from_ms,first_eligible_close_time_ms=first_eligible_close_time_ms,
        state="REBASE_REQUIRED",armed_at_close_time_ms=None,last_observed_close_time_ms=max(consumed) if consumed else None,
        last_detector_status=None,projection_version=1 if current is None else current.projection_version+1)


def recovery_rebase_entry_rejection(*, checkpoint: AuthorityRecoveryCheckpoint | None,
    episode_domain_key: str, recovery_id: str, recovery_revision: int,
    recovery_committed_at_ms: int, first_eligible_close_time_ms: int, signal_close_time_ms: int,
) -> str | None:
    """Additional ENTRY gate; never blocks observation needed to establish rebase.

    Current Owner/Selection/Universe authority and Episode identity remain
    separate mandatory checks. The commit time is the frozen recovery origin,
    not the nominal start of a future Selection period.
    """
    if checkpoint is None:
        return "RECOVERY_REBASE_REQUIRED"
    checkpoint = AuthorityRecoveryCheckpoint.model_validate(checkpoint.model_dump())
    if (checkpoint.episode_domain_key,checkpoint.recovery_id,checkpoint.recovery_revision,
        checkpoint.effective_from_ms,checkpoint.first_eligible_close_time_ms) != (
        episode_domain_key,recovery_id,recovery_revision,recovery_committed_at_ms,first_eligible_close_time_ms):
        return "RECOVERY_REBASE_AUTHORITY_CHANGED"
    if checkpoint.state != "ARMED" or checkpoint.armed_at_close_time_ms is None:
        return "RECOVERY_REBASE_REQUIRED"
    if checkpoint.last_detector_status is not DetectorStatus.TRIGGERED or checkpoint.last_observed_close_time_ms != signal_close_time_ms or signal_close_time_ms <= checkpoint.armed_at_close_time_ms:
        return "RECOVERY_TRIGGER_NOT_CURRENT"
    return None


class RecoveryBoundExposureEpisodeTransition(BaseModel):
    """One atomic persistence input; never a Signal, Ticket or authority grant."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    recovery_checkpoint: AuthorityRecoveryCheckpoint
    comparison_checkpoint: ComparisonBindingEpisodeCheckpoint | None
    episode_transition: ExposureEpisodeTransition | None
    signal_eligible: bool
    suppression_reason: str | None

    @model_validator(mode="after")
    def _consistent_transition(self) -> RecoveryBoundExposureEpisodeTransition:
        key = self.recovery_checkpoint.episode_domain_key
        if self.comparison_checkpoint is not None and self.comparison_checkpoint.episode_domain_key != key:
            raise ValueError("recovery/comparison Episode identity differs")
        episode = self.episode_transition
        if episode is not None and (episode.current.episode_domain_key != key
            or episode.current.last_observed_at_ms != self.recovery_checkpoint.last_observed_close_time_ms
            or self.recovery_checkpoint.state != "ARMED"):
            raise ValueError("recovery Episode advancement requires its exact armed cursor")
        if episode is not None and self.comparison_checkpoint is not None and (
            self.comparison_checkpoint.state is not ComparisonBindingEpisodeState.ARMED_UNDER_BINDING
            or self.comparison_checkpoint.last_observed_at_ms != self.recovery_checkpoint.last_observed_close_time_ms):
            raise ValueError("recovery Episode must also satisfy its comparison barrier")
        if self.signal_eligible and (episode is None or not episode.created_new_episode or self.suppression_reason is not None):
            raise ValueError("recovery Signal requires one unsuppressed new Episode")
        return self


def advance_recovery_bound_exposure_episode(*, contract: RegisteredStrategyContract,
    current_episode: ExposureEpisodeState | None, current_recovery: AuthorityRecoveryCheckpoint | None,
    current_comparison: ComparisonBindingEpisodeCheckpoint | None,
    recovery_id: str, recovery_revision: int, effective_from_ms: int, first_eligible_close_time_ms: int,
    detector_status: DetectorStatus, occurred_at_ms: int | None, observed_at_ms: int,
    exchange_instrument_id: str, selection_mode: Literal["dynamic_selection", "static_baseline"],
    universe_version_id: str, comparison_binding: ComparisonUniverseBinding | None = None,
) -> RecoveryBoundExposureEpisodeTransition:
    """Compose recovery and comparison gates before the original Episode reducer.

    Caller must first prove current Owner/Authority/epoch/freshness and persist
    all returned projections atomically. A suppressed close preserves old Episode
    identity; it cannot mint an arm or silently increment comparison revision.
    """
    spec = generic_selection_spec(contract.strategy_group_id)
    if selection_mode not in {"dynamic_selection","static_baseline"} or not universe_version_id.strip():
        raise ValueError("recovery requires an exact current mode and Universe")
    static = selection_mode=="static_baseline"
    if contract.event_spec_id != spec.event_spec_id or not exchange_instrument_id.strip() or (not static and exchange_instrument_id not in spec.candidate_ids):
        raise ValueError("recovery Event or member differs from Generic Spec")
    if detector_status is DetectorStatus.INVALID or (
        detector_status is DetectorStatus.TRIGGERED and (occurred_at_ms is None or not 0 < occurred_at_ms <= observed_at_ms)
    ) or (detector_status is DetectorStatus.NOT_TRIGGERED and occurred_at_ms is not None):
        raise ValueError("recovery requires a valid closed-bar Detector result")
    key = build_episode_domain_key(event_spec_id=spec.event_spec_id,exchange_instrument_id=exchange_instrument_id,position_side=spec.position_side)
    if current_recovery is not None:
        current_recovery = AuthorityRecoveryCheckpoint.model_validate(current_recovery.model_dump())
    duplicate = current_recovery is not None and current_recovery.last_observed_close_time_ms == observed_at_ms
    if current_episode is not None:
        current_episode = ExposureEpisodeState.model_validate(current_episode.model_dump())
        if (current_episode.episode_domain_key,current_episode.event_spec_id,current_episode.exchange_instrument_id,current_episode.position_side) != (key,spec.event_spec_id,exchange_instrument_id,spec.position_side):
            raise ValueError("recovery Episode identity differs")
        if current_episode.last_observed_at_ms is not None and (current_episode.last_observed_at_ms > observed_at_ms or (current_episode.last_observed_at_ms == observed_at_ms and not duplicate)):
            raise ValueError("recovery cannot reuse a consumed Episode close")
    comparative = contract.strategy_group_id in {"MPG-001","MI-001"}
    comparison_binding_digest = None
    comparison_transition_revision = None
    if comparative:
        if comparison_binding is None:
            raise ValueError("recovery comparison binding is missing")
        comparison_binding = ComparisonUniverseBinding.model_validate(comparison_binding.model_dump())
        if comparison_binding.event_spec_id!=spec.event_spec_id or exchange_instrument_id not in comparison_binding.exchange_instrument_ids or (
            comparison_binding.source_static_universe_version_id!=(universe_version_id if static else None)):
            raise ValueError("recovery comparison mode, member or Universe differs")
        comparison_binding_digest = comparison_binding.member_set_digest
        comparison_transition_revision = comparison_binding.comparison_transition_revision
        if current_comparison is not None:
            current_comparison = ComparisonBindingEpisodeCheckpoint.model_validate(current_comparison.model_dump())
            if current_comparison.episode_domain_key != key or comparison_transition_revision < current_comparison.comparison_transition_revision or (
                comparison_transition_revision == current_comparison.comparison_transition_revision and comparison_binding_digest != current_comparison.comparison_binding_digest):
                raise ValueError("recovery comparison identity or revision differs")
            if current_comparison.last_observed_at_ms > observed_at_ms or (current_comparison.last_observed_at_ms == observed_at_ms and not duplicate):
                raise ValueError("recovery cannot reuse a consumed comparison close")
    elif current_comparison is not None or comparison_binding is not None:
        raise ValueError("non-comparative recovery forbids comparison identity")
    recovery = advance_authority_recovery_rebase(current=current_recovery,episode_domain_key=key,
        recovery_id=recovery_id,recovery_revision=recovery_revision,effective_from_ms=effective_from_ms,
        first_eligible_close_time_ms=first_eligible_close_time_ms,observed_close_time_ms=observed_at_ms,detector_status=detector_status)
    if not recovery.allow_episode_advance:
        return RecoveryBoundExposureEpisodeTransition(recovery_checkpoint=recovery.checkpoint,
            comparison_checkpoint=current_comparison,episode_transition=None,signal_eligible=False,suppression_reason=recovery.suppression_reason)
    if comparative and comparison_transition_revision != 0:
        assert comparison_binding_digest is not None and comparison_transition_revision is not None
        compared = advance_comparison_bound_exposure_episode(contract=contract,current_episode=current_episode,
            current_checkpoint=current_comparison,detector_status=detector_status,occurred_at_ms=occurred_at_ms,
            observed_at_ms=observed_at_ms,exchange_instrument_id=exchange_instrument_id,
            comparison_binding_digest=comparison_binding_digest,comparison_transition_revision=comparison_transition_revision)
        return RecoveryBoundExposureEpisodeTransition(recovery_checkpoint=recovery.checkpoint,
            comparison_checkpoint=compared.checkpoint,episode_transition=compared.episode_transition,
            signal_eligible=compared.signal_eligible,suppression_reason=compared.suppression_reason)
    episode = advance_exposure_episode(contract=contract,current=current_episode,detector_status=detector_status,
        occurred_at_ms=occurred_at_ms,observed_at_ms=observed_at_ms,exchange_instrument_id=exchange_instrument_id)
    return RecoveryBoundExposureEpisodeTransition(recovery_checkpoint=recovery.checkpoint,
        comparison_checkpoint=None,episode_transition=episode,
        signal_eligible=episode.created_new_episode and detector_status is DetectorStatus.TRIGGERED,suppression_reason=None)


def advance_authority_recovery_rebase(*, current: AuthorityRecoveryCheckpoint | None,
    episode_domain_key: str,recovery_id: str,recovery_revision: int,effective_from_ms: int,
    first_eligible_close_time_ms: int,observed_close_time_ms: int,detector_status: DetectorStatus,
) -> AuthorityRecoveryRebaseTransition:
    """Caller supplies authorized Observation only, then applies the ordinary Episode reducer.

    This gate never mints an Episode ID, mutates a comparison revision or grants
    trading authority. Owner/epoch/freshness/current Authority checks remain mandatory.
    """
    if observed_close_time_ms<first_eligible_close_time_ms or observed_close_time_ms%HOUR_MS:
        raise ValueError("recovery Observation must use a future eligible hourly close")
    if current is not None:
        current = AuthorityRecoveryCheckpoint.model_validate(current.model_dump())
        if current.episode_domain_key!=episode_domain_key or recovery_revision<current.recovery_revision:
            raise ValueError("recovery checkpoint scope or revision is stale")
        if recovery_revision==current.recovery_revision and (
            recovery_id!=current.recovery_id or effective_from_ms!=current.effective_from_ms
            or first_eligible_close_time_ms!=current.first_eligible_close_time_ms
        ):
            raise ValueError("same recovery revision has contradictory identity")
        if current.last_observed_close_time_ms is not None and observed_close_time_ms<current.last_observed_close_time_ms:
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
