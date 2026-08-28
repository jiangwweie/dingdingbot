"""Typed read-only fact ports used by bounded runtime workers."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskSnapshot,
    MaintenanceMarginBracket,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.order_attribution import (
    OrderRole,
    TicketOrderReference,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.domain.review import ReviewEconomicsFacts


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
    def _validate_admission_window(self) -> EntryAdmissionSnapshotRequest:
        if self.observed_at_ms <= 0 or self.valid_for_ms <= 0:
            raise ValueError("entry admission request window must be positive")
        return self


class EntryAdmissionFactsSource(Protocol):
    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot: ...


class AccountRiskSnapshotRequest(BaseModel):
    """Exact account observation requested for one risk decision."""

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
    def _require_account_risk_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("account risk request identities must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_account_risk_window(self) -> AccountRiskSnapshotRequest:
        if self.observed_at_ms <= 0 or self.valid_for_ms <= 0:
            raise ValueError("account risk request window must be positive")
        return self


class AccountRiskSnapshotSource(Protocol):
    async def read_account_risk_snapshot(
        self,
        request: AccountRiskSnapshotRequest,
    ) -> AccountRiskSnapshot: ...


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
    exchange_max_leverage: int
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
    notional_coefficient: Decimal
    notional_coefficient_certified: bool
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
        "notional_coefficient",
    )
    @classmethod
    def _require_positive_rule(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("instrument rules must be positive")
        return value

    @field_validator("exchange_max_leverage")
    @classmethod
    def _require_positive_exchange_leverage(cls, value: int) -> int:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("exchange maximum leverage must be a positive integer")
        return value

    @field_validator("maintenance_margin_brackets_digest")
    @classmethod
    def _require_bracket_digest(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if len(normalized) != 71 or not normalized.startswith("sha256:"):
            raise ValueError("maintenance brackets require a canonical digest")
        return normalized

    @model_validator(mode="after")
    def _validate_rule_window(self) -> InstrumentRulesFacts:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("instrument rule window must be current")
        if not self.maintenance_margin_brackets:
            raise ValueError("instrument rules require maintenance margin brackets")
        return self


class InstrumentRulesSource(Protocol):
    async def read_instrument_rules(
        self,
        request: InstrumentRulesRequest,
    ) -> InstrumentRulesFacts: ...


class ProductSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    observed_at_ms: int

    @field_validator(
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_product_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Product Session request identities must be non-blank")
        return normalized

    @field_validator("observed_at_ms")
    @classmethod
    def _require_product_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Product Session request time must be positive")
        return value


class ProductSessionSource(Protocol):
    async def read_product_session(
        self,
        request: ProductSessionRequest,
    ) -> ProductSessionSnapshot: ...


class EntryFactsSource(
    EntryAdmissionFactsSource,
    AccountRiskSnapshotSource,
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


class FeeDiscountCapabilityFacts(BaseModel):
    """Read-only account facts for the optional BNB fee discount."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fee_burn_enabled: bool
    bnb_futures_wallet_balance: Decimal
    observed_at_ms: int
    source: Literal["binance_usdm_readonly"]

    @field_validator("bnb_futures_wallet_balance")
    @classmethod
    def _require_nonnegative_bnb_balance(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("BNB fee capability balance must be finite and non-negative")
        return value

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_observed_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("BNB fee capability observation time must be positive")
        return value


FeeDiscountCapabilityStatus = Literal[
    "available",
    "unavailable",
    "low_balance",
    "unknown",
]


def classify_fee_discount_capability(
    facts: FeeDiscountCapabilityFacts,
    *,
    low_balance_threshold: Decimal | None = None,
) -> FeeDiscountCapabilityStatus:
    """Classify an optional cost optimization without changing trade authority."""

    if low_balance_threshold is not None and (
        not low_balance_threshold.is_finite() or low_balance_threshold <= 0
    ):
        raise ValueError("BNB low balance threshold must be finite and positive")
    if not facts.fee_burn_enabled or facts.bnb_futures_wallet_balance == 0:
        return "unavailable"
    if (
        low_balance_threshold is not None
        and facts.bnb_futures_wallet_balance < low_balance_threshold
    ):
        return "low_balance"
    return "available"


class FeeDiscountCapabilitySource(Protocol):
    async def read_fee_discount_capability(
        self,
        *,
        observed_at_ms: int,
    ) -> FeeDiscountCapabilityFacts: ...


class LifecycleFactsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    netting_domain: NettingDomain
    event_spec_id: str
    timeframe: Literal["15m", "1h"]
    entry_quantity: Decimal
    expected_position_quantity: Decimal
    entry_order_reference: TicketOrderReference
    tp1_exchange_order_id: str | None
    exposure_started_at_ms: int
    price_tick: Decimal
    structure_window_bars: int
    atr_period: int
    time_stop_max_holding_bars: int | None = None
    runner_market_required: bool
    observed_at_ms: int

    @field_validator(
        "ticket_id",
        "event_spec_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("lifecycle fact request identities must be non-blank")
        return normalized

    @field_validator("tp1_exchange_order_id", mode="before")
    @classmethod
    def _normalize_optional_identity(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("time_stop_max_holding_bars")
    @classmethod
    def _require_bounded_time_stop(
        cls,
        value: int | None,
    ) -> int | None:
        if value is not None and (value <= 0 or value > 96):
            raise ValueError("lifecycle TimeStop window must be in [1, 96]")
        return value

    @model_validator(mode="after")
    def _validate_facts(self) -> LifecycleFactsRequest:
        if self.entry_order_reference.role is not OrderRole.ENTRY:
            raise ValueError("lifecycle entry order reference must be an ENTRY")
        if self.entry_quantity <= 0 or self.expected_position_quantity < 0:
            raise ValueError("lifecycle quantities are invalid")
        if self.price_tick <= 0:
            raise ValueError("lifecycle price tick must be positive")
        if (
            self.exposure_started_at_ms <= 0
            or self.observed_at_ms < self.exposure_started_at_ms
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
    entry_order_reference: TicketOrderReference
    exit_order_references: tuple[TicketOrderReference, ...]
    entry_time_ms: int
    exit_time_ms: int
    funding_attribution_exact: bool
    observed_at_ms: int

    @field_validator(
        "ticket_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("review economics request identities must be non-blank")
        return normalized

    @field_validator("exit_order_references", mode="before")
    @classmethod
    def _normalize_exit_references(
        cls,
        value: object,
    ) -> tuple[TicketOrderReference, ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError(  # noqa: TRY004 - Pydantic must surface a ValidationError.
                "review exit order references must be a sequence"
            )
        normalized = tuple(value)
        if not normalized:
            raise ValueError("review requires exit order references")
        if any(not isinstance(item, TicketOrderReference) for item in normalized):
            raise ValueError("review exit order references must be typed")
        if len({item.command_id for item in normalized}) != len(normalized):
            raise ValueError("review exit order commands must be unique")
        return normalized

    @model_validator(mode="after")
    def _validate_review_window(self) -> ReviewEconomicsRequest:
        if self.expected_entry_quantity <= 0:
            raise ValueError("review expected entry quantity must be positive")
        if self.entry_order_reference.role is not OrderRole.ENTRY:
            raise ValueError("review entry order reference must be an ENTRY")
        if any(reference.role is not OrderRole.EXIT for reference in self.exit_order_references):
            raise ValueError("review exit order references must be EXIT commands")
        if self.entry_order_reference.command_id in {
            reference.command_id for reference in self.exit_order_references
        }:
            raise ValueError("entry command cannot also be an exit command")
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
