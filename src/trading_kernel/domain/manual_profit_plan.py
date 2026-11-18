"""Active manual plan or automatic TP retired by an Owner replacement attempt.

The source kind retains the original order attribution; cancellation never
restores its quantity exit or manufactures a filled TP.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManualProfitPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_kind: Literal["manual", "retired_automatic"] = "manual"
    operation_id: str = Field(min_length=1)
    exchange_order_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    target_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    prior_tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    started_from_runner: bool
    cancelled: bool = False

    @model_validator(mode="after")
    def retired_automatic_is_never_an_active_manual_plan(self):
        if self.source_kind == "retired_automatic" and not self.cancelled:
            raise ValueError(
                "retired automatic TP cannot become an active manual order"
            )
        return self
