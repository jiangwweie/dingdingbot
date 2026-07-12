"""Pure opportunity-frequency and replay/live parity calibration.

This module consumes already evaluated strategy observations.  It deliberately
does not evaluate strategy rules, perform I/O, or create runtime authority.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DAY_MS = 86_400_000
DEFAULT_WINDOW_DAYS = (90, 365)
_RATE_QUANTUM = Decimal("0.000001")


class CalibrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpportunitySource(str, Enum):
    REPLAY = "replay"
    LIVE = "live"


class OpportunityResult(str, Enum):
    SIGNAL = "signal"
    NEAR_MISS = "near_miss"
    NO_SIGNAL = "no_signal"
    INVALID = "invalid"


class CalibrationProposal(str, Enum):
    KEEP_OBSERVING = "keep_observing"
    REPAIR_REPLAY_LIVE_PARITY = "repair_replay_live_parity"
    REPAIR_LIVE_COVERAGE = "repair_live_coverage"
    REVIEW_STRATEGY_REVISION = "review_strategy_revision"
    REVIEW_SCOPE_EXPANSION = "review_scope_expansion"
    REVIEW_PARK = "review_park"
    NEEDS_MORE_SAMPLES = "needs_more_samples"


FactValue = bool | int | str | Decimal | None


class OpportunityEvaluation(CalibrationModel):
    strategy_group_id: str = Field(min_length=1, max_length=128)
    strategy_group_version_id: str = Field(min_length=1, max_length=160)
    evaluator_version_id: str = Field(min_length=1, max_length=128)
    event_spec_id: str = Field(min_length=1, max_length=192)
    event_spec_version_id: str = Field(min_length=1, max_length=192)
    event_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: Literal["long", "short"]
    timeframe: str = Field(min_length=1, max_length=32)
    trigger_candle_close_time_ms: int = Field(ge=0)
    observed_at_ms: int = Field(ge=0)
    source: OpportunitySource
    result: OpportunityResult
    fact_results: dict[str, FactValue] = Field(default_factory=dict)
    failed_facts: list[str] = Field(default_factory=list)
    parity_expected: bool = False
    calibration_only: Literal[True] = True
    not_live_signal_authority: Literal[True] = True
    not_execution_authority: Literal[True] = True
    finalgate_allowed: Literal[False] = False
    operation_layer_allowed: Literal[False] = False
    exchange_write_allowed: Literal[False] = False
    real_order_allowed: Literal[False] = False
    owner_policy_mutation_allowed: Literal[False] = False

    @model_validator(mode="after")
    def _validate_fact_shape(self) -> "OpportunityEvaluation":
        normalized_failed = sorted(dict.fromkeys(self.failed_facts))
        if normalized_failed != self.failed_facts:
            raise ValueError("failed_facts_must_be_sorted_and_unique")
        if any(not str(key).strip() for key in self.fact_results):
            raise ValueError("fact_result_key_required")
        return self

    @property
    def comparison_identity(self) -> str:
        return "|".join(
            (
                self.strategy_group_id,
                self.strategy_group_version_id,
                self.evaluator_version_id,
                self.event_spec_id,
                self.event_spec_version_id,
                self.event_id,
                self.symbol,
                self.side,
                self.timeframe,
                str(self.trigger_candle_close_time_ms),
            )
        )


class OpportunitySourceSummary(CalibrationModel):
    total_evaluations: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    near_miss_count: int = Field(ge=0)
    no_signal_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    observations_per_30_days: Decimal = Field(ge=Decimal("0"))
    failed_fact_counts: dict[str, int] = Field(default_factory=dict)


class OpportunityCalibrationWindow(CalibrationModel):
    window_days: int = Field(gt=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    replay: OpportunitySourceSummary
    live: OpportunitySourceSummary


class ReplayLiveParityMismatch(CalibrationModel):
    comparison_identity: str = Field(min_length=1)
    replay_result: OpportunityResult
    live_result: OpportunityResult
    result_mismatch: bool
    mismatched_fact_keys: list[str] = Field(default_factory=list)


class OpportunityCalibrationResult(CalibrationModel):
    as_of_ms: int = Field(ge=0)
    windows: list[OpportunityCalibrationWindow]
    parity_mismatches: list[ReplayLiveParityMismatch] = Field(default_factory=list)
    missing_live_identities: list[str] = Field(default_factory=list)
    missing_replay_identities: list[str] = Field(default_factory=list)
    proposal: CalibrationProposal
    next_action: str = Field(min_length=1, max_length=256)
    owner_confirmation_required: bool
    calibration_only: Literal[True] = True
    runtime_authority_created: Literal[False] = False
    owner_policy_mutated: Literal[False] = False
    exchange_write_called: Literal[False] = False


def calibrate_opportunity_feedback(
    observations: list[OpportunityEvaluation],
    *,
    as_of_ms: int,
    window_days: tuple[int, ...] = DEFAULT_WINDOW_DAYS,
) -> OpportunityCalibrationResult:
    """Aggregate opportunity supply and exact replay/live parity.

    Historical replay observations do not require a live counterpart unless
    ``parity_expected`` is explicitly true.  This prevents old market windows
    from being mislabeled as current live coverage failures.
    """

    if as_of_ms < 0:
        raise ValueError("as_of_ms_must_be_non_negative")
    if not window_days or any(days <= 0 for days in window_days):
        raise ValueError("positive_window_days_required")
    if len(set(window_days)) != len(window_days):
        raise ValueError("window_days_must_be_unique")

    windows = [
        _window(observations, as_of_ms=as_of_ms, days=days)
        for days in window_days
    ]
    parity, missing_live, missing_replay = _parity(observations)

    if parity:
        proposal = CalibrationProposal.REPAIR_REPLAY_LIVE_PARITY
        next_action = "repair_replay_live_parity_before_strategy_review"
    elif missing_live or missing_replay:
        proposal = CalibrationProposal.REPAIR_LIVE_COVERAGE
        next_action = "repair_comparable_replay_live_coverage"
    elif not any(window.replay.total_evaluations or window.live.total_evaluations for window in windows):
        proposal = CalibrationProposal.NEEDS_MORE_SAMPLES
        next_action = "collect_more_version_pinned_observations"
    else:
        proposal = CalibrationProposal.KEEP_OBSERVING
        next_action = "continue_version_pinned_observation"

    return OpportunityCalibrationResult(
        as_of_ms=as_of_ms,
        windows=windows,
        parity_mismatches=parity,
        missing_live_identities=missing_live,
        missing_replay_identities=missing_replay,
        proposal=proposal,
        next_action=next_action,
        owner_confirmation_required=proposal
        in {
            CalibrationProposal.REVIEW_STRATEGY_REVISION,
            CalibrationProposal.REVIEW_SCOPE_EXPANSION,
            CalibrationProposal.REVIEW_PARK,
        },
    )


def _window(
    observations: list[OpportunityEvaluation],
    *,
    as_of_ms: int,
    days: int,
) -> OpportunityCalibrationWindow:
    start_ms = max(0, as_of_ms - days * DAY_MS)
    selected = [
        item
        for item in observations
        if start_ms <= item.trigger_candle_close_time_ms <= as_of_ms
    ]
    return OpportunityCalibrationWindow(
        window_days=days,
        start_ms=start_ms,
        end_ms=as_of_ms,
        replay=_source_summary(selected, OpportunitySource.REPLAY, days),
        live=_source_summary(selected, OpportunitySource.LIVE, days),
    )


def _source_summary(
    observations: list[OpportunityEvaluation],
    source: OpportunitySource,
    window_days: int,
) -> OpportunitySourceSummary:
    selected = [item for item in observations if item.source == source]
    result_counts = Counter(item.result for item in selected)
    failed_facts: Counter[str] = Counter()
    for item in selected:
        failed_facts.update(item.failed_facts)
    rate = (
        (Decimal(len(selected)) * Decimal("30") / Decimal(window_days)).quantize(
            _RATE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if selected
        else Decimal("0")
    )
    return OpportunitySourceSummary(
        total_evaluations=len(selected),
        signal_count=result_counts[OpportunityResult.SIGNAL],
        near_miss_count=result_counts[OpportunityResult.NEAR_MISS],
        no_signal_count=result_counts[OpportunityResult.NO_SIGNAL],
        invalid_count=result_counts[OpportunityResult.INVALID],
        observations_per_30_days=rate,
        failed_fact_counts=dict(sorted(failed_facts.items())),
    )


def _parity(
    observations: list[OpportunityEvaluation],
) -> tuple[list[ReplayLiveParityMismatch], list[str], list[str]]:
    expected = [item for item in observations if item.parity_expected]
    by_identity: dict[str, dict[OpportunitySource, OpportunityEvaluation]] = {}
    for item in expected:
        sources = by_identity.setdefault(item.comparison_identity, {})
        if item.source in sources:
            raise ValueError(
                f"duplicate_parity_observation:{item.comparison_identity}:{item.source.value}"
            )
        sources[item.source] = item

    mismatches: list[ReplayLiveParityMismatch] = []
    missing_live: list[str] = []
    missing_replay: list[str] = []
    for identity, sources in sorted(by_identity.items()):
        replay = sources.get(OpportunitySource.REPLAY)
        live = sources.get(OpportunitySource.LIVE)
        if replay is None:
            missing_replay.append(identity)
            continue
        if live is None:
            missing_live.append(identity)
            continue
        fact_keys = sorted(set(replay.fact_results) | set(live.fact_results))
        fact_mismatches = [
            key
            for key in fact_keys
            if replay.fact_results.get(key) != live.fact_results.get(key)
        ]
        result_mismatch = replay.result != live.result
        if result_mismatch or fact_mismatches:
            mismatches.append(
                ReplayLiveParityMismatch(
                    comparison_identity=identity,
                    replay_result=replay.result,
                    live_result=live.result,
                    result_mismatch=result_mismatch,
                    mismatched_fact_keys=fact_mismatches,
                )
            )
    return mismatches, missing_live, missing_replay
