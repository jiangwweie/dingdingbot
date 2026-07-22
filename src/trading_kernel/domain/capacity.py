"""Immutable action-time capacity authority for one Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.ticket import EntryOrderType, TradeTicket


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class CapacityClaimStatus(StrEnum):
    CLAIMED = "claimed"
    SIGNAL_INVALID_OR_STALE = "signal_invalid_or_stale"
    SCOPE_OR_POLICY_MISMATCH = "scope_or_policy_mismatch"
    ACTION_FACTS_INVALID_OR_STALE = "action_facts_invalid_or_stale"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    INSTRUMENT_RULES_INVALID = "instrument_rules_invalid"
    NETTING_DOMAIN_OCCUPIED = "netting_domain_occupied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROTECTION_UNAVAILABLE = "protection_unavailable"


class ActionTimeFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    runtime_scope_id: str
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    best_bid_price: Decimal
    best_ask_price: Decimal
    account_equity: Decimal
    available_margin: Decimal
    netting_domain_position_qty: Decimal
    netting_domain_open_order_count: int
    observed_at_ms: int
    valid_until_ms: int

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
            raise ValueError("action-time identities must be non-blank")
        return normalized

    @field_validator("best_bid_price", "best_ask_price", "account_equity")
    @classmethod
    def _require_positive_value(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("action-time prices and equity must be positive")
        return value

    @field_validator("available_margin", "netting_domain_position_qty")
    @classmethod
    def _require_nonnegative_value(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("action-time margin and position must be nonnegative")
        return value

    @field_validator("netting_domain_open_order_count")
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("open-order count must be nonnegative")
        return value

    @model_validator(mode="after")
    def _validate_window_and_spread(self) -> "ActionTimeFacts":
        if (
            self.observed_at_ms <= 0
            or self.valid_until_ms <= self.observed_at_ms
        ):
            raise ValueError("action-time fact window must be positive")
        if self.best_ask_price < self.best_bid_price:
            raise ValueError("best ask cannot be below best bid")
        return self

    def digest(self) -> str:
        return _digest(self.model_dump(mode="python"))


class CapacityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_policy_id: str
    policy_version: int
    max_concurrent_tickets: int
    max_gross_notional: Decimal
    max_gross_risk_at_stop: Decimal
    max_ticket_risk_at_stop: Decimal
    target_leverage: Decimal

    @field_validator("owner_policy_id", mode="before")
    @classmethod
    def _require_policy_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("capacity policy identity must be non-blank")
        return normalized

    @field_validator("policy_version", "max_concurrent_tickets")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("capacity policy versions and counts must be positive")
        return value

    @field_validator(
        "max_gross_notional",
        "max_gross_risk_at_stop",
        "max_ticket_risk_at_stop",
        "target_leverage",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("capacity policy financial limits must be positive")
        return value


class CapacityUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    gross_notional: Decimal
    gross_risk_at_stop: Decimal
    active_ticket_count: int

    @field_validator("gross_notional", "gross_risk_at_stop")
    @classmethod
    def _require_nonnegative_decimal(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("capacity usage cannot be negative")
        return value

    @field_validator("active_ticket_count")
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("active Ticket count cannot be negative")
        return value


class CapacityInstrumentRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    projection_version: int
    observed_at_ms: int
    valid_until_ms: int

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
    def _validate_rule_authority(self) -> "CapacityInstrumentRules":
        if (
            self.projection_version <= 0
            or self.observed_at_ms <= 0
            or self.valid_until_ms <= self.observed_at_ms
        ):
            raise ValueError("instrument rule identity must be current and versioned")
        return self


class CapacityClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    capacity_claim_id: str
    ticket_identity: TicketIdentity
    owner_policy_id: str
    owner_policy_version: int
    runtime_scope_id: str
    runtime_scope_version: int
    fact_digest: str
    action_facts_digest: str
    instrument_rules_projection_version: int
    created_at_ms: int
    expires_at_ms: int
    entry_reference_price: Decimal
    quantity: Decimal
    notional: Decimal
    leverage: Decimal
    risk_at_stop: Decimal
    entry_order_type: EntryOrderType
    entry_limit_price: Decimal | None
    initial_stop_price: Decimal
    take_profit_prices: tuple[Decimal, ...]
    decision_digest: str

    @field_validator(
        "capacity_claim_id",
        "owner_policy_id",
        "runtime_scope_id",
        mode="before",
    )
    @classmethod
    def _require_claim_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("CapacityClaim identities must be non-blank")
        return normalized

    @field_validator("fact_digest", "action_facts_digest", "decision_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("CapacityClaim digests must be canonical sha256 values")
        return value

    @field_validator(
        "entry_reference_price",
        "quantity",
        "notional",
        "leverage",
        "initial_stop_price",
    )
    @classmethod
    def _require_positive_financial(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("CapacityClaim financial values must be positive")
        return value

    @field_validator("risk_at_stop")
    @classmethod
    def _require_nonnegative_risk(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("CapacityClaim risk cannot be negative")
        return value

    @model_validator(mode="after")
    def _validate_claim(self) -> "CapacityClaim":
        if (
            self.owner_policy_version <= 0
            or self.runtime_scope_version <= 0
            or self.instrument_rules_projection_version <= 0
            or self.created_at_ms <= 0
            or self.expires_at_ms <= self.created_at_ms
        ):
            raise ValueError("CapacityClaim authority and time must be positive")
        if self.entry_order_type is EntryOrderType.MARKET:
            if self.entry_limit_price is not None:
                raise ValueError("market CapacityClaim forbids a limit price")
        elif self.entry_limit_price is None or self.entry_limit_price <= 0:
            raise ValueError("limit CapacityClaim requires a positive limit price")
        expected_digest = build_capacity_claim_digest(self)
        if expected_digest != self.decision_digest:
            raise ValueError("CapacityClaim decision digest differs from its payload")
        if self.capacity_claim_id != f"claim:{expected_digest.removeprefix('sha256:')[:32]}":
            raise ValueError("CapacityClaim identity differs from its decision digest")
        return self

    def to_ticket(self) -> TradeTicket:
        return TradeTicket(
            identity=self.ticket_identity,
            owner_policy_id=self.owner_policy_id,
            owner_policy_version=self.owner_policy_version,
            runtime_scope_id=self.runtime_scope_id,
            runtime_scope_version=self.runtime_scope_version,
            fact_digest=self.fact_digest,
            created_at_ms=self.created_at_ms,
            expires_at_ms=self.expires_at_ms,
            entry_reference_price=self.entry_reference_price,
            quantity=self.quantity,
            notional=self.notional,
            leverage=self.leverage,
            risk_at_stop=self.risk_at_stop,
            entry_order_type=self.entry_order_type,
            entry_limit_price=self.entry_limit_price,
            initial_stop_price=self.initial_stop_price,
            take_profit_prices=self.take_profit_prices,
        )


class CapacityClaimDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CapacityClaimStatus
    claim: CapacityClaim | None

    @model_validator(mode="after")
    def _validate_decision_shape(self) -> "CapacityClaimDecision":
        if (self.status is CapacityClaimStatus.CLAIMED) != (self.claim is not None):
            raise ValueError("claimed decisions require exactly one CapacityClaim")
        return self


def freeze_capacity_claim(
    *,
    ticket_identity: TicketIdentity,
    owner_policy_id: str,
    owner_policy_version: int,
    runtime_scope_id: str,
    runtime_scope_version: int,
    fact_digest: str,
    action_facts_digest: str,
    instrument_rules_projection_version: int,
    created_at_ms: int,
    expires_at_ms: int,
    entry_reference_price: Decimal,
    quantity: Decimal,
    notional: Decimal,
    leverage: Decimal,
    risk_at_stop: Decimal,
    entry_order_type: EntryOrderType,
    entry_limit_price: Decimal | None,
    initial_stop_price: Decimal,
    take_profit_prices: tuple[Decimal, ...],
) -> CapacityClaim:
    payload: dict[str, Any] = {
        "capacity_claim_id": "claim:pending",
        "ticket_identity": ticket_identity,
        "owner_policy_id": owner_policy_id,
        "owner_policy_version": owner_policy_version,
        "runtime_scope_id": runtime_scope_id,
        "runtime_scope_version": runtime_scope_version,
        "fact_digest": fact_digest,
        "action_facts_digest": action_facts_digest,
        "instrument_rules_projection_version": instrument_rules_projection_version,
        "created_at_ms": created_at_ms,
        "expires_at_ms": expires_at_ms,
        "entry_reference_price": entry_reference_price,
        "quantity": quantity,
        "notional": notional,
        "leverage": leverage,
        "risk_at_stop": risk_at_stop,
        "entry_order_type": entry_order_type,
        "entry_limit_price": entry_limit_price,
        "initial_stop_price": initial_stop_price,
        "take_profit_prices": take_profit_prices,
        "decision_digest": "sha256:" + "0" * 64,
    }
    provisional = CapacityClaim.model_construct(**payload)
    decision_digest = build_capacity_claim_digest(provisional)
    return CapacityClaim.model_validate(
        {
            **payload,
            "capacity_claim_id": (
                f"claim:{decision_digest.removeprefix('sha256:')[:32]}"
            ),
            "decision_digest": decision_digest,
        }
    )


def build_capacity_claim_digest(claim: CapacityClaim) -> str:
    return _digest(
        claim.model_dump(
            mode="python",
            exclude={"capacity_claim_id", "decision_digest"},
        )
    )


def _digest(payload: object) -> str:
    canonical = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _canonicalize(value: object) -> object:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value
