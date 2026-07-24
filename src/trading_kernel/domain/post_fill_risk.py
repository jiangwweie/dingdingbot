"""Pure post-fill protection disposition for one filled Ticket."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class PostFillRiskStatus(StrEnum):
    WITHIN_BUDGET = "within_budget"
    TOLERATED_OVERRUN = "tolerated_overrun"
    HARD_OVERRUN = "hard_overrun"
    LIQUIDATION_SAFETY_DEGRADED = "liquidation_safety_degraded"
    PROTECTION_DIRECTION_INVALID = "protection_direction_invalid"


class PostFillDisposition(StrEnum):
    NORMAL = "normal"
    FLATTEN_AFTER_PROTECTION = "flatten_after_protection"
    FLATTEN_IMMEDIATELY = "flatten_immediately"


class PostFillRiskRequest(BaseModel):
    """Frozen Ticket limits plus exact exchange facts after a full entry fill."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position_side: Literal["long", "short"]
    filled_quantity: Decimal
    average_fill_price: Decimal
    initial_stop_price: Decimal
    planned_stop_risk_budget: Decimal
    post_fill_stop_risk_limit: Decimal
    current_liquidation_price: Decimal | None
    min_liquidation_distance_to_stop_distance_ratio: Decimal

    @field_validator(
        "filled_quantity",
        "average_fill_price",
        "initial_stop_price",
        "planned_stop_risk_budget",
        "post_fill_stop_risk_limit",
        "min_liquidation_distance_to_stop_distance_ratio",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("post-fill risk values must be finite and positive")
        return value

    @field_validator("current_liquidation_price")
    @classmethod
    def _require_optional_positive_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (not value.is_finite() or value <= 0):
            raise ValueError("liquidation evidence must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_frozen_limits(self) -> "PostFillRiskRequest":
        if self.post_fill_stop_risk_limit < self.planned_stop_risk_budget:
            raise ValueError("post-fill limit cannot undercut the planned budget")
        return self


class PostFillRiskDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PostFillRiskStatus
    disposition: PostFillDisposition
    actual_stop_risk: Decimal
    actual_liquidation_price: Decimal | None
    actual_liquidation_distance: Decimal | None
    actual_liquidation_distance_to_stop_distance_ratio: Decimal | None


def assess_post_fill_risk(request: PostFillRiskRequest) -> PostFillRiskDecision:
    """Assess the exact filled exposure without mutating immutable Ticket terms."""

    stop_distance = abs(request.average_fill_price - request.initial_stop_price)
    actual_stop_risk = request.filled_quantity * stop_distance
    liquidation_distance, liquidation_ratio = _liquidation_evidence(request, stop_distance)

    if not _stop_is_protective(request):
        return _decision(
            status=PostFillRiskStatus.PROTECTION_DIRECTION_INVALID,
            disposition=PostFillDisposition.FLATTEN_IMMEDIATELY,
            actual_stop_risk=actual_stop_risk,
            request=request,
            liquidation_distance=liquidation_distance,
            liquidation_ratio=liquidation_ratio,
        )
    if actual_stop_risk > request.post_fill_stop_risk_limit:
        return _decision(
            status=PostFillRiskStatus.HARD_OVERRUN,
            disposition=PostFillDisposition.FLATTEN_AFTER_PROTECTION,
            actual_stop_risk=actual_stop_risk,
            request=request,
            liquidation_distance=liquidation_distance,
            liquidation_ratio=liquidation_ratio,
        )
    if not _liquidation_is_safe(request, liquidation_ratio):
        return _decision(
            status=PostFillRiskStatus.LIQUIDATION_SAFETY_DEGRADED,
            disposition=PostFillDisposition.FLATTEN_AFTER_PROTECTION,
            actual_stop_risk=actual_stop_risk,
            request=request,
            liquidation_distance=liquidation_distance,
            liquidation_ratio=liquidation_ratio,
        )
    if actual_stop_risk > request.planned_stop_risk_budget:
        return _decision(
            status=PostFillRiskStatus.TOLERATED_OVERRUN,
            disposition=PostFillDisposition.NORMAL,
            actual_stop_risk=actual_stop_risk,
            request=request,
            liquidation_distance=liquidation_distance,
            liquidation_ratio=liquidation_ratio,
        )
    return _decision(
        status=PostFillRiskStatus.WITHIN_BUDGET,
        disposition=PostFillDisposition.NORMAL,
        actual_stop_risk=actual_stop_risk,
        request=request,
        liquidation_distance=liquidation_distance,
        liquidation_ratio=liquidation_ratio,
    )


def _stop_is_protective(request: PostFillRiskRequest) -> bool:
    return (
        request.initial_stop_price < request.average_fill_price
        if request.position_side == "long"
        else request.initial_stop_price > request.average_fill_price
    )


def _liquidation_evidence(
    request: PostFillRiskRequest,
    stop_distance: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    if request.current_liquidation_price is None or stop_distance == 0:
        return None, None
    distance = (
        request.initial_stop_price - request.current_liquidation_price
        if request.position_side == "long"
        else request.current_liquidation_price - request.initial_stop_price
    )
    return distance, distance / stop_distance


def _liquidation_is_safe(
    request: PostFillRiskRequest,
    ratio: Decimal | None,
) -> bool:
    liquidation = request.current_liquidation_price
    if liquidation is None or ratio is None:
        return False
    beyond_stop = (
        liquidation < request.initial_stop_price
        if request.position_side == "long"
        else liquidation > request.initial_stop_price
    )
    return (
        beyond_stop
        and ratio >= request.min_liquidation_distance_to_stop_distance_ratio
    )


def _decision(
    *,
    status: PostFillRiskStatus,
    disposition: PostFillDisposition,
    actual_stop_risk: Decimal,
    request: PostFillRiskRequest,
    liquidation_distance: Decimal | None,
    liquidation_ratio: Decimal | None,
) -> PostFillRiskDecision:
    return PostFillRiskDecision(
        status=status,
        disposition=disposition,
        actual_stop_risk=actual_stop_risk,
        actual_liquidation_price=request.current_liquidation_price,
        actual_liquidation_distance=liquidation_distance,
        actual_liquidation_distance_to_stop_distance_ratio=liquidation_ratio,
    )
