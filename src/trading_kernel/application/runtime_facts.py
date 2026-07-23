"""Typed read-only fact ports used by bounded runtime workers."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.capacity import ActionTimeFacts
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts
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


class EntryAdmissionSnapshotRequest(BaseModel):
    """Exact account observation requested before one new-ENTRY decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    observed_at_ms: int
    valid_for_ms: int

    @field_validator(
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_admission_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("entry admission request identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_admission_window(self) -> "EntryAdmissionSnapshotRequest":
        if self.observed_at_ms <= 0 or self.valid_for_ms <= 0:
            raise ValueError("entry admission request window must be positive")
        return self


class EntryAdmissionFactsSource(Protocol):
    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot: ...


class InstrumentRulesRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    observed_at_ms: int
    valid_for_ms: int

    @field_validator(
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_rule_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("instrument rule identities must be non-blank")
        return normalized

    @field_validator("observed_at_ms", "valid_for_ms")
    @classmethod
    def _require_positive_rule_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("instrument rule times must be positive")
        return value


class InstrumentRulesFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    observed_at_ms: int
    valid_until_ms: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("instrument rules require instrument identity")
        return normalized

    @field_validator(
        "quantity_step",
        "price_tick",
        "min_quantity",
        "min_notional",
    )
    @classmethod
    def _require_positive_rule(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("instrument rules must be positive")
        return value

    @model_validator(mode="after")
    def _validate_rule_window(self) -> "InstrumentRulesFacts":
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("instrument rule window must be current")
        return self


class InstrumentRulesSource(Protocol):
    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts: ...


class EntryFactsSource(
    EntryAdmissionFactsSource,
    ActionTimeFactsSource,
    InstrumentRulesSource,
    Protocol,
):
    pass


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


class ReviewEconomicsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    netting_domain: NettingDomain
    expected_entry_quantity: Decimal
    entry_venue_client_order_id: str
    exit_venue_client_order_ids: tuple[str, ...]
    entry_time_ms: int
    exit_time_ms: int
    funding_attribution_exact: bool
    observed_at_ms: int

    @field_validator(
        "ticket_id",
        "entry_venue_client_order_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("review economics request identities must be non-blank")
        return normalized

    @field_validator("exit_venue_client_order_ids", mode="before")
    @classmethod
    def _normalize_exit_identities(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("review exit order identities must be a sequence")
        normalized = tuple(str(item or "").strip() for item in value)
        if not normalized or any(not item for item in normalized):
            raise ValueError("review requires non-blank exit order identities")
        if len(set(normalized)) != len(normalized):
            raise ValueError("review exit order identities must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_review_window(self) -> "ReviewEconomicsRequest":
        if self.expected_entry_quantity <= 0:
            raise ValueError("review expected entry quantity must be positive")
        if self.entry_venue_client_order_id in self.exit_venue_client_order_ids:
            raise ValueError("entry order identity cannot also be an exit identity")
        if (
            self.entry_time_ms <= 0
            or self.exit_time_ms < self.entry_time_ms
            or self.observed_at_ms < self.exit_time_ms
        ):
            raise ValueError("review economics time window is invalid")
        return self


class ReviewEconomicsSource(Protocol):
    async def read_review_economics(
        self,
        request: ReviewEconomicsRequest,
    ) -> ReviewEconomicsFacts: ...
