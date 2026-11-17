"""Read one exact Ticket and prepare an Owner preview; no dispatch authority."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionFacts,
    OwnerReductionPreview,
    preview_owner_reduction,
)


class PreviewOwnerReductionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str = Field(min_length=1)
    expected_version: int = Field(gt=0)
    requested_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    quantity_step: Decimal = Field(gt=0, allow_inf_nan=False)
    minimum_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    minimum_notional: Decimal = Field(gt=0, allow_inf_nan=False)
    facts: OwnerReductionFacts
    now_ms: int = Field(gt=0)

    @field_validator(
        "requested_quantity",
        "quantity_step",
        "minimum_quantity",
        "minimum_notional",
        mode="before",
    )
    @classmethod
    def exact_values(cls, value: object) -> object:
        if isinstance(value, (float, bool)):
            raise TypeError("financial values must be exact")
        return value


async def build_owner_reduction_preview(
    uow: KernelUnitOfWork,
    request: PreviewOwnerReductionRequest,
) -> OwnerReductionPreview:
    aggregate = await uow.aggregates.get(request.ticket_id)
    if aggregate is None:
        raise ValueError("owner_reduction_ticket_missing")
    if aggregate.version != request.expected_version:
        raise ValueError("owner_reduction_version_changed")
    return preview_owner_reduction(
        aggregate=aggregate,
        facts=request.facts,
        requested_quantity=request.requested_quantity,
        quantity_step=request.quantity_step,
        minimum_quantity=request.minimum_quantity,
        minimum_notional=request.minimum_notional,
        now_ms=request.now_ms,
    )
