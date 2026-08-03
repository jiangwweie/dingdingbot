"""Pure rising-edge Exposure Episode identity and state transitions."""

from __future__ import annotations

import json
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
