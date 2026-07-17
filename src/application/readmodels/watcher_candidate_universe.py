"""Bounded current projection used by the production watcher."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _FrozenProjectionModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_name=True,
    )


class WatcherCandidateScopeRow(_FrozenProjectionModel):
    candidate_scope_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    exchange_instrument_id: str = Field(min_length=1)
    asset_class: str = Field(min_length=1)
    side: Literal["long", "short"]
    policy_current_id: str = Field(min_length=1)
    status: Literal["active"]


class WatcherCandidateEventBindingRow(_FrozenProjectionModel):
    binding_id: str = Field(min_length=1)
    candidate_scope_id: str = Field(min_length=1)
    event_spec_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: Literal["long", "short"]
    status: Literal["active"]


class WatcherRuntimeScopeBindingRow(_FrozenProjectionModel):
    runtime_scope_binding_id: str = Field(min_length=1)
    candidate_scope_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: Literal["long", "short"]
    runtime_profile_id: str = Field(min_length=1)
    status: Literal["active"]


class WatcherStrategySideEventSpecRow(_FrozenProjectionModel):
    event_spec_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    strategy_group_version_id: str = Field(min_length=1)
    event_spec_version: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    side: Literal["long", "short"]
    timeframe: str = Field(min_length=1)
    time_authority: Literal["trigger_candle_close_time_ms"]
    status: Literal["current"]


class WatcherCandidateUniverseCurrentProjection(_FrozenProjectionModel):
    schema_id: Literal["brc.watcher_candidate_universe_current.v1"] = Field(
        default="brc.watcher_candidate_universe_current.v1",
        alias="schema",
        serialization_alias="schema",
    )
    source_mode: Literal["db_backed"] = "db_backed"
    projection_target: Literal["production_current"] = "production_current"
    read_profile: Literal["watcher_candidate_universe_current"] = (
        "watcher_candidate_universe_current"
    )
    read_now_ms: int
    candidate_scope: tuple[WatcherCandidateScopeRow, ...]
    candidate_scope_event_bindings: tuple[WatcherCandidateEventBindingRow, ...]
    runtime_scope_bindings: tuple[WatcherRuntimeScopeBindingRow, ...]
    strategy_side_event_specs: tuple[WatcherStrategySideEventSpecRow, ...]

    @property
    def schema(self) -> str:
        return self.schema_id

    def to_control_state(self) -> dict[str, object]:
        return self.model_dump(mode="json", by_alias=True)
