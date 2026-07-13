"""Immutable production identity for one registered runtime lane."""

from __future__ import annotations

from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuntimeLaneIdentity(BaseModel):
    """PG-resolved identity that evaluator evidence may not override."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_scope_id: str = Field(min_length=1, max_length=192)
    candidate_scope_event_binding_id: str = Field(min_length=1, max_length=192)
    runtime_scope_binding_id: str = Field(min_length=1, max_length=192)
    runtime_instance_id: str = Field(min_length=1, max_length=192)
    runtime_profile_id: str = Field(min_length=1, max_length=192)
    policy_current_id: str = Field(min_length=1, max_length=192)
    strategy_group_id: str = Field(min_length=1, max_length=128)
    strategy_group_version_id: str = Field(min_length=1, max_length=192)
    symbol: str = Field(min_length=1, max_length=128)
    asset_class: str = Field(min_length=1, max_length=96)
    side: Literal["long", "short"]
    event_spec_id: str = Field(min_length=1, max_length=192)
    event_spec_version: str = Field(min_length=1, max_length=96)
    event_id: str = Field(min_length=1, max_length=128)
    timeframe: str = Field(min_length=1, max_length=32)
    time_authority: Literal["trigger_candle_close_time_ms"]

    @field_validator(
        "candidate_scope_id",
        "candidate_scope_event_binding_id",
        "runtime_scope_binding_id",
        "runtime_instance_id",
        "runtime_profile_id",
        "policy_current_id",
        "strategy_group_id",
        "strategy_group_version_id",
        "symbol",
        "asset_class",
        "event_spec_id",
        "event_spec_version",
        "event_id",
        "timeframe",
        mode="before",
    )
    @classmethod
    def _require_nonblank_string(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runtime lane identity field must be nonblank")
        return normalized

    @property
    def identity_key(self) -> str:
        """Stable lineage key derived from all canonical identity fields."""

        fields = self.model_dump(mode="json")
        payload = "|".join(f"{key}={fields[key]}" for key in sorted(fields))
        return "runtime_lane:" + sha256(payload.encode("utf-8")).hexdigest()


class RuntimeLaneIdentityMismatch(ValueError):
    """Raised when one downstream representation changes lane identity."""

    def __init__(
        self,
        *,
        boundary: str,
        expected: RuntimeLaneIdentity,
        actual: RuntimeLaneIdentity,
    ) -> None:
        super().__init__(f"runtime_lane_identity_mismatch:{boundary}")
        self.boundary = boundary
        self.expected = expected
        self.actual = actual
