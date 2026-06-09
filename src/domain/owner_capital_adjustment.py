"""Owner-recorded capital adjustment semantics for BRC review.

This module is pure domain logic. It models Owner-recorded external capital
events so review can distinguish trading PnL from manual withdrawal,
injection, or capital-base reset facts. It never creates withdrawal,
transfer, order, runtime, or exchange instructions.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OwnerCapitalAdjustmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerCapitalAdjustmentType(str, Enum):
    OWNER_MANUAL_WITHDRAWAL = "owner_manual_withdrawal"
    MANUAL_PROFIT_EXTRACTION = "manual_profit_extraction"
    OWNER_CAPITAL_INJECTION = "owner_capital_injection"
    CAPITAL_BASE_RESET = "capital_base_reset"


class OwnerCapitalMovementClassification(str, Enum):
    EXPLAINED_BY_TRADING_ONLY = "explained_by_trading_only"
    EXPLAINED_BY_OWNER_CAPITAL_EVENTS = "explained_by_owner_capital_events"
    EXPLAINED_BY_TRADING_AND_OWNER_CAPITAL_EVENTS = (
        "explained_by_trading_and_owner_capital_events"
    )
    UNRESOLVED_EQUITY_DELTA = "unresolved_equity_delta"
    INVALID_CAPITAL_BASE = "invalid_capital_base"


_WITHDRAWAL_TYPES = {
    OwnerCapitalAdjustmentType.OWNER_MANUAL_WITHDRAWAL,
    OwnerCapitalAdjustmentType.MANUAL_PROFIT_EXTRACTION,
}


class OwnerCapitalAdjustmentRecord(OwnerCapitalAdjustmentModel):
    adjustment_id: str = Field(min_length=1, max_length=128)
    adjustment_type: OwnerCapitalAdjustmentType
    currency: str = Field(default="USDT", min_length=1, max_length=16)
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    capital_base_delta: Optional[Decimal] = None
    target_capital_base: Optional[Decimal] = Field(default=None, ge=Decimal("0"))
    reason: str = Field(min_length=1, max_length=512)
    occurred_at_ms: int = Field(ge=0)
    recorded_by: str = Field(default="owner", min_length=1, max_length=128)
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    records_external_owner_action: Literal[True] = True
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    order_instruction_created: Literal[False] = False
    exchange_called: Literal[False] = False
    mutates_runtime_budget: Literal[False] = False
    mutates_strategy_pnl: Literal[False] = False
    creates_risk_event: Literal[False] = False

    @model_validator(mode="after")
    def _validate_adjustment_shape(self) -> "OwnerCapitalAdjustmentRecord":
        if self.adjustment_type == OwnerCapitalAdjustmentType.CAPITAL_BASE_RESET:
            if self.target_capital_base is None:
                raise ValueError("capital base reset requires target_capital_base")
            if self.amount is not None:
                raise ValueError("capital base reset must not carry amount")
            if self.capital_base_delta is not None:
                raise ValueError("capital base reset must not carry capital_base_delta")
            return self

        if self.amount is None:
            raise ValueError(f"{self.adjustment_type.value} requires amount")
        if self.target_capital_base is not None:
            raise ValueError(
                f"{self.adjustment_type.value} must not carry target_capital_base"
            )
        return self


class OwnerCapitalAdjustmentEffect(OwnerCapitalAdjustmentModel):
    adjustment_id: str
    adjustment_type: OwnerCapitalAdjustmentType
    equity_flow_delta: Decimal
    capital_base_delta: Optional[Decimal] = None
    target_capital_base: Optional[Decimal] = None
    trading_pnl_delta: Decimal = Decimal("0")
    strategy_loss_attribution: Literal[False] = False
    risk_event_created: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    order_instruction_created: Literal[False] = False
    exchange_called: Literal[False] = False


class OwnerCapitalBaseReviewInput(OwnerCapitalAdjustmentModel):
    previous_account_equity: Decimal = Field(ge=Decimal("0"))
    current_account_equity: Decimal = Field(ge=Decimal("0"))
    starting_capital_base: Decimal = Field(ge=Decimal("0"))
    realized_trading_pnl: Decimal = Decimal("0")
    owner_capital_adjustments: list[OwnerCapitalAdjustmentRecord] = Field(
        default_factory=list
    )
    tolerance: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class OwnerCapitalBaseReviewResult(OwnerCapitalAdjustmentModel):
    classification: OwnerCapitalMovementClassification
    previous_account_equity: Decimal
    current_account_equity: Decimal
    observed_account_equity_delta: Decimal
    realized_trading_pnl: Decimal
    owner_equity_flow_delta: Decimal
    expected_account_equity_delta: Decimal
    unexplained_account_equity_delta: Decimal
    starting_capital_base: Decimal
    ending_capital_base: Decimal
    effects: list[OwnerCapitalAdjustmentEffect] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    owner_capital_events_are_strategy_pnl: Literal[False] = False
    owner_capital_events_are_risk_events: Literal[False] = False
    withdrawal_instruction_created: Literal[False] = False
    transfer_instruction_created: Literal[False] = False
    order_instruction_created: Literal[False] = False
    exchange_called: Literal[False] = False


def review_owner_capital_base_movement(
    review_input: OwnerCapitalBaseReviewInput,
) -> OwnerCapitalBaseReviewResult:
    """Classify account equity movement for review without execution authority."""

    capital_base = review_input.starting_capital_base
    owner_equity_flow_delta = Decimal("0")
    effects: list[OwnerCapitalAdjustmentEffect] = []
    blockers: list[str] = []
    warnings: list[str] = []

    for adjustment in sorted(
        review_input.owner_capital_adjustments,
        key=lambda item: (item.occurred_at_ms, item.adjustment_id),
    ):
        effect = _effect_for_adjustment(adjustment)
        effects.append(effect)
        owner_equity_flow_delta += effect.equity_flow_delta
        if effect.target_capital_base is not None:
            capital_base = effect.target_capital_base
        elif effect.capital_base_delta is not None:
            capital_base += effect.capital_base_delta
        if capital_base < Decimal("0"):
            blockers.append("capital_base_negative_after_owner_adjustment")

    observed_delta = (
        review_input.current_account_equity - review_input.previous_account_equity
    )
    expected_delta = review_input.realized_trading_pnl + owner_equity_flow_delta
    unexplained_delta = observed_delta - expected_delta
    if abs(unexplained_delta) > review_input.tolerance:
        blockers.append("unresolved_account_equity_delta")
        warnings.append(
            "equity_delta_requires_trade_reconciliation_or_owner_capital_record"
        )

    if "capital_base_negative_after_owner_adjustment" in blockers:
        classification = OwnerCapitalMovementClassification.INVALID_CAPITAL_BASE
    elif "unresolved_account_equity_delta" in blockers:
        classification = OwnerCapitalMovementClassification.UNRESOLVED_EQUITY_DELTA
    elif effects and review_input.realized_trading_pnl != Decimal("0"):
        classification = (
            OwnerCapitalMovementClassification.EXPLAINED_BY_TRADING_AND_OWNER_CAPITAL_EVENTS
        )
    elif effects:
        classification = (
            OwnerCapitalMovementClassification.EXPLAINED_BY_OWNER_CAPITAL_EVENTS
        )
    else:
        classification = OwnerCapitalMovementClassification.EXPLAINED_BY_TRADING_ONLY

    return OwnerCapitalBaseReviewResult(
        classification=classification,
        previous_account_equity=review_input.previous_account_equity,
        current_account_equity=review_input.current_account_equity,
        observed_account_equity_delta=observed_delta,
        realized_trading_pnl=review_input.realized_trading_pnl,
        owner_equity_flow_delta=owner_equity_flow_delta,
        expected_account_equity_delta=expected_delta,
        unexplained_account_equity_delta=unexplained_delta,
        starting_capital_base=review_input.starting_capital_base,
        ending_capital_base=capital_base,
        effects=effects,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def _effect_for_adjustment(
    adjustment: OwnerCapitalAdjustmentRecord,
) -> OwnerCapitalAdjustmentEffect:
    if adjustment.adjustment_type in _WITHDRAWAL_TYPES:
        assert adjustment.amount is not None
        equity_flow_delta = -adjustment.amount
        capital_base_delta = (
            adjustment.capital_base_delta
            if adjustment.capital_base_delta is not None
            else -adjustment.amount
        )
        return OwnerCapitalAdjustmentEffect(
            adjustment_id=adjustment.adjustment_id,
            adjustment_type=adjustment.adjustment_type,
            equity_flow_delta=equity_flow_delta,
            capital_base_delta=capital_base_delta,
        )

    if adjustment.adjustment_type == OwnerCapitalAdjustmentType.OWNER_CAPITAL_INJECTION:
        assert adjustment.amount is not None
        equity_flow_delta = adjustment.amount
        capital_base_delta = (
            adjustment.capital_base_delta
            if adjustment.capital_base_delta is not None
            else adjustment.amount
        )
        return OwnerCapitalAdjustmentEffect(
            adjustment_id=adjustment.adjustment_id,
            adjustment_type=adjustment.adjustment_type,
            equity_flow_delta=equity_flow_delta,
            capital_base_delta=capital_base_delta,
        )

    if adjustment.adjustment_type == OwnerCapitalAdjustmentType.CAPITAL_BASE_RESET:
        assert adjustment.target_capital_base is not None
        return OwnerCapitalAdjustmentEffect(
            adjustment_id=adjustment.adjustment_id,
            adjustment_type=adjustment.adjustment_type,
            equity_flow_delta=Decimal("0"),
            target_capital_base=adjustment.target_capital_base,
        )

    raise ValueError(f"unsupported owner capital adjustment: {adjustment.adjustment_type}")
