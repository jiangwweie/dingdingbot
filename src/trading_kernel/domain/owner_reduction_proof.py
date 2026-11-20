"""Exact completed close fills and surviving protection for Owner continuation."""

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exit_execution import EntryFill
from src.trading_kernel.domain.identities import NettingDomain

if TYPE_CHECKING:
    from src.trading_kernel.domain.aggregate import TradeAggregate


class RetiredProtectionProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    evidence_id: str = Field(min_length=1)
    exchange_order_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    order_namespace: Literal["conditional"] = "conditional"
    status: Literal["CANCELED", "EXPIRED"]
    executed_quantity: Decimal = Field(ge=0, le=0, allow_inf_nan=False)
    observed_at_ms: int = Field(gt=0)


class OwnerReductionProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_stage: Literal["pre_tp", "pre_tp_unplaced", "wait_price", "runner"]
    source_tp_filled_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    retired_protections: tuple[RetiredProtectionProof, ...] = Field(
        default=(), max_length=2
    )
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
            or self.original_tp_filled_quantity != self.source_tp_filled_quantity
            or len({p.exchange_order_id for p in self.retired_protections})
            != len(self.retired_protections)
            or any(
                p.observed_at_ms > self.observed_at_ms
                or p.exchange_order_id == self.protection_order_id
                for p in self.retired_protections
            )
            or not self.observed_at_ms < self.valid_until_ms
        ):
            raise ValueError("owner_reduction_proof_incomplete")
        if self.source_stage == "pre_tp":
            if (
                not self.original_tp_order_id
                or not self.original_tp_cancelled
                or self.source_tp_filled_quantity != 0
            ):
                raise ValueError("owner_reduction_proof_unretired_tp")
        elif self.original_tp_order_id is not None or self.original_tp_cancelled:
            raise ValueError("owner_reduction_proof_repeated_tp_cancel")
        if self.source_stage in {"wait_price", "pre_tp_unplaced"} and self.source_tp_filled_quantity != 0:
            raise ValueError("owner_reduction_proof_changed_tp_history")
        return self

    def require_source(self, aggregate: "TradeAggregate") -> None:
        from src.trading_kernel.domain.aggregate import AggregateStatus

        stage = (
            "runner"
            if aggregate.status is AggregateStatus.RUNNER_PROTECTED
            else "wait_price"
            if aggregate.status is AggregateStatus.POSITION_PROTECTED
            and aggregate.owner_reduction_context is not None
            else "pre_tp_unplaced"
            if aggregate.status is AggregateStatus.TP1_PENDING
            and aggregate.tp1_exchange_order_id is None
            else "pre_tp"
            if aggregate.status is AggregateStatus.POSITION_PROTECTED
            else None
        )
        if (
            stage != self.source_stage
            or aggregate.identity.ticket_id != self.ticket_id
            or aggregate.identity.netting_domain != self.domain
            or aggregate.position_qty != self.source_quantity
            or aggregate.tp1_filled_qty != self.source_tp_filled_quantity
            or (
                stage == "pre_tp"
                and self.original_tp_order_id != aggregate.tp1_exchange_order_id
            )
        ):
            raise ValueError("owner_reduction_proof_source_changed")
        old_ids = {
            oid
            for oid in (
                aggregate.active_stop_exchange_order_id,
                aggregate.initial_stop_exchange_order_id,
            )
            if oid
        }
        retired = {item.exchange_order_id for item in self.retired_protections}
        if not retired.issubset(old_ids):
            raise ValueError("owner_reduction_proof_retired_stop_unknown")
        if (
            aggregate.active_stop_exchange_order_id != self.protection_order_id
            and aggregate.active_stop_exchange_order_id not in retired
        ):
            raise ValueError("owner_reduction_proof_old_stop_unresolved")

    @property
    def average_price(self) -> Decimal:
        return (
            sum((f.quantity * f.price for f in self.fills), Decimal(0))
            / self.executed_quantity
        )

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))
