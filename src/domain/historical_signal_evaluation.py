"""Historical signal evaluation experiment domain models.

These models store compact historical research evidence. They do not authorize
execution, write trial-trade-intent evidence, create execution intents, create
orders, or update strategy registry status.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from statistics import median
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_family_signal import (
    SignalDataQualityStatus,
    SignalSide,
    SignalType,
    reject_forbidden_execution_fields,
)


class HistoricalSignalEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoricalSignalEvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class HistoricalForwardOutcomeStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class HistoricalExperimentVerdict(str, Enum):
    CONTINUE = "continue"
    PARK = "park"
    NEEDS_REFINEMENT = "needs_refinement"
    REGIME_DEPENDENT_CONTINUE = "regime_dependent_continue"


class HistoricalSignalEvaluationRun(HistoricalSignalEvaluationModel):
    run_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    playbook_id: Optional[str] = Field(default=None, max_length=128)
    symbols: list[str] = Field(default_factory=list)
    primary_timeframe: str = Field(min_length=1, max_length=32)
    context_timeframes: list[str] = Field(default_factory=list)
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    sampling_method: str = Field(default="explicit_timestamps", max_length=64)
    sampling_interval_bars: int = Field(default=1, ge=1)
    sample_limit: int = Field(default=100, ge=1)
    status: HistoricalSignalEvaluationStatus = HistoricalSignalEvaluationStatus.PENDING
    summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _validate_range_and_reject_execution_fields(self) -> "HistoricalSignalEvaluationRun":
        if self.end_time_ms < self.start_time_ms:
            raise ValueError("end_time_ms must be >= start_time_ms")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_signal_run")
        return self


class HistoricalSignalOutputRecord(HistoricalSignalEvaluationModel):
    run_id: str = Field(min_length=1, max_length=128)
    signal_id: str = Field(min_length=1, max_length=128)
    evaluation_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    timeframe: str = Field(min_length=1, max_length=32)
    signal_type: SignalType
    side: SignalSide
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reason_codes: list[str] = Field(default_factory=list)
    data_quality_status: SignalDataQualityStatus
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    review_plan: dict[str, Any] = Field(default_factory=dict)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalSignalOutputRecord":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_signal_output")
        return self


class HistoricalForwardOutcome(HistoricalSignalEvaluationModel):
    outcome_id: str = Field(min_length=1, max_length=192)
    run_id: str = Field(min_length=1, max_length=128)
    signal_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    side: SignalSide
    window_label: str = Field(min_length=1, max_length=32)
    bars_ahead: int = Field(ge=1)
    status: HistoricalForwardOutcomeStatus
    mfe_pct: Optional[Decimal] = None
    mae_pct: Optional[Decimal] = None
    time_to_mfe_bars: Optional[int] = Field(default=None, ge=0)
    time_to_mae_bars: Optional[int] = Field(default=None, ge=0)
    pain_before_profit_pct: Optional[Decimal] = None
    profit_giveback_pct: Optional[Decimal] = None
    follow_through: bool = False
    invalidation_hit: bool = False
    return_time_curve: list[dict[str, Any]] = Field(default_factory=list)
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalForwardOutcome":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_forward_outcome")
        return self


class HistoricalSignalEvaluationSummary(HistoricalSignalEvaluationModel):
    run_id: str = Field(min_length=1, max_length=128)
    total_evaluations: int = Field(ge=0)
    signal_counts_by_type: dict[str, int] = Field(default_factory=dict)
    would_enter_count: int = Field(ge=0)
    would_enter_ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    invalid_ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    by_symbol: dict[str, int] = Field(default_factory=dict)
    by_year: dict[str, int] = Field(default_factory=dict)
    by_side: dict[str, int] = Field(default_factory=dict)
    by_data_quality: dict[str, int] = Field(default_factory=dict)
    forward_by_window: dict[str, dict[str, Any]] = Field(default_factory=dict)
    incomplete_outcome_count: int = Field(ge=0)
    suggested_verdict: HistoricalExperimentVerdict
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalSignalEvaluationSummary":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_signal_summary")
        return self


class HistoricalSignalEvaluationOwnerReport(HistoricalSignalEvaluationModel):
    run_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    symbols: list[str] = Field(default_factory=list)
    total_evaluations: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    no_action_count: int = Field(ge=0)
    would_enter_count: int = Field(ge=0)
    would_enter_ratio: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    symbol_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)
    data_quality_breakdown: dict[str, int] = Field(default_factory=dict)
    forward_outcome_by_window: dict[str, dict[str, Any]] = Field(default_factory=dict)
    return_time_curve_summary: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    advisory_verdict: HistoricalExperimentVerdict
    verdict_reasons: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4096)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalSignalEvaluationOwnerReport":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_signal_owner_report")
        return self


class HistoricalRegimeWindowReport(HistoricalSignalEvaluationModel):
    window_name: str = Field(min_length=1, max_length=128)
    window_role: str = Field(min_length=1, max_length=128)
    decision_weight: str = Field(min_length=1, max_length=64)
    start_time_ms: int = Field(ge=0)
    end_time_ms: int = Field(ge=0)
    run_id: str = Field(min_length=1, max_length=128)
    owner_report: HistoricalSignalEvaluationOwnerReport

    @model_validator(mode="after")
    def _validate_range_and_reject_execution_fields(self) -> "HistoricalRegimeWindowReport":
        if self.end_time_ms < self.start_time_ms:
            raise ValueError("end_time_ms must be >= start_time_ms")
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_regime_window_report")
        return self


class HistoricalRegimeSplitComparisonReport(HistoricalSignalEvaluationModel):
    comparison_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    child_run_ids_by_window_name: dict[str, str] = Field(default_factory=dict)
    primary_window_verdict: HistoricalExperimentVerdict
    recent_window_verdict: HistoricalExperimentVerdict
    legacy_window_verdict: HistoricalExperimentVerdict
    full_diagnostic_verdict: HistoricalExperimentVerdict
    weighted_owner_verdict: HistoricalExperimentVerdict
    weighted_verdict_reasons: list[str] = Field(default_factory=list)
    regime_dependency_notes: list[str] = Field(default_factory=list)
    by_symbol_highlights: dict[str, Any] = Field(default_factory=dict)
    current_structure_vs_legacy_delta: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    window_reports: list[HistoricalRegimeWindowReport] = Field(default_factory=list)
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "HistoricalRegimeSplitComparisonReport":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="historical_regime_split_report")
        return self


def signal_output_record_from_output(
    *,
    run_id: str,
    output,
    created_at_ms: int,
) -> HistoricalSignalOutputRecord:
    """Convert a StrategyFamilySignalOutput into compact PG-ready evidence."""

    return HistoricalSignalOutputRecord(
        run_id=run_id,
        signal_id=output.signal_id,
        evaluation_id=output.evaluation_id,
        strategy_family_id=output.strategy_family_id,
        symbol=output.symbol,
        timestamp_ms=output.timestamp_ms,
        timeframe=output.timeframe,
        signal_type=output.signal_type,
        side=output.side,
        confidence=output.confidence,
        reason_codes=list(output.reason_codes),
        data_quality_status=output.data_quality.status,
        evidence_payload=dict(output.evidence_payload),
        review_plan=output.review_plan.model_dump(mode="json"),
        not_order=output.not_order,
        not_execution_intent=output.not_execution_intent,
        created_at_ms=created_at_ms,
    )


def build_historical_signal_owner_report(
    *,
    run: HistoricalSignalEvaluationRun,
    signal_records: list[HistoricalSignalOutputRecord],
    outcomes: list[HistoricalForwardOutcome],
    summary: HistoricalSignalEvaluationSummary,
    notes: str = "",
) -> HistoricalSignalEvaluationOwnerReport:
    signal_counts = summary.signal_counts_by_type
    symbol_breakdown: dict[str, dict[str, int]] = {}
    for record in signal_records:
        counts = symbol_breakdown.setdefault(
            record.symbol,
            {
                SignalType.INVALID.value: 0,
                SignalType.NO_ACTION.value: 0,
                SignalType.WOULD_ENTER.value: 0,
            },
        )
        counts[record.signal_type.value] = counts.get(record.signal_type.value, 0) + 1

    forward_outcome_by_window = _aggregate_owner_forward_windows(outcomes)
    return_time_curve_summary = _aggregate_return_time_curve(outcomes)
    verdict_reasons = _verdict_reasons(
        summary=summary,
        forward_outcome_by_window=forward_outcome_by_window,
        symbols=run.symbols,
    )
    return HistoricalSignalEvaluationOwnerReport(
        run_id=run.run_id,
        strategy_family_id=run.strategy_family_id,
        symbols=list(run.symbols),
        total_evaluations=summary.total_evaluations,
        invalid_count=signal_counts.get(SignalType.INVALID.value, 0),
        no_action_count=signal_counts.get(SignalType.NO_ACTION.value, 0),
        would_enter_count=summary.would_enter_count,
        would_enter_ratio=summary.would_enter_ratio,
        symbol_breakdown=dict(sorted(symbol_breakdown.items())),
        data_quality_breakdown=dict(summary.by_data_quality),
        forward_outcome_by_window=forward_outcome_by_window,
        return_time_curve_summary=return_time_curve_summary,
        advisory_verdict=summary.suggested_verdict,
        verdict_reasons=verdict_reasons,
        notes=notes or "Advisory historical research report only; not alpha proof.",
    )


def build_regime_split_comparison_report(
    *,
    comparison_id: str,
    strategy_family_id: str,
    window_reports: list[HistoricalRegimeWindowReport],
    created_at_ms: int,
) -> HistoricalRegimeSplitComparisonReport:
    by_name = {item.window_name: item for item in window_reports}
    primary = by_name["primary_current_structure_2024_to_now"]
    recent = by_name["recent_current_structure_2025_to_now"]
    legacy = by_name["legacy_control_2021_to_2023"]
    full = by_name["full_diagnostic_2021_to_now"]
    weighted_verdict, reasons, notes = _weighted_regime_verdict(
        primary.owner_report.advisory_verdict,
        recent.owner_report.advisory_verdict,
        legacy.owner_report.advisory_verdict,
        full.owner_report.advisory_verdict,
    )
    return HistoricalRegimeSplitComparisonReport(
        comparison_id=comparison_id,
        strategy_family_id=strategy_family_id,
        child_run_ids_by_window_name={item.window_name: item.run_id for item in window_reports},
        primary_window_verdict=primary.owner_report.advisory_verdict,
        recent_window_verdict=recent.owner_report.advisory_verdict,
        legacy_window_verdict=legacy.owner_report.advisory_verdict,
        full_diagnostic_verdict=full.owner_report.advisory_verdict,
        weighted_owner_verdict=weighted_verdict,
        weighted_verdict_reasons=reasons,
        regime_dependency_notes=notes,
        by_symbol_highlights=_regime_symbol_highlights(window_reports),
        current_structure_vs_legacy_delta=_current_vs_legacy_delta(primary, recent, legacy),
        warnings=[
            "2021-2023 is a low-weight legacy control window and must not alone reject current-market hypotheses.",
            "Full 2021-to-now is diagnostic only and is not the primary verdict source.",
            "Historical evidence is not alpha proof and does not authorize live trading.",
        ],
        window_reports=window_reports,
        created_at_ms=created_at_ms,
    )


def compute_historical_signal_summary(
    *,
    run_id: str,
    signal_records: list[HistoricalSignalOutputRecord],
    outcomes: list[HistoricalForwardOutcome],
    notes: str = "",
) -> HistoricalSignalEvaluationSummary:
    total = len(signal_records)
    denominator = Decimal(total or 1)
    signal_counts: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    by_year: dict[str, int] = {}
    by_side: dict[str, int] = {}
    by_data_quality: dict[str, int] = {}

    for record in signal_records:
        signal_counts[record.signal_type.value] = signal_counts.get(record.signal_type.value, 0) + 1
        by_symbol[record.symbol] = by_symbol.get(record.symbol, 0) + 1
        year = str(datetime.fromtimestamp(record.timestamp_ms / 1000, tz=timezone.utc).year)
        by_year[year] = by_year.get(year, 0) + 1
        by_side[record.side.value] = by_side.get(record.side.value, 0) + 1
        quality = record.data_quality_status.value
        by_data_quality[quality] = by_data_quality.get(quality, 0) + 1

    would_enter_count = signal_counts.get(SignalType.WOULD_ENTER.value, 0)
    invalid_count = signal_counts.get(SignalType.INVALID.value, 0)
    forward_by_window = _aggregate_forward_windows(outcomes)
    incomplete_count = sum(1 for outcome in outcomes if outcome.status != HistoricalForwardOutcomeStatus.COMPLETE)
    verdict = _suggest_verdict(
        total=total,
        would_enter_count=would_enter_count,
        invalid_count=invalid_count,
        by_symbol=by_symbol,
        by_year=by_year,
        forward_by_window=forward_by_window,
    )
    return HistoricalSignalEvaluationSummary(
        run_id=run_id,
        total_evaluations=total,
        signal_counts_by_type=dict(sorted(signal_counts.items())),
        would_enter_count=would_enter_count,
        would_enter_ratio=Decimal(would_enter_count) / denominator,
        invalid_ratio=Decimal(invalid_count) / denominator,
        by_symbol=dict(sorted(by_symbol.items())),
        by_year=dict(sorted(by_year.items())),
        by_side=dict(sorted(by_side.items())),
        by_data_quality=dict(sorted(by_data_quality.items())),
        forward_by_window=forward_by_window,
        incomplete_outcome_count=incomplete_count,
        suggested_verdict=verdict,
        notes=notes,
    )


def _aggregate_forward_windows(outcomes: list[HistoricalForwardOutcome]) -> dict[str, dict[str, Any]]:
    by_window: dict[str, list[HistoricalForwardOutcome]] = {}
    for outcome in outcomes:
        by_window.setdefault(outcome.window_label, []).append(outcome)

    result: dict[str, dict[str, Any]] = {}
    for window, window_outcomes in sorted(by_window.items()):
        complete = [
            outcome
            for outcome in window_outcomes
            if outcome.status == HistoricalForwardOutcomeStatus.COMPLETE
            and outcome.mfe_pct is not None
            and outcome.mae_pct is not None
        ]
        mfe_values = [outcome.mfe_pct for outcome in complete if outcome.mfe_pct is not None]
        mae_values = [abs(outcome.mae_pct) for outcome in complete if outcome.mae_pct is not None]
        mean_mfe = _mean_decimal(mfe_values)
        mean_abs_mae = _mean_decimal(mae_values)
        result[window] = {
            "outcome_count": len(window_outcomes),
            "complete_count": len(complete),
            "incomplete_count": len(window_outcomes) - len(complete),
            "mean_mfe_pct": mean_mfe,
            "median_mfe_pct": _median_decimal(mfe_values),
            "mean_abs_mae_pct": mean_abs_mae,
            "median_abs_mae_pct": _median_decimal(mae_values),
            "mfe_mae_ratio": mean_mfe / mean_abs_mae if mean_abs_mae and mean_abs_mae > 0 else None,
            "follow_through_rate": _bool_ratio([outcome.follow_through for outcome in complete]),
        }
    return result


def _aggregate_owner_forward_windows(outcomes: list[HistoricalForwardOutcome]) -> dict[str, dict[str, Any]]:
    by_window: dict[str, list[HistoricalForwardOutcome]] = {}
    for outcome in outcomes:
        by_window.setdefault(outcome.window_label, []).append(outcome)

    result: dict[str, dict[str, Any]] = {}
    for window, window_outcomes in sorted(by_window.items()):
        complete = [
            outcome
            for outcome in window_outcomes
            if outcome.status == HistoricalForwardOutcomeStatus.COMPLETE
            and outcome.mfe_pct is not None
            and outcome.mae_pct is not None
        ]
        mfe_values = [outcome.mfe_pct for outcome in complete if outcome.mfe_pct is not None]
        mae_values = [abs(outcome.mae_pct) for outcome in complete if outcome.mae_pct is not None]
        pain_values = [
            abs(outcome.pain_before_profit_pct)
            for outcome in complete
            if outcome.pain_before_profit_pct is not None
        ]
        giveback_values = [
            outcome.profit_giveback_pct
            for outcome in complete
            if outcome.profit_giveback_pct is not None
        ]
        mean_mfe = _mean_decimal(mfe_values)
        mean_abs_mae = _mean_decimal(mae_values)
        result[window] = {
            "outcome_count": len(window_outcomes),
            "complete_count": len(complete),
            "incomplete_count": len(window_outcomes) - len(complete),
            "mean_mfe_pct": mean_mfe,
            "median_mfe_pct": _median_decimal(mfe_values),
            "mean_abs_mae_pct": mean_abs_mae,
            "median_abs_mae_pct": _median_decimal(mae_values),
            "mfe_mae_ratio": mean_mfe / mean_abs_mae if mean_abs_mae and mean_abs_mae > 0 else None,
            "follow_through_rate": _bool_ratio([outcome.follow_through for outcome in complete]),
            "invalidation_hit_rate": _bool_ratio([outcome.invalidation_hit for outcome in complete]),
            "mean_pain_before_profit_pct": _mean_decimal(pain_values),
            "median_pain_before_profit_pct": _median_decimal(pain_values),
            "mean_profit_giveback_pct": _mean_decimal(giveback_values),
            "median_profit_giveback_pct": _median_decimal(giveback_values),
        }
    return result


def _aggregate_return_time_curve(outcomes: list[HistoricalForwardOutcome]) -> dict[str, list[dict[str, Any]]]:
    values_by_window_and_bar: dict[str, dict[int, list[Decimal]]] = {}
    for outcome in outcomes:
        if outcome.status != HistoricalForwardOutcomeStatus.COMPLETE:
            continue
        per_bar = values_by_window_and_bar.setdefault(outcome.window_label, {})
        for item in outcome.return_time_curve:
            bar = int(item["bar"])
            per_bar.setdefault(bar, []).append(Decimal(str(item["return_pct"])))

    result: dict[str, list[dict[str, Any]]] = {}
    for window, per_bar in sorted(values_by_window_and_bar.items()):
        result[window] = [
            {
                "bar": bar,
                "mean_return_pct": _mean_decimal(values),
                "median_return_pct": _median_decimal(values),
                "sample_count": len(values),
            }
            for bar, values in sorted(per_bar.items())
        ]
    return result


def _verdict_reasons(
    *,
    summary: HistoricalSignalEvaluationSummary,
    forward_outcome_by_window: dict[str, dict[str, Any]],
    symbols: list[str],
) -> list[str]:
    reasons: list[str] = []
    if summary.total_evaluations == 0:
        reasons.append("No evaluations were produced.")
    if summary.would_enter_count < 2:
        reasons.append("Would-enter count is too small for a continue decision.")
    if summary.invalid_ratio > Decimal("0.5"):
        reasons.append("Invalid ratio is above the conservative threshold.")
    favorable_windows = [
        window
        for window, metrics in forward_outcome_by_window.items()
        if metrics.get("mean_mfe_pct") is not None
        and metrics.get("mean_abs_mae_pct") is not None
        and metrics["mean_mfe_pct"] > metrics["mean_abs_mae_pct"]
    ]
    if not favorable_windows and forward_outcome_by_window:
        reasons.append("MFE profile does not exceed MAE profile in reviewed windows.")
    if len(summary.by_symbol) < min(2, len(symbols)):
        reasons.append("Evidence does not span enough requested symbols.")
    if summary.suggested_verdict == HistoricalExperimentVerdict.CONTINUE:
        reasons.append("Evidence is nontrivial across multiple symbols/years and favorable windows.")
    elif summary.suggested_verdict == HistoricalExperimentVerdict.NEEDS_REFINEMENT:
        reasons.append("Signals exist, but evidence is mixed or not broad enough.")
    elif not reasons:
        reasons.append("Conservative thresholds recommend parking this hypothesis for now.")
    return reasons


def _mean_decimal(values: list[Decimal]) -> Optional[Decimal]:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _median_decimal(values: list[Decimal]) -> Optional[Decimal]:
    if not values:
        return None
    return Decimal(str(median(values)))


def _bool_ratio(values: list[bool]) -> Optional[Decimal]:
    if not values:
        return None
    return Decimal(sum(1 for value in values if value)) / Decimal(len(values))


def _suggest_verdict(
    *,
    total: int,
    would_enter_count: int,
    invalid_count: int,
    by_symbol: dict[str, int],
    by_year: dict[str, int],
    forward_by_window: dict[str, dict[str, Any]],
) -> HistoricalExperimentVerdict:
    if total == 0 or would_enter_count < 2:
        return HistoricalExperimentVerdict.PARK
    if Decimal(invalid_count) / Decimal(total) > Decimal("0.5"):
        return HistoricalExperimentVerdict.PARK

    complete_windows = [
        metrics
        for metrics in forward_by_window.values()
        if metrics.get("complete_count", 0) > 0
        and metrics.get("mean_mfe_pct") is not None
        and metrics.get("mean_abs_mae_pct") is not None
    ]
    favorable_windows = [
        metrics
        for metrics in complete_windows
        if metrics["mean_mfe_pct"] > metrics["mean_abs_mae_pct"]
    ]
    if complete_windows and len(favorable_windows) < (len(complete_windows) / 2):
        return HistoricalExperimentVerdict.PARK
    if len(by_symbol) >= 2 and len(by_year) >= 2 and len(favorable_windows) >= 2:
        return HistoricalExperimentVerdict.CONTINUE
    return HistoricalExperimentVerdict.NEEDS_REFINEMENT


def _weighted_regime_verdict(
    primary: HistoricalExperimentVerdict,
    recent: HistoricalExperimentVerdict,
    legacy: HistoricalExperimentVerdict,
    full: HistoricalExperimentVerdict,
) -> tuple[HistoricalExperimentVerdict, list[str], list[str]]:
    reasons: list[str] = []
    notes = [
        "Primary decision weight is assigned to 2024-to-now and 2025-to-now windows.",
        "Legacy 2021-2023 evidence is contrast/stress context only.",
    ]
    if primary == HistoricalExperimentVerdict.CONTINUE and recent == HistoricalExperimentVerdict.CONTINUE:
        if legacy == HistoricalExperimentVerdict.PARK:
            return (
                HistoricalExperimentVerdict.REGIME_DEPENDENT_CONTINUE,
                [
                    "Current-structure windows are supportive.",
                    "Legacy control window is weak but explicitly low-weight.",
                    "Continue only as regime-dependent historical research, not alpha proof.",
                ],
                notes,
            )
        return (
            HistoricalExperimentVerdict.CONTINUE,
            [
                "Both high-weight current-structure windows are supportive.",
                "Legacy/full diagnostic windows do not override current evidence.",
                "Continue remains research-only and not alpha proof.",
            ],
            notes,
        )
    if primary == HistoricalExperimentVerdict.PARK and recent == HistoricalExperimentVerdict.PARK:
        reasons.append("Both high-weight current-structure windows are weak.")
        if legacy == HistoricalExperimentVerdict.CONTINUE:
            reasons.append("Legacy strength does not override weak current-structure evidence.")
        return HistoricalExperimentVerdict.PARK, reasons, notes
    if primary == HistoricalExperimentVerdict.PARK or recent == HistoricalExperimentVerdict.PARK:
        reasons.append("At least one high-weight current-structure window is weak.")
        return HistoricalExperimentVerdict.NEEDS_REFINEMENT, reasons, notes
    reasons.append("Current-structure evidence is mixed or improving but not strong enough for continue.")
    if full == HistoricalExperimentVerdict.PARK and legacy == HistoricalExperimentVerdict.PARK:
        reasons.append("Full diagnostic weakness appears legacy-influenced and is not used as sole veto.")
    return HistoricalExperimentVerdict.NEEDS_REFINEMENT, reasons, notes


def _regime_symbol_highlights(window_reports: list[HistoricalRegimeWindowReport]) -> dict[str, Any]:
    highlights: dict[str, dict[str, Any]] = {}
    for window_report in window_reports:
        for symbol, counts in window_report.owner_report.symbol_breakdown.items():
            symbol_highlight = highlights.setdefault(symbol, {})
            symbol_highlight[window_report.window_name] = {
                "would_enter": counts.get(SignalType.WOULD_ENTER.value, 0),
                "no_action": counts.get(SignalType.NO_ACTION.value, 0),
                "invalid": counts.get(SignalType.INVALID.value, 0),
            }
    return dict(sorted(highlights.items()))


def _current_vs_legacy_delta(
    primary: HistoricalRegimeWindowReport,
    recent: HistoricalRegimeWindowReport,
    legacy: HistoricalRegimeWindowReport,
) -> dict[str, Any]:
    primary_ratio = primary.owner_report.would_enter_ratio
    recent_ratio = recent.owner_report.would_enter_ratio
    legacy_ratio = legacy.owner_report.would_enter_ratio
    return {
        "would_enter_ratio_primary_minus_legacy": primary_ratio - legacy_ratio,
        "would_enter_ratio_recent_minus_legacy": recent_ratio - legacy_ratio,
        "primary_4h_mfe_mae_ratio": _window_ratio(primary.owner_report, "4h"),
        "recent_4h_mfe_mae_ratio": _window_ratio(recent.owner_report, "4h"),
        "legacy_4h_mfe_mae_ratio": _window_ratio(legacy.owner_report, "4h"),
    }


def _window_ratio(report: HistoricalSignalEvaluationOwnerReport, window: str):
    metrics = report.forward_outcome_by_window.get(window) or {}
    return metrics.get("mfe_mae_ratio")
