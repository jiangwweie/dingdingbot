"""Versioned pure exit-policy contracts for the six registered Events."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import StrEnum
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)


PositionSide = Literal["long", "short"]


class RunnerKind(StrEnum):
    STRUCTURAL_ATR = "structural_atr"


class ExitDecisionKind(StrEnum):
    NO_CHANGE = "no_change"
    MOVE_STOP = "move_stop"
    EXIT = "exit"


class LifecycleMarketFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watermark_ms: int
    is_final_closed_candle: bool
    structure_reference: Decimal
    atr: Decimal
    holding_bars: int

    @model_validator(mode="after")
    def _validate_facts(self) -> "LifecycleMarketFacts":
        if self.watermark_ms <= 0 or self.holding_bars < 0:
            raise ValueError("lifecycle market watermark and holding bars are invalid")
        if self.structure_reference <= 0 or self.atr <= 0:
            raise ValueError("lifecycle structure and ATR facts must be positive")
        return self


class ExitDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ExitDecisionKind
    reason: str
    source_watermark_ms: int
    proposed_stop: Decimal | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "ExitDecision":
        if not self.reason.strip() or self.source_watermark_ms <= 0:
            raise ValueError("exit decision reason and watermark are required")
        if self.kind is ExitDecisionKind.MOVE_STOP:
            if self.proposed_stop is None or self.proposed_stop <= 0:
                raise ValueError("runner move decision requires a positive stop")
        elif self.proposed_stop is not None:
            raise ValueError("non-move exit decision forbids a stop price")
        return self


class TakeProfitRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reward_multiple: Decimal
    quantity_fraction: Decimal
    execution_style: Literal["limit_gtc"] = "limit_gtc"
    market_fallback_allowed: Literal[False] = False

    @model_validator(mode="after")
    def _validate_rule(self) -> "TakeProfitRule":
        if self.reward_multiple <= 0:
            raise ValueError("take-profit reward multiple must be positive")
        if not Decimal("0") < self.quantity_fraction < Decimal("1"):
            raise ValueError("take-profit quantity fraction must be in (0, 1)")
        return self


class BreakEvenFloorRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_fee_basis: Literal["conservative_taker"] = "conservative_taker"
    slippage_buffer_ticks: int
    minimum_improvement_ticks: int

    @model_validator(mode="after")
    def _validate_ticks(self) -> "BreakEvenFloorRule":
        if self.slippage_buffer_ticks < 0:
            raise ValueError("break-even slippage ticks cannot be negative")
        if self.minimum_improvement_ticks <= 0:
            raise ValueError("break-even minimum improvement must be positive")
        return self


class StructuralAtrRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RunnerKind = RunnerKind.STRUCTURAL_ATR
    timeframe: Literal["15m", "1h"]
    structure_rule: Literal["confirmed_higher_low", "confirmed_lower_high"]
    structure_reference_fact: str
    structure_window_bars: int
    atr_period: int
    atr_buffer_multiple: Decimal
    minimum_improvement_ticks: int

    @field_validator("structure_reference_fact", mode="before")
    @classmethod
    def _require_reference_fact(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("runner structure reference fact must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_parameters(self) -> "StructuralAtrRunnerRule":
        if self.structure_window_bars <= 0 or self.atr_period <= 0:
            raise ValueError("runner structure and ATR windows must be positive")
        if self.atr_buffer_multiple < 0:
            raise ValueError("runner ATR buffer cannot be negative")
        if self.minimum_improvement_ticks <= 0:
            raise ValueError("runner minimum improvement must be positive")
        return self


class TimeStopRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_holding_bars: int

    @field_validator("max_holding_bars")
    @classmethod
    def _require_positive_bars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("time-stop holding bars must be positive")
        return value


class ExitPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_policy_id: str
    exit_policy_version: str
    event_spec_id: str
    event_id: str
    position_side: PositionSide
    tp1: TakeProfitRule
    break_even_floor: BreakEvenFloorRule
    runner: StructuralAtrRunnerRule
    time_stop: TimeStopRule | None = None

    @field_validator(
        "exit_policy_id",
        "exit_policy_version",
        "event_spec_id",
        "event_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("exit-policy identities must be non-blank")
        return normalized

    def semantic_hash(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{sha256(encoded).hexdigest()}"


class TakeProfitSplit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tp1_quantity: Decimal
    runner_quantity: Decimal

    @model_validator(mode="after")
    def _require_two_positive_legs(self) -> "TakeProfitSplit":
        if self.tp1_quantity <= 0 or self.runner_quantity <= 0:
            raise ValueError("TP1 and runner quantities must both be positive")
        return self


def registered_exit_policies() -> tuple[ExitPolicy, ...]:
    return tuple(_policy_for_contract(item) for item in registered_strategy_contracts())


def exit_policy_for(event_spec_id: str) -> ExitPolicy:
    normalized = str(event_spec_id or "").strip()
    matches = [
        policy
        for policy in registered_exit_policies()
        if policy.event_spec_id == normalized
    ]
    if len(matches) != 1:
        raise ValueError("registered Event must resolve exactly one exit policy")
    return matches[0]


def split_tp1_quantity(
    *,
    total_quantity: Decimal,
    quantity_step: Decimal,
    quantity_fraction: Decimal,
) -> TakeProfitSplit:
    if total_quantity <= 0 or quantity_step <= 0:
        raise ValueError("quantity and quantity step must be positive")
    if total_quantity % quantity_step != 0:
        raise ValueError("total quantity must be aligned to the quantity step")
    if not Decimal("0") < quantity_fraction < Decimal("1"):
        raise ValueError("TP1 quantity fraction must be in (0, 1)")
    tp1_quantity = _round_to_step(
        total_quantity * quantity_fraction,
        quantity_step,
        rounding=ROUND_FLOOR,
    )
    return TakeProfitSplit(
        tp1_quantity=tp1_quantity,
        runner_quantity=total_quantity - tp1_quantity,
    )


def calculate_cost_adjusted_break_even(
    *,
    side: str,
    entry_average_price: Decimal,
    runner_quantity: Decimal,
    allocated_entry_fee_quote: Decimal,
    exit_taker_fee_rate: Decimal,
    price_tick: Decimal,
    slippage_buffer_ticks: int,
) -> Decimal:
    _require_financial_inputs(
        entry_average_price=entry_average_price,
        runner_quantity=runner_quantity,
        price_tick=price_tick,
        allocated_entry_fee_quote=allocated_entry_fee_quote,
        exit_taker_fee_rate=exit_taker_fee_rate,
        slippage_buffer_ticks=slippage_buffer_ticks,
    )
    slippage_buffer_quote = (
        price_tick * Decimal(slippage_buffer_ticks) * runner_quantity
    )
    entry_notional = entry_average_price * runner_quantity
    if side == "long":
        raw = (
            entry_notional
            + allocated_entry_fee_quote
            + slippage_buffer_quote
        ) / (runner_quantity * (Decimal("1") - exit_taker_fee_rate))
        return _round_to_step(raw, price_tick, rounding=ROUND_CEILING)
    if side == "short":
        raw = (
            entry_notional
            - allocated_entry_fee_quote
            - slippage_buffer_quote
        ) / (runner_quantity * (Decimal("1") + exit_taker_fee_rate))
        if raw <= 0:
            raise ValueError("short break-even floor must remain positive")
        return _round_to_step(raw, price_tick, rounding=ROUND_FLOOR)
    raise ValueError("position side must be long or short")


def calculate_structural_runner_stop(
    *,
    side: str,
    structure_reference: Decimal,
    atr: Decimal,
    atr_buffer_multiple: Decimal,
    price_tick: Decimal,
) -> Decimal:
    if (
        structure_reference <= 0
        or atr <= 0
        or atr_buffer_multiple < 0
        or price_tick <= 0
    ):
        raise ValueError("runner price, ATR, multiplier, and tick must be valid")
    offset = atr * atr_buffer_multiple
    if side == "long":
        raw = structure_reference - offset
        if raw <= 0:
            raise ValueError("long structural runner stop must remain positive")
        return _round_to_step(raw, price_tick, rounding=ROUND_FLOOR)
    if side == "short":
        return _round_to_step(
            structure_reference + offset,
            price_tick,
            rounding=ROUND_CEILING,
        )
    raise ValueError("position side must be long or short")


def evaluate_exit_policy(
    *,
    policy: ExitPolicy,
    current_stop: Decimal,
    break_even_floor: Decimal,
    price_tick: Decimal,
    last_runner_watermark_ms: int,
    market_facts: LifecycleMarketFacts,
) -> ExitDecision:
    if current_stop <= 0 or break_even_floor <= 0 or price_tick <= 0:
        raise ValueError("runner evaluation prices and tick must be positive")
    if market_facts.watermark_ms <= last_runner_watermark_ms:
        return _exit_decision(
            ExitDecisionKind.NO_CHANGE,
            "market_watermark_not_new",
            market_facts.watermark_ms,
        )
    if not market_facts.is_final_closed_candle:
        return _exit_decision(
            ExitDecisionKind.NO_CHANGE,
            "closed_candle_required",
            market_facts.watermark_ms,
        )
    if (
        policy.time_stop is not None
        and market_facts.holding_bars >= policy.time_stop.max_holding_bars
    ):
        return _exit_decision(
            ExitDecisionKind.EXIT,
            "time_stop_hit",
            market_facts.watermark_ms,
        )
    candidate = calculate_structural_runner_stop(
        side=policy.position_side,
        structure_reference=market_facts.structure_reference,
        atr=market_facts.atr,
        atr_buffer_multiple=policy.runner.atr_buffer_multiple,
        price_tick=price_tick,
    )
    candidate = (
        max(candidate, break_even_floor)
        if policy.position_side == "long"
        else min(candidate, break_even_floor)
    )
    required_improvement = (
        price_tick * policy.runner.minimum_improvement_ticks
    )
    improvement = (
        candidate - current_stop
        if policy.position_side == "long"
        else current_stop - candidate
    )
    if improvement < required_improvement:
        return _exit_decision(
            ExitDecisionKind.NO_CHANGE,
            "runner_stop_not_improved",
            market_facts.watermark_ms,
        )
    return ExitDecision(
        kind=ExitDecisionKind.MOVE_STOP,
        reason="structural_atr_runner_improvement",
        source_watermark_ms=market_facts.watermark_ms,
        proposed_stop=candidate,
    )


def _policy_for_contract(contract: RegisteredStrategyContract) -> ExitPolicy:
    return ExitPolicy(
        exit_policy_id=contract.exit_policy_id,
        exit_policy_version="2026-07-22-v1",
        event_spec_id=contract.event_spec_id,
        event_id=contract.event_id,
        position_side=contract.position_side,
        tp1=TakeProfitRule(
            reward_multiple=Decimal("1"),
            quantity_fraction=Decimal("0.5"),
        ),
        break_even_floor=BreakEvenFloorRule(
            slippage_buffer_ticks=2,
            minimum_improvement_ticks=2,
        ),
        runner=StructuralAtrRunnerRule(
            timeframe=contract.timeframe,
            structure_rule=(
                "confirmed_higher_low"
                if contract.position_side == "long"
                else "confirmed_lower_high"
            ),
            structure_reference_fact=contract.protection_reference_fact,
            structure_window_bars=4,
            atr_period=14,
            atr_buffer_multiple=Decimal("0.5"),
            minimum_improvement_ticks=2,
        ),
        time_stop=(
            TimeStopRule(max_holding_bars=96)
            if contract.event_id == "SOR-LONG"
            else None
        ),
    )


def _round_to_step(value: Decimal, step: Decimal, *, rounding: str) -> Decimal:
    return (value / step).to_integral_value(rounding=rounding) * step


def _require_financial_inputs(
    *,
    entry_average_price: Decimal,
    runner_quantity: Decimal,
    price_tick: Decimal,
    allocated_entry_fee_quote: Decimal,
    exit_taker_fee_rate: Decimal,
    slippage_buffer_ticks: int,
) -> None:
    if entry_average_price <= 0 or runner_quantity <= 0 or price_tick <= 0:
        raise ValueError("break-even price, quantity, and tick must be positive")
    if allocated_entry_fee_quote < 0 or slippage_buffer_ticks < 0:
        raise ValueError("break-even fee and slippage values cannot be negative")
    if not Decimal("0") <= exit_taker_fee_rate < Decimal("1"):
        raise ValueError("exit taker fee rate must be in [0, 1)")


def _exit_decision(
    kind: ExitDecisionKind,
    reason: str,
    source_watermark_ms: int,
) -> ExitDecision:
    return ExitDecision(
        kind=kind,
        reason=reason,
        source_watermark_ms=source_watermark_ms,
    )
