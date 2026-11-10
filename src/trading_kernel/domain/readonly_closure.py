"""Exact positive exit evidence, independent of unprovable absence of intervention."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.trade_management import OrderEvidence


class ClosureFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    trade_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    occurred_at_ms: int = Field(gt=0)


class TerminalOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    namespace: Literal["regular", "conditional"]
    order_id: str = Field(min_length=1)
    status: Literal["FILLED", "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "FINISHED", "REJECTED"]
    executed_quantity: Decimal = Field(ge=0, allow_inf_nan=False)


class ReadonlyClosureProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str = Field(min_length=1)
    domain: NettingDomain
    entry_order_id: str = Field(min_length=1)
    exit_order_id: str = Field(min_length=1)
    exit_evidence: OrderEvidence
    entry_fills: tuple[ClosureFill, ...] = Field(min_length=1, max_length=100)
    exit_fills: tuple[ClosureFill, ...] = Field(min_length=1, max_length=100)
    terminal_orders: tuple[TerminalOrder, ...] = Field(min_length=2, max_length=200)
    snapshot: PositionSnapshot
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def coherent(self) -> ReadonlyClosureProof:
        if self.domain != self.snapshot.netting_domain or self.snapshot.quantity != 0:
            raise ValueError("closure requires exact flat position")
        if self.snapshot.open_orders or not self.snapshot.orders_complete:
            raise ValueError("closure forbids residual or incomplete orders")
        if self.entry_order_id == self.exit_order_id:
            raise ValueError("external exit cannot be the entry")
        t=self.exit_evidence.terms
        if t.identity[:4] != (self.domain.venue_id,self.domain.account_id,self.domain.exchange_instrument_id,self.domain.position_side) or t.order_namespace!='regular' or t.exchange_order_id!=self.exit_order_id:
            raise ValueError("closure exit evidence identity differs")
        if self.exit_evidence.action.value!='trade' or not t.reduces_position or t.order_type!='MARKET' or not self.exit_evidence.coverage_complete or self.exit_evidence.known_command_outcome_pending:
            raise ValueError("closure requires exact external market execution")
        if self.exit_evidence.received_at_ms>self.observed_at_ms:
            raise ValueError("closure exit evidence was received after snapshot")
        if self.snapshot.observed_at_ms != self.observed_at_ms or not 0 < self.valid_until_ms-self.observed_at_ms <= 30_000:
            raise ValueError("closure observation window differs")
        identities=[(o.namespace,o.order_id) for o in self.terminal_orders]
        if len(set(identities)) != len(identities):
            raise ValueError("closure order identity duplicated")
        trades=[f.trade_id for f in (*self.entry_fills,*self.exit_fills)]
        if len(set(trades)) != len(trades):
            raise ValueError("closure trade identity duplicated")
        if any(f.order_id != self.entry_order_id for f in self.entry_fills) or any(f.order_id != self.exit_order_id for f in self.exit_fills):
            raise ValueError("closure fill belongs to another order")
        if max(f.occurred_at_ms for f in self.entry_fills)>min(f.occurred_at_ms for f in self.exit_fills):
            raise ValueError("closure exit precedes entry")
        if max(f.occurred_at_ms for f in (*self.entry_fills,*self.exit_fills))>self.observed_at_ms:
            raise ValueError("closure fill is in future")
        return self

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))
