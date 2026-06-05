"""Metadata-only strategy family registry domain models.

The registry describes observation candidates and playbooks. It does not run
strategies, select strategies dynamically, size trades, grant permissions,
create trial trade intents, create execution intents, or create orders.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import (
    CONTRACT_VERSION,
    SignalType,
    reject_forbidden_execution_fields,
)


class StrategyFamilyRegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyFamilyStatus(str, Enum):
    REGISTERED_HYPOTHESIS_ONLY = "registered_hypothesis_only"
    ACTIVE_OBSERVATION_CANDIDATE = "active_observation_candidate"
    LIVE_READONLY_OBSERVATION = "live_readonly_observation"
    PARKED = "parked"
    RETIRED = "retired"


class StrategyFamilyType(str, Enum):
    TREND_FOLLOWING = "trend_following"
    VOLATILITY_BREAKOUT = "volatility_breakout"
    MEAN_REVERSION = "mean_reversion"
    PULLBACK_CONTINUATION = "pullback_continuation"
    EVENT_DRIVEN_DISCRETIONARY = "event_driven_discretionary"
    FUNDING_OI_DISLOCATION = "funding_oi_dislocation"
    UNKNOWN = "unknown"


class StrategyFamilyMetadata(StrategyFamilyRegistryModel):
    family_id: str = Field(min_length=1, max_length=128)
    family_name: str = Field(min_length=1, max_length=256)
    family_type: StrategyFamilyType = StrategyFamilyType.UNKNOWN
    status: StrategyFamilyStatus
    version_id: str = Field(min_length=1, max_length=128)
    hypothesis: str = Field(default="", max_length=4096)
    alpha_claim: bool = False
    carrier_validation: bool = False
    supported_symbols: list[str] = Field(default_factory=list)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    input_requirements: list[str] = Field(default_factory=list)
    allowed_signal_types: list[SignalType] = Field(default_factory=list)
    reason_code_taxonomy: dict[str, str] = Field(default_factory=dict)
    review_metrics: list[str] = Field(default_factory=list)
    known_failure_modes: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4096)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "StrategyFamilyMetadata":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="strategy_family_metadata")
        return self


class StrategyFamilyPlaybookMetadata(StrategyFamilyRegistryModel):
    playbook_id: str = Field(min_length=1, max_length=128)
    family_id: str = Field(min_length=1, max_length=128)
    version_id: str = Field(min_length=1, max_length=128)
    playbook_name: str = Field(min_length=1, max_length=256)
    playbook_status: StrategyFamilyStatus
    symbol_universe: list[str] = Field(default_factory=list)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    signal_contract_version: str = Field(default=CONTRACT_VERSION, min_length=1, max_length=128)
    allowed_signal_types: list[SignalType] = Field(default_factory=list)
    review_windows: list[str] = Field(default_factory=list)
    review_metrics: list[str] = Field(default_factory=list)
    input_requirements: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    parameter_profile: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4096)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "StrategyFamilyPlaybookMetadata":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="strategy_family_playbook_metadata")
        return self


class StrategyFamilyRegistrySeed(StrategyFamilyRegistryModel):
    families: list[StrategyFamilyMetadata]
    playbooks: list[StrategyFamilyPlaybookMetadata]


_TF_REVIEW_METRICS = [
    "signal_frequency",
    "no_action_ratio",
    "invalid_ratio",
    "would_enter_ratio",
    "MFE after 4h",
    "MFE after 24h",
    "MFE after 72h",
    "MAE after 4h",
    "MAE after 24h",
    "MAE after 72h",
    "follow_through_rate",
    "invalidation_hit_rate",
    "time_to_MFE",
    "time_to_MAE",
    "return_time_curve",
    "evidence_completeness_score",
]

_TF_INPUT_REQUIREMENTS = [
    "1h OHLCV",
    "4h OHLCV",
    "1d OHLCV",
    "mark price or last price",
    "volume",
    "ATR or volatility proxy",
    "funding rate optional",
    "account facts snapshot",
    "reconciliation status",
    "runtime safety snapshot",
    "execution permission resolution",
    "trial constraints snapshot",
]

_TF_EVIDENCE_REQUIREMENTS = [
    "input_refs",
    "signal_snapshot",
    "reason_codes",
    "data_quality",
    "review_plan",
    "context_tags",
    "not_order = true",
    "not_execution_intent = true",
]


def initial_strategy_family_registry_seed(*, now_ms: int) -> StrategyFamilyRegistrySeed:
    """Return the BRC-R5-003B metadata-only initial registry seed."""

    tf_family = StrategyFamilyMetadata(
        family_id="TF-001-live-readonly-v0",
        family_name="Major Trend Continuation / Trend Following",
        family_type=StrategyFamilyType.TREND_FOLLOWING,
        status=StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE,
        version_id="TF-001-live-readonly-v0",
        hypothesis=(
            "BTC / ETH / SOL on 1h, with 4h / 1d context, may produce observable, "
            "explainable, reviewable major-trend continuation signals."
        ),
        alpha_claim=False,
        carrier_validation=True,
        supported_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        input_requirements=list(_TF_INPUT_REQUIREMENTS),
        allowed_signal_types=[
            SignalType.NO_ACTION,
            SignalType.WOULD_ENTER,
            SignalType.INVALID,
        ],
        reason_code_taxonomy={
            "trend_context_absent": "Major trend context is not observable.",
            "trend_continuation_context": "Major trend continuation context is observable.",
            "invalid_data_quality": "Required input evidence is missing or stale.",
        },
        review_metrics=list(_TF_REVIEW_METRICS),
        known_failure_modes=[
            "range chop false continuation",
            "late trend entry",
            "false breakout",
            "event shock",
            "funding crowding",
            "SOL higher noise",
        ],
        evidence_requirements=list(_TF_EVIDENCE_REQUIREMENTS),
        notes="Carrier validation and signal contract validation only; not alpha proof.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    tf_playbook = StrategyFamilyPlaybookMetadata(
        playbook_id="TF-001-live-readonly-v0",
        family_id=tf_family.family_id,
        version_id=tf_family.version_id,
        playbook_name="TF-001 Live Read-only Observation v0",
        playbook_status=StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE,
        symbol_universe=list(tf_family.supported_symbols),
        primary_timeframe=tf_family.primary_timeframe,
        context_timeframes=list(tf_family.context_timeframes),
        allowed_signal_types=list(tf_family.allowed_signal_types),
        review_windows=["4h", "24h", "72h", "7d"],
        review_metrics=list(tf_family.review_metrics),
        input_requirements=list(tf_family.input_requirements),
        evidence_requirements=list(tf_family.evidence_requirements),
        parameter_profile={
            "profile_kind": "metadata_only",
            "trend_context": ["1h primary", "4h context", "1d context"],
            "volatility_context": "ATR or volatility proxy required",
            "funding_context": "optional",
        },
        notes="Does not allow would_exit, would_reduce, or would_cancel for this playbook.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )

    vb_family = StrategyFamilyMetadata(
        family_id="VB-001-live-readonly-v0",
        family_name="Volatility Contraction Breakout",
        family_type=StrategyFamilyType.VOLATILITY_BREAKOUT,
        status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        version_id="VB-001-live-readonly-v0",
        hypothesis=(
            "Volatility contraction followed by breakout may produce observable "
            "directional release evidence."
        ),
        alpha_claim=False,
        carrier_validation=False,
        supported_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        input_requirements=["OHLCV", "ATR or volatility proxy", "volume", "read-only account facts"],
        allowed_signal_types=[SignalType.NO_ACTION, SignalType.WOULD_ENTER, SignalType.INVALID],
        reason_code_taxonomy={
            "contraction_absent": "Volatility contraction context is absent.",
            "breakout_context": "Breakout context is observable after contraction.",
        },
        review_metrics=[
            "signal_frequency",
            "false_breakout_rate",
            "follow_through_rate",
            "evidence_completeness_score",
        ],
        known_failure_modes=["fake breakout", "news wick", "low volume breakout"],
        evidence_requirements=list(_TF_EVIDENCE_REQUIREMENTS),
        notes="Hypothesis-only. No evaluator and no runner activation.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    vb_playbook = StrategyFamilyPlaybookMetadata(
        playbook_id="VB-001-live-readonly-v0",
        family_id=vb_family.family_id,
        version_id=vb_family.version_id,
        playbook_name="VB-001 Live Read-only Hypothesis v0",
        playbook_status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        symbol_universe=list(vb_family.supported_symbols),
        primary_timeframe=vb_family.primary_timeframe,
        context_timeframes=list(vb_family.context_timeframes),
        allowed_signal_types=list(vb_family.allowed_signal_types),
        review_windows=["4h", "24h", "72h"],
        review_metrics=list(vb_family.review_metrics),
        input_requirements=list(vb_family.input_requirements),
        evidence_requirements=list(vb_family.evidence_requirements),
        parameter_profile={"profile_kind": "metadata_only", "activation": "not_active"},
        notes="Do not activate in runner.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )

    cpm_family = StrategyFamilyMetadata(
        family_id="CPM-RO-001",
        family_name="Pullback Continuation Read-only Observation",
        family_type=StrategyFamilyType.PULLBACK_CONTINUATION,
        status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        version_id="CPM-RO-001",
        hypothesis=(
            "In intact higher-timeframe trends, normal pullback and reclaim structures "
            "may produce continuation opportunities."
        ),
        alpha_claim=False,
        carrier_validation=False,
        supported_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        input_requirements=["HTF trend context", "pullback depth", "ATR", "volume", "read-only account facts"],
        allowed_signal_types=[SignalType.NO_ACTION, SignalType.WOULD_ENTER, SignalType.INVALID],
        reason_code_taxonomy={
            "trend_not_intact": "Higher-timeframe trend is not intact.",
            "pullback_reclaim_context": "Pullback reclaim context is observable.",
        },
        review_metrics=[
            "regime_match_score",
            "reclaim_follow_through",
            "invalidation_hit_rate",
            "evidence_completeness_score",
        ],
        known_failure_modes=["bear-market bounce", "false reclaim", "parameter puzzle"],
        evidence_requirements=list(_TF_EVIDENCE_REQUIREMENTS),
        notes="Historical performance is not current alpha proof; revalidation required.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    cpm_playbook = StrategyFamilyPlaybookMetadata(
        playbook_id="CPM-RO-001",
        family_id=cpm_family.family_id,
        version_id=cpm_family.version_id,
        playbook_name="CPM Read-only Revalidation v0",
        playbook_status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        symbol_universe=list(cpm_family.supported_symbols),
        primary_timeframe=cpm_family.primary_timeframe,
        context_timeframes=list(cpm_family.context_timeframes),
        allowed_signal_types=list(cpm_family.allowed_signal_types),
        review_windows=["4h", "24h", "72h", "7d"],
        review_metrics=list(cpm_family.review_metrics),
        input_requirements=list(cpm_family.input_requirements),
        evidence_requirements=list(cpm_family.evidence_requirements),
        parameter_profile={"profile_kind": "metadata_only", "historical_revalidation_required": True},
        notes="Do not treat historical 2024 behavior as current alpha proof.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )

    mr_family = StrategyFamilyMetadata(
        family_id="MR-001-live-readonly-v0",
        family_name="Range Mean Reversion Read-only Observation",
        family_type=StrategyFamilyType.MEAN_REVERSION,
        status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        version_id="MR-001-live-readonly-v0",
        hypothesis=(
            "In bounded range regimes, statistically stretched moves back toward "
            "accepted value may produce observable mean-reversion evidence."
        ),
        alpha_claim=False,
        carrier_validation=False,
        supported_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        primary_timeframe="1h",
        context_timeframes=["4h", "1d"],
        input_requirements=[
            "range regime context",
            "deviation from accepted value",
            "ATR or volatility proxy",
            "volume and liquidity sanity",
            "read-only account facts",
            "reconciliation status",
        ],
        allowed_signal_types=[
            SignalType.NO_ACTION,
            SignalType.WOULD_ENTER,
            SignalType.INVALID,
        ],
        reason_code_taxonomy={
            "range_context_absent": "Market is not in a bounded range context.",
            "mean_reversion_context": "Price is stretched inside a bounded range context.",
            "trend_break_risk": "Trend continuation risk overrides reversion setup.",
            "invalid_data_quality": "Required input evidence is missing or stale.",
        },
        review_metrics=[
            "range_context_precision",
            "snapback_follow_through",
            "trend_break_failure_rate",
            "invalidation_hit_rate",
            "evidence_completeness_score",
        ],
        known_failure_modes=[
            "catching falling knife",
            "range break becomes trend continuation",
            "liquidity wick beyond invalidation",
            "late reversion after stop",
        ],
        evidence_requirements=list(_TF_EVIDENCE_REQUIREMENTS),
        notes=(
            "Hypothesis-only mean-reversion candidate. No live scope, no evaluator "
            "activation, and no order authority."
        ),
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    mr_playbook = StrategyFamilyPlaybookMetadata(
        playbook_id="MR-001-live-readonly-v0",
        family_id=mr_family.family_id,
        version_id=mr_family.version_id,
        playbook_name="MR-001 Range Mean Reversion Read-only Hypothesis v0",
        playbook_status=StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY,
        symbol_universe=list(mr_family.supported_symbols),
        primary_timeframe=mr_family.primary_timeframe,
        context_timeframes=list(mr_family.context_timeframes),
        allowed_signal_types=list(mr_family.allowed_signal_types),
        review_windows=["4h", "24h", "72h"],
        review_metrics=list(mr_family.review_metrics),
        input_requirements=list(mr_family.input_requirements),
        evidence_requirements=list(mr_family.evidence_requirements),
        parameter_profile={
            "profile_kind": "metadata_only",
            "activation": "not_active",
            "range_context_required": True,
        },
        notes="Do not activate in runner and do not infer execution permission.",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )

    return StrategyFamilyRegistrySeed(
        families=[tf_family, vb_family, cpm_family, mr_family],
        playbooks=[tf_playbook, vb_playbook, cpm_playbook, mr_playbook],
    )
