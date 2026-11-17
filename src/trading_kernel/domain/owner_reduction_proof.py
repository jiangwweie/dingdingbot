"""Exact completed close fills and surviving protection for Owner continuation."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exit_execution import EntryFill
from src.trading_kernel.domain.identities import NettingDomain


class OwnerReductionProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    authorization_id: str = Field(min_length=1)
    operation_id: str = Field(min_length=1)
    ticket_id: str = Field(min_length=1)
    domain: NettingDomain
    command_id: str = Field(min_length=1)
    exchange_order_id: str = Field(min_length=1)
    venue_client_order_id: str = Field(min_length=1)
    order_status: Literal["FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"]
    requested_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    executed_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    source_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    remaining_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    fills: tuple[EntryFill, ...] = Field(min_length=1, max_length=1000)
    original_tp_order_id: str | None
    original_tp_cancelled: bool
    original_tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    protection_order_id: str = Field(min_length=1)
    protection_price: Decimal = Field(gt=0, allow_inf_nan=False)
    protected_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def conserved(self):
        if (
            self.executed_quantity > self.requested_quantity
            or self.source_quantity != self.remaining_quantity + self.executed_quantity
        ):
            raise ValueError("owner_reduction_proof_quantity_mismatch")
        if (
            len({x.trade_id for x in self.fills}) != len(self.fills)
            or sum((f.quantity for f in self.fills), Decimal(0))
            != self.executed_quantity
            or self.protected_quantity != self.remaining_quantity
            or not self.original_tp_cancelled
            or self.original_tp_filled_quantity != 0
            or not self.observed_at_ms < self.valid_until_ms
        ):
            raise ValueError("owner_reduction_proof_incomplete")
        return self

    @property
    def average_price(self) -> Decimal:
        return (
            sum((f.quantity * f.price for f in self.fills), Decimal(0))
            / self.executed_quantity
        )

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))
