"""Verified per-Ticket continuation source; no synthetic TP fills."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OwnerReductionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operation_id: str = Field(min_length=1)
    cumulative_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    original_tp_order_id: str | None
    original_tp_price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    last_reduction_observed_at_ms: int = Field(gt=0)
    price_condition_satisfied: bool = False
    condition_observed_at_ms: int | None = Field(default=None, gt=0)
