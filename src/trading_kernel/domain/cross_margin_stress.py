"""Pure account-level Cross Margin Stop stress authority."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MODEL_ID: Final = "cross-margin-stop-stress-v1"


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


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        _canonicalize(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _require_identity(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-blank")
    return normalized


class MaintenanceMarginBracket(BaseModel):
    """One certified, effective maintenance-margin bracket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bracket_id: str
    notional_floor: Decimal
    notional_cap: Decimal | None
    maintenance_margin_rate: Decimal
    maintenance_amount: Decimal

    @field_validator("bracket_id", mode="before")
    @classmethod
    def _require_bracket_identity(cls, value: object) -> str:
        return _require_identity(value, label="maintenance bracket identity")

    @field_validator("notional_floor", "maintenance_amount")
    @classmethod
    def _require_finite_nonnegative(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("maintenance bracket values must be finite and nonnegative")
        return value

    @field_validator("notional_cap")
    @classmethod
    def _require_finite_positive_cap(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("maintenance bracket cap must be finite and positive")
        return value

    @field_validator("maintenance_margin_rate")
    @classmethod
    def _require_rate(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0 or value >= 1:
            raise ValueError("maintenance margin rate must be finite in [0, 1)")
        return value

    @model_validator(mode="after")
    def _validate_range(self) -> Self:
        if self.notional_cap is not None and self.notional_cap <= self.notional_floor:
            raise ValueError("maintenance bracket cap must exceed its floor")
        return self


class AccountRiskPosition(BaseModel):
    """One open Side from the target instrument in the account response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal
    current_unrealized_pnl: Decimal
    current_maintenance_margin: Decimal

    @field_validator("exchange_instrument_id", mode="before")
    @classmethod
    def _require_instrument_identity(cls, value: object) -> str:
        return _require_identity(value, label="account risk instrument identity")

    @field_validator("quantity", "average_entry_price")
    @classmethod
    def _require_finite_positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("quantity must be finite and positive")
        return value

    @field_validator("current_unrealized_pnl")
    @classmethod
    def _require_finite_unrealized_pnl(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("unrealized PnL must be finite")
        return value

    @field_validator("current_maintenance_margin")
    @classmethod
    def _require_finite_nonnegative_maintenance(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("maintenance margin must be finite and nonnegative")
        return value


class AccountRiskSnapshot(BaseModel):
    """One immutable standard Binance USD-M single-asset account observation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    account_risk_mode: Literal["standard_usdm_single_asset"]
    settlement_asset: Literal["USDT"]
    position_mode: Literal["independent_sides"]
    margin_mode: Literal["cross"]
    exchange_instrument_id: str
    mark_price: Decimal
    configured_leverage: int
    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    total_maintenance_margin: Decimal
    available_margin: Decimal
    account_positions: tuple[AccountRiskPosition, ...]
    observed_at_ms: int
    valid_until_ms: int
    snapshot_digest: str

    @classmethod
    def create(cls, **values: object) -> Self:
        payload = dict(values)
        raw_positions = payload.get("account_positions", ())
        if not isinstance(raw_positions, (tuple, list)):
            raise ValueError(  # noqa: TRY004 - Pydantic creation rejects bad input.
                "account risk positions must be a sequence"
            )
        positions = tuple(
            sorted(
                (
                    AccountRiskPosition.model_validate(position)
                    for position in raw_positions
                ),
                key=lambda position: (
                    position.exchange_instrument_id,
                    position.position_side,
                ),
            )
        )
        payload["account_positions"] = positions
        payload["snapshot_digest"] = _canonical_digest(payload)
        return cls.model_validate(payload)

    @field_validator(
        "venue_id",
        "account_id",
        "exchange_instrument_id",
        mode="before",
    )
    @classmethod
    def _require_snapshot_identities(cls, value: object) -> str:
        return _require_identity(value, label="account risk snapshot identity")

    @field_validator("mark_price")
    @classmethod
    def _require_mark_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("account risk mark price must be finite and positive")
        return value

    @field_validator("configured_leverage", mode="before")
    @classmethod
    def _require_configured_leverage(cls, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("configured leverage must be a positive integer")
        return value

    @field_validator("total_margin_balance")
    @classmethod
    def _require_margin_balance(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("account margin balance must be finite")
        return value

    @field_validator(
        "total_wallet_balance",
        "total_initial_margin",
        "total_maintenance_margin",
        "available_margin",
    )
    @classmethod
    def _require_total_maintenance(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError(
                "account maintenance margin must be finite and nonnegative"
            )
        return value

    @field_validator("snapshot_digest")
    @classmethod
    def _require_snapshot_digest(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("account risk snapshot requires a canonical digest")
        return normalized

    @model_validator(mode="after")
    def _validate_snapshot(self) -> Self:
        if self.observed_at_ms <= 0 or self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("account risk snapshot window must be positive and ordered")
        keys = tuple(
            (position.exchange_instrument_id, position.position_side)
            for position in self.account_positions
        )
        if len(set(keys)) != len(keys):
            raise ValueError("account risk position sides must be unique")
        payload = self.model_dump(mode="python", exclude={"snapshot_digest"})
        if _canonical_digest(payload) != self.snapshot_digest:
            raise ValueError("account risk snapshot digest differs from its payload")
        return self


class StressPosition(BaseModel):
    """One projected Side for the exact instrument stress interval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal

    @field_validator("quantity", "average_entry_price")
    @classmethod
    def _require_finite_positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("stress position values must be finite and positive")
        return value


class CrossMarginStressRequest(BaseModel):
    """Complete typed facts for one deterministic stop-stress decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_snapshot: AccountRiskSnapshot
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    maintenance_margin_brackets_digest: str
    notional_coefficient: Decimal
    notional_coefficient_certified: bool
    evaluated_side: Literal["long", "short"]
    reference_entry_price: Decimal
    initial_stop_price: Decimal
    post_stop_stress_multiple: Decimal
    projected_instrument_positions: tuple[StressPosition, ...]

    @field_validator("maintenance_margin_brackets_digest")
    @classmethod
    def _require_bracket_digest(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("stress request requires a canonical bracket digest")
        return normalized

    @field_validator(
        "notional_coefficient",
        "reference_entry_price",
        "initial_stop_price",
        "post_stop_stress_multiple",
    )
    @classmethod
    def _require_finite_positive(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("stress request financial values must be finite and positive")
        return value

    @field_validator("projected_instrument_positions", mode="before")
    @classmethod
    def _canonicalize_projected_positions(
        cls,
        value: object,
    ) -> tuple[StressPosition, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError(  # noqa: TRY004 - Pydantic must surface ValidationError.
                "projected stress positions must be a sequence"
            )
        return tuple(
            sorted(
                (StressPosition.model_validate(position) for position in value),
                key=lambda position: position.position_side,
            )
        )

    @model_validator(mode="after")
    def _validate_request(self) -> Self:
        if not self.maintenance_margin_brackets:
            raise ValueError("stress request requires maintenance brackets")
        sides = tuple(
            position.position_side
            for position in self.projected_instrument_positions
        )
        if not sides or len(set(sides)) != len(sides):
            raise ValueError("projected stress position sides must be unique")
        if self.evaluated_side not in sides:
            raise ValueError("evaluated Side must exist in projected positions")
        if (
            self.evaluated_side == "long"
            and self.initial_stop_price >= self.reference_entry_price
        ) or (
            self.evaluated_side == "short"
            and self.initial_stop_price <= self.reference_entry_price
        ):
            raise ValueError("Initial Stop must be on the protective side")
        return self


class CrossMarginStressStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    FACTS_CONTRADICTORY = "facts_contradictory"


class CrossMarginStressProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: Literal["cross-margin-stop-stress-v1"]
    snapshot_digest: str
    maintenance_margin_brackets_digest: str
    status: CrossMarginStressStatus
    stress_price: Decimal
    stress_boundary_clamped_to_zero: bool
    minimum_margin_surplus: Decimal | None
    minimum_margin_surplus_price: Decimal | None
    evaluated_point_count: int
    contradiction_reason: str | None
    proof_digest: str

    @field_validator(
        "snapshot_digest",
        "maintenance_margin_brackets_digest",
        "proof_digest",
    )
    @classmethod
    def _require_digest(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if _SHA256_DIGEST.fullmatch(normalized) is None:
            raise ValueError("stress proof requires canonical digests")
        return normalized

    @field_validator("stress_price")
    @classmethod
    def _require_nonnegative_stress_price(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < 0:
            raise ValueError("stress price must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        if self.status is CrossMarginStressStatus.FACTS_CONTRADICTORY:
            if (
                self.minimum_margin_surplus is not None
                or self.minimum_margin_surplus_price is not None
                or self.evaluated_point_count != 0
                or not self.contradiction_reason
            ):
                raise ValueError("contradictory stress proof has invalid shape")
            return self
        if (
            self.minimum_margin_surplus is None
            or not self.minimum_margin_surplus.is_finite()
            or self.minimum_margin_surplus_price is None
            or not self.minimum_margin_surplus_price.is_finite()
            or self.minimum_margin_surplus_price < 0
            or self.evaluated_point_count <= 0
            or self.contradiction_reason is not None
        ):
            raise ValueError("evaluated stress proof has invalid shape")
        if (
            self.status is CrossMarginStressStatus.PASSED
            and self.minimum_margin_surplus <= 0
        ):
            raise ValueError("passed stress proof requires positive surplus")
        return self


class CrossMarginStressEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: CrossMarginStressRequest
    proof: CrossMarginStressProof

    @model_validator(mode="after")
    def _validate_binding(self) -> Self:
        if self.request.account_snapshot.snapshot_digest != self.proof.snapshot_digest:
            raise ValueError("stress evidence snapshot digest mismatch")
        if (
            self.request.maintenance_margin_brackets_digest
            != self.proof.maintenance_margin_brackets_digest
        ):
            raise ValueError("stress evidence bracket digest mismatch")
        return self


def evaluate_cross_margin_stress(
    request: CrossMarginStressRequest,
) -> CrossMarginStressEvidence:
    """Evaluate one finite, account-level price interval without root solving."""

    stress_price, clamped = _stress_boundary(request)
    if not request.notional_coefficient_certified:
        return _contradictory(
            request,
            stress_price=stress_price,
            clamped=clamped,
            reason="notional coefficient is not certified",
        )
    if not _bracket_schedule_is_valid(request.maintenance_margin_brackets):
        return _contradictory(
            request,
            stress_price=stress_price,
            clamped=clamped,
            reason="maintenance bracket schedule invalid",
        )

    current_positions = tuple(
        position
        for position in request.account_snapshot.account_positions
        if position.exchange_instrument_id
        == request.account_snapshot.exchange_instrument_id
    )
    base_margin_balance = request.account_snapshot.total_margin_balance - sum(
        (
            position.current_unrealized_pnl
            for position in current_positions
        ),
        Decimal(0),
    )
    base_maintenance_margin = (
        request.account_snapshot.total_maintenance_margin
        - sum(
            (
                position.current_maintenance_margin
                for position in current_positions
            ),
            Decimal(0),
        )
    )
    if base_maintenance_margin < 0:
        return _contradictory(
            request,
            stress_price=stress_price,
            clamped=clamped,
            reason="instrument maintenance margin exceeds account total",
        )

    points = _evaluation_points(request, stress_price=stress_price)
    surplus_by_price = tuple(
        (
            price,
            _margin_surplus(
                request,
                price=price,
                base_margin_balance=base_margin_balance,
                base_maintenance_margin=base_maintenance_margin,
            ),
        )
        for price in points
    )
    minimum_price, minimum_surplus = min(
        surplus_by_price,
        key=lambda item: (item[1], item[0]),
    )
    mark_is_protected = (
        request.account_snapshot.mark_price > request.initial_stop_price
        if request.evaluated_side == "long"
        else request.account_snapshot.mark_price < request.initial_stop_price
    )
    status = (
        CrossMarginStressStatus.PASSED
        if mark_is_protected and minimum_surplus > 0
        else CrossMarginStressStatus.FAILED
    )
    proof = _proof(
        request,
        status=status,
        stress_price=stress_price,
        clamped=clamped,
        minimum_margin_surplus=minimum_surplus,
        minimum_margin_surplus_price=minimum_price,
        evaluated_point_count=len(points),
        contradiction_reason=None,
    )
    return CrossMarginStressEvidence(request=request, proof=proof)


def _stress_boundary(
    request: CrossMarginStressRequest,
) -> tuple[Decimal, bool]:
    stop_distance = abs(
        request.reference_entry_price - request.initial_stop_price
    )
    if request.evaluated_side == "short":
        return (
            request.initial_stop_price
            + request.post_stop_stress_multiple * stop_distance,
            False,
        )
    raw_stress_price = (
        request.initial_stop_price
        - request.post_stop_stress_multiple * stop_distance
    )
    return (max(Decimal(0), raw_stress_price), raw_stress_price < 0)


def _bracket_schedule_is_valid(
    brackets: tuple[MaintenanceMarginBracket, ...],
) -> bool:
    if (
        not brackets
        or brackets[0].notional_floor != 0
        or brackets[-1].notional_cap is not None
        or len({bracket.bracket_id for bracket in brackets}) != len(brackets)
    ):
        return False
    for index, bracket in enumerate(brackets):
        if index == 0:
            if bracket.maintenance_amount != 0:
                return False
            continue
        previous = brackets[index - 1]
        if (
            previous.notional_cap != bracket.notional_floor
            or bracket.maintenance_margin_rate
            < previous.maintenance_margin_rate
        ):
            return False
        boundary = bracket.notional_floor
        previous_margin = (
            boundary * previous.maintenance_margin_rate
            - previous.maintenance_amount
        )
        current_margin = (
            boundary * bracket.maintenance_margin_rate
            - bracket.maintenance_amount
        )
        if current_margin != previous_margin or current_margin < 0:
            return False
    return True


def _evaluation_points(
    request: CrossMarginStressRequest,
    *,
    stress_price: Decimal,
) -> tuple[Decimal, ...]:
    mark_price = request.account_snapshot.mark_price
    lower = min(mark_price, stress_price)
    upper = max(mark_price, stress_price)
    points = {
        mark_price,
        request.initial_stop_price,
        stress_price,
    }
    for position in request.projected_instrument_positions:
        for bracket in request.maintenance_margin_brackets:
            boundaries = (bracket.notional_floor, bracket.notional_cap)
            for boundary in boundaries:
                if boundary is None:
                    continue
                boundary_price = boundary / position.quantity
                if lower <= boundary_price <= upper:
                    points.add(boundary_price)
    return tuple(sorted(points))


def _margin_surplus(
    request: CrossMarginStressRequest,
    *,
    price: Decimal,
    base_margin_balance: Decimal,
    base_maintenance_margin: Decimal,
) -> Decimal:
    projected_upnl = Decimal(0)
    projected_maintenance = Decimal(0)
    for position in request.projected_instrument_positions:
        projected_upnl += (
            position.quantity * (price - position.average_entry_price)
            if position.position_side == "long"
            else position.quantity * (position.average_entry_price - price)
        )
        notional = position.quantity * price
        bracket = _bracket_for(
            request.maintenance_margin_brackets,
            notional=notional,
        )
        projected_maintenance += (
            notional * bracket.maintenance_margin_rate
            - bracket.maintenance_amount
        )
    return (
        base_margin_balance
        + projected_upnl
        - base_maintenance_margin
        - projected_maintenance
    )


def _bracket_for(
    brackets: tuple[MaintenanceMarginBracket, ...],
    *,
    notional: Decimal,
) -> MaintenanceMarginBracket:
    for bracket in brackets:
        if (
            notional >= bracket.notional_floor
            and (
                bracket.notional_cap is None
                or notional < bracket.notional_cap
            )
        ):
            return bracket
    raise ValueError("validated maintenance schedule does not cover notional")


def _contradictory(
    request: CrossMarginStressRequest,
    *,
    stress_price: Decimal,
    clamped: bool,
    reason: str,
) -> CrossMarginStressEvidence:
    proof = _proof(
        request,
        status=CrossMarginStressStatus.FACTS_CONTRADICTORY,
        stress_price=stress_price,
        clamped=clamped,
        minimum_margin_surplus=None,
        minimum_margin_surplus_price=None,
        evaluated_point_count=0,
        contradiction_reason=reason,
    )
    return CrossMarginStressEvidence(request=request, proof=proof)


def _proof(
    request: CrossMarginStressRequest,
    *,
    status: CrossMarginStressStatus,
    stress_price: Decimal,
    clamped: bool,
    minimum_margin_surplus: Decimal | None,
    minimum_margin_surplus_price: Decimal | None,
    evaluated_point_count: int,
    contradiction_reason: str | None,
) -> CrossMarginStressProof:
    payload = {
        "model_id": _MODEL_ID,
        "snapshot_digest": request.account_snapshot.snapshot_digest,
        "maintenance_margin_brackets_digest": (
            request.maintenance_margin_brackets_digest
        ),
        "status": status,
        "stress_price": stress_price,
        "stress_boundary_clamped_to_zero": clamped,
        "minimum_margin_surplus": minimum_margin_surplus,
        "minimum_margin_surplus_price": minimum_margin_surplus_price,
        "evaluated_point_count": evaluated_point_count,
        "contradiction_reason": contradiction_reason,
    }
    proof_digest = _canonical_digest(
        {
            "request": request,
            "result": payload,
        }
    )
    return CrossMarginStressProof(
        model_id=_MODEL_ID,
        snapshot_digest=request.account_snapshot.snapshot_digest,
        maintenance_margin_brackets_digest=(
            request.maintenance_margin_brackets_digest
        ),
        status=status,
        stress_price=stress_price,
        stress_boundary_clamped_to_zero=clamped,
        minimum_margin_surplus=minimum_margin_surplus,
        minimum_margin_surplus_price=minimum_margin_surplus_price,
        evaluated_point_count=evaluated_point_count,
        contradiction_reason=contradiction_reason,
        proof_digest=proof_digest,
    )
