"""Pure classification of readonly instrument eligibility facts."""

from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CertificationStatus = Literal[
    "eligible",
    "owner_action_required",
    "temporarily_unavailable",
]
InstrumentCertificationBlockerCode = Literal[
    "product_not_trading",
    "missing_order_rule",
    "position_mode_mismatch",
    "margin_mode_mismatch",
    "configured_leverage_mismatch",
    "unowned_position",
    "unowned_open_order",
    "readonly_facts_unavailable",
]


class InstrumentCertificationFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_profile_id: str
    exchange_instrument_id: str
    product_status: str
    tick_size: Decimal | None
    step_size: Decimal | None
    min_qty: Decimal | None
    min_notional: Decimal | None
    position_mode: str | None
    margin_mode: str | None
    configured_leverage: int | None
    unowned_position_qty: Decimal
    unowned_open_order_count: int
    observed_at_ms: int

    @field_validator("runtime_profile_id", "exchange_instrument_id", mode="before")
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("certification identity must be non-blank")
        return normalized

    @field_validator("unowned_position_qty")
    @classmethod
    def _require_nonnegative_position(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("unowned position quantity must be non-negative")
        return value

    @field_validator("unowned_open_order_count", "observed_at_ms")
    @classmethod
    def _require_nonnegative_integer(cls, value: int) -> int:
        if value < 0:
            raise ValueError("certification counts and time must be non-negative")
        return value


class InstrumentCertification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CertificationStatus
    blocker_code: InstrumentCertificationBlockerCode | None
    facts_digest: str
    observed_at_ms: int
    valid_until_ms: int


def classify_instrument_certification(
    facts: InstrumentCertificationFacts,
    *,
    required_leverage: int,
    required_margin_mode: Literal["cross"],
    valid_for_ms: int,
) -> InstrumentCertification:
    """Classify facts without clock, database, venue, or mutation authority."""

    if required_leverage <= 0:
        raise ValueError("required leverage must be positive")
    if valid_for_ms <= 0:
        raise ValueError("certification validity must be positive")
    blocker_code = _blocker_code(
        facts,
        required_leverage=required_leverage,
        required_margin_mode=required_margin_mode,
    )
    return InstrumentCertification(
        status="eligible" if blocker_code is None else "owner_action_required",
        blocker_code=blocker_code,
        facts_digest=_facts_digest(facts),
        observed_at_ms=facts.observed_at_ms,
        valid_until_ms=facts.observed_at_ms + valid_for_ms,
    )


def _blocker_code(
    facts: InstrumentCertificationFacts,
    *,
    required_leverage: int,
    required_margin_mode: Literal["cross"],
) -> InstrumentCertificationBlockerCode | None:
    if facts.product_status != "trading":
        return "product_not_trading"
    if any(
        value is None or value <= 0
        for value in (facts.tick_size, facts.step_size, facts.min_qty, facts.min_notional)
    ):
        return "missing_order_rule"
    if facts.position_mode != "independent_sides":
        return "position_mode_mismatch"
    if facts.margin_mode != required_margin_mode:
        return "margin_mode_mismatch"
    if facts.configured_leverage != required_leverage:
        return "configured_leverage_mismatch"
    if facts.unowned_position_qty != 0:
        return "unowned_position"
    if facts.unowned_open_order_count != 0:
        return "unowned_open_order"
    return None


def _facts_digest(facts: InstrumentCertificationFacts) -> str:
    canonical = json.dumps(
        facts.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"
