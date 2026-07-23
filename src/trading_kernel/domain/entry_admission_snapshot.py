"""One immutable venue observation cycle used by every new-ENTRY decision."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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


class AdmissionInstrumentFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    mark_price: Decimal
    configured_leverage: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        return _require_identity(value, label="instrument identity")

    @field_validator("mark_price")
    @classmethod
    def _require_finite_positive_mark(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("mark price must be finite and positive")
        return value

    @field_validator("configured_leverage", mode="before")
    @classmethod
    def _require_positive_integer_leverage(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("configured leverage must be an integer")
        return value


class AdmissionPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal | None

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        return _require_identity(value, label="position instrument identity")

    @field_validator("quantity")
    @classmethod
    def _require_finite_nonnegative_quantity(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("position quantity must be finite and nonnegative")
        return value

    @field_validator("average_entry_price")
    @classmethod
    def _require_finite_positive_average(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("average entry price must be finite and positive")
        return value

    @model_validator(mode="after")
    def _require_average_for_open_position(self) -> "AdmissionPosition":
        if self.quantity > 0 and self.average_entry_price is None:
            raise ValueError("open position requires average entry price")
        if self.quantity == 0 and self.average_entry_price is not None:
            raise ValueError("flat position forbids average entry price")
        return self


class AdmissionOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str
    venue_client_order_id: str | None
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    reduce_only: bool

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


class AdmissionOwnership(BaseModel):
    """Current kernel-owned external identities loaded before classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    owned_position_domain_keys: tuple[str, ...] = ()
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


class EntryAdmissionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    position_mode: Literal["independent_sides", "one_way"]
    margin_mode: Literal["cross", "isolated"]
    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    total_maintenance_margin: Decimal
    available_margin: Decimal
    best_bid_price: Decimal
    best_ask_price: Decimal
    instrument_facts: tuple[AdmissionInstrumentFacts, ...]
    positions: tuple[AdmissionPosition, ...]
    open_orders: tuple[AdmissionOrder, ...]
    observed_at_ms: int
    valid_until_ms: int

    @field_validator("venue_id", "account_id", mode="before")
    @classmethod
    def _require_snapshot_identity(cls, value: object) -> str:
        return _require_identity(value, label="snapshot identity")

    @field_validator(
        "total_wallet_balance",
        "total_margin_balance",
        "total_initial_margin",
        "total_maintenance_margin",
        "available_margin",
    )
    @classmethod
    def _require_finite_nonnegative_financial(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("admission financial facts must be finite and nonnegative")
        return value

    @field_validator("best_bid_price", "best_ask_price")
    @classmethod
    def _require_finite_positive_quote(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("admission quote must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_shape(self) -> "EntryAdmissionSnapshot":
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("admission snapshot window must be positive and ordered")
        if self.best_ask_price < self.best_bid_price:
            raise ValueError("admission best ask cannot be below best bid")
        instruments = tuple(item.exchange_instrument_id for item in self.instrument_facts)
        position_keys = tuple(
            f"{item.exchange_instrument_id}:{item.position_side}"
            for item in self.positions
        )
        order_ids = tuple(item.exchange_order_id for item in self.open_orders)
        if not instruments or len(set(instruments)) != len(instruments):
            raise ValueError("admission snapshot requires unique instrument facts")
        if len(set(position_keys)) != len(position_keys):
            raise ValueError("admission snapshot position sides must be unique")
        if len(set(order_ids)) != len(order_ids):
            raise ValueError("admission snapshot order identities must be unique")
        return self

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="python"))

    def instrument_facts_for(self, exchange_instrument_id: str) -> AdmissionInstrumentFacts:
        normalized = _require_identity(
            exchange_instrument_id,
            label="requested instrument identity",
        )
        for facts in self.instrument_facts:
            if facts.exchange_instrument_id == normalized:
                return facts
        raise ValueError("admission snapshot lacks requested instrument facts")

    def position_domain_key(self, position: AdmissionPosition) -> str:
        return (
            f"{self.venue_id}:{self.account_id}:"
            f"{position.exchange_instrument_id}:{position.position_side}"
        )
