"""Typed read-only fact ports used by bounded runtime workers."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)


class ActionTimeFactsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    runtime_scope_id: str
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    observed_at_ms: int
    valid_for_ms: int

    @field_validator(
        "signal_event_id",
        "runtime_scope_id",
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("action-time fact request identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "ActionTimeFactsRequest":
        if self.observed_at_ms <= 0 or self.valid_for_ms <= 0:
            raise ValueError("action-time fact request window must be positive")
        return self


class ActionTimeFactsSource(Protocol):
    async def read_action_time_facts(
        self,
        request: ActionTimeFactsRequest,
    ) -> ActionTimeFacts: ...


class PositionSnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    netting_domain: NettingDomain
    observed_at_ms: int

    @field_validator("ticket_id", mode="before")
    @classmethod
    def _require_ticket_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("position snapshot request requires Ticket identity")
        return normalized

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("position snapshot request time must be positive")
        return value


class PositionSnapshotSource(Protocol):
    async def read_position_snapshot(
        self,
        request: PositionSnapshotRequest,
    ) -> PositionSnapshot: ...


class LifecycleFactsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    netting_domain: NettingDomain
    event_spec_id: str
    timeframe: Literal["15m", "1h"]
    entry_quantity: Decimal
    expected_position_quantity: Decimal
    entry_venue_client_order_id: str
    tp1_venue_client_order_id: str | None
    entered_at_ms: int
    price_tick: Decimal
    structure_window_bars: int
    atr_period: int
    runner_market_required: bool
    observed_at_ms: int

    @field_validator(
        "ticket_id",
        "event_spec_id",
        "entry_venue_client_order_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("lifecycle fact request identities must be non-blank")
        return normalized

    @field_validator("tp1_venue_client_order_id", mode="before")
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_facts(self) -> "LifecycleFactsRequest":
        if self.entry_quantity <= 0 or self.expected_position_quantity < 0:
            raise ValueError("lifecycle quantities are invalid")
        if self.price_tick <= 0:
            raise ValueError("lifecycle price tick must be positive")
        if (
            self.entered_at_ms <= 0
            or self.observed_at_ms < self.entered_at_ms
            or self.structure_window_bars <= 0
            or self.atr_period <= 0
        ):
            raise ValueError("lifecycle market window is invalid")
        return self


class LifecycleFactsSource(Protocol):
    async def read_lifecycle_facts(
        self,
        request: LifecycleFactsRequest,
    ) -> TicketLifecycleFacts: ...
