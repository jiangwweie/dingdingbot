"""Typed side effects emitted by the pure lifecycle reducer."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.ticket import TradeTicket


class _Effect(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PrepareEntryCommand(_Effect):
    ticket: TradeTicket


class PrepareInitialStopCommand(_Effect):
    ticket_id: str
    quantity: Decimal
    stop_price: Decimal


class PrepareTakeProfitCommand(_Effect):
    ticket_id: str
    quantity: Decimal
    limit_price: Decimal


class PrepareProtectionReplacementCommand(_Effect):
    ticket_id: str
    quantity: Decimal
    stop_price: Decimal
    replaces_exchange_order_id: str
    source_watermark_ms: int


class PrepareExitCommand(_Effect):
    ticket_id: str
    quantity: Decimal
    reason: str


class CancelEntryRemainder(_Effect):
    ticket_id: str


class RequestControlledFlatten(_Effect):
    ticket_id: str
    quantity: Decimal


class PrepareControlledFlattenCommand(_Effect):
    ticket_id: str
    quantity: Decimal


class CancelProtectionOrders(_Effect):
    ticket_id: str
    exchange_order_id: str


class MarkCancelCommandReconciledAbsent(_Effect):
    ticket_id: str
    exchange_order_id: str


class OpenIncident(_Effect):
    ticket_id: str
    incident_kind: str


class ResolveIncident(_Effect):
    ticket_id: str
    incident_kind: str


class ReleaseEntryLane(_Effect):
    ticket_id: str


class SettleBudget(_Effect):
    ticket_id: str


class ReleaseBudget(_Effect):
    ticket_id: str


KernelEffect = (
    PrepareEntryCommand
    | PrepareInitialStopCommand
    | PrepareTakeProfitCommand
    | PrepareProtectionReplacementCommand
    | PrepareExitCommand
    | CancelEntryRemainder
    | RequestControlledFlatten
    | PrepareControlledFlattenCommand
    | CancelProtectionOrders
    | MarkCancelCommandReconciledAbsent
    | OpenIncident
    | ResolveIncident
    | ReleaseEntryLane
    | SettleBudget
    | ReleaseBudget
)
