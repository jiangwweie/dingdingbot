"""Pure runtime-lane identity and source-lineage conservation guards."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.runtime_lane_identity import (
    RuntimeLaneIdentity,
    RuntimeLaneIdentityMismatch,
)


class RuntimeLaneLineage(BaseModel):
    """Immutable reference carried from a named signal to its Ticket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lane_identity_key: str = Field(min_length=1, max_length=192)
    signal_event_id: str = Field(min_length=1, max_length=192)
    source_watermark: str = Field(min_length=1, max_length=256)

    @field_validator(
        "lane_identity_key",
        "signal_event_id",
        "source_watermark",
        mode="before",
    )
    @classmethod
    def _require_nonblank_string(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runtime lane lineage field must be nonblank")
        return normalized


class RuntimeLaneIdentityConservationError(ValueError):
    """Typed blocker for an incomplete or altered persisted lineage."""

    def __init__(self, blocker: str) -> None:
        super().__init__(blocker)
        self.blocker = blocker


def require_runtime_lane_identity_match(
    *,
    expected: RuntimeLaneIdentity,
    actual: RuntimeLaneIdentity,
    boundary: str,
) -> None:
    """Reject a downstream representation that changes the resolved lane."""

    if expected != actual:
        raise RuntimeLaneIdentityMismatch(
            boundary=boundary,
            expected=expected,
            actual=actual,
        )


def require_runtime_lane_lineage_match(
    *,
    expected: RuntimeLaneLineage,
    actual: RuntimeLaneLineage,
    boundary: str,
) -> None:
    """Reject reuse of a lane by another source event or source watermark."""

    if expected != actual:
        error = RuntimeLaneIdentityMismatch(
            boundary=boundary,
            expected=expected,  # type: ignore[arg-type]
            actual=actual,  # type: ignore[arg-type]
        )
        raise error


def runtime_lane_identity_from_live_signal(
    row: Mapping[str, Any],
) -> RuntimeLaneIdentity:
    """Rehydrate the complete identity from typed live-signal columns only."""

    try:
        identity = RuntimeLaneIdentity.model_validate(
            {field: row.get(field) for field in RuntimeLaneIdentity.model_fields}
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeLaneIdentityConservationError(
            "runtime_lane_identity_mismatch:live_signal_typed_identity"
        ) from exc

    persisted_key = str(row.get("lane_identity_key") or "").strip()
    if persisted_key != identity.identity_key:
        raise RuntimeLaneIdentityConservationError(
            "runtime_lane_identity_mismatch:live_signal_identity_key"
        )
    return identity


def runtime_lane_lineage_from_record(
    row: Mapping[str, Any],
) -> RuntimeLaneLineage:
    """Read the compact immutable lineage carried by downstream rows."""

    try:
        return RuntimeLaneLineage(
            lane_identity_key=row.get("lane_identity_key"),
            signal_event_id=row.get("signal_event_id"),
            source_watermark=row.get("source_watermark"),
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeLaneIdentityConservationError(
            "runtime_lane_identity_mismatch:source_lineage_missing"
        ) from exc
