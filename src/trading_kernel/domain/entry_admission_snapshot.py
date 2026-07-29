"""One immutable venue observation cycle used by every new-ENTRY decision."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
)
from src.trading_kernel.domain.incident_blocking import EntryBlockScope


def _require_identity(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-blank")
    return normalized


def _canonicalize(value: object) -> object:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    return value


def canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


class AdmissionOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str
    venue_client_order_id: str | None
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    reduce_only: bool
    order_namespace: Literal["regular", "conditional"] = "regular"
    order_side: Literal["buy", "sell"] | None = None
    quantity: Decimal | None = None
    trigger_price: Decimal | None = None
    limit_price: Decimal | None = None

    @field_validator(
        "exchange_order_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_identity_fields(cls, value: object) -> str:
        return _require_identity(value, label="order identity")

    @field_validator("venue_client_order_id", mode="before")
    @classmethod
    def _normalize_optional_client_id(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("quantity", "trigger_price", "limit_price")
    @classmethod
    def _require_optional_positive_decimal(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("open-order numeric facts must be finite and positive")
        return value


class OwnedPositionProjection(BaseModel):
    """Authoritative Kernel quantity for one currently owned NettingDomain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    netting_domain_key: str
    quantity: Decimal

    @field_validator("netting_domain_key", mode="before")
    @classmethod
    def _require_domain_key(cls, value: object) -> str:
        return _require_identity(value, label="owned position domain")

    @field_validator("quantity")
    @classmethod
    def _require_projected_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("owned position quantity must be finite and nonnegative")
        return value


class AdmissionOwnership(BaseModel):
    """Current kernel-owned external identities loaded before classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owned_position_domain_keys: tuple[str, ...] = ()
    owned_position_projections: tuple[OwnedPositionProjection, ...] = ()
    owned_exchange_order_ids: tuple[str, ...] = ()
    open_incident_scopes: tuple[EntryBlockScope, ...] = ()
    unknown_command_outcome_ticket_ids: tuple[str, ...] = ()

    @field_validator(
        "owned_position_domain_keys",
        "owned_exchange_order_ids",
        "unknown_command_outcome_ticket_ids",
    )
    @classmethod
    def _require_unique_nonblank_values(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(str(value or "").strip() for value in values)
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("ownership identities must be unique and non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_position_projections(self) -> AdmissionOwnership:
        projection_keys = tuple(
            projection.netting_domain_key
            for projection in self.owned_position_projections
        )
        if len(set(projection_keys)) != len(projection_keys):
            raise ValueError("owned position projections must be unique")
        if set(projection_keys) != set(self.owned_position_domain_keys):
            raise ValueError(
                "owned position projections must match owned domain identities"
            )
        return self

    def projected_position_quantity(
        self,
        netting_domain_key: str,
    ) -> Decimal | None:
        return next(
            (
                projection.quantity
                for projection in self.owned_position_projections
                if projection.netting_domain_key == netting_domain_key
            ),
            None,
        )


class EntryAdmissionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_risk_snapshot: AccountRiskSnapshot
    best_bid_price: Decimal
    best_ask_price: Decimal
    open_orders: tuple[AdmissionOrder, ...]
    observed_at_ms: int
    valid_until_ms: int

    @field_validator("best_bid_price", "best_ask_price")
    @classmethod
    def _require_finite_positive_quote(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("admission quote must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_shape(self) -> EntryAdmissionSnapshot:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("admission snapshot window must be positive and ordered")
        if (
            self.account_risk_snapshot.observed_at_ms != self.observed_at_ms
            or self.account_risk_snapshot.valid_until_ms != self.valid_until_ms
        ):
            raise ValueError("admission and account risk windows must agree")
        if self.best_ask_price < self.best_bid_price:
            raise ValueError("admission best ask cannot be below best bid")
        order_ids = tuple(item.exchange_order_id for item in self.open_orders)
        if len(set(order_ids)) != len(order_ids):
            raise ValueError("admission snapshot order identities must be unique")
        return self

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="python"))

    def position_domain_key(self, position: AccountRiskPosition) -> str:
        return (
            f"{self.account_risk_snapshot.venue_id}:"
            f"{self.account_risk_snapshot.account_id}:"
            f"{position.exchange_instrument_id}:{position.position_side}"
        )
