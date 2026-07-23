"""Immutable action-time capacity authority for one Ticket."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from enum import StrEnum
from hashlib import sha256
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.identities import TicketIdentity
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.ticket import EntryOrderType, TradeTicket


_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PERSISTED_DECIMAL_QUANTUM = Decimal("0.000000000000000001")


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


class CapacityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_policy_id: str
    policy_version: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    min_liquidation_distance_to_stop_distance_ratio: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal

    @field_validator("owner_policy_id", mode="before")
    @classmethod
    def _require_policy_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("capacity policy identity must be non-blank")
        return normalized

    @field_validator("policy_version", "max_concurrent_tickets", "max_leverage")
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("capacity policy versions and counts must be positive")
        return value

    @field_validator(
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
    )
    @classmethod
    def _require_policy_fraction(cls, value: Decimal) -> Decimal:
        if value <= 0 or value > 1:
            raise ValueError("capacity policy fractions must be in (0, 1]")
        return value

    @field_validator(
        "min_liquidation_distance_to_stop_distance_ratio",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("capacity policy safety values must be positive")
        return value

    @field_validator("max_post_fill_stop_risk_overrun_fraction")
    @classmethod
    def _require_overrun_fraction(cls, value: Decimal) -> Decimal:
        if value < 0 or value >= 1:
            raise ValueError("capacity policy post-fill overrun must be in [0, 1)")
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

    venue_id: str
    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    exchange_max_leverage: int
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
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
        if self.exchange_max_leverage <= 0 or not self.maintenance_margin_brackets:
            raise ValueError("instrument leverage and maintenance authority are required")
        if _SHA256_DIGEST.fullmatch(self.maintenance_margin_brackets_digest) is None:
            raise ValueError("instrument maintenance authority requires a digest")
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
    entry_admission_snapshot_digest: str
    account_entry_health_digest: str
    instrument_entry_health_digest: str
    instrument_rules_projection_version: int
    account_capacity_domain_key: str
    leverage_domain_key: str
    total_wallet_balance_at_claim: Decimal
    total_margin_balance_at_claim: Decimal
    total_initial_margin_at_claim: Decimal
    total_maintenance_margin_at_claim: Decimal
    available_margin_at_claim: Decimal
    mark_price_at_claim: Decimal
    position_mode_at_claim: Literal["independent_sides", "one_way"]
    margin_mode_at_claim: Literal["cross", "isolated"]
    active_ticket_count_at_claim: int
    remaining_slots_at_claim: int
    planned_stop_risk_fraction: Decimal
    planned_stop_risk_budget: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal
    post_fill_stop_risk_limit: Decimal
    max_initial_margin_utilization: Decimal
    min_liquidation_distance_to_stop_distance_ratio: Decimal
    ticket_margin_budget: Decimal
    required_leverage: int
    selected_leverage: int
    configured_leverage_at_claim: int
    leverage_change_required: bool
    exchange_max_leverage: int
    reserved_margin: Decimal
    maintenance_margin_bracket_id: str
    projected_liquidation_price: Decimal
    projected_liquidation_distance: Decimal
    projected_liquidation_distance_to_stop_distance_ratio: Decimal
    created_at_ms: int
    expires_at_ms: int
    entry_reference_price: Decimal
    quantity: Decimal
    notional: Decimal
    risk_at_stop: Decimal
    entry_order_type: EntryOrderType
    entry_limit_price: Decimal | None
    initial_stop_price: Decimal
    take_profit_prices: tuple[Decimal, ...]
    take_profit_quantities: tuple[Decimal, ...]
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

    @field_validator(
        "fact_digest",
        "entry_admission_snapshot_digest",
        "account_entry_health_digest",
        "instrument_entry_health_digest",
        "decision_digest",
    )
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("CapacityClaim digests must be canonical sha256 values")
        return value

    @field_validator(
        "entry_reference_price",
        "quantity",
        "notional",
        "initial_stop_price",
        "total_wallet_balance_at_claim",
        "total_margin_balance_at_claim",
        "available_margin_at_claim",
        "mark_price_at_claim",
        "planned_stop_risk_fraction",
        "planned_stop_risk_budget",
        "post_fill_stop_risk_limit",
        "max_initial_margin_utilization",
        "min_liquidation_distance_to_stop_distance_ratio",
        "ticket_margin_budget",
        "reserved_margin",
        "projected_liquidation_price",
        "projected_liquidation_distance",
        "projected_liquidation_distance_to_stop_distance_ratio",
    )
    @classmethod
    def _require_positive_financial(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("CapacityClaim financial values must be positive")
        return value

    @field_validator(
        "total_initial_margin_at_claim",
        "total_maintenance_margin_at_claim",
    )
    @classmethod
    def _require_nonnegative_financial(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("CapacityClaim account margin facts cannot be negative")
        return value

    @field_validator("risk_at_stop")
    @classmethod
    def _require_nonnegative_risk(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("CapacityClaim risk cannot be negative")
        return value

    @field_validator(
        "active_ticket_count_at_claim",
    )
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("CapacityClaim active count cannot be negative")
        return value

    @field_validator(
        "remaining_slots_at_claim",
        "required_leverage",
        "selected_leverage",
        "configured_leverage_at_claim",
        "exchange_max_leverage",
    )
    @classmethod
    def _require_positive_integer(cls, value: int) -> int:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("CapacityClaim integer evidence must be positive")
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
        if len(self.take_profit_prices) != len(self.take_profit_quantities):
            raise ValueError("CapacityClaim take-profit legs must align")
        if any(value <= 0 for value in self.take_profit_prices):
            raise ValueError("CapacityClaim take-profit prices must be positive")
        if any(value <= 0 for value in self.take_profit_quantities):
            raise ValueError("CapacityClaim take-profit quantities must be positive")
        if sum(self.take_profit_quantities, Decimal("0")) >= self.quantity:
            raise ValueError("CapacityClaim take-profit legs must preserve a runner")
        if self.selected_leverage > self.exchange_max_leverage:
            raise ValueError("CapacityClaim selected leverage exceeds exchange maximum")
        if self.risk_at_stop > self.planned_stop_risk_budget:
            raise ValueError("CapacityClaim stop risk exceeds its planned budget")
        if self.post_fill_stop_risk_limit < self.planned_stop_risk_budget:
            raise ValueError("CapacityClaim post-fill limit undercuts planned risk")
        if (
            self.projected_liquidation_distance_to_stop_distance_ratio
            < self.min_liquidation_distance_to_stop_distance_ratio
        ):
            raise ValueError("CapacityClaim liquidation proof is below policy")
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
            capacity_claim_id=self.capacity_claim_id,
            created_at_ms=self.created_at_ms,
            expires_at_ms=self.expires_at_ms,
            entry_reference_price=self.entry_reference_price,
            quantity=self.quantity,
            notional=self.notional,
            planned_stop_risk_budget=self.planned_stop_risk_budget,
            post_fill_stop_risk_limit=self.post_fill_stop_risk_limit,
            selected_leverage=self.selected_leverage,
            leverage_change_required=self.leverage_change_required,
            reserved_margin=self.reserved_margin,
            risk_reservation_basis="planned_stop_distance",
            margin_mode=self.margin_mode_at_claim,
            min_liquidation_distance_to_stop_distance_ratio=(
                self.min_liquidation_distance_to_stop_distance_ratio
            ),
            projected_liquidation_price=self.projected_liquidation_price,
            projected_liquidation_distance_to_stop_distance_ratio=(
                self.projected_liquidation_distance_to_stop_distance_ratio
            ),
            risk_at_stop=self.risk_at_stop,
            entry_order_type=self.entry_order_type,
            entry_limit_price=self.entry_limit_price,
            initial_stop_price=self.initial_stop_price,
            take_profit_prices=self.take_profit_prices,
            take_profit_quantities=self.take_profit_quantities,
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
    entry_admission_snapshot_digest: str,
    account_entry_health_digest: str,
    instrument_entry_health_digest: str,
    instrument_rules_projection_version: int,
    account_capacity_domain_key: str,
    leverage_domain_key: str,
    total_wallet_balance_at_claim: Decimal,
    total_margin_balance_at_claim: Decimal,
    total_initial_margin_at_claim: Decimal,
    total_maintenance_margin_at_claim: Decimal,
    available_margin_at_claim: Decimal,
    mark_price_at_claim: Decimal,
    position_mode_at_claim: Literal["independent_sides", "one_way"],
    margin_mode_at_claim: Literal["cross", "isolated"],
    active_ticket_count_at_claim: int,
    remaining_slots_at_claim: int,
    planned_stop_risk_fraction: Decimal,
    planned_stop_risk_budget: Decimal,
    max_post_fill_stop_risk_overrun_fraction: Decimal,
    post_fill_stop_risk_limit: Decimal,
    max_initial_margin_utilization: Decimal,
    min_liquidation_distance_to_stop_distance_ratio: Decimal,
    ticket_margin_budget: Decimal,
    required_leverage: int,
    selected_leverage: int,
    configured_leverage_at_claim: int,
    leverage_change_required: bool,
    exchange_max_leverage: int,
    reserved_margin: Decimal,
    maintenance_margin_bracket_id: str,
    projected_liquidation_price: Decimal,
    projected_liquidation_distance: Decimal,
    projected_liquidation_distance_to_stop_distance_ratio: Decimal,
    created_at_ms: int,
    expires_at_ms: int,
    entry_reference_price: Decimal,
    quantity: Decimal,
    notional: Decimal,
    risk_at_stop: Decimal,
    entry_order_type: EntryOrderType,
    entry_limit_price: Decimal | None,
    initial_stop_price: Decimal,
    take_profit_prices: tuple[Decimal, ...],
    take_profit_quantities: tuple[Decimal, ...],
) -> CapacityClaim:
    payload: dict[str, Any] = {
        "capacity_claim_id": "claim:pending",
        "ticket_identity": ticket_identity,
        "owner_policy_id": owner_policy_id,
        "owner_policy_version": owner_policy_version,
        "runtime_scope_id": runtime_scope_id,
        "runtime_scope_version": runtime_scope_version,
        "fact_digest": fact_digest,
        "entry_admission_snapshot_digest": entry_admission_snapshot_digest,
        "account_entry_health_digest": account_entry_health_digest,
        "instrument_entry_health_digest": instrument_entry_health_digest,
        "instrument_rules_projection_version": instrument_rules_projection_version,
        "account_capacity_domain_key": account_capacity_domain_key,
        "leverage_domain_key": leverage_domain_key,
        "total_wallet_balance_at_claim": total_wallet_balance_at_claim,
        "total_margin_balance_at_claim": total_margin_balance_at_claim,
        "total_initial_margin_at_claim": total_initial_margin_at_claim,
        "total_maintenance_margin_at_claim": total_maintenance_margin_at_claim,
        "available_margin_at_claim": available_margin_at_claim,
        "mark_price_at_claim": mark_price_at_claim,
        "position_mode_at_claim": position_mode_at_claim,
        "margin_mode_at_claim": margin_mode_at_claim,
        "active_ticket_count_at_claim": active_ticket_count_at_claim,
        "remaining_slots_at_claim": remaining_slots_at_claim,
        "planned_stop_risk_fraction": planned_stop_risk_fraction,
        "planned_stop_risk_budget": planned_stop_risk_budget,
        "max_post_fill_stop_risk_overrun_fraction": (
            max_post_fill_stop_risk_overrun_fraction
        ),
        "post_fill_stop_risk_limit": post_fill_stop_risk_limit,
        "max_initial_margin_utilization": max_initial_margin_utilization,
        "min_liquidation_distance_to_stop_distance_ratio": (
            min_liquidation_distance_to_stop_distance_ratio
        ),
        "ticket_margin_budget": ticket_margin_budget,
        "required_leverage": required_leverage,
        "selected_leverage": selected_leverage,
        "configured_leverage_at_claim": configured_leverage_at_claim,
        "leverage_change_required": leverage_change_required,
        "exchange_max_leverage": exchange_max_leverage,
        "reserved_margin": reserved_margin,
        "maintenance_margin_bracket_id": maintenance_margin_bracket_id,
        "projected_liquidation_price": projected_liquidation_price,
        "projected_liquidation_distance": projected_liquidation_distance,
        "projected_liquidation_distance_to_stop_distance_ratio": (
            projected_liquidation_distance_to_stop_distance_ratio
        ),
        "created_at_ms": created_at_ms,
        "expires_at_ms": expires_at_ms,
        "entry_reference_price": entry_reference_price,
        "quantity": quantity,
        "notional": notional,
        "risk_at_stop": risk_at_stop,
        "entry_order_type": entry_order_type,
        "entry_limit_price": entry_limit_price,
        "initial_stop_price": initial_stop_price,
        "take_profit_prices": take_profit_prices,
        "take_profit_quantities": take_profit_quantities,
        "decision_digest": "sha256:" + "0" * 64,
    }
    _normalize_claim_decimals_for_storage(
        payload,
        position_side=ticket_identity.netting_domain.position_side,
    )
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


def _normalize_claim_decimals_for_storage(
    payload: dict[str, Any],
    *,
    position_side: Literal["long", "short"],
) -> None:
    """Freeze Claim arithmetic at the exact NUMERIC(38, 18) storage boundary."""

    floor_fields = {
        "total_wallet_balance_at_claim",
        "total_margin_balance_at_claim",
        "available_margin_at_claim",
        "ticket_margin_budget",
        "max_initial_margin_utilization",
        "min_liquidation_distance_to_stop_distance_ratio",
        "max_post_fill_stop_risk_overrun_fraction",
        "planned_stop_risk_fraction",
        "projected_liquidation_distance",
        "projected_liquidation_distance_to_stop_distance_ratio",
        "quantity",
    }
    ceiling_fields = {
        "total_initial_margin_at_claim",
        "total_maintenance_margin_at_claim",
        "planned_stop_risk_budget",
        "post_fill_stop_risk_limit",
        "reserved_margin",
        "notional",
        "risk_at_stop",
    }
    for field_name in floor_fields:
        payload[field_name] = _quantize_storage_decimal(
            payload[field_name],
            rounding=ROUND_FLOOR,
        )
    for field_name in ceiling_fields:
        payload[field_name] = _quantize_storage_decimal(
            payload[field_name],
            rounding=ROUND_CEILING,
        )
    payload["mark_price_at_claim"] = _quantize_storage_decimal(
        payload["mark_price_at_claim"],
        rounding=ROUND_FLOOR,
    )
    payload["entry_reference_price"] = _quantize_storage_decimal(
        payload["entry_reference_price"],
        rounding=ROUND_FLOOR,
    )
    payload["initial_stop_price"] = _quantize_storage_decimal(
        payload["initial_stop_price"],
        rounding=ROUND_FLOOR,
    )
    payload["projected_liquidation_price"] = _quantize_storage_decimal(
        payload["projected_liquidation_price"],
        rounding=(ROUND_CEILING if position_side == "long" else ROUND_FLOOR),
    )
    payload["entry_limit_price"] = (
        None
        if payload["entry_limit_price"] is None
        else _quantize_storage_decimal(
            payload["entry_limit_price"],
            rounding=ROUND_FLOOR,
        )
    )
    payload["take_profit_prices"] = tuple(
        _quantize_storage_decimal(value, rounding=ROUND_FLOOR)
        for value in payload["take_profit_prices"]
    )
    payload["take_profit_quantities"] = tuple(
        _quantize_storage_decimal(value, rounding=ROUND_FLOOR)
        for value in payload["take_profit_quantities"]
    )


def _quantize_storage_decimal(value: Decimal, *, rounding: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError("CapacityClaim financial values must be finite and nonnegative")
    with localcontext() as context:
        context.prec = 60
        return value.quantize(_PERSISTED_DECIMAL_QUANTUM, rounding=rounding)
    venue_id: str
    exchange_instrument_id: str
