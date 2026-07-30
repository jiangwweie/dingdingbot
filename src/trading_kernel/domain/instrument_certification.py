"""Pure classification of readonly instrument eligibility facts."""

from __future__ import annotations

import json
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
    "notional_coefficient_unverified",
    "unowned_position",
    "unowned_open_order",
    "readonly_facts_unavailable",
]


class CertificationBatchStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class CertificationBatchMemberResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    status: Literal["eligible", "owner_action_required"]
    blocker_code: InstrumentCertificationBlockerCode | None
    facts_digest: str
    product_rules_digest: str | None
    observed_at_ms: int
    valid_until_ms: int

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_member_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("certification batch member identity must be non-blank")
        return normalized

    @field_validator("facts_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if len(value) != 71 or not value.startswith("sha256:"):
            raise ValueError("certification batch member digest must be sha256")
        try:
            int(value[7:], 16)
        except ValueError as exc:
            raise ValueError(
                "certification batch member digest must be sha256"
            ) from exc
        return value

    @field_validator("product_rules_digest")
    @classmethod
    def _require_optional_digest(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return cls._require_digest(value)

    @model_validator(mode="after")
    def _validate_result(self) -> CertificationBatchMemberResult:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("certification batch member validity is invalid")
        if self.status == "eligible" and self.blocker_code is not None:
            raise ValueError("eligible certification batch member cannot be blocked")
        if self.status == "eligible" and self.product_rules_digest is None:
            raise ValueError("eligible certification batch member requires rules")
        if self.status == "owner_action_required" and self.blocker_code is None:
            raise ValueError("blocked certification batch member requires blocker")
        return self


class CertificationBatchEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: CertificationBatchStatus
    required_member_count: int
    completed_member_count: int
    valid_until_ms: int | None
    blocker_code: InstrumentCertificationBlockerCode | None


def build_certification_manifest_digest(
    exchange_instrument_ids: tuple[str, ...],
) -> str:
    """Build the unordered exact manifest identity used by deployment batches."""

    normalized = tuple(sorted(str(value or "").strip() for value in exchange_instrument_ids))
    if not 1 <= len(normalized) <= 10:
        raise ValueError("certification batch manifest must contain 1..10 members")
    if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("certification batch manifest members must be unique")
    canonical = json.dumps(
        normalized,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def evaluate_certification_batch(
    *,
    manifest: tuple[str, ...],
    member_results: tuple[CertificationBatchMemberResult, ...],
    minimum_valid_until_ms: int,
) -> CertificationBatchEvaluation:
    """Evaluate exact immutable results without database or clock authority."""

    if minimum_valid_until_ms <= 0:
        raise ValueError("certification batch promotion window must be positive")
    build_certification_manifest_digest(manifest)
    manifest_set = set(manifest)
    result_ids = tuple(item.exchange_instrument_id for item in member_results)
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("certification batch member results must be unique")
    if not set(result_ids).issubset(manifest_set):
        raise ValueError("certification batch result is outside exact manifest")
    blocked = tuple(
        item
        for item in sorted(
            member_results,
            key=lambda value: value.exchange_instrument_id,
        )
        if item.status == "owner_action_required"
    )
    if blocked:
        return CertificationBatchEvaluation(
            status=CertificationBatchStatus.BLOCKED,
            required_member_count=len(manifest),
            completed_member_count=len(member_results),
            valid_until_ms=None,
            blocker_code=blocked[0].blocker_code,
        )
    if len(member_results) != len(manifest):
        return CertificationBatchEvaluation(
            status=CertificationBatchStatus.PENDING,
            required_member_count=len(manifest),
            completed_member_count=len(member_results),
            valid_until_ms=None,
            blocker_code=None,
        )
    earliest_valid_until_ms = min(item.valid_until_ms for item in member_results)
    if earliest_valid_until_ms < minimum_valid_until_ms:
        return CertificationBatchEvaluation(
            status=CertificationBatchStatus.PENDING,
            required_member_count=len(manifest),
            completed_member_count=len(member_results),
            valid_until_ms=None,
            blocker_code=None,
        )
    return CertificationBatchEvaluation(
        status=CertificationBatchStatus.COMPLETED,
        required_member_count=len(manifest),
        completed_member_count=len(member_results),
        valid_until_ms=earliest_valid_until_ms,
        blocker_code=None,
    )


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
    notional_coefficient_certified: bool
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
    if not facts.notional_coefficient_certified:
        return "notional_coefficient_unverified"
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
