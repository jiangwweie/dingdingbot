"""Immutable product compatibility and current Session facts."""

from __future__ import annotations

import json
from decimal import Decimal
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

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized.startswith("binance-usdm:"):
            raise ValueError("product profile requires a canonical instrument identity")
        return normalized

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
