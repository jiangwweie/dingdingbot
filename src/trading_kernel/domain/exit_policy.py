"""Versioned pure exit-policy contracts for registered Events."""

from __future__ import annotations

import json
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)

PositionSide = Literal["long", "short"]


class RunnerKind(StrEnum):
    STRUCTURAL_ATR = "structural_atr"


class RunnerRuleKind(StrEnum):
    ROLLING_EXTREME_ATR = "rolling_extreme_atr"


class TimeStopMode(StrEnum):
    PRE_TP1 = "pre_tp1"
    ABSOLUTE = "absolute"


class PreTp1GuardKind(StrEnum):
    RECLAIM_REFERENCE = "reclaim_reference"
    SESSION_EXPIRY = "session_expiry"


class ExitDecisionKind(StrEnum):
    NO_CHANGE = "no_change"
    MOVE_STOP = "move_stop"
    EXIT = "exit"


class LifecycleMarketFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watermark_ms: int
    is_final_closed_candle: bool
    latest_close: Decimal
    structure_reference: Decimal
    atr: Decimal
    holding_bars: int

    @model_validator(mode="after")
    def _validate_facts(self) -> LifecycleMarketFacts:
        if self.watermark_ms <= 0 or self.holding_bars < 0:
            raise ValueError("lifecycle market watermark and holding bars are invalid")
        if self.latest_close <= 0 or self.structure_reference <= 0 or self.atr <= 0:
            raise ValueError("lifecycle structure and ATR facts must be positive")
        return self


class ExitDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ExitDecisionKind
    reason: str
    source_watermark_ms: int
    proposed_stop: Decimal | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> ExitDecision:
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
    def _validate_rule(self) -> TakeProfitRule:
        if self.reward_multiple <= 0:
            raise ValueError("take-profit reward multiple must be positive")
        if not Decimal(0) < self.quantity_fraction < Decimal(1):
            raise ValueError("take-profit quantity fraction must be in (0, 1)")
        return self


class BreakEvenFloorRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_fee_basis: Literal["conservative_taker"] = "conservative_taker"
    slippage_buffer_ticks: int
    minimum_improvement_ticks: int

    @model_validator(mode="after")
    def _validate_ticks(self) -> BreakEvenFloorRule:
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
    def _validate_parameters(self) -> StructuralAtrRunnerRule:
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
    mode: TimeStopMode = TimeStopMode.ABSOLUTE

    @field_validator("max_holding_bars")
    @classmethod
    def _require_positive_bars(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("time-stop holding bars must be positive")
        return value


class RollingExtremeAtrRunnerRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RunnerRuleKind = RunnerRuleKind.ROLLING_EXTREME_ATR
    timeframe: Literal["15m", "1h"]
    lookback_bars: int
    atr_period: int
    atr_buffer_multiple: Decimal
    minimum_improvement_ticks: int

    @model_validator(mode="after")
    def _validate_parameters(self) -> RollingExtremeAtrRunnerRule:
        if self.lookback_bars <= 0 or self.atr_period <= 0:
            raise ValueError("runner lookback and ATR windows must be positive")
        if self.atr_buffer_multiple < 0:
            raise ValueError("runner ATR buffer cannot be negative")
        if self.minimum_improvement_ticks <= 0:
            raise ValueError("runner minimum improvement must be positive")
        return self


class ExitProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_profile_id: str
    exit_profile_version: int
    profile_schema_version: Literal["exit_profile_v1"]
    position_side: PositionSide
    tp1: TakeProfitRule
    break_even_floor: BreakEvenFloorRule
    runner: RollingExtremeAtrRunnerRule
    time_stop: TimeStopRule | None
    pre_tp1_guards: tuple[PreTp1GuardKind, ...]

    @field_validator("exit_profile_id", mode="before")
    @classmethod
    def _require_profile_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("ExitProfile identity must be non-blank")
        return normalized

    @model_validator(mode="after")
    def _validate_profile(self) -> ExitProfile:
        if self.exit_profile_version <= 0:
            raise ValueError("ExitProfile version must be positive")
        canonical_guards = tuple(
            sorted(set(self.pre_tp1_guards), key=lambda item: item.value)
        )
        if canonical_guards != self.pre_tp1_guards:
            raise ValueError("ExitProfile guards must be canonical and unique")
        return self

    def semantic_hash(self) -> str:
        return _semantic_hash(self.model_dump(mode="json"))


class EventExitBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_binding_id: str
    binding_version: int
    event_spec_id: str
    exit_profile_id: str
    exit_profile_semantic_hash: str
    binding_semantic_hash: str
    activation_reason: str
    created_at_ms: int

    @field_validator(
        "exit_binding_id",
        "event_spec_id",
        "exit_profile_id",
        "activation_reason",
        mode="before",
    )
    @classmethod
    def _require_binding_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("EventExitBinding identity must be non-blank")
        return normalized

    @field_validator("exit_profile_semantic_hash", "binding_semantic_hash")
    @classmethod
    def _require_binding_hash(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("EventExitBinding hash must be canonical SHA-256")
        return value

    @model_validator(mode="after")
    def _validate_binding(self) -> EventExitBinding:
        if self.binding_version <= 0 or self.created_at_ms <= 0:
            raise ValueError("Binding version and creation time must be positive")
        if self.binding_semantic_hash != _event_exit_binding_hash(
            binding_version=self.binding_version,
            event_spec_id=self.event_spec_id,
            exit_profile_id=self.exit_profile_id,
            exit_profile_semantic_hash=self.exit_profile_semantic_hash,
            activation_reason=self.activation_reason,
        ):
            raise ValueError("EventExitBinding semantic hash differs")
        return self


class CurrentEventExitBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_spec_id: str
    exit_binding_id: str
    binding_semantic_hash: str
    projection_version: int
    activated_at_ms: int

    @field_validator("event_spec_id", "exit_binding_id", mode="before")
    @classmethod
    def _require_current_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("current EventExitBinding identity must be non-blank")
        return normalized

    @field_validator("binding_semantic_hash")
    @classmethod
    def _require_current_hash(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != 71:
            raise ValueError("current EventExitBinding hash must be canonical")
        return value

    @model_validator(mode="after")
    def _validate_current(self) -> CurrentEventExitBinding:
        if self.projection_version <= 0 or self.activated_at_ms <= 0:
            raise ValueError("current Binding version and time must be positive")
        return self


class ExitProfileRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ExitProfile
    status: Literal["active", "retired"]


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
    def _require_two_positive_legs(self) -> TakeProfitSplit:
        if self.tp1_quantity <= 0 or self.runner_quantity <= 0:
            raise ValueError("TP1 and runner quantities must both be positive")
        return self


def registered_exit_profiles() -> tuple[ExitProfile, ...]:
    return tuple(
        sorted(
            (
                _exit_profile(
                    exit_profile_id="exit-profile:trend-continuation:1h:long:v1",
                    side="long",
                    timeframe="1h",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=None,
                    guards=(),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:momentum-tail:1h:long:v1",
                    side="long",
                    timeframe="1h",
                    quantity_fraction=Decimal("0.33"),
                    lookback_bars=5,
                    atr_buffer_multiple=Decimal("0.75"),
                    time_stop=None,
                    guards=(),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:impulse-decay:1h:long:v1",
                    side="long",
                    timeframe="1h",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=12,
                        mode=TimeStopMode.PRE_TP1,
                    ),
                    guards=(),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:failure-reversal:1h:short:v1",
                    side="short",
                    timeframe="1h",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=12,
                        mode=TimeStopMode.PRE_TP1,
                    ),
                    guards=(),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:orb-crypto:15m:long:v1",
                    side="long",
                    timeframe="15m",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=96,
                        mode=TimeStopMode.ABSOLUTE,
                    ),
                    guards=(
                        PreTp1GuardKind.RECLAIM_REFERENCE,
                        PreTp1GuardKind.SESSION_EXPIRY,
                    ),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:orb-crypto:15m:short:v1",
                    side="short",
                    timeframe="15m",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=96,
                        mode=TimeStopMode.ABSOLUTE,
                    ),
                    guards=(
                        PreTp1GuardKind.RECLAIM_REFERENCE,
                        PreTp1GuardKind.SESSION_EXPIRY,
                    ),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:orb-us:15m:long:v1",
                    side="long",
                    timeframe="15m",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=8,
                        mode=TimeStopMode.ABSOLUTE,
                    ),
                    guards=(
                        PreTp1GuardKind.RECLAIM_REFERENCE,
                        PreTp1GuardKind.SESSION_EXPIRY,
                    ),
                ),
                _exit_profile(
                    exit_profile_id="exit-profile:orb-us:15m:short:v1",
                    side="short",
                    timeframe="15m",
                    quantity_fraction=Decimal("0.50"),
                    lookback_bars=4,
                    atr_buffer_multiple=Decimal("0.50"),
                    time_stop=TimeStopRule(
                        max_holding_bars=8,
                        mode=TimeStopMode.ABSOLUTE,
                    ),
                    guards=(
                        PreTp1GuardKind.RECLAIM_REFERENCE,
                        PreTp1GuardKind.SESSION_EXPIRY,
                    ),
                ),
            ),
            key=lambda item: item.exit_profile_id,
        )
    )


def registered_event_exit_bindings() -> tuple[EventExitBinding, ...]:
    profile_ids = {
        "CPM-LONG": "exit-profile:trend-continuation:1h:long:v1",
        "MPG-LONG": "exit-profile:momentum-tail:1h:long:v1",
        "MI-LONG": "exit-profile:impulse-decay:1h:long:v1",
        "BRF2-SHORT": "exit-profile:failure-reversal:1h:short:v1",
        "SOR-LONG": "exit-profile:orb-crypto:15m:long:v1",
        "SOR-SHORT": "exit-profile:orb-crypto:15m:short:v1",
        "SOR-US-LONG-15M": "exit-profile:orb-us:15m:long:v1",
        "SOR-US-SHORT-15M": "exit-profile:orb-us:15m:short:v1",
    }
    profiles = {item.exit_profile_id: item for item in registered_exit_profiles()}
    bindings = []
    for contract in registered_strategy_contracts():
        profile_id = profile_ids[contract.event_id]
        profile = profiles[profile_id]
        bindings.append(
            build_event_exit_binding(
                exit_binding_id=f"exit-binding:{contract.event_spec_id}:v1",
                binding_version=1,
                event_spec_id=contract.event_spec_id,
                exit_profile_id=profile_id,
                exit_profile_semantic_hash=profile.semantic_hash(),
                activation_reason="owner_frozen_v1",
                created_at_ms=1,
            )
        )
    return tuple(sorted(bindings, key=lambda item: item.event_spec_id))


def build_exit_profile_catalog_digest() -> str:
    return _semantic_hash(
        {
            "profiles": [
                item.model_dump(mode="json")
                for item in registered_exit_profiles()
            ],
            "bindings": [
                item.model_dump(mode="json")
                for item in registered_event_exit_bindings()
            ],
        }
    )


def registered_exit_policies() -> tuple[ExitPolicy, ...]:
    """Return legacy source-revision provenance for migration verification only."""

    return tuple(
        _legacy_source_exit_policy(item)
        for item in registered_strategy_contracts()
    )


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
    if not Decimal(0) < quantity_fraction < Decimal(1):
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


def build_event_exit_binding(
    *,
    exit_binding_id: str,
    binding_version: int,
    event_spec_id: str,
    exit_profile_id: str,
    exit_profile_semantic_hash: str,
    activation_reason: str,
    created_at_ms: int,
) -> EventExitBinding:
    return EventExitBinding(
        exit_binding_id=exit_binding_id,
        binding_version=binding_version,
        event_spec_id=event_spec_id,
        exit_profile_id=exit_profile_id,
        exit_profile_semantic_hash=exit_profile_semantic_hash,
        binding_semantic_hash=_event_exit_binding_hash(
            binding_version=binding_version,
            event_spec_id=event_spec_id,
            exit_profile_id=exit_profile_id,
            exit_profile_semantic_hash=exit_profile_semantic_hash,
            activation_reason=activation_reason,
        ),
        activation_reason=activation_reason,
        created_at_ms=created_at_ms,
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
        ) / (runner_quantity * (Decimal(1) - exit_taker_fee_rate))
        return _round_to_step(raw, price_tick, rounding=ROUND_CEILING)
    if side == "short":
        raw = (
            entry_notional
            - allocated_entry_fee_quote
            - slippage_buffer_quote
        ) / (runner_quantity * (Decimal(1) + exit_taker_fee_rate))
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


def calculate_rolling_extreme_atr_stop(
    *,
    side: str,
    rolling_extreme: Decimal,
    atr: Decimal,
    atr_buffer_multiple: Decimal,
    price_tick: Decimal,
) -> Decimal:
    return calculate_structural_runner_stop(
        side=side,
        structure_reference=rolling_extreme,
        atr=atr,
        atr_buffer_multiple=atr_buffer_multiple,
        price_tick=price_tick,
    )


def evaluate_profile_runner_exit(
    *,
    profile: ExitProfile,
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
        profile.time_stop is not None
        and profile.time_stop.mode is TimeStopMode.ABSOLUTE
        and market_facts.holding_bars >= profile.time_stop.max_holding_bars
    ):
        return _exit_decision(
            ExitDecisionKind.EXIT,
            "absolute_time_stop_hit",
            market_facts.watermark_ms,
        )
    candidate = calculate_rolling_extreme_atr_stop(
        side=profile.position_side,
        rolling_extreme=market_facts.structure_reference,
        atr=market_facts.atr,
        atr_buffer_multiple=profile.runner.atr_buffer_multiple,
        price_tick=price_tick,
    )
    candidate = (
        max(candidate, break_even_floor)
        if profile.position_side == "long"
        else min(candidate, break_even_floor)
    )
    required_improvement = price_tick * profile.runner.minimum_improvement_ticks
    improvement = (
        candidate - current_stop
        if profile.position_side == "long"
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
        reason="rolling_extreme_atr_runner_improvement",
        source_watermark_ms=market_facts.watermark_ms,
        proposed_stop=candidate,
    )


def evaluate_profile_pre_tp1_exit(
    *,
    profile: ExitProfile,
    market_facts: LifecycleMarketFacts,
    observed_at_ms: int,
    pre_tp1_reclaim_price: Decimal | None = None,
    exposure_session_end_ms: int | None = None,
) -> ExitDecision:
    if observed_at_ms < market_facts.watermark_ms:
        raise ValueError("pre-TP1 observation precedes market facts")
    if not market_facts.is_final_closed_candle:
        return _exit_decision(
            ExitDecisionKind.NO_CHANGE,
            "closed_candle_required",
            market_facts.watermark_ms,
        )
    guards = set(profile.pre_tp1_guards)
    if PreTp1GuardKind.SESSION_EXPIRY in guards:
        if exposure_session_end_ms is None or exposure_session_end_ms <= 0:
            raise ValueError("session-expiry guard requires a positive deadline")
        if observed_at_ms >= exposure_session_end_ms:
            return _exit_decision(
                ExitDecisionKind.EXIT,
                "session_expired",
                market_facts.watermark_ms,
            )
    if PreTp1GuardKind.RECLAIM_REFERENCE in guards:
        if pre_tp1_reclaim_price is None or pre_tp1_reclaim_price <= 0:
            raise ValueError("reclaim guard requires a positive reference")
        reclaim_hit = (
            market_facts.latest_close <= pre_tp1_reclaim_price
            if profile.position_side == "long"
            else market_facts.latest_close >= pre_tp1_reclaim_price
        )
        if reclaim_hit:
            return _exit_decision(
                ExitDecisionKind.EXIT,
                (
                    "failed_breakout_reclaimed"
                    if profile.position_side == "long"
                    else "failed_breakdown_reclaimed"
                ),
                market_facts.watermark_ms,
            )
    if (
        profile.time_stop is not None
        and profile.time_stop.mode is TimeStopMode.ABSOLUTE
        and market_facts.holding_bars >= profile.time_stop.max_holding_bars
    ):
        return _exit_decision(
            ExitDecisionKind.EXIT,
            "absolute_time_stop_hit",
            market_facts.watermark_ms,
        )
    if (
        profile.time_stop is not None
        and profile.time_stop.mode is TimeStopMode.PRE_TP1
        and market_facts.holding_bars >= profile.time_stop.max_holding_bars
    ):
        return _exit_decision(
            ExitDecisionKind.EXIT,
            "pre_tp1_time_stop_hit",
            market_facts.watermark_ms,
        )
    return _exit_decision(
        ExitDecisionKind.NO_CHANGE,
        "pre_tp1_plan_intact",
        market_facts.watermark_ms,
    )


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


def evaluate_pre_tp1_exit(
    *,
    policy: ExitPolicy,
    pre_tp1_reclaim_price: Decimal,
    exposure_session_end_ms: int,
    market_facts: LifecycleMarketFacts,
    observed_at_ms: int,
) -> ExitDecision:
    if pre_tp1_reclaim_price <= 0 or exposure_session_end_ms <= 0:
        raise ValueError("pre-TP1 exit plan must be positive")
    if observed_at_ms < market_facts.watermark_ms:
        raise ValueError("pre-TP1 observation precedes market facts")
    if not market_facts.is_final_closed_candle:
        return _exit_decision(
            ExitDecisionKind.NO_CHANGE,
            "closed_candle_required",
            market_facts.watermark_ms,
        )
    if observed_at_ms >= exposure_session_end_ms:
        return _exit_decision(
            ExitDecisionKind.EXIT,
            "sor_session_expired",
            market_facts.watermark_ms,
        )
    reclaim_hit = (
        market_facts.latest_close <= pre_tp1_reclaim_price
        if policy.position_side == "long"
        else market_facts.latest_close >= pre_tp1_reclaim_price
    )
    if reclaim_hit:
        return _exit_decision(
            ExitDecisionKind.EXIT,
            (
                "failed_breakout_reclaimed"
                if policy.position_side == "long"
                else "failed_breakdown_reclaimed"
            ),
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
    return _exit_decision(
        ExitDecisionKind.NO_CHANGE,
        "pre_tp1_plan_intact",
        market_facts.watermark_ms,
    )


def _legacy_source_exit_policy(
    contract: RegisteredStrategyContract,
) -> ExitPolicy:
    return ExitPolicy(
        exit_policy_id=contract.exit_policy_id,
        exit_policy_version=(
            "2026-07-31-sor-v3"
            if contract.strategy_group_id == "SOR-001"
            else "2026-08-11-us-sor-v1"
            if contract.strategy_group_id == "SOR-US-EQ-PERP-001"
            else "2026-07-22-v1"
        ),
        event_spec_id=contract.event_spec_id,
        event_id=contract.event_id,
        position_side=contract.position_side,
        tp1=TakeProfitRule(
            reward_multiple=Decimal(1),
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
            if contract.strategy_group_id == "SOR-001"
            else TimeStopRule(max_holding_bars=8)
            if contract.strategy_group_id == "SOR-US-EQ-PERP-001"
            else None
        ),
    )


def _exit_profile(
    *,
    exit_profile_id: str,
    side: PositionSide,
    timeframe: Literal["15m", "1h"],
    quantity_fraction: Decimal,
    lookback_bars: int,
    atr_buffer_multiple: Decimal,
    time_stop: TimeStopRule | None,
    guards: tuple[PreTp1GuardKind, ...],
) -> ExitProfile:
    return ExitProfile(
        exit_profile_id=exit_profile_id,
        exit_profile_version=1,
        profile_schema_version="exit_profile_v1",
        position_side=side,
        tp1=TakeProfitRule(
            reward_multiple=Decimal(1),
            quantity_fraction=quantity_fraction,
            execution_style="limit_gtc",
            market_fallback_allowed=False,
        ),
        break_even_floor=BreakEvenFloorRule(
            exit_fee_basis="conservative_taker",
            slippage_buffer_ticks=2,
            minimum_improvement_ticks=2,
        ),
        runner=RollingExtremeAtrRunnerRule(
            kind=RunnerRuleKind.ROLLING_EXTREME_ATR,
            timeframe=timeframe,
            lookback_bars=lookback_bars,
            atr_period=14,
            atr_buffer_multiple=atr_buffer_multiple,
            minimum_improvement_ticks=2,
        ),
        time_stop=time_stop,
        pre_tp1_guards=guards,
    )


def _round_to_step(value: Decimal, step: Decimal, *, rounding: str) -> Decimal:
    return (value / step).to_integral_value(rounding=rounding) * step


def _semantic_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _event_exit_binding_hash(
    *,
    binding_version: int,
    event_spec_id: str,
    exit_profile_id: str,
    exit_profile_semantic_hash: str,
    activation_reason: str,
) -> str:
    return _semantic_hash(
        {
            "binding_version": binding_version,
            "event_spec_id": event_spec_id,
            "exit_profile_id": exit_profile_id,
            "exit_profile_semantic_hash": exit_profile_semantic_hash,
            "activation_reason": activation_reason,
        }
    )


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
    if not Decimal(0) <= exit_taker_fee_rate < Decimal(1):
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
