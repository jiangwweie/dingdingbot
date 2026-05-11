"""Strategy Contract v2 domain models.

This module is a pure type contract. It does not wire strategies into runtime,
permissions, risk checks, order creation, or execution.
"""

from __future__ import annotations

import time
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.models import Direction


class StrategyContractModel(BaseModel):
    """Base model for Strategy Contract v2 value objects."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")


class StrategyFamily(str, Enum):
    """Strategy family labels for contract classification, not routing."""

    PATTERN = "pattern"
    LIFECYCLE_BREAKOUT = "lifecycle_breakout"
    LIFECYCLE = "lifecycle"
    PULLBACK = "pullback"
    CUSTOM = "custom"


class EntryPolicyKind(str, Enum):
    """How a strategy-level signal intends to enter if later permitted."""

    MARKET_AFTER_CONFIRMED_CLOSE = "market_after_confirmed_close"
    # Design note: this means the next executable market opportunity after a
    # confirmed closed-bar signal. It does not guarantee exact live submission
    # at the exchange's next kline open; strict next-bar-open scheduling needs
    # a separate execution scheduling design.
    MARKET_NEXT_OPEN = "market_next_open"
    MARKET_NEXT_EXECUTABLE_OPPORTUNITY = "market_next_executable_opportunity"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    SIGNAL_ONLY = "signal_only"


class StopPolicyKind(str, Enum):
    """Structured protective stop semantics."""

    FIXED_PRICE = "fixed_price"
    PRIOR_BAR_LOW = "prior_bar_low"
    PRIOR_BAR_HIGH = "prior_bar_high"
    ATR_MULTIPLE = "atr_multiple"
    STRUCTURE_REFERENCE = "structure_reference"
    DONCHIAN_INVALIDATED = "donchian_invalidated"
    NONE = "none"


class TakeProfitPolicyKind(str, Enum):
    """Structured take-profit policy semantics."""

    MULTI_TP_RR = "multi_tp_rr"
    NO_FIXED_TP = "no_fixed_tp"
    LIFECYCLE_ONLY = "lifecycle_only"


class LifecycleExitPolicyKind(str, Enum):
    """Strategy-owned lifecycle exit family."""

    NONE = "none"
    EMA_CLOSE_BREAK = "ema_close_break"
    TRAILING_ATR = "trailing_atr"
    TIME_STOP = "time_stop"
    CUSTOM_NAMED = "custom_named"


class LifecycleAppliesTo(str, Enum):
    """Scope for lifecycle exit evaluation."""

    EXISTING_POSITION_ONLY = "existing_position_only"


class ExitSignalRef(str, Enum):
    """Reference to the exit signal model emitted by a lifecycle policy."""

    EXIT_SIGNAL = "ExitSignal"


class ExitDesiredAction(str, Enum):
    """Desired action expressed by an ExitSignal before execution translation."""

    CLOSE_POSITION = "close_position"
    REDUCE_POSITION = "reduce_position"
    REPORT_ONLY = "report_only"


class ExitQuantityPolicy(str, Enum):
    """Quantity semantics for an ExitSignal."""

    FULL_POSITION = "full_position"
    PERCENT = "percent"
    FIXED_QTY = "fixed_qty"
    NONE = "none"


class StrategyPermissionState(str, Enum):
    """Mode eligibility only; this is not OwnerGateState and does not authorize execution."""

    DISABLED = "DISABLED"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    PAPER_ALLOWED = "PAPER_ALLOWED"
    TESTNET_ALLOWED = "TESTNET_ALLOWED"
    LIVE_ALLOWED = "LIVE_ALLOWED"


class EntryPolicy(StrategyContractModel):
    """Structured strategy entry semantics."""

    kind: EntryPolicyKind
    trigger: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reference_price: Optional[Decimal] = None
    valid_after_ms: Optional[int] = None
    valid_until_ms: Optional[int] = None


class StopPolicy(StrategyContractModel):
    """Structured stop policy.

    StopPolicy carries formal trading semantics and must not be hidden in
    PatternResult.details. For lifecycle strategies such as Direction A, a
    protective SL is a capital-protection / catastrophic-loss boundary, not the
    EMA60 payoff-engine lifecycle exit.
    """

    kind: StopPolicyKind
    required: bool
    price: Optional[Decimal] = None
    reference: Optional[dict[str, Any]] = None
    risk_notes: Optional[str] = None


class TakeProfitLevel(StrategyContractModel):
    """One RR-based take-profit level."""

    rr: Decimal
    position_ratio: Decimal


class TakeProfitPolicy(StrategyContractModel):
    """Structured take-profit semantics."""

    kind: TakeProfitPolicyKind
    levels: list[TakeProfitLevel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_levels_for_kind(self) -> "TakeProfitPolicy":
        if self.kind in {
            TakeProfitPolicyKind.NO_FIXED_TP,
            TakeProfitPolicyKind.LIFECYCLE_ONLY,
        } and self.levels:
            raise ValueError(f"{self.kind.value} must not define fixed TP levels")
        return self


class LifecycleExitPolicy(StrategyContractModel):
    """Structured lifecycle exit semantics, separate from TP/SL geometry."""

    kind: LifecycleExitPolicyKind
    timeframe: Optional[str] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    applies_to: LifecycleAppliesTo = LifecycleAppliesTo.EXISTING_POSITION_ONLY
    emits: ExitSignalRef = ExitSignalRef.EXIT_SIGNAL


class RequiredHistory(StrategyContractModel):
    """Minimum market history and indicator warmup requirements."""

    same_timeframe_bars: int = Field(default=0, ge=0)
    indicator_warmup: dict[str, int] = Field(default_factory=dict)


class StrategySignalV2(StrategyContractModel):
    """Future unified strategy-level signal contract."""

    strategy_id: str
    strategy_family: StrategyFamily | str
    symbol: str
    timeframe: str
    direction: Direction
    entry_policy: EntryPolicy
    stop_policy: StopPolicy
    take_profit_policy: TakeProfitPolicy
    lifecycle_exit_policy: LifecycleExitPolicy
    required_history: RequiredHistory
    score: Optional[Decimal] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    source_context_id: Optional[str] = None


class ExitSignal(StrategyContractModel):
    """Pure lifecycle exit signal model; not connected to execution."""

    strategy_id: str
    position_id: Optional[str] = None
    signal_id: Optional[str] = None
    symbol: str
    direction: Direction
    reason_code: str
    trigger_timeframe: str
    trigger_kline_timestamp: int
    desired_action: ExitDesiredAction
    quantity_policy: ExitQuantityPolicy
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyPermissionKey(StrategyContractModel):
    """Eligibility key: strategy_id + symbol + timeframe."""

    strategy_id: str
    symbol: str
    timeframe: str

    @property
    def value(self) -> str:
        return f"{self.strategy_id}:{self.symbol}:{self.timeframe}"
