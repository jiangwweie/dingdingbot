"""Pure rising-edge Exposure Episode identity and state transitions."""

from __future__ import annotations

import json
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.strategy_registry import RegisteredStrategyContract

EpisodeState = Literal["armed", "triggered"]


class ExposureEpisodeState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    episode_domain_key: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    episode_policy: Literal["rising_edge"] = "rising_edge"
    state: EpisodeState
    exposure_episode_id: str | None
    triggered_at_ms: int | None
    rearmed_at_ms: int | None
    last_observed_at_ms: int
    projection_version: int

    @field_validator(
        "episode_domain_key",
        "event_spec_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Exposure Episode identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_shape(self) -> ExposureEpisodeState:
        if self.last_observed_at_ms <= 0 or self.projection_version <= 0:
            raise ValueError("Exposure Episode time and version must be positive")
        if self.rearmed_at_ms is not None and self.rearmed_at_ms <= 0:
            raise ValueError("Exposure Episode re-arm time must be positive")
        if self.state == "triggered":
            if self.exposure_episode_id is None or self.triggered_at_ms is None:
                raise ValueError("triggered Episode requires identity and trigger time")
            if self.triggered_at_ms <= 0:
                raise ValueError("Episode trigger time must be positive")
        elif self.exposure_episode_id is not None or self.triggered_at_ms is not None:
            raise ValueError("armed Episode forbids active identity and trigger time")
        return self


class ExposureEpisodeTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    current: ExposureEpisodeState
    exposure_episode_id: str | None
    created_new_episode: bool

    @model_validator(mode="after")
    def _validate_shape(self) -> ExposureEpisodeTransition:
        if self.exposure_episode_id != self.current.exposure_episode_id:
            raise ValueError("Episode transition identity differs from current state")
        if self.created_new_episode and self.exposure_episode_id is None:
            raise ValueError("new Episode transition requires an identity")
        return self


class ComparisonBindingEpisodeState(StrEnum):
    """Whether an MPG/MI scope has armed under its active comparison binding."""

    REBASE_REQUIRED = "rebase_required"
    ARMED_UNDER_BINDING = "armed_under_binding"


class ComparisonBindingEpisodeCheckpoint(BaseModel):
    """Scope-local barrier that prevents comparison changes fabricating an edge.

    The stable Episode domain key deliberately remains unchanged.  This
    checkpoint records only whether that existing scope has first observed a
    valid not-triggered close under the active comparison revision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    episode_domain_key: str
    comparison_binding_digest: str
    comparison_transition_revision: int
    state: ComparisonBindingEpisodeState
    armed_at_ms: int | None
    last_observed_at_ms: int
    last_detector_status: DetectorStatus
    projection_version: int

    @field_validator("episode_domain_key", mode="before")
    @classmethod
    def _require_checkpoint_key(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("comparison checkpoint requires an Episode domain key")
        return normalized

    @field_validator("comparison_binding_digest", mode="before")
    @classmethod
    def _require_comparison_digest(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if (
            not normalized.startswith("sha256:")
            or len(normalized) != 71
            or normalized != normalized.lower()
        ):
            raise ValueError("comparison binding digest must be canonical sha256")
        try:
            int(normalized[7:], 16)
        except ValueError as exc:
            raise ValueError("comparison binding digest must be canonical sha256") from exc
        return normalized

    @model_validator(mode="after")
    def _validate_checkpoint(self) -> ComparisonBindingEpisodeCheckpoint:
        if (
            self.comparison_transition_revision <= 0
            or self.last_observed_at_ms <= 0
            or self.projection_version <= 0
        ):
            raise ValueError("comparison checkpoint version and time must be positive")
        if self.last_detector_status not in {
            DetectorStatus.TRIGGERED,
            DetectorStatus.NOT_TRIGGERED,
        }:
            raise ValueError("comparison checkpoint requires a valid detector status")
        if self.state is ComparisonBindingEpisodeState.REBASE_REQUIRED:
            if self.armed_at_ms is not None:
                raise ValueError("rebase-required comparison checkpoint forbids arming")
            if self.last_detector_status is not DetectorStatus.TRIGGERED:
                raise ValueError("rebase-required checkpoint records suppressed trigger")
        elif (
            self.armed_at_ms is None
            or self.armed_at_ms <= 0
            or self.armed_at_ms > self.last_observed_at_ms
        ):
            raise ValueError("armed comparison checkpoint requires a prior valid arm")
        return self


class ComparisonBoundExposureEpisodeTransition(BaseModel):
    """One comparison-aware Observation result before Signal construction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint: ComparisonBindingEpisodeCheckpoint
    episode_transition: ExposureEpisodeTransition | None
    signal_eligible: bool
    suppression_reason: str | None

    @model_validator(mode="after")
    def _validate_comparison_transition(self) -> ComparisonBoundExposureEpisodeTransition:
        if self.suppression_reason is not None:
            if self.signal_eligible or self.episode_transition is not None:
                raise ValueError("suppressed comparison trigger cannot advance an Episode")
        elif self.checkpoint.state is ComparisonBindingEpisodeState.REBASE_REQUIRED:
            raise ValueError("rebase-required comparison transition must be suppressed")
        return self


def advance_exposure_episode(
    *,
    contract: RegisteredStrategyContract,
    current: ExposureEpisodeState | None,
    detector_status: DetectorStatus,
    occurred_at_ms: int | None,
    observed_at_ms: int,
    exchange_instrument_id: str,
) -> ExposureEpisodeTransition:
    """Apply one valid closed-bar result to a rising-edge Episode projection."""

    if contract.episode_policy != "rising_edge":
        raise ValueError("rising-edge reducer requires a rising-edge Event contract")
    if detector_status not in {
        DetectorStatus.TRIGGERED,
        DetectorStatus.NOT_TRIGGERED,
    }:
        raise ValueError("Episode reducer accepts triggered or not_triggered only")
    if observed_at_ms <= 0:
        raise ValueError("Episode observation time must be positive")
    instrument_id = str(exchange_instrument_id or "").strip()
    if not instrument_id:
        raise ValueError("Episode instrument identity must be non-blank")
    if detector_status is DetectorStatus.TRIGGERED:
        if occurred_at_ms is None or occurred_at_ms <= 0:
            raise ValueError("triggered Episode transition requires occurrence time")
    elif occurred_at_ms is not None:
        raise ValueError("not-triggered Episode transition forbids occurrence time")

    domain_key = build_episode_domain_key(
        event_spec_id=contract.event_spec_id,
        exchange_instrument_id=instrument_id,
        position_side=contract.position_side,
    )
    if current is not None:
        if (
            current.episode_domain_key != domain_key
            or current.event_spec_id != contract.event_spec_id
            or current.exchange_instrument_id != instrument_id
            or current.position_side != contract.position_side
        ):
            raise ValueError("Exposure Episode current state identity differs")
        if observed_at_ms < current.last_observed_at_ms:
            raise ValueError("Exposure Episode observation cannot move backwards")
        if observed_at_ms == current.last_observed_at_ms:
            expected_state = (
                "triggered"
                if detector_status is DetectorStatus.TRIGGERED
                else "armed"
            )
            if current.state != expected_state:
                raise ValueError("same Episode observation has contradictory result")
            return ExposureEpisodeTransition(
                current=current,
                exposure_episode_id=current.exposure_episode_id,
                created_new_episode=False,
            )

    version = 1 if current is None else current.projection_version + 1
    rearmed_at_ms = None if current is None else current.rearmed_at_ms
    if detector_status is DetectorStatus.NOT_TRIGGERED:
        if current is None or current.state == "triggered":
            rearmed_at_ms = observed_at_ms
        state = ExposureEpisodeState(
            episode_domain_key=domain_key,
            event_spec_id=contract.event_spec_id,
            exchange_instrument_id=instrument_id,
            position_side=contract.position_side,
            state="armed",
            exposure_episode_id=None,
            triggered_at_ms=None,
            rearmed_at_ms=rearmed_at_ms,
            last_observed_at_ms=observed_at_ms,
            projection_version=version,
        )
        return ExposureEpisodeTransition(
            current=state,
            exposure_episode_id=None,
            created_new_episode=False,
        )

    if current is not None and current.state == "triggered":
        episode_id = current.exposure_episode_id
        triggered_at_ms = current.triggered_at_ms
        created_new_episode = False
    else:
        if occurred_at_ms is None:
            raise AssertionError("validated Episode occurrence disappeared")
        episode_id = build_exposure_episode_id(
            event_spec_id=contract.event_spec_id,
            exchange_instrument_id=instrument_id,
            position_side=contract.position_side,
            occurred_at_ms=occurred_at_ms,
        )
        triggered_at_ms = occurred_at_ms
        created_new_episode = True
    state = ExposureEpisodeState(
        episode_domain_key=domain_key,
        event_spec_id=contract.event_spec_id,
        exchange_instrument_id=instrument_id,
        position_side=contract.position_side,
        state="triggered",
        exposure_episode_id=episode_id,
        triggered_at_ms=triggered_at_ms,
        rearmed_at_ms=rearmed_at_ms,
        last_observed_at_ms=observed_at_ms,
        projection_version=version,
    )
    return ExposureEpisodeTransition(
        current=state,
        exposure_episode_id=episode_id,
        created_new_episode=created_new_episode,
    )


def advance_comparison_bound_exposure_episode(
    *,
    contract: RegisteredStrategyContract,
    current_episode: ExposureEpisodeState | None,
    current_checkpoint: ComparisonBindingEpisodeCheckpoint | None,
    detector_status: DetectorStatus,
    occurred_at_ms: int | None,
    observed_at_ms: int,
    exchange_instrument_id: str,
    comparison_binding_digest: str,
    comparison_transition_revision: int,
) -> ComparisonBoundExposureEpisodeTransition:
    """Advance a rising-edge scope without trusting a prior comparison arm.

    A binding digest or transition revision change enters REBASE_REQUIRED.  A
    first trigger there is observation-only.  A later valid NOT_TRIGGERED
    creates the arm under the target binding; only a strictly later trigger may
    proceed to the ordinary rising-edge reducer.
    """

    _validate_comparison_request(
        contract=contract,
        detector_status=detector_status,
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=observed_at_ms,
        exchange_instrument_id=exchange_instrument_id,
        comparison_binding_digest=comparison_binding_digest,
        comparison_transition_revision=comparison_transition_revision,
    )
    domain_key = build_episode_domain_key(
        event_spec_id=contract.event_spec_id,
        exchange_instrument_id=exchange_instrument_id,
        position_side=contract.position_side,
    )
    if current_episode is not None and current_episode.episode_domain_key != domain_key:
        raise ValueError("comparison Episode state identity differs")
    if current_checkpoint is not None and current_checkpoint.episode_domain_key != domain_key:
        raise ValueError("comparison checkpoint Episode identity differs")

    binding_changed = current_checkpoint is None or (
        current_checkpoint.comparison_binding_digest != comparison_binding_digest
        or current_checkpoint.comparison_transition_revision
        != comparison_transition_revision
    )
    if binding_changed:
        if (
            current_checkpoint is not None
            and observed_at_ms <= current_checkpoint.last_observed_at_ms
        ):
            raise ValueError("comparison transition must use a later Observation close")
        if detector_status is DetectorStatus.TRIGGERED:
            return ComparisonBoundExposureEpisodeTransition(
                checkpoint=ComparisonBindingEpisodeCheckpoint(
                    episode_domain_key=domain_key,
                    comparison_binding_digest=comparison_binding_digest,
                    comparison_transition_revision=comparison_transition_revision,
                    state=ComparisonBindingEpisodeState.REBASE_REQUIRED,
                    armed_at_ms=None,
                    last_observed_at_ms=observed_at_ms,
                    last_detector_status=DetectorStatus.TRIGGERED,
                    projection_version=(
                        1
                        if current_checkpoint is None
                        else current_checkpoint.projection_version + 1
                    ),
                ),
                episode_transition=None,
                signal_eligible=False,
                suppression_reason="COMPARISON_REBASE_REQUIRED",
            )
        return _arm_under_comparison_binding(
            contract=contract,
            current_episode=current_episode,
            current_checkpoint=current_checkpoint,
            detector_status=detector_status,
            occurred_at_ms=occurred_at_ms,
            observed_at_ms=observed_at_ms,
            exchange_instrument_id=exchange_instrument_id,
            comparison_binding_digest=comparison_binding_digest,
            comparison_transition_revision=comparison_transition_revision,
        )

    if current_checkpoint is None:
        raise AssertionError("unchanged comparison binding lost its checkpoint")
    if observed_at_ms < current_checkpoint.last_observed_at_ms:
        raise ValueError("comparison Observation cannot move backwards")
    if observed_at_ms == current_checkpoint.last_observed_at_ms:
        if detector_status is not current_checkpoint.last_detector_status:
            raise ValueError("same comparison Observation has contradictory result")
        if current_checkpoint.state is ComparisonBindingEpisodeState.REBASE_REQUIRED:
            return ComparisonBoundExposureEpisodeTransition(
                checkpoint=current_checkpoint,
                episode_transition=None,
                signal_eligible=False,
                suppression_reason="COMPARISON_REBASE_REQUIRED",
            )

    if current_checkpoint.state is ComparisonBindingEpisodeState.REBASE_REQUIRED:
        if detector_status is DetectorStatus.TRIGGERED:
            return ComparisonBoundExposureEpisodeTransition(
                checkpoint=current_checkpoint.model_copy(
                    update={
                        "last_observed_at_ms": observed_at_ms,
                        "last_detector_status": DetectorStatus.TRIGGERED,
                        "projection_version": current_checkpoint.projection_version + 1,
                    }
                ),
                episode_transition=None,
                signal_eligible=False,
                suppression_reason="COMPARISON_REBASE_REQUIRED",
            )
        return _arm_under_comparison_binding(
            contract=contract,
            current_episode=current_episode,
            current_checkpoint=current_checkpoint,
            detector_status=detector_status,
            occurred_at_ms=occurred_at_ms,
            observed_at_ms=observed_at_ms,
            exchange_instrument_id=exchange_instrument_id,
            comparison_binding_digest=comparison_binding_digest,
            comparison_transition_revision=comparison_transition_revision,
        )

    armed_at_ms = current_checkpoint.armed_at_ms
    if armed_at_ms is None:
        raise AssertionError("armed comparison checkpoint lost arming time")
    if detector_status is DetectorStatus.TRIGGERED and observed_at_ms <= armed_at_ms:
        raise ValueError("comparison trigger must be later than its arming close")
    episode_transition = advance_exposure_episode(
        contract=contract,
        current=current_episode,
        detector_status=detector_status,
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=observed_at_ms,
        exchange_instrument_id=exchange_instrument_id,
    )
    checkpoint = current_checkpoint.model_copy(
        update={
            "last_observed_at_ms": observed_at_ms,
            "last_detector_status": detector_status,
            "projection_version": current_checkpoint.projection_version + 1,
        }
    )
    return ComparisonBoundExposureEpisodeTransition(
        checkpoint=checkpoint,
        episode_transition=episode_transition,
        signal_eligible=detector_status is DetectorStatus.TRIGGERED,
        suppression_reason=None,
    )


def _arm_under_comparison_binding(
    *,
    contract: RegisteredStrategyContract,
    current_episode: ExposureEpisodeState | None,
    current_checkpoint: ComparisonBindingEpisodeCheckpoint | None,
    detector_status: DetectorStatus,
    occurred_at_ms: int | None,
    observed_at_ms: int,
    exchange_instrument_id: str,
    comparison_binding_digest: str,
    comparison_transition_revision: int,
) -> ComparisonBoundExposureEpisodeTransition:
    if detector_status is not DetectorStatus.NOT_TRIGGERED or occurred_at_ms is not None:
        raise AssertionError("comparison binding arm requires validated NOT_TRIGGERED")
    episode_transition = advance_exposure_episode(
        contract=contract,
        current=current_episode,
        detector_status=detector_status,
        occurred_at_ms=None,
        observed_at_ms=observed_at_ms,
        exchange_instrument_id=exchange_instrument_id,
    )
    return ComparisonBoundExposureEpisodeTransition(
        checkpoint=ComparisonBindingEpisodeCheckpoint(
            episode_domain_key=episode_transition.current.episode_domain_key,
            comparison_binding_digest=comparison_binding_digest,
            comparison_transition_revision=comparison_transition_revision,
            state=ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
            armed_at_ms=observed_at_ms,
            last_observed_at_ms=observed_at_ms,
            last_detector_status=DetectorStatus.NOT_TRIGGERED,
            projection_version=(
                1 if current_checkpoint is None else current_checkpoint.projection_version + 1
            ),
        ),
        episode_transition=episode_transition,
        signal_eligible=False,
        suppression_reason=None,
    )


def _validate_comparison_request(
    *,
    contract: RegisteredStrategyContract,
    detector_status: DetectorStatus,
    occurred_at_ms: int | None,
    observed_at_ms: int,
    exchange_instrument_id: str,
    comparison_binding_digest: str,
    comparison_transition_revision: int,
) -> None:
    if contract.episode_policy != "rising_edge":
        raise ValueError("comparison barrier requires a rising-edge Event contract")
    if detector_status not in {DetectorStatus.TRIGGERED, DetectorStatus.NOT_TRIGGERED}:
        raise ValueError("comparison barrier accepts triggered or not_triggered only")
    if observed_at_ms <= 0 or not str(exchange_instrument_id or "").strip():
        raise ValueError("comparison barrier Observation identity is invalid")
    if comparison_transition_revision <= 0:
        raise ValueError("comparison transition revision must be positive")
    ComparisonBindingEpisodeCheckpoint(
        episode_domain_key="validation",
        comparison_binding_digest=comparison_binding_digest,
        comparison_transition_revision=comparison_transition_revision,
        state=ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
        armed_at_ms=observed_at_ms,
        last_observed_at_ms=observed_at_ms,
        last_detector_status=DetectorStatus.NOT_TRIGGERED,
        projection_version=1,
    )
    if detector_status is DetectorStatus.TRIGGERED:
        if occurred_at_ms is None or occurred_at_ms <= 0:
            raise ValueError("triggered comparison barrier requires occurrence time")
    elif occurred_at_ms is not None:
        raise ValueError("not-triggered comparison barrier forbids occurrence time")


def build_episode_domain_key(
    *,
    event_spec_id: str,
    exchange_instrument_id: str,
    position_side: Literal["long", "short"],
) -> str:
    return _digest(
        "episode-domain",
        {
            "event_spec_id": event_spec_id,
            "exchange_instrument_id": exchange_instrument_id,
            "position_side": position_side,
        },
    )


def build_exposure_episode_id(
    *,
    event_spec_id: str,
    exchange_instrument_id: str,
    position_side: Literal["long", "short"],
    occurred_at_ms: int,
) -> str:
    if occurred_at_ms <= 0:
        raise ValueError("Exposure Episode occurrence time must be positive")
    return _digest(
        "episode",
        {
            "event_spec_id": event_spec_id,
            "exchange_instrument_id": exchange_instrument_id,
            "position_side": position_side,
            "occurred_at_ms": occurred_at_ms,
        },
    )


def _digest(prefix: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{prefix}:{sha256(canonical).hexdigest()}"
