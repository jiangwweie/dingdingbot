"""Runtime exchange-close projection recovery domain model.

This is local projection recovery for an already-observed exchange close fill.
It never authorizes, submits, cancels, amends, closes, withdraws, or transfers.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeExchangeCloseProjectionRecoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExchangeCloseProjectionRecoveryStatus(str, Enum):
    BLOCKED = "blocked"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    ALREADY_PROJECTED = "already_projected"


class RuntimeExchangeCloseProjectionRecoveryRequest(
    RuntimeExchangeCloseProjectionRecoveryModel
):
    symbol: str = Field(min_length=1, max_length=128)
    exit_local_order_id: str = Field(min_length=1, max_length=128)
    exit_exchange_order_id: Optional[str] = Field(default=None, max_length=128)
    exit_trade_id: str = Field(min_length=1, max_length=128)
    apply: bool = False
    operator_reason: str = Field(
        default="runtime_exchange_close_projection_recovery",
        min_length=1,
        max_length=256,
    )


class RuntimeExchangeCloseProjectionRecoveryResult(
    RuntimeExchangeCloseProjectionRecoveryModel
):
    recovery_id: str = Field(min_length=1, max_length=320)
    status: RuntimeExchangeCloseProjectionRecoveryStatus
    symbol: str = Field(min_length=1, max_length=128)
    exit_local_order_id: str = Field(min_length=1, max_length=128)
    exit_exchange_order_id: Optional[str] = Field(default=None, max_length=128)
    exit_trade_id: str = Field(min_length=1, max_length=128)
    signal_id: Optional[str] = Field(default=None, max_length=128)
    runtime_instance_id: Optional[str] = Field(default=None, max_length=128)
    local_position_id: Optional[str] = Field(default=None, max_length=128)
    position_direction: Optional[str] = Field(default=None, max_length=32)
    expected_close_side: Optional[str] = Field(default=None, max_length=16)
    observed_trade_side: Optional[str] = Field(default=None, max_length=16)
    observed_trade_qty: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    observed_trade_price: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    observed_trade_timestamp_ms: Optional[int] = Field(default=None, ge=0)
    local_position_qty_before: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    local_position_qty_after: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    realized_pnl_delta: Decimal = Decimal("0")
    realized_pnl_after: Optional[Decimal] = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    local_state_mutated: bool
    order_status_changed: bool
    position_projection_changed: bool
    exchange_read_only: Literal[True] = True
    exchange_write_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    exchange_order_cancelled: Literal[False] = False
    exchange_order_amended: Literal[False] = False
    exchange_position_closed: Literal[False] = False
    order_created: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _status_contract(self) -> "RuntimeExchangeCloseProjectionRecoveryResult":
        if self.status == RuntimeExchangeCloseProjectionRecoveryStatus.BLOCKED:
            if not self.blockers:
                raise ValueError("blocked close projection recovery requires blockers")
            if self.local_state_mutated or self.order_status_changed or self.position_projection_changed:
                raise ValueError("blocked recovery cannot mutate local state")
        if self.status == RuntimeExchangeCloseProjectionRecoveryStatus.READY_TO_APPLY:
            if self.local_state_mutated or self.order_status_changed or self.position_projection_changed:
                raise ValueError("ready dry-run recovery cannot mutate local state")
        if self.status == RuntimeExchangeCloseProjectionRecoveryStatus.APPLIED:
            if not self.local_state_mutated:
                raise ValueError("applied recovery must mutate local state")
            if not (self.order_status_changed or self.position_projection_changed):
                raise ValueError("applied recovery requires an order or position projection change")
        return self


def recovery_id_for_trade(*, exit_local_order_id: str, exit_trade_id: str) -> str:
    return f"runtime-close-projection-recovery-{exit_local_order_id}-{exit_trade_id}"

