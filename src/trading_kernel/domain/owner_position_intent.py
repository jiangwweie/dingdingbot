"""The exact position intent confirmed on the phone."""

from decimal import Decimal, localcontext
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

INTENT_PATH = "/api/owner/v1/mobile/operations/intent"
START_WINDOW_MS = 60_000
DECIMAL_PATTERN = r"^(?:\d+(?:\.\d+)?|\.\d+)$"


class OwnerPositionIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    ticket_id: str = Field(min_length=1, max_length=160)
    kind: Literal[
        "position_reduce",
        "position_close",
        "protection_tighten",
        "manual_tp_set",
        "manual_tp_cancel",
    ]
    quantity: str | None = Field(default=None, max_length=64, pattern=DECIMAL_PATTERN)
    price: str | None = Field(default=None, max_length=64, pattern=DECIMAL_PATTERN)
    basis_quantity: str | None = Field(
        default=None, max_length=64, pattern=DECIMAL_PATTERN
    )
    basis_version: int | None = Field(default=None, gt=0)
    basis_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    tp_order_id: str | None = Field(default=None, min_length=1, max_length=160)

    @property
    def amount(self) -> Decimal | None:
        return None if self.quantity is None else Decimal(self.quantity)

    @model_validator(mode="after")
    def exact_terms(self) -> Self:
        if (self.quantity is not None) != (
            self.kind in {"position_reduce", "manual_tp_set"}
        ) or (self.price is not None) != (
            self.kind in {"protection_tighten", "manual_tp_set"}
        ):
            raise ValueError("unexpected_amount")
        for value in (self.quantity, self.price, self.basis_quantity):
            if value is not None and Decimal(value) <= 0:
                raise ValueError("nonpositive_amount")
        basis = (self.basis_quantity, self.basis_version, self.basis_token)
        if self.kind == "position_reduce":
            if any(value is None for value in basis):
                raise ValueError("reduction_basis_required")
            assert self.basis_quantity is not None and self.amount is not None
            with localcontext() as context:
                context.prec = 66
                if self.amount * 2 > Decimal(self.basis_quantity):
                    raise ValueError("reduction_exceeds_half")
        elif any(value is not None for value in basis):
            raise ValueError("unexpected_reduction_basis")
        if self.kind == "manual_tp_cancel" and self.tp_order_id is None:
            raise ValueError("manual_tp_identity_required")
        if self.tp_order_id is not None and self.kind not in {
            "manual_tp_set",
            "manual_tp_cancel",
        }:
            raise ValueError("unexpected_tp_identity")
        return self
