"""Immutable execution decision for one exposure episode."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.exposure_family import ExposureFamily
from src.trading_kernel.domain.identities import (
    NettingDomain,
    RuntimeIdentity,
    TicketIdentity,
)

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class EntryOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TicketStatus(StrEnum):
    ISSUED = "issued"
    EXPIRED_BEFORE_SUBMIT = "expired_before_submit"
    LEVERAGE_REJECTED = "leverage_rejected"
    ENTRY_REJECTED = "entry_rejected"
    ENTRY_RECONCILED_ABSENT = "entry_reconciled_absent"
    TERMINAL = "terminal"


class TradeTicket(BaseModel):
    """Complete post-Action-Time decision consumed by the trading kernel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: TicketIdentity
    owner_policy_id: str
    owner_policy_version: int
    runtime_scope_id: str
    runtime_scope_version: int
    universe_version_id: str
    universe_semantic_digest: str
    fact_digest: str
    exposure_family: ExposureFamily
    active_family_ticket_count_at_claim: int
    family_ticket_limit: int
    directional_risk_at_stop_at_claim: Decimal
    directional_stop_risk_limit_fraction: Decimal
    min_materialization_ratio: Decimal
    minimum_stop_risk_budget: Decimal
    exit_policy_id: str
    exit_policy_semantic_hash: str
    exit_binding_id: str | None = None
    exit_binding_semantic_hash: str | None = None
    exit_binding_authority_version: int | None = None
    capacity_claim_id: str
    created_at_ms: int
    expires_at_ms: int
    entry_reference_price: Decimal
    quantity: Decimal
    notional: Decimal
    planned_stop_risk_budget: Decimal
    post_fill_stop_risk_limit: Decimal
    selected_leverage: int
    leverage_change_required: bool
    reserved_margin: Decimal
    risk_reservation_basis: str
    margin_mode: Literal["cross"]
    cross_margin_stress_model_id: Literal["cross-margin-stop-stress-v1"]
    post_stop_stress_multiple: Decimal
    claim_stress_proof_digest: str
    risk_at_stop: Decimal
    entry_order_type: EntryOrderType
    entry_limit_price: Decimal | None = None
    initial_stop_price: Decimal
    pre_tp1_reclaim_price: Decimal | None = None
    exposure_session_end_ms: int | None = None
    take_profit_prices: tuple[Decimal, ...] = ()
    take_profit_quantities: tuple[Decimal, ...] = ()
    status: TicketStatus = TicketStatus.ISSUED
    selection_authority_id: str | None = None

    @field_validator(
        "owner_policy_id",
        "runtime_scope_id",
        "universe_version_id",
        "exit_policy_id",
        "capacity_claim_id",
        "risk_reservation_basis",
        mode="before",
    )
    @classmethod
    def _require_non_blank_reference(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("ticket references must be non-blank strings")
        return value.strip()

    @field_validator("selection_authority_id", mode="before")
    @classmethod
    def _normalize_optional_selection_authority(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("exit_binding_id", mode="before")
    @classmethod
    def _normalize_optional_exit_binding(cls, value: object) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator(
        "fact_digest",
        "universe_semantic_digest",
        "claim_stress_proof_digest",
        "exit_policy_semantic_hash",
        mode="before",
    )
    @classmethod
    def _require_digest(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("ticket digests must be exact sha256 identities")
        return normalized

    @field_validator("exit_binding_semantic_hash")
    @classmethod
    def _require_optional_binding_digest(cls, value: str | None) -> str | None:
        if value is not None and _SHA256_DIGEST.fullmatch(value) is None:
            raise ValueError("Ticket Binding hash must be exact sha256")
        return value

    @field_validator("exit_binding_authority_version")
    @classmethod
    def _require_optional_binding_version(cls, value: int | None) -> int | None:
        if value is not None and (isinstance(value, bool) or value <= 0):
            raise ValueError("Ticket Binding authority version must be positive")
        return value

    @field_validator("owner_policy_version", "runtime_scope_version")
    @classmethod
    def _require_positive_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ticket authority versions must be positive")
        return value

    @field_validator(
        "quantity",
        "notional",
        "planned_stop_risk_budget",
        "post_fill_stop_risk_limit",
        "reserved_margin",
        "entry_reference_price",
        "initial_stop_price",
        "post_stop_stress_multiple",
        "directional_stop_risk_limit_fraction",
        "min_materialization_ratio",
        "minimum_stop_risk_budget",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("financial value must be positive")
        return value

    @field_validator("risk_at_stop", "directional_risk_at_stop_at_claim")
    @classmethod
    def _require_nonnegative_risk(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("risk_at_stop must be nonnegative")
        return value

    @field_validator("pre_tp1_reclaim_price")
    @classmethod
    def _require_optional_positive_reclaim(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and value <= 0:
            raise ValueError("pre-TP1 reclaim price must be positive")
        return value

    @field_validator("selected_leverage")
    @classmethod
    def _require_positive_integer_leverage(cls, value: int) -> int:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("selected leverage must be a positive integer")
        return value

    @field_validator(
        "active_family_ticket_count_at_claim",
    )
    @classmethod
    def _require_nonnegative_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("active Family Ticket count cannot be negative")
        return value

    @field_validator("family_ticket_limit")
    @classmethod
    def _require_positive_family_limit(cls, value: int) -> int:
        if isinstance(value, bool) or value <= 0:
            raise ValueError("Family Ticket limit must be positive")
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

    @field_validator("take_profit_quantities")
    @classmethod
    def _require_positive_take_profit_quantities(
        cls,
        values: tuple[Decimal, ...],
    ) -> tuple[Decimal, ...]:
        if any(value <= 0 for value in values):
            raise ValueError("take-profit quantities must be positive")
        return values

    @model_validator(mode="after")
    def _validate_deadline_and_order_shape(self) -> TradeTicket:
        binding_lineage = (
            self.exit_binding_id,
            self.exit_binding_semantic_hash,
            self.exit_binding_authority_version,
        )
        if any(value is None for value in binding_lineage) and not all(
            value is None for value in binding_lineage
        ):
            raise ValueError("Ticket Binding lineage must be all-null or all-present")
        if self.expires_at_ms <= self.created_at_ms:
            raise ValueError("ticket expiry must be after creation")
        if self.entry_order_type is EntryOrderType.LIMIT:
            if self.entry_limit_price is None or self.entry_limit_price <= 0:
                raise ValueError("limit entry requires a positive limit price")
        elif self.entry_limit_price is not None:
            raise ValueError("market entry forbids a limit price")
        if len(self.take_profit_prices) != len(self.take_profit_quantities):
            raise ValueError("take-profit prices and quantities must align")
        if sum(self.take_profit_quantities, Decimal(0)) >= self.quantity:
            raise ValueError("take-profit quantities must preserve a runner position")
        if self.risk_at_stop > self.planned_stop_risk_budget:
            raise ValueError("Ticket stop risk cannot exceed planned risk budget")
        if self.post_fill_stop_risk_limit < self.planned_stop_risk_budget:
            raise ValueError("Ticket post-fill stop risk limit cannot undercut plan")
        if self.active_family_ticket_count_at_claim >= self.family_ticket_limit:
            raise ValueError("Ticket Family capacity was exhausted at claim")
        if self.risk_at_stop < self.minimum_stop_risk_budget:
            raise ValueError("Ticket is below minimum materialization")
        if (self.pre_tp1_reclaim_price is None) != (
            self.exposure_session_end_ms is None
        ):
            raise ValueError("Ticket pre-TP1 plan fields must be paired")
        if (
            self.exposure_session_end_ms is not None
            and self.exposure_session_end_ms <= 0
        ):
            raise ValueError("Ticket Session end must be positive")
        return self

    def decision_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"status"})
        if payload["selection_authority_id"] is None:
            payload.pop("selection_authority_id")
        if payload["exit_binding_id"] is None:
            payload.pop("exit_binding_id")
            payload.pop("exit_binding_semantic_hash")
            payload.pop("exit_binding_authority_version")
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
