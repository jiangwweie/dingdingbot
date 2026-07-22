"""Immutable execution decision for one exposure episode."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)


class EntryOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TicketStatus(StrEnum):
    ISSUED = "issued"
    EXPIRED_BEFORE_SUBMIT = "expired_before_submit"
    ENTRY_REJECTED = "entry_rejected"
    TERMINAL = "terminal"


class TradeTicket(BaseModel):
    """Complete post-Action-Time decision consumed by the trading kernel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: TicketIdentity
    owner_policy_version_id: str
    runtime_scope_version_id: str
    fact_digest: str
    created_at_ms: int
    expires_at_ms: int
    quantity: Decimal
    notional: Decimal
    leverage: Decimal
    risk_at_stop: Decimal
    entry_order_type: EntryOrderType
    entry_limit_price: Decimal | None = None
    initial_stop_price: Decimal
    take_profit_prices: tuple[Decimal, ...] = ()
    status: TicketStatus = TicketStatus.ISSUED

    @field_validator(
        "owner_policy_version_id",
        "runtime_scope_version_id",
        "fact_digest",
        mode="before",
    )
    @classmethod
    def _require_non_blank_reference(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("ticket references must be non-blank strings")
        return value.strip()

    @field_validator(
        "quantity",
        "notional",
        "leverage",
        "initial_stop_price",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("financial value must be positive")
        return value

    @field_validator("risk_at_stop")
    @classmethod
    def _require_nonnegative_risk(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("risk_at_stop must be nonnegative")
        return value

    @field_validator("take_profit_prices")
    @classmethod
    def _require_positive_take_profit_prices(
        cls,
        values: tuple[Decimal, ...],
    ) -> tuple[Decimal, ...]:
        if any(value <= 0 for value in values):
            raise ValueError("take-profit prices must be positive")
        return values

    @model_validator(mode="after")
    def _validate_deadline_and_order_shape(self) -> "TradeTicket":
        if self.expires_at_ms <= self.created_at_ms:
            raise ValueError("ticket expiry must be after creation")
        if self.entry_order_type is EntryOrderType.LIMIT:
            if self.entry_limit_price is None or self.entry_limit_price <= 0:
                raise ValueError("limit entry requires a positive limit price")
        elif self.entry_limit_price is not None:
            raise ValueError("market entry forbids a limit price")
        return self

    def decision_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status"})
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{sha256(encoded).hexdigest()}"


def build_ticket_id(
    *,
    signal_event_id: str,
    runtime: RuntimeIdentity,
    netting_domain: NettingDomain,
) -> str:
    """Build the one deterministic Ticket identity for a causal signal."""

    normalized_signal_id = str(signal_event_id or "").strip()
    if not normalized_signal_id:
        raise ValueError("signal_event_id must be non-blank")
    payload = {
        "signal_event_id": normalized_signal_id,
        "runtime": runtime.model_dump(mode="json"),
        "netting_domain": netting_domain.model_dump(mode="json"),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"ticket:{sha256(encoded).hexdigest()[:32]}"
