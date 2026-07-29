"""Typed exchange position and open-order truth for one Netting Domain."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.identities import NettingDomain


class VenueOrderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str
    venue_client_order_id: str | None
    position_side: Literal["long", "short"]
    reduce_only: bool
    order_namespace: Literal["regular", "conditional"] = "conditional"

    @field_validator("exchange_order_id", mode="before")
    @classmethod
    def _require_exchange_order_id(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("venue order identity must be non-blank")
        return normalized


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    netting_domain: NettingDomain
    quantity: Decimal
    average_entry_price: Decimal | None
    venue_reported_liquidation_price: Decimal | None = None
    venue_reported_liquidation_observation_status: Literal[
        "valid",
        "missing",
        "invalid",
    ] | None = None
    open_orders: tuple[VenueOrderSnapshot, ...] = ()
    observed_at_ms: int

    @model_validator(mode="before")
    @classmethod
    def _default_liquidation_observation_status(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, dict) and value.get(
            "venue_reported_liquidation_observation_status"
        ) is None:
            normalized = dict(value)
            normalized["venue_reported_liquidation_observation_status"] = (
                "valid"
                if value.get("venue_reported_liquidation_price") is not None
                else "missing"
            )
            return normalized
        return value

    @field_validator("quantity")
    @classmethod
    def _require_nonnegative_quantity(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("position quantity must be nonnegative")
        return value

    @field_validator("observed_at_ms")
    @classmethod
    def _require_positive_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("position observation time must be positive")
        return value

    @model_validator(mode="after")
    def _validate_price_shape(self) -> PositionSnapshot:
        if self.quantity > 0:
            if self.average_entry_price is None or self.average_entry_price <= 0:
                raise ValueError("open position requires average entry price")
        elif (
            self.average_entry_price is not None
            or self.venue_reported_liquidation_price is not None
        ):
            raise ValueError("flat position forbids entry and liquidation prices")
        if (
            self.venue_reported_liquidation_price is not None
            and (
                not self.venue_reported_liquidation_price.is_finite()
                or self.venue_reported_liquidation_price < 0
            )
        ):
            raise ValueError(
                "venue-reported liquidation price must be finite and nonnegative"
            )
        if (
            self.venue_reported_liquidation_observation_status == "valid"
        ) != (self.venue_reported_liquidation_price is not None):
            raise ValueError(
                "venue liquidation observation status differs from its value"
            )
        return self
