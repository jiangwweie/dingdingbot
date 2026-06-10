"""Strategy candidate semantics shared by reference evaluators.

These value objects describe a strategy candidate's entry, protection, exit,
and review quality in a machine-readable way. They are deliberately not order
instructions: no quantity, notional, leverage, venue, route, or execution
authority is represented here.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import reject_forbidden_execution_fields


class StrategyCandidateSemanticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "StrategyCandidateSemanticsModel":
        reject_forbidden_execution_fields(
            self.model_dump(mode="python"),
            root=self.__class__.__name__,
        )
        return self


class StrategyPayoffProfile(str, Enum):
    RIGHT_TAIL = "right_tail"
    MEAN_REVERSION = "mean_reversion"
    REGIME_CONTEXT = "regime_context"
    DATA_BACKLOG = "data_backlog"


class StrategyArchetype(str, Enum):
    LONG_PULLBACK_CONTINUATION = "long_pullback_continuation"
    BEAR_RALLY_FAILURE = "bear_rally_failure"
    BEAR_TREND_PULLBACK_CONTINUATION = "bear_trend_pullback_continuation"
    LIQUIDITY_SWEEP_REVERSAL = "liquidity_sweep_reversal"
    RANGE_BOUNDARY_REVERSION = "range_boundary_reversion"
    VOLATILITY_COMPRESSION_BREAKOUT = "volatility_compression_breakout"
    REGIME_CLASSIFIER = "regime_classifier"
    DATA_BACKLOG = "data_backlog"


class EntrySetupKind(str, Enum):
    PULLBACK_RECLAIM = "pullback_reclaim"
    RALLY_FAILURE = "rally_failure"
    TREND_PULLBACK_LOSS = "trend_pullback_loss"
    LIQUIDITY_SWEEP_RECLAIM = "liquidity_sweep_reclaim"
    RANGE_BOUNDARY_REJECTION = "range_boundary_rejection"
    COMPRESSION_BREAKOUT = "compression_breakout"
    SIGNAL_ONLY = "signal_only"


class ProtectionReferenceKind(str, Enum):
    STRUCTURE_EXTREME = "structure_extreme"
    ATR_BUFFERED_STRUCTURE = "atr_buffered_structure"
    RANGE_BOUNDARY_BUFFER = "range_boundary_buffer"
    COMPRESSION_BOUNDARY_BUFFER = "compression_boundary_buffer"
    NONE = "none"


class ExitPlanKind(str, Enum):
    PARTIAL_TP_PLUS_RUNNER = "partial_tp_plus_runner"
    FIXED_RR_OR_RANGE_TARGETS = "fixed_rr_or_range_targets"
    CLASSIFIER_ONLY = "classifier_only"
    DATA_BACKLOG_ONLY = "data_backlog_only"


class StrategyFeatureSnapshot(StrategyCandidateSemanticsModel):
    feature_set_id: str = Field(min_length=1, max_length=128)
    timeframe: str = Field(min_length=1, max_length=32)
    source: str = Field(min_length=1, max_length=128)
    features: dict[str, Any] = Field(default_factory=dict)


class EntrySetupProposal(StrategyCandidateSemanticsModel):
    kind: EntrySetupKind
    side: Literal["long", "short", "none"]
    trigger: str = Field(min_length=1, max_length=128)
    entry_price_reference: Decimal | None = None
    trigger_candle_open_time_ms: int | None = Field(default=None, ge=0)
    valid_timeframe: str = Field(default="1h", max_length=32)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ProtectionProposal(StrategyCandidateSemanticsModel):
    reference_kind: ProtectionReferenceKind
    mandatory: bool = True
    stop_price_reference: Decimal | None = None
    invalidation_condition: str = Field(default="", max_length=256)
    risk_unit_reference: str = Field(default="entry_to_stop_distance", max_length=128)
    buffer_description: str = Field(default="", max_length=256)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _mandatory_requires_stop_reference(self) -> "ProtectionProposal":
        if self.mandatory and self.reference_kind != ProtectionReferenceKind.NONE:
            if self.stop_price_reference is None:
                raise ValueError("mandatory ProtectionProposal requires stop_price_reference")
        return self


class TakeProfitTargetProposal(StrategyCandidateSemanticsModel):
    target_id: str = Field(min_length=1, max_length=64)
    target_kind: str = Field(min_length=1, max_length=128)
    rr: Decimal | None = None
    price_reference: Decimal | None = None
    position_fraction: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    notes: list[str] = Field(default_factory=list)


class RunnerProposal(StrategyCandidateSemanticsModel):
    enabled: bool
    trail_kind: str = Field(default="none", max_length=128)
    trail_reference: str = Field(default="", max_length=256)
    preserve_right_tail: bool = False


class ExitProposal(StrategyCandidateSemanticsModel):
    plan_kind: ExitPlanKind
    payoff_profile: StrategyPayoffProfile
    take_profit_targets: list[TakeProfitTargetProposal] = Field(default_factory=list)
    runner: RunnerProposal | None = None
    time_stop_bars: int | None = Field(default=None, ge=1)
    invalidation_conditions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CandidateQualityComponent(StrategyCandidateSemanticsModel):
    component_id: str = Field(min_length=1, max_length=64)
    score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reason: str = Field(default="", max_length=256)


class CandidateQualityScore(StrategyCandidateSemanticsModel):
    score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    score_semantics: Literal[
        "candidate_structure_quality_not_alpha_probability"
    ] = "candidate_structure_quality_not_alpha_probability"
    components: list[CandidateQualityComponent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StrategyCandidateSemantics(StrategyCandidateSemanticsModel):
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    archetype: StrategyArchetype
    payoff_profile: StrategyPayoffProfile
    feature_snapshots: list[StrategyFeatureSnapshot] = Field(default_factory=list)
    entry: EntrySetupProposal
    protection: ProtectionProposal
    exit: ExitProposal
    quality: CandidateQualityScore
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True

