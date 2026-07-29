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

    @field_validator(
        "filled_quantity",
        "average_fill_price",
        "initial_stop_price",
        "planned_stop_risk_budget",
        "post_fill_stop_risk_limit",
    )
    @classmethod
    def _require_positive_decimal(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("post-fill risk values must be finite and positive")
        return value

    @model_validator(mode="after")
    def _validate_frozen_limits(self) -> PostFillRiskRequest:
        if self.post_fill_stop_risk_limit < self.planned_stop_risk_budget:
            raise ValueError("post-fill limit cannot undercut the planned budget")
        return self


class PostFillRiskDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: PostFillRiskStatus
    disposition: PostFillDisposition
    actual_stop_risk: Decimal


def assess_post_fill_risk(request: PostFillRiskRequest) -> PostFillRiskDecision:
    """Assess the exact filled exposure without mutating immutable Ticket terms."""

    stop_distance = abs(request.average_fill_price - request.initial_stop_price)
    actual_stop_risk = request.filled_quantity * stop_distance

    if not _stop_is_protective(request):
        return PostFillRiskDecision(
            status=PostFillRiskStatus.PROTECTION_DIRECTION_INVALID,
            disposition=PostFillDisposition.FLATTEN_IMMEDIATELY,
            actual_stop_risk=actual_stop_risk,
        )
    if actual_stop_risk > request.post_fill_stop_risk_limit:
        return PostFillRiskDecision(
            status=PostFillRiskStatus.HARD_OVERRUN,
            disposition=PostFillDisposition.FLATTEN_AFTER_PROTECTION,
            actual_stop_risk=actual_stop_risk,
        )
    if actual_stop_risk > request.planned_stop_risk_budget:
        return PostFillRiskDecision(
            status=PostFillRiskStatus.TOLERATED_OVERRUN,
            disposition=PostFillDisposition.NORMAL,
            actual_stop_risk=actual_stop_risk,
        )
    return PostFillRiskDecision(
        status=PostFillRiskStatus.WITHIN_BUDGET,
        disposition=PostFillDisposition.NORMAL,
        actual_stop_risk=actual_stop_risk,
    )


def _stop_is_protective(request: PostFillRiskRequest) -> bool:
    return (
        request.initial_stop_price < request.average_fill_price
        if request.position_side == "long"
        else request.initial_stop_price > request.average_fill_price
    )
