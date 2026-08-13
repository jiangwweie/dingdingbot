"""Exact bounded Owner Policy scope across multiple RuntimeProfiles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventRuntimeProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    runtime_profile_id: str

    @field_validator("event_spec_id", "runtime_profile_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Owner Policy scope identities must be non-blank")
        return normalized


class OwnerPolicyScope(BaseModel):
    """One Policy's sorted, unique Event-to-RuntimeProfile authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_runtime_profiles: tuple[EventRuntimeProfile, ...] = Field(
        min_length=1,
        max_length=64,
    )

    @model_validator(mode="after")
    def _require_sorted_unique_events(self) -> OwnerPolicyScope:
        event_ids = tuple(
            item.event_spec_id for item in self.event_runtime_profiles
        )
        if event_ids != tuple(sorted(event_ids)) or len(set(event_ids)) != len(
            event_ids
        ):
            raise ValueError(
                "Owner Policy Event-to-Profile scope must be sorted and unique"
            )
        return self

    def runtime_profile_for(self, event_spec_id: str) -> str | None:
        return next(
            (
                item.runtime_profile_id
                for item in self.event_runtime_profiles
                if item.event_spec_id == event_spec_id
            ),
            None,
        )

    def authorizes(
        self,
        *,
        event_spec_id: str,
        runtime_profile_id: str,
    ) -> bool:
        return self.runtime_profile_for(event_spec_id) == runtime_profile_id
