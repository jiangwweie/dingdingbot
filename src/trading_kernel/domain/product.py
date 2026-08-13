"""Immutable product compatibility and current Session facts."""

from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ProductFamily = Literal["crypto_perpetual", "tradfi_equity_perpetual"]
AssetClass = Literal["crypto", "equity"]
ContractType = Literal["PERPETUAL", "TRADIFI_PERPETUAL"]
UnderlyingType = Literal["CRYPTO", "EQUITY"]
EntrySessionPolicy = Literal["continuous", "regular_only", "reference_only"]
ProductProfileStatus = Literal["candidate", "reference", "active", "retired"]
ProductStatus = Literal["active", "inactive", "temporarily_unavailable"]
SessionState = Literal[
    "pre_market",
    "regular",
    "after_market",
    "overnight",
    "no_trading",
    "unavailable",
]
CorporateEventStatus = Literal["clear", "blocked", "unavailable"]


class ProductEntryStatus(StrEnum):
    ALLOWED = "allowed"
    PROFILE_NOT_ENTRY_CAPABLE = "profile_not_entry_capable"
    IDENTITY_MISMATCH = "identity_mismatch"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    SESSION_NOT_REGULAR = "session_not_regular"
    SNAPSHOT_STALE = "snapshot_stale"
    MARKET_FACTS_MISSING = "market_facts_missing"
    SPREAD_TOO_WIDE = "spread_too_wide"
    MARK_INDEX_DEVIATION_TOO_WIDE = "mark_index_deviation_too_wide"
    CORPORATE_EVENT_BLOCKED = "corporate_event_blocked"


class ProductCompatibilityError(RuntimeError):
    """An Event and instrument do not share the same immutable product contract."""


class ProductCompatibility(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    product_family: ProductFamily
    asset_class: AssetClass
    contract_type: ContractType
    underlying_type: UnderlyingType
    margin_asset: Literal["USDT"] = "USDT"

    @field_validator("event_spec_id", mode="before")
    @classmethod
    def _require_event_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("event_spec:"):
            raise ValueError("product compatibility requires an Event Spec identity")
        return normalized

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(self.model_dump(mode="json"))


class InstrumentProductProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    product_family: ProductFamily
    asset_class: AssetClass
    contract_type: ContractType
    underlying_type: UnderlyingType
    margin_asset: Literal["USDT"] = "USDT"
    entry_session_policy: EntrySessionPolicy
    status: ProductProfileStatus
    max_entry_spread_bps: Decimal | None = None
    max_mark_index_deviation_bps: Decimal | None = None

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("binance-usdm:"):
            raise ValueError("product profile requires a canonical instrument identity")
        return normalized

    @field_validator(
        "max_entry_spread_bps",
        "max_mark_index_deviation_bps",
    )
    @classmethod
    def _require_optional_positive_bps(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("product Entry thresholds must be finite and positive")
        return value

    @property
    def semantic_digest(self) -> str:
        return _semantic_digest(self.model_dump(mode="json"))


class ProductSessionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    product_family: ProductFamily
    product_status: ProductStatus
    session_state: SessionState
    regular_session_open_ms: int | None
    regular_session_close_ms: int | None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    funding_rate: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    best_bid_quantity: Decimal | None = None
    best_ask_quantity: Decimal | None = None
    corporate_event_status: CorporateEventStatus = "unavailable"
    observed_at_ms: int
    valid_until_ms: int
    source_ref: str

    @field_validator("exchange_instrument_id", "source_ref", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("product Session identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_snapshot(self) -> ProductSessionSnapshot:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("product Session validity window is invalid")
        session_times = (
            self.regular_session_open_ms,
            self.regular_session_close_ms,
        )
        if (session_times[0] is None) != (session_times[1] is None):
            raise ValueError("regular Session open and close must be paired")
        if (
            session_times[0] is not None
            and session_times[1] is not None
            and session_times[1] <= session_times[0]
        ):
            raise ValueError("regular Session close must follow open")
        for price in (
            self.mark_price,
            self.index_price,
            self.best_bid,
            self.best_ask,
        ):
            if price is not None and price <= 0:
                raise ValueError("product market prices must be positive")
        if (
            self.best_bid is not None
            and self.best_ask is not None
            and self.best_ask < self.best_bid
        ):
            raise ValueError("best ask cannot be below best bid")
        for quantity in (self.best_bid_quantity, self.best_ask_quantity):
            if quantity is not None and quantity < 0:
                raise ValueError("product market quantity must be nonnegative")
        return self

    def usable_for_regular_observation(self, trigger_ms: int) -> bool:
        return (
            self.product_family == "tradfi_equity_perpetual"
            and self.product_status == "active"
            and self.session_state == "regular"
            and self.observed_at_ms <= trigger_ms < self.valid_until_ms
            and self.regular_session_open_ms is not None
            and self.regular_session_close_ms is not None
        )


class ProductEntryDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ProductEntryStatus
    spread_bps: Decimal | None = None
    mark_index_deviation_bps: Decimal | None = None
    corporate_event_warning: bool = False

    @property
    def allowed(self) -> bool:
        return self.status is ProductEntryStatus.ALLOWED


def evaluate_product_entry(
    *,
    profile: InstrumentProductProfile,
    snapshot: ProductSessionSnapshot | None,
    now_ms: int,
) -> ProductEntryDecision:
    """Evaluate current TradFi Product facts without creating trade authority."""

    if now_ms <= 0:
        raise ValueError("Product Entry evaluation time must be positive")
    if (
        profile.product_family != "tradfi_equity_perpetual"
        or profile.entry_session_policy != "regular_only"
        or profile.status in {"reference", "retired"}
        or profile.max_entry_spread_bps is None
        or profile.max_mark_index_deviation_bps is None
    ):
        return ProductEntryDecision(
            status=ProductEntryStatus.PROFILE_NOT_ENTRY_CAPABLE
        )
    if (
        snapshot is None
        or snapshot.exchange_instrument_id != profile.exchange_instrument_id
        or snapshot.product_family != profile.product_family
    ):
        return ProductEntryDecision(status=ProductEntryStatus.IDENTITY_MISMATCH)
    if snapshot.product_status != "active":
        return ProductEntryDecision(status=ProductEntryStatus.PRODUCT_UNAVAILABLE)
    if snapshot.session_state != "regular":
        return ProductEntryDecision(status=ProductEntryStatus.SESSION_NOT_REGULAR)
    if not snapshot.observed_at_ms <= now_ms < snapshot.valid_until_ms:
        return ProductEntryDecision(status=ProductEntryStatus.SNAPSHOT_STALE)
    if (
        snapshot.regular_session_open_ms is None
        or snapshot.regular_session_close_ms is None
        or not snapshot.regular_session_open_ms <= now_ms < snapshot.regular_session_close_ms
        or snapshot.mark_price is None
        or snapshot.index_price is None
        or snapshot.best_bid is None
        or snapshot.best_ask is None
        or snapshot.best_bid_quantity is None
        or snapshot.best_ask_quantity is None
        or snapshot.best_bid_quantity <= 0
        or snapshot.best_ask_quantity <= 0
    ):
        return ProductEntryDecision(status=ProductEntryStatus.MARKET_FACTS_MISSING)
    midpoint = (snapshot.best_bid + snapshot.best_ask) / Decimal(2)
    spread_bps = (
        (snapshot.best_ask - snapshot.best_bid) / midpoint * Decimal(10_000)
    )
    mark_index_deviation_bps = (
        abs(snapshot.mark_price - snapshot.index_price)
        / snapshot.index_price
        * Decimal(10_000)
    )
    if spread_bps > profile.max_entry_spread_bps:
        return ProductEntryDecision(
            status=ProductEntryStatus.SPREAD_TOO_WIDE,
            spread_bps=spread_bps,
            mark_index_deviation_bps=mark_index_deviation_bps,
        )
    if mark_index_deviation_bps > profile.max_mark_index_deviation_bps:
        return ProductEntryDecision(
            status=ProductEntryStatus.MARK_INDEX_DEVIATION_TOO_WIDE,
            spread_bps=spread_bps,
            mark_index_deviation_bps=mark_index_deviation_bps,
        )
    if snapshot.corporate_event_status == "blocked":
        return ProductEntryDecision(
            status=ProductEntryStatus.CORPORATE_EVENT_BLOCKED,
            spread_bps=spread_bps,
            mark_index_deviation_bps=mark_index_deviation_bps,
        )
    return ProductEntryDecision(
        status=ProductEntryStatus.ALLOWED,
        spread_bps=spread_bps,
        mark_index_deviation_bps=mark_index_deviation_bps,
        corporate_event_warning=(
            snapshot.corporate_event_status == "unavailable"
        ),
    )


def evaluate_event_product_entry(
    *,
    compatibility: ProductCompatibility,
    profile: InstrumentProductProfile | None,
    snapshot: ProductSessionSnapshot | None,
    now_ms: int,
) -> ProductEntryDecision:
    """Fail closed on Registry/Profile drift before applying family-specific gates."""

    if profile is None:
        return ProductEntryDecision(status=ProductEntryStatus.IDENTITY_MISMATCH)
    try:
        require_product_compatibility(compatibility, profile)
    except ProductCompatibilityError:
        return ProductEntryDecision(status=ProductEntryStatus.IDENTITY_MISMATCH)
    if compatibility.product_family == "tradfi_equity_perpetual":
        return evaluate_product_entry(
            profile=profile,
            snapshot=snapshot,
            now_ms=now_ms,
        )
    return ProductEntryDecision(status=ProductEntryStatus.ALLOWED)


def require_product_compatibility(
    compatibility: ProductCompatibility,
    profile: InstrumentProductProfile,
) -> None:
    expected = (
        compatibility.product_family,
        compatibility.asset_class,
        compatibility.contract_type,
        compatibility.underlying_type,
        compatibility.margin_asset,
    )
    actual = (
        profile.product_family,
        profile.asset_class,
        profile.contract_type,
        profile.underlying_type,
        profile.margin_asset,
    )
    if (
        actual != expected
        or profile.status in {"reference", "retired"}
        or profile.entry_session_policy == "reference_only"
    ):
        raise ProductCompatibilityError("PRODUCT_COMPATIBILITY_MISMATCH")


def registered_product_compatibilities() -> tuple[ProductCompatibility, ...]:
    crypto_events = (
        "event_spec:CPM-RO-001:CPM-LONG:v3",
        "event_spec:MPG-001:MPG-LONG:v3",
        "event_spec:MI-001:MI-LONG:v3",
        "event_spec:SOR-001:SOR-LONG:v4",
        "event_spec:SOR-001:SOR-SHORT:v4",
        "event_spec:BRF2-001:BRF2-SHORT:v3",
    )
    tradfi_events = (
        "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
        "event_spec:SOR-US-EQ-PERP-001:SOR-US-SHORT-15M:v1",
    )
    return (
        *(
            ProductCompatibility(
                event_spec_id=event_spec_id,
                product_family="crypto_perpetual",
                asset_class="crypto",
                contract_type="PERPETUAL",
                underlying_type="CRYPTO",
            )
            for event_spec_id in crypto_events
        ),
        *(
            ProductCompatibility(
                event_spec_id=event_spec_id,
                product_family="tradfi_equity_perpetual",
                asset_class="equity",
                contract_type="TRADIFI_PERPETUAL",
                underlying_type="EQUITY",
            )
            for event_spec_id in tradfi_events
        ),
    )


def product_compatibility_for(event_spec_id: str) -> ProductCompatibility:
    matches = tuple(
        item
        for item in registered_product_compatibilities()
        if item.event_spec_id == event_spec_id
    )
    if len(matches) != 1:
        raise ValueError("Event must resolve exactly one Product Compatibility")
    return matches[0]


def _semantic_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
