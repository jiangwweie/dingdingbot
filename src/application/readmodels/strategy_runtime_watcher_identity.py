"""Bounded runtime identity projection for the production watcher."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WatcherCandidateLaneKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_group_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(min_length=1, max_length=160)
    side: Literal["long", "short"]


class StrategyRuntimeWatcherIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_instance_id: str = Field(min_length=1, max_length=220)
    strategy_group_id: str = Field(min_length=1, max_length=160)
    strategy_group_version_id: str = Field(min_length=1, max_length=220)
    symbol: str = Field(min_length=1, max_length=160)
    side: Literal["long", "short"]
    carrier_id: str | None = Field(default=None, max_length=220)
    status: Literal["active"] = "active"


class StrategyRuntimeWatcherIdentityPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[StrategyRuntimeWatcherIdentity, ...]
    next_cursor: str | None = None
    has_more: bool
    excluded_active_count: int = Field(ge=0)
    excluded_active_sample_ids: tuple[str, ...] = Field(max_length=32)

    @model_validator(mode="after")
    def validate_page(self) -> "StrategyRuntimeWatcherIdentityPage":
        ids = [item.runtime_instance_id for item in self.items]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("active_runtime_pagination_invalid")
        if self.has_more:
            if not ids or self.next_cursor != ids[-1]:
                raise ValueError("active_runtime_pagination_invalid")
        elif self.next_cursor is not None:
            raise ValueError("active_runtime_pagination_invalid")
        return self

