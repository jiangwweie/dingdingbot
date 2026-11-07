"""Frozen observation batches shared by read-only collection and current authority."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.trade_management import OrderEvidence, OrderTerms


class ManagementScanRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    domain: NettingDomain
    since_ms: int = Field(gt=0)
    now_ms: int = Field(gt=0)
    known_orders: tuple[OrderTerms, ...] = ()


class ManagementScan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ticket_id: str
    snapshot: PositionSnapshot
    orders: tuple[OrderTerms, ...]
    evidence: tuple[OrderEvidence, ...]
    complete: bool
    reason: str | None = None
    covered_until_ms: int = Field(gt=0)
