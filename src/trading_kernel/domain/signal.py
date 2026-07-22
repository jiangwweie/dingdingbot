"""Typed strategy-to-kernel signal boundary."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator

from src.trading_kernel.domain.ticket import EntryOrderType


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class SignalFactSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_definition_id: str
    value: JsonValue
    satisfied: bool
    observed_at_ms: int
    valid_until_ms: int
    projection_version: int

    @field_validator("fact_definition_id", mode="before")
    @classmethod
    def _require_fact_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("fact definition identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_fact_window(self) -> "SignalFactSnapshot":
        if (
            self.observed_at_ms <= 0
            or self.valid_until_ms <= self.observed_at_ms
            or self.projection_version <= 0
        ):
            raise ValueError("fact snapshot time and version must be positive")
        return self


def build_signal_fact_digest(facts: Sequence[SignalFactSnapshot]) -> str:
    ordered = sorted(facts, key=lambda fact: fact.fact_definition_id)
    identities = [fact.fact_definition_id for fact in ordered]
    if len(identities) != len(set(identities)):
        raise ValueError("fact digest input contains duplicate definitions")
    canonical = json.dumps(
        [fact.model_dump(mode="json") for fact in ordered],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


class SignalTicketTerms(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity: Decimal
    notional: Decimal
    leverage: Decimal
    risk_at_stop: Decimal
    entry_order_type: EntryOrderType
    entry_limit_price: Decimal | None = None
    initial_stop_price: Decimal
    take_profit_prices: tuple[Decimal, ...] = ()

    @field_validator(
        "quantity",
        "notional",
        "leverage",
        "initial_stop_price",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("signal financial values must be positive")
        return value

    @field_validator("risk_at_stop")
    @classmethod
    def _require_nonnegative_risk(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("signal risk_at_stop must be nonnegative")
        return value

    @field_validator("take_profit_prices")
    @classmethod
    def _require_positive_take_profit_prices(
        cls,
        values: tuple[Decimal, ...],
    ) -> tuple[Decimal, ...]:
        if any(value <= 0 for value in values):
            raise ValueError("signal take-profit prices must be positive")
        return values

    @model_validator(mode="after")
    def _validate_order_shape(self) -> "SignalTicketTerms":
        if self.entry_order_type is EntryOrderType.LIMIT:
            if self.entry_limit_price is None or self.entry_limit_price <= 0:
                raise ValueError("limit signal requires a positive limit price")
        elif self.entry_limit_price is not None:
            raise ValueError("market signal forbids a limit price")
        return self


class ActionableSignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    fact_digest: str
    occurred_at_ms: int
    expires_at_ms: int
    terms: SignalTicketTerms

    @field_validator(
        "signal_event_id",
        "runtime_scope_id",
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_non_blank_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("signal identity values must be non-blank")
        return normalized

    @field_validator("fact_digest", mode="before")
    @classmethod
    def _require_fact_digest(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("signal fact digest must be an exact sha256 identity")
        return normalized

    @field_validator("runtime_scope_version")
    @classmethod
    def _require_positive_scope_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("signal runtime scope version must be positive")
        return value

    @model_validator(mode="after")
    def _validate_time_window(self) -> "ActionableSignal":
        if self.occurred_at_ms <= 0 or self.expires_at_ms <= self.occurred_at_ms:
            raise ValueError("signal expiry must follow a positive occurrence time")
        return self
