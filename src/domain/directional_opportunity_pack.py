"""Research-only Directional Opportunity Pack v0.1 spec."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import SignalSide, reject_forbidden_execution_fields


class DirectionalOpportunityPackModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DirectionalPackStatus(str, Enum):
    ACTIVE_OBSERVATION_CANDIDATE = "active_observation_candidate"
    REGISTERED_HYPOTHESIS_ONLY = "registered_hypothesis_only"
    PARKED = "parked"
    REJECTED = "rejected"


class DirectionalPackResearchStage(str, Enum):
    HYPOTHESIS = "hypothesis"
    HISTORICAL_FORWARD_OUTCOME = "historical_forward_outcome"
    COST_ADJUSTED = "cost_adjusted"
    BASELINE_CHECKED = "baseline_checked"
    CAMPAIGN_SHAPE_CHECKED = "campaign_shape_checked"
    LIVE_READONLY_OBSERVATION_CANDIDATE = "live_readonly_observation_candidate"
    LIVE_READONLY_OBSERVED = "live_readonly_observed"
    BOUNDED_TRIAL_CANDIDATE = "bounded_trial_candidate"


class DirectionalPackCandidateRole(str, Enum):
    CAMPAIGN_ENGINE_CANDIDATE = "campaign_engine_candidate"
    BENCHMARK_COMPONENT = "benchmark_component"
    REGIME_FILTER = "regime_filter"
    RISK_FILTER = "risk_filter"
    MANUAL_EVENT_TRACKER = "manual_event_tracker"
    RESEARCH_REFERENCE = "research_reference"


class DirectionalCandidateFamilySpec(DirectionalOpportunityPackModel):
    family_id: str = Field(min_length=1, max_length=128)
    family_name: str = Field(min_length=1, max_length=256)
    status: DirectionalPackStatus
    research_stage: DirectionalPackResearchStage
    candidate_roles: list[DirectionalPackCandidateRole]
    supported_sides: list[SignalSide]
    forward_windows: list[str]
    notes: str = Field(default="", max_length=1024)

    @model_validator(mode="after")
    def _validate_candidate(self) -> "DirectionalCandidateFamilySpec":
        if not self.candidate_roles:
            raise ValueError("candidate_roles must not be empty")
        if not self.supported_sides:
            raise ValueError("supported_sides must not be empty")
        if not self.forward_windows:
            raise ValueError("forward_windows must not be empty")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="directional_candidate")
        return self


class DirectionalOpportunityPackSpec(DirectionalOpportunityPackModel):
    pack_id: str = Field(default="btc-eth-sol-bnb-long-short-directional-pack-v0.1")
    canonical_symbols: list[str]
    sides: list[SignalSide]
    forward_windows: list[str]
    required_metric_names: list[str]
    candidate_families: list[DirectionalCandidateFamilySpec]

    @model_validator(mode="after")
    def _validate_pack(self) -> "DirectionalOpportunityPackSpec":
        if set(self.sides) != {SignalSide.LONG, SignalSide.SHORT}:
            raise ValueError("directional pack must include long and short sides only")
        family_ids = [candidate.family_id for candidate in self.candidate_families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("candidate family ids must be unique")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="directional_pack")
        return self


CANONICAL_DIRECTIONAL_SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
]

CANONICAL_FORWARD_WINDOWS = ["1h", "4h", "12h", "24h", "72h", "7d"]

DIRECTIONAL_PACK_METRICS = [
    "signal_count",
    "signal_frequency",
    "forward_return",
    "cost_adjusted_return",
    "MFE",
    "MAE",
    "giveback",
    "time_to_MFE",
    "time_to_MAE",
    "random_baseline_delta",
    "side_baseline_delta",
    "symbol_baseline_delta",
    "campaign_ruin_rate",
    "top_5_percent",
    "top_10_percent",
    "bottom_5_percent",
    "bottom_10_percent",
    "median_campaign",
    "max_consecutive_failures",
    "time_to_step_up",
]


def btc_eth_sol_bnb_directional_opportunity_pack() -> DirectionalOpportunityPackSpec:
    """Return the minimal pack spec for long-short directional research."""

    candidate_windows = list(CANONICAL_FORWARD_WINDOWS)
    return DirectionalOpportunityPackSpec(
        canonical_symbols=list(CANONICAL_DIRECTIONAL_SYMBOLS),
        sides=[SignalSide.LONG, SignalSide.SHORT],
        forward_windows=candidate_windows,
        required_metric_names=list(DIRECTIONAL_PACK_METRICS),
        candidate_families=[
            DirectionalCandidateFamilySpec(
                family_id="PULLBACK-CONT-001",
                family_name="Pullback continuation long-short hypothesis",
                status=DirectionalPackStatus.REGISTERED_HYPOTHESIS_ONLY,
                research_stage=DirectionalPackResearchStage.HYPOTHESIS,
                candidate_roles=[DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE],
                supported_sides=[SignalSide.LONG, SignalSide.SHORT],
                forward_windows=candidate_windows,
                notes="Long side is CPM-like continuation; short side is rebound-fail or breakdown continuation.",
            ),
            DirectionalCandidateFamilySpec(
                family_id="VB-001",
                family_name="Volatility expansion long-short hypothesis",
                status=DirectionalPackStatus.REGISTERED_HYPOTHESIS_ONLY,
                research_stage=DirectionalPackResearchStage.HYPOTHESIS,
                candidate_roles=[DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE],
                supported_sides=[SignalSide.LONG, SignalSide.SHORT],
                forward_windows=candidate_windows,
                notes="Compression release up or down; no active evaluator in this pack spec.",
            ),
            DirectionalCandidateFamilySpec(
                family_id="TB-001",
                family_name="Trend breakout long-short hypothesis",
                status=DirectionalPackStatus.REGISTERED_HYPOTHESIS_ONLY,
                research_stage=DirectionalPackResearchStage.HYPOTHESIS,
                candidate_roles=[DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE],
                supported_sides=[SignalSide.LONG, SignalSide.SHORT],
                forward_windows=candidate_windows,
                notes="Donchian or ATR breakout and breakdown family placeholder.",
            ),
            DirectionalCandidateFamilySpec(
                family_id="BTC-REGIME-RS-001",
                family_name="BTC regime relative-strength hypothesis",
                status=DirectionalPackStatus.REGISTERED_HYPOTHESIS_ONLY,
                research_stage=DirectionalPackResearchStage.HYPOTHESIS,
                candidate_roles=[DirectionalPackCandidateRole.REGIME_FILTER],
                supported_sides=[SignalSide.LONG, SignalSide.SHORT],
                forward_windows=candidate_windows,
                notes="BTC is the market anchor; ETH, SOL, and BNB are beta-symbol comparison candidates.",
            ),
            DirectionalCandidateFamilySpec(
                family_id="CPM-RO-001",
                family_name="CPM read-only benchmark reference",
                status=DirectionalPackStatus.PARKED,
                research_stage=DirectionalPackResearchStage.CAMPAIGN_SHAPE_CHECKED,
                candidate_roles=[
                    DirectionalPackCandidateRole.BENCHMARK_COMPONENT,
                    DirectionalPackCandidateRole.RESEARCH_REFERENCE,
                ],
                supported_sides=[SignalSide.LONG, SignalSide.SHORT],
                forward_windows=candidate_windows,
                notes="Benchmark/reference only; do not continue CPM single-strategy optimization from this pack.",
            ),
        ],
    )
