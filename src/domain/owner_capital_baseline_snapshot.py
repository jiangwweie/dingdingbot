"""Owner capital baseline snapshots for withdrawal-aware review.

These records freeze account-equity and capital-base facts for review. They do
not create withdrawals, transfers, orders, exchange calls, runtime-budget
mutations, strategy-PnL mutations, or risk events.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OwnerCapitalBaselineSnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerCapitalBaselineSnapshotSource(str, Enum):
    OWNER_RECORDED = "owner_recorded"
    TRADING_CONSOLE_READ_MODEL = "trading_console_read_model"
    STARTUP_ACCOUNT_FACT = "startup_account_fact"
    READ_ONLY_ACCOUNT_FACT = "read_only_account_fact"
    MANUAL_REVIEW = "manual_review"


class OwnerCapitalBaselineSnapshot(OwnerCapitalBaselineSnapshotModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    currency: str = Field(default="USDT", min_length=1, max_length=16)
    account_equity: Decimal = Field(ge=Decimal("0"))
    capital_base: Decimal = Field(ge=Decimal("0"))
    available_balance: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    unrealized_pnl: Optional[Decimal] = None
    source: OwnerCapitalBaselineSnapshotSource
    reason: str = Field(min_length=1, max_length=512)
    occurred_at_ms: int = Field(ge=0)
    recorded_by: str = Field(default="owner", min_length=1, max_length=128)
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    records_account_equity_fact: Literal[True] = True
    creates_withdrawal_instruction: Literal[False] = False
    creates_transfer_instruction: Literal[False] = False
    creates_order_instruction: Literal[False] = False
    calls_exchange: Literal[False] = False
    mutates_runtime_budget: Literal[False] = False
    mutates_strategy_pnl: Literal[False] = False
    creates_risk_event: Literal[False] = False
