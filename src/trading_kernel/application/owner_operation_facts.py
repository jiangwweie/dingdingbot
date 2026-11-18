"""Bounded readonly facts used by the existing Kernel operation coordinator."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.commands import ExchangeCommand
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionFacts,
    OwnerReductionState,
)
from src.trading_kernel.domain.owner_reduction_proof import OwnerReductionProof
from src.trading_kernel.domain.readonly_closure import ClosureFill
from src.trading_kernel.domain.trade_management import OrderEvidence


class OwnerReductionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    facts: OwnerReductionFacts
    protection_close_position: bool
    proof: OwnerReductionProof | None = None


class OwnerOperationFactsSource(Protocol):
    async def read_owner_position(
        self,
        *,
        aggregate: TradeAggregate,
        commands: tuple[ExchangeCommand, ...],
        accepted_order_ids: dict[str, str],
        operation_id: str | None,
    ) -> "OwnerPositionObservation": ...
    async def read_owner_reduction(
        self,
        *,
        aggregate: TradeAggregate,
        state: OwnerReductionState,
        authorization_id: str,
        commands: tuple[ExchangeCommand, ...],
        accepted_order_ids: dict[str, str],
    ) -> OwnerReductionObservation: ...


class OwnerOrderObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    command_id: str
    evidence: "OrderEvidence"
    status: str
    fills: tuple["ClosureFill", ...] = ()


class OwnerPositionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    facts: OwnerReductionFacts
    orders: tuple[OwnerOrderObservation, ...]
    protection_close_position: bool
