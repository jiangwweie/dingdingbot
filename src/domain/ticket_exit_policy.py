"""Pure, versioned Ticket exit-policy semantics.

This module owns typed policy validation, canonical identity hashing, financial
calculations, and deterministic decisions only.  It has no database, network,
filesystem, scheduler, or exchange-command authority.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Annotated, Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_TIMEFRAME_RE = re.compile(r"^[1-9][0-9]*(?:m|h|d)$")


class TpExecutionStyle(str, Enum):
    LIMIT_GTC = "limit_gtc"
    PASSIVE_LIMIT_GTX = "passive_limit_gtx"


class RewardBasis(str, Enum):
    ACTUAL_ENTRY_R = "actual_entry_r"


class PolicyFamily(str, Enum):
    RIGHT_TAIL_RUNNER = "right_tail_runner"
    FIXED_TARGETS = "fixed_targets"
    LIFECYCLE_ONLY = "lifecycle_only"


class ExitDecisionKind(str, Enum):
    NOOP = "noop"
    MOVE_RUNNER_STOP = "move_runner_stop"
    CLOSE_RUNNER = "close_runner"
    BLOCKED = "blocked"


class TicketTakeProfitLeg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["TP1", "TP2", "TP3", "TP4", "TP5"]
    reward_multiple: Decimal
    quantity_fraction: Decimal
    execution_style: TpExecutionStyle
    market_fallback_allowed: Literal[False] = False

    @model_validator(mode="after")
    def _validate_financial_values(self) -> "TicketTakeProfitLeg":
        if self.reward_multiple <= 0:
            raise ValueError("take-profit reward_multiple must be positive")
        if not Decimal("0") < self.quantity_fraction <= Decimal("1"):
            raise ValueError("take-profit quantity_fraction must be in (0, 1]")
        return self


class RunnerBreakEvenFloorRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["runner_leg_cost_adjusted_break_even"]
    trigger: Literal["tp1_target_quantity_complete"]
    exit_fee_basis: Literal["conservative_taker"]
    slippage_buffer_ticks: int
    minimum_improvement_ticks: int

    @model_validator(mode="after")
    def _validate_ticks(self) -> "RunnerBreakEvenFloorRule":
        if self.slippage_buffer_ticks < 0:
            raise ValueError("slippage_buffer_ticks must be non-negative")
        if self.minimum_improvement_ticks < 1:
            raise ValueError("minimum_improvement_ticks must be positive")
        return self


class StructuralAtrRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["structural_atr"]
    timeframe: str
    structure_rule: str
    structure_window_bars: int
    atr_period: int
    atr_buffer_multiple: Decimal
    minimum_improvement_ticks: int

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, value: str) -> str:
        if not _TIMEFRAME_RE.fullmatch(value):
            raise ValueError("timeframe must use a positive integer plus m, h, or d")
        return value

    @model_validator(mode="after")
    def _validate_parameters(self) -> "StructuralAtrRunnerRule":
        if not self.structure_rule.strip():
            raise ValueError("structure_rule is required")
        if self.structure_window_bars < 1 or self.atr_period < 1:
            raise ValueError("structure and ATR windows must be positive")
        if self.atr_buffer_multiple < 0:
            raise ValueError("atr_buffer_multiple must be non-negative")
        if self.minimum_improvement_ticks < 1:
            raise ValueError("minimum_improvement_ticks must be positive")
        return self


class ReferenceTrailRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["reference_trail"]
    timeframe: str
    reference_key: str
    buffer_ticks: int
    minimum_improvement_ticks: int

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, value: str) -> str:
        if not _TIMEFRAME_RE.fullmatch(value):
            raise ValueError("timeframe must use a positive integer plus m, h, or d")
        return value

    @model_validator(mode="after")
    def _validate_parameters(self) -> "ReferenceTrailRunnerRule":
        if not self.reference_key.strip():
            raise ValueError("reference_key is required")
        if self.buffer_ticks < 0:
            raise ValueError("buffer_ticks must be non-negative")
        if self.minimum_improvement_ticks < 1:
            raise ValueError("minimum_improvement_ticks must be positive")
        return self


class NoRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["no_runner"]


RunnerRule = Annotated[
    StructuralAtrRunnerRule | ReferenceTrailRunnerRule | NoRunnerRule,
    Field(discriminator="kind"),
]


class ReferencePriceCrossInvalidationRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["reference_price_cross"]
    rule_id: str
    trigger: Literal["close_below_or_equal", "close_above_or_equal"]
    reference_key: str

    @model_validator(mode="after")
    def _validate_identity(self) -> "ReferencePriceCrossInvalidationRule":
        if not self.rule_id.strip() or not self.reference_key.strip():
            raise ValueError("invalidation rule identity is required")
        return self


class MaxHoldingBarsTimeStopRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["max_holding_bars"]
    max_holding_bars: int

    @model_validator(mode="after")
    def _validate_bars(self) -> "MaxHoldingBarsTimeStopRule":
        if self.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be positive")
        return self


class TicketExitPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_policy_id: str
    exit_policy_version: str
    strategy_group_id: str
    strategy_version: str
    event_spec_id: str
    event_spec_version: str
    side: Literal["long", "short"]
    policy_family: PolicyFamily
    reward_basis: RewardBasis
    take_profit_legs: tuple[TicketTakeProfitLeg, ...]
    tp_completion_tolerance_qty_steps: int
    post_tp1_floor_rule: RunnerBreakEvenFloorRule | None
    invalidation_rules: tuple[ReferencePriceCrossInvalidationRule, ...]
    time_stop_rule: MaxHoldingBarsTimeStopRule | None
    runner_rule: RunnerRule
    payload_hash: str

    @classmethod
    def with_canonical_hash(
        cls,
        payload: Mapping[str, Any],
    ) -> "TicketExitPolicySnapshot":
        values = dict(payload)
        values.pop("payload_hash", None)
        return cls(**values, payload_hash=canonical_payload_hash(values))

    @model_validator(mode="after")
    def _validate_policy(self) -> "TicketExitPolicySnapshot":
        identity_values = (
            self.exit_policy_id,
            self.exit_policy_version,
            self.strategy_group_id,
            self.strategy_version,
            self.event_spec_id,
            self.event_spec_version,
        )
        if any(not value.strip() for value in identity_values):
            raise ValueError("policy identity fields must be non-empty")
        if self.tp_completion_tolerance_qty_steps < 0:
            raise ValueError("tp_completion_tolerance_qty_steps must be non-negative")
        roles = [leg.role for leg in self.take_profit_legs]
        if len(roles) != len(set(roles)):
            raise ValueError("take-profit roles must be unique")
        total_fraction = sum(
            (leg.quantity_fraction for leg in self.take_profit_legs),
            Decimal("0"),
        )
        if total_fraction > 1:
            raise ValueError("take-profit quantity fractions must not exceed one")
        if self.policy_family is PolicyFamily.RIGHT_TAIL_RUNNER:
            if not self.take_profit_legs or total_fraction >= 1:
                raise ValueError("right-tail policy must preserve a positive runner fraction")
            if isinstance(self.runner_rule, NoRunnerRule):
                raise ValueError("right-tail policy requires a runner rule")
            if self.post_tp1_floor_rule is None:
                raise ValueError("right-tail policy requires a post-TP1 floor rule")
        elif self.policy_family is PolicyFamily.FIXED_TARGETS:
            if not self.take_profit_legs or total_fraction != 1:
                raise ValueError("fixed-target policy fractions must total exactly one")
            if not isinstance(self.runner_rule, NoRunnerRule):
                raise ValueError("fixed-target policy cannot define a runner")
            if self.post_tp1_floor_rule is not None:
                raise ValueError("fixed-target policy cannot define a runner floor")
        else:
            if self.take_profit_legs:
                raise ValueError("lifecycle-only policy cannot define take-profit legs")
            if not isinstance(self.runner_rule, NoRunnerRule):
                raise ValueError("lifecycle-only policy cannot define a runner")
            if self.post_tp1_floor_rule is not None:
                raise ValueError("lifecycle-only policy cannot define a runner floor")
        expected_hash = canonical_payload_hash(
            self.model_dump(mode="python", exclude={"payload_hash"})
        )
        if self.payload_hash != expected_hash:
            raise ValueError("exit policy payload hash mismatch")
        return self


class TicketExitExecutionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    exit_policy_id: str
    exit_policy_version: str
    entry_avg_fill_price: Decimal
    entry_filled_qty: Decimal
    initial_stop_price: Decimal
    actual_r_per_unit: Decimal
    resolved_tp1_price: Decimal
    resolved_tp1_target_qty: Decimal
    runner_target_qty: Decimal
    entry_fee_quote: Decimal
    certified_exit_taker_fee_rate: Decimal
    slippage_buffer_quote: Decimal
    payload_hash: str

    @classmethod
    def with_canonical_hash(
        cls,
        payload: Mapping[str, Any],
    ) -> "TicketExitExecutionSnapshot":
        values = dict(payload)
        values.pop("payload_hash", None)
        return cls(**values, payload_hash=canonical_payload_hash(values))

    @model_validator(mode="after")
    def _validate_execution(self) -> "TicketExitExecutionSnapshot":
        positive_values = (
            self.entry_avg_fill_price,
            self.entry_filled_qty,
            self.initial_stop_price,
            self.actual_r_per_unit,
            self.resolved_tp1_price,
            self.resolved_tp1_target_qty,
        )
        if any(value <= 0 for value in positive_values):
            raise ValueError("execution price, quantity, and R values must be positive")
        if self.runner_target_qty < 0:
            raise ValueError("runner_target_qty must be non-negative")
        if self.resolved_tp1_target_qty + self.runner_target_qty > self.entry_filled_qty:
            raise ValueError("resolved exit quantities exceed entry fill quantity")
        if self.entry_fee_quote < 0 or self.slippage_buffer_quote < 0:
            raise ValueError("fee and slippage values must be non-negative")
        if not Decimal("0") <= self.certified_exit_taker_fee_rate < Decimal("1"):
            raise ValueError("certified exit taker fee rate must be in [0, 1)")
        expected_hash = canonical_payload_hash(
            self.model_dump(mode="python", exclude={"payload_hash"})
        )
        if self.payload_hash != expected_hash:
            raise ValueError("exit execution payload hash mismatch")
        return self


class ExitMarketFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watermark_ms: int
    is_final_closed_candle: bool
    close_price: Decimal
    holding_bars: int
    invalidation_rule_ids_hit: tuple[str, ...] = ()
    structural_stop_candidate: Decimal | None = None
    reference_stop_candidate: Decimal | None = None

    @model_validator(mode="after")
    def _validate_fact(self) -> "ExitMarketFact":
        if self.watermark_ms <= 0 or self.close_price <= 0 or self.holding_bars < 0:
            raise ValueError("market fact values are invalid")
        for candidate in (
            self.structural_stop_candidate,
            self.reference_stop_candidate,
        ):
            if candidate is not None and candidate <= 0:
                raise ValueError("stop candidates must be positive")
        return self


class ExitEvaluationInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: TicketExitPolicySnapshot
    ticket_id: str
    exchange_instrument_id: str
    venue_id: str
    side: Literal["long", "short"]
    position_qty: Decimal
    current_runner_stop: Decimal | None
    active_runner_generation: int | None
    protection_identity_exact: bool
    tp1_completion_state: Literal["unfilled", "partial", "complete", "contradictory"]
    immediate_runner_floor: Decimal | None = None
    minimum_price_tick: Decimal
    market_fact: ExitMarketFact | None = None
    evaluated_watermark_ms: int

    @model_validator(mode="after")
    def _validate_input(self) -> "ExitEvaluationInput":
        if not self.ticket_id.strip() or not self.exchange_instrument_id.strip():
            raise ValueError("ticket and instrument identity are required")
        if not self.venue_id.strip() or self.side != self.policy.side:
            raise ValueError("venue and exact policy side are required")
        if self.position_qty < 0 or self.minimum_price_tick <= 0:
            raise ValueError("position quantity and price tick are invalid")
        if self.current_runner_stop is not None and self.current_runner_stop <= 0:
            raise ValueError("current runner stop must be positive")
        if self.immediate_runner_floor is not None and self.immediate_runner_floor <= 0:
            raise ValueError("immediate runner floor must be positive")
        if self.active_runner_generation is not None and self.active_runner_generation < 1:
            raise ValueError("active runner generation must be positive")
        if self.evaluated_watermark_ms <= 0:
            raise ValueError("evaluation watermark must be positive")
        return self


class ExitDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ExitDecisionKind
    reason_code: str
    source_watermark_ms: int
    proposed_stop: Decimal | None = None
    close_qty: Decimal | None = None
    blockers: tuple[str, ...] = ()


def canonical_payload_hash(value: Any) -> str:
    canonical = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def calculate_runner_break_even_floor(
    *,
    side: Literal["long", "short"],
    entry_avg_fill_price: Decimal,
    runner_qty: Decimal,
    allocated_entry_fee_quote: Decimal | None,
    certified_exit_taker_fee_rate: Decimal,
    slippage_buffer_quote: Decimal,
    minimum_price_tick: Decimal,
) -> Decimal:
    values = (
        entry_avg_fill_price,
        runner_qty,
        certified_exit_taker_fee_rate,
        slippage_buffer_quote,
        minimum_price_tick,
    )
    if any(not isinstance(value, Decimal) for value in values):
        raise ValueError("runner floor financial values must use Decimal")
    if allocated_entry_fee_quote is None:
        raise ValueError("allocated entry fee basis is required")
    if entry_avg_fill_price <= 0 or runner_qty <= 0 or minimum_price_tick <= 0:
        raise ValueError("runner floor price, quantity, and tick must be positive")
    if allocated_entry_fee_quote < 0 or slippage_buffer_quote < 0:
        raise ValueError("runner floor fee and slippage values must be non-negative")
    if not Decimal("0") <= certified_exit_taker_fee_rate < Decimal("1"):
        raise ValueError("exit taker fee rate must be in [0, 1)")
    entry_notional = entry_avg_fill_price * runner_qty
    if side == "long":
        raw = (
            entry_notional + allocated_entry_fee_quote + slippage_buffer_quote
        ) / (runner_qty * (Decimal("1") - certified_exit_taker_fee_rate))
        return _round_to_tick(raw, minimum_price_tick, rounding=ROUND_CEILING)
    if side == "short":
        raw = (
            entry_notional - allocated_entry_fee_quote - slippage_buffer_quote
        ) / (runner_qty * (Decimal("1") + certified_exit_taker_fee_rate))
        if raw <= 0:
            raise ValueError("short runner floor must remain positive")
        return _round_to_tick(raw, minimum_price_tick, rounding=ROUND_FLOOR)
    raise ValueError("side must be long or short")


def evaluate_exit_policy(value: ExitEvaluationInput) -> ExitDecision:
    source_watermark = (
        value.market_fact.watermark_ms
        if value.market_fact is not None
        else value.evaluated_watermark_ms
    )
    if value.position_qty == 0:
        return _decision(ExitDecisionKind.NOOP, "position_terminal", source_watermark)
    if not value.protection_identity_exact:
        return _blocked("active_protection_identity_not_exact", source_watermark)
    if value.tp1_completion_state == "contradictory":
        return _blocked("tp1_completion_truth_contradictory", source_watermark)
    if isinstance(value.policy.runner_rule, NoRunnerRule):
        return _decision(ExitDecisionKind.NOOP, "policy_has_no_runner", source_watermark)
    if value.current_runner_stop is None or value.active_runner_generation is None:
        return _blocked("active_runner_protection_missing", source_watermark)

    fact = value.market_fact
    if fact is not None and not fact.is_final_closed_candle:
        if (
            fact.invalidation_rule_ids_hit
            or fact.structural_stop_candidate is not None
            or fact.reference_stop_candidate is not None
            or (
                value.policy.time_stop_rule is not None
                and fact.holding_bars >= value.policy.time_stop_rule.max_holding_bars
            )
        ):
            return _blocked("closed_market_fact_required", source_watermark)
    if fact is not None and fact.is_final_closed_candle:
        configured_invalidation_ids = {
            rule.rule_id for rule in value.policy.invalidation_rules
        }
        if configured_invalidation_ids.intersection(fact.invalidation_rule_ids_hit):
            return ExitDecision(
                kind=ExitDecisionKind.CLOSE_RUNNER,
                reason_code="strategy_invalidation_hit",
                source_watermark_ms=source_watermark,
                close_qty=value.position_qty,
            )
        if (
            value.policy.time_stop_rule is not None
            and fact.holding_bars >= value.policy.time_stop_rule.max_holding_bars
        ):
            return ExitDecision(
                kind=ExitDecisionKind.CLOSE_RUNNER,
                reason_code="time_stop_hit",
                source_watermark_ms=source_watermark,
                close_qty=value.position_qty,
            )

    if fact is None:
        if value.tp1_completion_state == "complete":
            return _floor_only_decision(value, source_watermark)
        return _decision(ExitDecisionKind.NOOP, "no_due_market_fact", source_watermark)
    if not fact.is_final_closed_candle:
        if value.tp1_completion_state == "complete":
            return _floor_only_decision(value, source_watermark)
        return _decision(ExitDecisionKind.NOOP, "open_candle_ignored", source_watermark)
    if isinstance(value.policy.runner_rule, StructuralAtrRunnerRule):
        candidate = fact.structural_stop_candidate
        minimum_ticks = value.policy.runner_rule.minimum_improvement_ticks
        reason_code = "structural_atr_runner_improvement"
    elif isinstance(value.policy.runner_rule, ReferenceTrailRunnerRule):
        candidate = fact.reference_stop_candidate
        minimum_ticks = value.policy.runner_rule.minimum_improvement_ticks
        reason_code = "reference_runner_improvement"
    else:
        candidate = None
        minimum_ticks = 1
        reason_code = "runner_candidate_absent"
    if candidate is None:
        if value.tp1_completion_state == "complete":
            return _floor_only_decision(value, source_watermark)
        return _decision(ExitDecisionKind.NOOP, "runner_candidate_absent", source_watermark)
    if value.tp1_completion_state == "complete":
        if value.immediate_runner_floor is None:
            return _blocked("runner_break_even_floor_missing", source_watermark)
        candidate = (
            max(candidate, value.immediate_runner_floor)
            if value.side == "long"
            else min(candidate, value.immediate_runner_floor)
        )
    return _stop_decision(
        value=value,
        proposed=candidate,
        minimum_improvement_ticks=minimum_ticks,
        reason_code=reason_code,
        source_watermark=source_watermark,
    )


def _floor_only_decision(
    value: ExitEvaluationInput,
    source_watermark: int,
) -> ExitDecision:
    if value.immediate_runner_floor is None:
        return _blocked("runner_break_even_floor_missing", source_watermark)
    minimum_ticks = (
        value.policy.post_tp1_floor_rule.minimum_improvement_ticks
        if value.policy.post_tp1_floor_rule is not None
        else 1
    )
    return _stop_decision(
        value=value,
        proposed=value.immediate_runner_floor,
        minimum_improvement_ticks=minimum_ticks,
        reason_code="tp1_completion_runner_floor",
        source_watermark=source_watermark,
    )


def _stop_decision(
    *,
    value: ExitEvaluationInput,
    proposed: Decimal,
    minimum_improvement_ticks: int,
    reason_code: str,
    source_watermark: int,
) -> ExitDecision:
    if not _is_tick_aligned(proposed, value.minimum_price_tick):
        return _blocked("proposed_stop_not_tick_aligned", source_watermark)
    current = value.current_runner_stop
    if current is None:
        return _blocked("active_runner_protection_missing", source_watermark)
    required = value.minimum_price_tick * minimum_improvement_ticks
    improvement = proposed - current if value.side == "long" else current - proposed
    if improvement < required:
        return _decision(
            ExitDecisionKind.NOOP,
            "runner_stop_not_improved",
            source_watermark,
        )
    return ExitDecision(
        kind=ExitDecisionKind.MOVE_RUNNER_STOP,
        reason_code=reason_code,
        source_watermark_ms=source_watermark,
        proposed_stop=proposed,
    )


def _blocked(reason_code: str, source_watermark: int) -> ExitDecision:
    return ExitDecision(
        kind=ExitDecisionKind.BLOCKED,
        reason_code=reason_code,
        source_watermark_ms=source_watermark,
        blockers=(reason_code,),
    )


def _decision(
    kind: ExitDecisionKind,
    reason_code: str,
    source_watermark: int,
) -> ExitDecision:
    return ExitDecision(
        kind=kind,
        reason_code=reason_code,
        source_watermark_ms=source_watermark,
    )


def _round_to_tick(value: Decimal, tick: Decimal, *, rounding: str) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _is_tick_aligned(value: Decimal, tick: Decimal) -> bool:
    return value > 0 and value % tick == 0


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical payload cannot contain non-finite Decimal")
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) != "payload_hash"
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical payload value: {type(value).__name__}")
