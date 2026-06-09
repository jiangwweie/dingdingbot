"""Read-only strategy-group observation v1 for Owner review.

This module wires strategy-specific signal evaluator glue for MI-001 and
CPM-RO-001 without starting a runtime loop, creating execution intents,
placing orders, or granting execution permission.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from src.application.runtime_strategy_signal_scheduler_assembly import (
    RuntimeStrategySignalSchedulerAssemblyService,
    RuntimeStrategySignalSchedulerReadinessStatus,
)
from src.domain.cpm_historical_evaluator import CPMRO001HistoricalEvaluator
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    ExpectedRiskShape,
    MarketSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    SignalInputRefs,
    SignalReviewPlan,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)


OBSERVATION_V1_SOURCE = "strategy_group_live_readonly_observation_v1"
MI001_FAMILY_ID = "MI-001"
MI001_VERSION_ID = "MI-001-smoke-v0"
CPM_FAMILY_ID = "CPM-RO-001"
CPM_VERSION_ID = "CPM-RO-001-v0"
MI_LOOKBACK_BARS = 12
MI_RETURN_THRESHOLD = Decimal("3")


class StrategyGroupObservationCandidate(BaseModel):
    candidate_id: str
    strategy_group_id: str
    strategy_family_version_id: str | None = None
    symbol: str
    side: str
    observation_role: str
    evaluator_glue_status: str
    signal_contract: list[str] = Field(default_factory=lambda: ["no_action", "would_enter", "invalid"])
    review_windows: list[str] = Field(default_factory=lambda: ["24h", "72h", "7d"])
    latest_signal_preview: dict[str, Any] = Field(default_factory=dict)
    evidence_payload_fields: list[str] = Field(default_factory=list)
    evidence_record_mapping: str = "metadata_only_observation_record_ready"
    readiness_status: str
    blockers: list[str] = Field(default_factory=list)
    not_allowed_now: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    runtime_signal_planning_readiness: dict[str, Any] = Field(default_factory=dict)


class StrategyGroupLiveReadOnlyObservationResponse(BaseModel):
    generated_from: str = OBSERVATION_V1_SOURCE
    candidates: list[StrategyGroupObservationCandidate]
    current_signals: list["StrategyGroupObservationRecord"] = Field(default_factory=list)
    signal_history: list["StrategyGroupObservationRecord"] = Field(default_factory=list)
    forward_review_summary: dict[str, Any] = Field(
        default_factory=lambda: {
            "sink_id": "pg_brc_strategy_group_forward_reviews",
            "review_count": 0,
            "by_observation_id": {},
            "writes_execution_or_order_tables": False,
            "runtime_effect": "none",
            "status": "not_loaded",
        }
    )
    sink_summary: dict[str, Any] = Field(default_factory=dict)
    input_source_summary: dict[str, Any] = Field(default_factory=dict)
    review_hook_summary: dict[str, Any] = Field(default_factory=dict)
    runner_mapping: dict[str, Any] = Field(default_factory=dict)
    observation_chain_summary: dict[str, Any] = Field(default_factory=dict)
    runtime_signal_planning_summary: dict[str, Any] = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(default_factory=dict)
    live_observation_active: Literal[False] = False
    live_ready: Literal[False] = False


class StrategyGroupObservationRecord(BaseModel):
    record_id: str
    candidate_id: str
    strategy_group_id: str
    strategy_family_version_id: str | None = None
    symbol: str
    side: str
    evaluated_at_ms: int
    recorded_at_ms: int | None = None
    source: str
    source_type: str = "local_sqlite_fallback"
    market_source: str
    market_bar_timestamp_ms: int
    market_bar_close: str | None = None
    signal_type: str
    confidence: str
    reason_codes: list[str] = Field(default_factory=list)
    human_summary: str
    evidence_payload: dict[str, Any] = Field(default_factory=dict)
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    invalidation_conditions: list[dict[str, Any]] = Field(default_factory=list)
    review_windows: list[str] = Field(default_factory=list)
    review_status_by_window: dict[str, str] = Field(default_factory=dict)
    input_refs: dict[str, Any] = Field(default_factory=dict)
    runtime_signal_planning_readiness: dict[str, Any] = Field(default_factory=dict)
    sink_status: str = "preview_not_recorded"
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    no_execution_permission: Literal[True] = True
    no_order_permission: Literal[True] = True
    no_runtime_start: Literal[True] = True


@dataclass(frozen=True)
class RecentCandle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    close_time_ms: int | None = None
    is_closed: bool = True


class StrategyGroupMarketBarSource(Protocol):
    """Read-only closed-candle source for one-shot observation evaluation."""

    source_id: str

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        """Return latest closed candles without exchange writes or runtime start."""


class StrategyGroupObservationSink(Protocol):
    """Observation evidence sink that cannot create orders or execution intents."""

    sink_id: str

    def record(self, record: StrategyGroupObservationRecord) -> StrategyGroupObservationRecord:
        """Persist or buffer observe-only record metadata."""

    def list_recent(self, *, limit: int = 50) -> list[StrategyGroupObservationRecord]:
        """Return recent observe-only records."""


class InMemoryStrategyGroupObservationSink:
    """Process-local observation sink for tests and safe console previews.

    This is intentionally not a runtime source of truth. It gives the Owner
    Console a harmless current/history shape while the PG observation schema is
    still not present.
    """

    sink_id = "process_local_in_memory_strategy_group_observation_sink"

    def __init__(self, *, max_records: int = 200) -> None:
        self._max_records = max_records
        self._records: list[StrategyGroupObservationRecord] = []

    def record(self, record: StrategyGroupObservationRecord) -> StrategyGroupObservationRecord:
        recorded = record.model_copy(update={"recorded_at_ms": now_ms(), "sink_status": "recorded_process_local"})
        self._records = [item for item in self._records if item.record_id != recorded.record_id]
        self._records.append(recorded)
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records :]
        return recorded

    def list_recent(self, *, limit: int = 50) -> list[StrategyGroupObservationRecord]:
        return list(reversed(self._records[-limit:]))


class SampleStrategyGroupMarketBarSource:
    """Deterministic read-only source used when no local market source is bound."""

    source_id = "sample_closed_candle_source_display_model_only"

    def latest_closed_candles(self, *, symbol: str, timeframe: str, limit: int) -> list[RecentCandle]:
        if symbol == "ETH/USDT:USDT" and timeframe == "4h":
            raw = _sample_cpm_candles_4h()
        elif symbol == "ETH/USDT:USDT":
            raw = _sample_cpm_candles_1h()
        else:
            raw = _sample_mi_candles()
        candles = [_parse_candle(item) for item in raw]
        return candles[-limit:]


_DEFAULT_OBSERVATION_SINK = InMemoryStrategyGroupObservationSink()


class MI001MomentumImpulseReadOnlyEvaluator:
    """Pure MI-001 live-observation evaluator over closed candle context."""

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> StrategyFamilySignalOutput:
        if signal_input.strategy_family_id != MI001_FAMILY_ID:
            return _invalid_output(
                signal_input,
                reason_codes=["mi001_invalid_wrong_family"],
                human_summary="Input is not for MI-001.",
                evidence_payload={},
            )

        candles = _candles_from_input(signal_input)
        if len(candles) <= MI_LOOKBACK_BARS:
            return _invalid_output(
                signal_input,
                reason_codes=["mi001_invalid_insufficient_candles"],
                human_summary="MI-001 requires at least 13 closed 1h candles for the 12h close-to-close impulse.",
                evidence_payload={"candle_count": len(candles), "min_needed": MI_LOOKBACK_BARS + 1},
            )

        current = candles[-1]
        lookback = candles[-(MI_LOOKBACK_BARS + 1)]
        impulse_return_pct = ((current.close - lookback.close) / lookback.close) * Decimal("100")
        evidence = {
            "logic_version": "mi001-readonly-observation-v1",
            "lookback_bars": MI_LOOKBACK_BARS,
            "return_threshold_pct": str(MI_RETURN_THRESHOLD),
            "lookback_close": str(lookback.close),
            "latest_close": str(current.close),
            "impulse_return_pct": str(impulse_return_pct.quantize(Decimal("0.0001"))),
            "closed_candle_count": len(candles),
        }
        if impulse_return_pct >= MI_RETURN_THRESHOLD:
            return StrategyFamilySignalOutput(
                signal_id=f"mi001-{_stable_suffix(signal_input.evaluation_id)}",
                evaluation_id=signal_input.evaluation_id,
                strategy_family_id=MI001_FAMILY_ID,
                strategy_family_version_id=signal_input.strategy_family_version_id,
                playbook_id=signal_input.playbook_id,
                symbol=signal_input.symbol,
                timestamp_ms=signal_input.timestamp_ms,
                timeframe=signal_input.primary_timeframe,
                signal_type=SignalType.WOULD_ENTER,
                side=SignalSide.LONG,
                confidence=Decimal("0.65"),
                reason_codes=["mi001_12h_momentum_impulse", "observe_only_review_required"],
                human_summary="MI-001 would-enter long observation: 12h close-to-close momentum impulse crossed threshold.",
                required_execution_mode="observe_only",
                expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
                invalidation_conditions=[
                    {"condition_type": "momentum_exhaustion", "description": "Fast reversal after impulse."},
                    {"condition_type": "adverse_path", "description": "High MAE remains an Owner review risk."},
                ],
                signal_snapshot={
                    "strategy_family": MI001_FAMILY_ID,
                    "logic_version": "mi001-readonly-observation-v1",
                    "context_tags": {"impulse": "threshold_crossed", "side": "long"},
                },
                evidence_payload=evidence,
                input_refs=_input_refs(signal_input),
                data_quality=signal_input.input_quality,
                review_plan=SignalReviewPlan(
                    review_required=True,
                    review_windows=["24h", "72h", "7d"],
                    forward_outcome_metrics=["MFE", "MAE", "follow_through", "return_time_curve"],
                    owner_review_status="pending",
                ),
            )

        return StrategyFamilySignalOutput(
            signal_id=f"mi001-{_stable_suffix(signal_input.evaluation_id)}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=MI001_FAMILY_ID,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            playbook_id=signal_input.playbook_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=SignalType.NO_ACTION,
            side=SignalSide.NONE,
            confidence=Decimal("0.20"),
            reason_codes=["mi001_no_action_impulse_below_threshold"],
            human_summary="MI-001 no-action observation: 12h close-to-close impulse is below threshold.",
            required_execution_mode="observe_only",
            expected_risk_shape=ExpectedRiskShape.TREND_FOLLOWING_WIDE_STOP,
            signal_snapshot={
                "strategy_family": MI001_FAMILY_ID,
                "logic_version": "mi001-readonly-observation-v1",
                "context_tags": {"impulse": "below_threshold"},
            },
            evidence_payload=evidence,
            input_refs=_input_refs(signal_input),
            data_quality=signal_input.input_quality,
            review_plan=SignalReviewPlan(review_required=False, review_windows=["24h", "72h", "7d"]),
        )


class CPMRO001LiveReadOnlyEvaluator:
    """Read-only CPM wrapper over the existing pure CPM signal evaluator."""

    def __init__(self) -> None:
        self._delegate = CPMRO001HistoricalEvaluator()

    def evaluate(self, signal_input: StrategyFamilySignalInput) -> StrategyFamilySignalOutput:
        return self._delegate.evaluate(signal_input)


@dataclass(frozen=True)
class _ObservationSpec:
    candidate_id: str
    strategy_group_id: str
    strategy_family_version_id: str
    playbook_id: str
    symbol: str
    side: SignalSide
    side_label: str
    observation_role: str
    review_windows: list[str]
    evidence_payload_fields: list[str]
    source_refs: list[str]
    candidate_blockers: list[str]
    evaluator: Any


def _observation_specs() -> list[_ObservationSpec]:
    mi_evaluator = MI001MomentumImpulseReadOnlyEvaluator()
    return [
        _ObservationSpec(
            candidate_id="MI-001-SOL-LONG",
            strategy_group_id=MI001_FAMILY_ID,
            strategy_family_version_id=MI001_VERSION_ID,
            playbook_id="MI-001-SOL-LONG-BT-001",
            symbol="SOL/USDT:USDT",
            side=SignalSide.LONG,
            side_label="long",
            observation_role="primary_chain_sample",
            review_windows=["24h", "72h", "7d"],
            evidence_payload_fields=[
                "lookback_bars",
                "return_threshold_pct",
                "lookback_close",
                "latest_close",
                "impulse_return_pct",
            ],
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md",
            ],
            candidate_blockers=["scheduled live read-only observation not started", "PG observation sink schema gap"],
            evaluator=mi_evaluator,
        ),
        _ObservationSpec(
            candidate_id="MI-001-BNB-LONG",
            strategy_group_id=MI001_FAMILY_ID,
            strategy_family_version_id=MI001_VERSION_ID,
            playbook_id="MI-001-BNB-LONG-OBS-001",
            symbol="BNB/USDT:USDT",
            side=SignalSide.LONG,
            side_label="long",
            observation_role="strong_repaired_coverage_observation_candidate",
            review_windows=["24h", "72h", "7d"],
            evidence_payload_fields=[
                "lookback_bars",
                "return_threshold_pct",
                "lookback_close",
                "latest_close",
                "impulse_return_pct",
            ],
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md",
            ],
            candidate_blockers=[
                "scheduled live read-only observation not started",
                "PG observation sink schema gap",
                "Owner review of repaired BNB evidence remains pending",
            ],
            evaluator=mi_evaluator,
        ),
        _ObservationSpec(
            candidate_id="CPM-RO-001",
            strategy_group_id=CPM_FAMILY_ID,
            strategy_family_version_id=CPM_VERSION_ID,
            playbook_id="CPM-RO-001",
            symbol="ETH/USDT:USDT",
            side=SignalSide.NONE,
            side_label="long_or_short_observation",
            observation_role="owner_special_observation",
            review_windows=["4h", "24h", "72h", "7d"],
            evidence_payload_fields=[
                "htf_trend",
                "primary_trend",
                "pullback_depth_pct",
                "entry_pattern",
                "long_reclaim_confirmed",
                "short_loss_confirmed",
            ],
            source_refs=[
                "src/domain/cpm_historical_evaluator.py",
                "docs/ops/crypto-pullback-module-v1-oos-failure-classification.md",
            ],
            candidate_blockers=[
                "scheduled live read-only observation not started",
                "PG observation sink schema gap",
                "CPM remains not proven alpha and not runtime eligible by default",
            ],
            evaluator=CPMRO001LiveReadOnlyEvaluator(),
        ),
    ]


def _evaluate_observation_candidate(
    spec: _ObservationSpec,
    market_source: StrategyGroupMarketBarSource,
    runtime_signal_planning_assembly: RuntimeStrategySignalSchedulerAssemblyService,
) -> tuple[StrategyGroupObservationRecord | None, StrategyGroupObservationCandidate, list[str]]:
    blockers: list[str] = []
    runtime_signal_planning_readiness: dict[str, Any] = {}
    try:
        one_hour = market_source.latest_closed_candles(
            symbol=spec.symbol,
            timeframe="1h",
            limit=96 if spec.strategy_group_id == CPM_FAMILY_ID else 30,
        )
        four_hour = (
            market_source.latest_closed_candles(symbol=spec.symbol, timeframe="4h", limit=40)
            if spec.strategy_group_id == CPM_FAMILY_ID
            else []
        )
        if spec.strategy_group_id == CPM_FAMILY_ID and not four_hour:
            blockers.append("missing_4h_candle_context")
        if not one_hour:
            blockers.append("missing_1h_candle_context")
            raise ValueError("market source returned no 1h closed candles")

        timestamp_ms = one_hour[-1].open_time_ms
        signal_input = _sample_signal_input(
            family_id=spec.strategy_group_id,
            version_id=spec.strategy_family_version_id,
            playbook_id=spec.playbook_id,
            symbol=spec.symbol,
            side=spec.side,
            market_snapshot=_market_snapshot(
                symbol=spec.symbol,
                candles=_raw_candles_from_recent(one_hour),
                four_hour_candles=_raw_candles_from_recent(four_hour) if four_hour else None,
                timestamp_ms=timestamp_ms,
                source=getattr(market_source, "source_id", "read_only_market_bar_source"),
                freshness="latest_available_closed_bar",
            ),
            input_source=getattr(market_source, "source_id", "read_only_market_bar_source"),
            freshness="latest_available_closed_bar",
        )
        output = spec.evaluator.evaluate(signal_input)
        runtime_signal_planning_readiness = runtime_signal_planning_assembly.preview(
            signal_input,
            output,
            candidate_id=spec.candidate_id,
        ).model_dump(mode="json")
        record = _observation_record_from_output(
            spec,
            output,
            getattr(market_source, "source_id", "unknown"),
            getattr(market_source, "source_type", None),
            runtime_signal_planning_readiness=runtime_signal_planning_readiness,
        )
        preview = _signal_preview(output)
    except Exception as exc:
        blockers.append("market_source_evaluation_failed")
        record = None
        preview = {
            "signal_type": "invalid",
            "side": "none",
            "reason_codes": ["observation_source_unavailable"],
            "human_summary": f"Observation unavailable: {type(exc).__name__}",
            "not_order": True,
            "not_execution_intent": True,
            "symbol": spec.symbol,
        }
        runtime_signal_planning_readiness = {
            "candidate_id": spec.candidate_id,
            "strategy_family_id": spec.strategy_group_id,
            "strategy_family_version_id": spec.strategy_family_version_id,
            "symbol": spec.symbol,
            "status": RuntimeStrategySignalSchedulerReadinessStatus.BLOCKED.value,
            "blockers": sorted(set(blockers)),
            "planner_call_performed": False,
            "signal_evaluation_created": False,
            "order_candidate_created": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "not_order": True,
            "not_execution_intent": True,
            "not_execution_authority": True,
        }

    readiness_status = (
        "one_shot_observation_ready_pg_sink_gap"
        if record is not None
        else "blocked_market_source_or_context_unavailable"
    )
    all_blockers = sorted(set(spec.candidate_blockers + blockers))
    candidate = StrategyGroupObservationCandidate(
        candidate_id=spec.candidate_id,
        strategy_group_id=spec.strategy_group_id,
        strategy_family_version_id=spec.strategy_family_version_id,
        symbol=spec.symbol,
        side=spec.side_label,
        observation_role=spec.observation_role,
        evaluator_glue_status="wired_read_only_v1",
        review_windows=list(spec.review_windows),
        latest_signal_preview=preview,
        evidence_payload_fields=list(spec.evidence_payload_fields),
        evidence_record_mapping="observe_only_signal_record_ready_pg_schema_gap",
        readiness_status=readiness_status,
        blockers=all_blockers,
        not_allowed_now=_not_allowed_now(),
        source_refs=list(spec.source_refs),
        runtime_signal_planning_readiness=runtime_signal_planning_readiness,
    )
    return record, candidate, blockers


def _observation_record_from_output(
    spec: _ObservationSpec,
    output: StrategyFamilySignalOutput,
    market_source_id: str,
    source_type: str | None = None,
    runtime_signal_planning_readiness: dict[str, Any] | None = None,
) -> StrategyGroupObservationRecord:
    review_status = {
        window: (
            "pending_forward_outcome_capture"
            if output.review_plan.review_required
            else "not_required_for_no_action_or_invalid"
        )
        for window in spec.review_windows
    }
    return StrategyGroupObservationRecord(
        record_id=f"{spec.candidate_id}:{output.signal_id}:{output.timestamp_ms}",
        candidate_id=spec.candidate_id,
        strategy_group_id=spec.strategy_group_id,
        strategy_family_version_id=output.strategy_family_version_id,
        symbol=output.symbol,
        side=output.side.value,
        evaluated_at_ms=output.timestamp_ms,
        source=OBSERVATION_V1_SOURCE,
        source_type=source_type
        or ("local_sqlite_fallback" if "sqlite" in market_source_id else "read_only_market_source"),
        market_source=market_source_id,
        market_bar_timestamp_ms=output.timestamp_ms,
        market_bar_close=output.evidence_payload.get("latest_close")
        or output.evidence_payload.get("latest_1h_close"),
        signal_type=output.signal_type.value,
        confidence=str(output.confidence),
        reason_codes=list(output.reason_codes),
        human_summary=output.human_summary,
        evidence_payload=output.evidence_payload,
        signal_snapshot=output.signal_snapshot,
        invalidation_conditions=list(output.invalidation_conditions),
        review_windows=list(spec.review_windows),
        review_status_by_window=review_status,
        input_refs=output.input_refs.model_dump(mode="json"),
        runtime_signal_planning_readiness=dict(runtime_signal_planning_readiness or {}),
    )


def build_strategy_group_live_readonly_observation_v1(
    *,
    market_source: StrategyGroupMarketBarSource | None = None,
    sink: StrategyGroupObservationSink | None = None,
    record_observation: bool = False,
    runtime_signal_planning_assembly: RuntimeStrategySignalSchedulerAssemblyService | None = None,
) -> StrategyGroupLiveReadOnlyObservationResponse:
    """Return current observation v1 status without starting runtime.

    When ``record_observation`` is true the function writes only observe-only
    signal records to the provided sink. It never creates execution intents,
    grants permissions, places orders, starts runtime, or calls exchange writes.
    """

    source = market_source or SampleStrategyGroupMarketBarSource()
    observation_sink = sink or _DEFAULT_OBSERVATION_SINK
    planning_assembly = (
        runtime_signal_planning_assembly
        or RuntimeStrategySignalSchedulerAssemblyService()
    )
    candidates: list[StrategyGroupObservationCandidate] = []
    current_signals: list[StrategyGroupObservationRecord] = []
    source_blockers: list[str] = []

    for spec in _observation_specs():
        record, candidate, blockers = _evaluate_observation_candidate(
            spec,
            source,
            planning_assembly,
        )
        source_blockers.extend(blockers)
        if record is not None:
            if record_observation:
                record = observation_sink.record(record)
            current_signals.append(record)
        candidates.append(candidate)

    history = observation_sink.list_recent(limit=50)
    sink_status = (
        "process_local_sink_recording_enabled"
        if record_observation
        else "process_local_sink_available_not_recorded_by_get"
    )
    if source_blockers:
        sink_status = "source_blocked_no_recording"

    source_id = getattr(source, "source_id", "unknown_market_source")
    source_type = getattr(
        source,
        "source_type",
        "local_sqlite_fallback" if "sqlite" in source_id else "read_only_market_source",
    )
    fallback_used = bool(getattr(source, "fallback_used", source_type == "local_sqlite_fallback"))
    is_live_read_only = bool(getattr(source, "is_live_read_only", source_type == "live_market_read_only"))
    latest_bar_timestamp_ms = max((record.market_bar_timestamp_ms for record in current_signals), default=None)

    return StrategyGroupLiveReadOnlyObservationResponse(
        candidates=candidates,
        current_signals=current_signals,
        signal_history=history,
        sink_summary={
            "sink_id": getattr(observation_sink, "sink_id", "unknown_observation_sink"),
            "sink_status": sink_status,
            "record_count": len(history),
            "pg_observation_sink": "blocked_schema_gap_no_live_observation_table_found",
            "writes_execution_or_order_tables": False,
            "runtime_effect": "none",
        },
        input_source_summary={
            "source_id": source_id,
            "source_type": source_type,
            "source_kind": "closed_candle_read_only",
            "freshness": getattr(source, "freshness", "latest_available_closed_bar"),
            "is_live_read_only": is_live_read_only,
            "fallback_used": fallback_used,
            "latest_market_bar_timestamp_ms": latest_bar_timestamp_ms,
            "external_exchange_write": False,
            "runtime_started": False,
            "source_blockers": sorted(set(source_blockers)),
        },
        review_hook_summary={
            "review_windows": ["24h", "72h", "7d"],
            "cpm_extra_windows": ["4h"],
            "review_hook_status": "records_include_pending_forward_outcome_windows",
            "review_calculation_status": "pending_future_outcome_capture",
            "not_runtime_source_of_truth": True,
        },
        runner_mapping={
            "existing_runner": "brc_live_read_only_detection_runner",
            "runner_source": "src/application/brc_live_read_only_detection_runner.py",
            "can_record_metadata_and_evidence_without_orders": True,
            "strategy_specific_signal_evaluator_glue_wired": True,
            "observation_sink_wiring_status": "process_local_sink_ready_pg_sink_schema_gap",
            "one_shot_observation_api_ready": True,
            "live_runner_started_by_this_endpoint": False,
            "live_observation_active": False,
        },
        observation_chain_summary={
            "MI-001": "MI evaluator glue can evaluate SOL and BNB from read-only closed candle snapshots.",
            "CPM-RO-001": "CPM evaluator glue can evaluate ETH 1h/4h read-only closed candle snapshots.",
            "active_live_readonly_observation": False,
            "current_signal_available": bool(current_signals),
            "signal_history_available": bool(history),
            "main_blocker": "scheduler_and_pg_observation_sink_not_bound",
        },
        runtime_signal_planning_summary=_runtime_signal_planning_summary(candidates),
        non_permissions={
            "no_trial_start": True,
            "no_execution_intent": True,
            "no_order_permission": True,
            "no_runtime_start": True,
            "no_automatic_strategy_routing": True,
            "no_exchange_write": True,
        },
    )


def run_strategy_group_live_readonly_observation_once(
    *,
    market_source: StrategyGroupMarketBarSource | None = None,
    sink: StrategyGroupObservationSink | None = None,
    runtime_signal_planning_assembly: RuntimeStrategySignalSchedulerAssemblyService | None = None,
) -> StrategyGroupLiveReadOnlyObservationResponse:
    """Evaluate and record one observe-only snapshot for MI/CPM candidates."""

    return build_strategy_group_live_readonly_observation_v1(
        market_source=market_source,
        sink=sink,
        record_observation=True,
        runtime_signal_planning_assembly=runtime_signal_planning_assembly,
    )


def _invalid_output(
    signal_input: StrategyFamilySignalInput,
    *,
    reason_codes: list[str],
    human_summary: str,
    evidence_payload: dict[str, Any],
) -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id=f"invalid-{_stable_suffix(signal_input.evaluation_id)}",
        evaluation_id=signal_input.evaluation_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        playbook_id=signal_input.playbook_id,
        symbol=signal_input.symbol,
        timestamp_ms=signal_input.timestamp_ms,
        timeframe=signal_input.primary_timeframe,
        signal_type=SignalType.INVALID,
        side=SignalSide.NONE,
        confidence=Decimal("0"),
        reason_codes=reason_codes,
        human_summary=human_summary,
        required_execution_mode="observe_only",
        evidence_payload=evidence_payload,
        input_refs=_input_refs(signal_input),
        data_quality=SignalDataQuality(
            status=SignalDataQualityStatus.INVALID,
            warnings=["read-only evaluator returned invalid input"],
        ),
        review_plan=SignalReviewPlan(review_required=False, owner_review_status="not_required"),
    )


def _candles_from_input(signal_input: StrategyFamilySignalInput) -> list[RecentCandle]:
    windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
    raw = list(windows.get("1h") or windows.get(signal_input.primary_timeframe) or [])
    return [_parse_candle(item) for item in raw]


def _parse_candle(raw: dict[str, Any]) -> RecentCandle:
    return RecentCandle(
        open_time_ms=int(raw["open_time_ms"]),
        open=Decimal(str(raw["open"])),
        high=Decimal(str(raw["high"])),
        low=Decimal(str(raw["low"])),
        close=Decimal(str(raw["close"])),
        volume=Decimal(str(raw.get("volume", "0"))),
    )


def _input_refs(signal_input: StrategyFamilySignalInput) -> SignalInputRefs:
    return SignalInputRefs(
        market_snapshot_ref=f"readonly_market:{signal_input.symbol}:{signal_input.timestamp_ms}",
        account_facts_snapshot_ref=f"readonly_account:{signal_input.timestamp_ms}",
        permission_resolution_ref="execution_permission:not_requested",
        trial_constraints_snapshot_ref="trial_constraints:not_applicable_observation_only",
        playbook_snapshot_ref=signal_input.playbook_id,
        runtime_safety_snapshot_ref="runtime_safety:not_started",
        evaluation_ref=signal_input.evaluation_id,
    )


def _sample_signal_input(
    *,
    family_id: str,
    version_id: str,
    playbook_id: str,
    symbol: str,
    side: SignalSide,
    market_snapshot: MarketSnapshot,
    input_source: str = "read_only_observation_preview",
    freshness: str = "sample_preview",
) -> StrategyFamilySignalInput:
    timestamp_ms = market_snapshot.timestamp_ms
    return StrategyFamilySignalInput(
        evaluation_id=f"{OBSERVATION_V1_SOURCE}:{family_id}:{symbol}:{timestamp_ms}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        playbook_id=playbook_id,
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        primary_timeframe="1h",
        context_timeframes=["4h", "24h", "72h", "7d"],
        market_snapshot=market_snapshot,
        account_facts_snapshot=AccountFactsSnapshot(
            source=input_source,
            truth_level="summary",
            timestamp_ms=timestamp_ms,
            freshness=freshness,
            account_status="not_checked",
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "not_checked"},
            read_only_provider=input_source,
            limitations=["observation signal input does not require account facts"],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "not_checked"},
        runtime_safety_snapshot={"runtime_started": False, "strategy_execution_started": False},
        execution_permission_resolution={"requested": "none", "granted": False},
        trial_constraints_snapshot={"observation_only": True, "side": side.value},
        playbook_snapshot={"playbook_id": playbook_id, "runtime_eligible": False},
        strategy_family_metadata={"family_id": family_id, "owner_review_only": True},
        source=OBSERVATION_V1_SOURCE,
        freshness=freshness,
        input_quality=SignalDataQuality(status=SignalDataQualityStatus.OK),
    )


def _market_snapshot(
    *,
    symbol: str,
    candles: list[dict[str, Any]],
    timestamp_ms: int,
    four_hour_candles: list[dict[str, Any]] | None = None,
    source: str = "read_only_observation_preview",
    freshness: str = "sample_preview",
) -> MarketSnapshot:
    latest = Decimal(str(candles[-1]["close"]))
    windows: dict[str, list[dict[str, Any]]] = {"1h": candles}
    if four_hour_candles is not None:
        windows["4h"] = four_hour_candles
    return MarketSnapshot(
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        source=source,
        freshness=freshness,
        last_price=latest,
        mark_price=latest,
        timeframe="1h",
        candle_context={"windows": windows, "closed_bar": True},
    )


def _raw_candles_from_recent(candles: list[RecentCandle]) -> list[dict[str, Any]]:
    return [
        {
            "open_time_ms": candle.open_time_ms,
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
        }
        for candle in candles
    ]


def _sample_mi_candles() -> list[dict[str, Any]]:
    base = Decimal("100")
    candles: list[dict[str, Any]] = []
    for index in range(13):
        close = base + Decimal(index) * Decimal("0.35")
        candles.append(_raw_candle(index, close))
    return candles


def _sample_cpm_candles_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(25):
        close = Decimal("100") + Decimal(index) * Decimal("0.18")
        if index > 18:
            close -= Decimal("1.2") - Decimal(index - 18) * Decimal("0.25")
        candles.append(_raw_candle(index, close))
    return candles


def _sample_cpm_candles_4h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(25):
        close = Decimal("98") + Decimal(index) * Decimal("0.3")
        candles.append(_raw_candle(index * 4, close))
    return candles


def _raw_candle(index: int, close: Decimal) -> dict[str, Any]:
    timestamp_ms = 1770000000000 + index * 60 * 60 * 1000
    return {
        "open_time_ms": timestamp_ms,
        "open": str(close - Decimal("0.1")),
        "high": str(close + Decimal("0.4")),
        "low": str(close - Decimal("0.5")),
        "close": str(close),
        "volume": "1000",
    }


def _signal_preview(output: StrategyFamilySignalOutput) -> dict[str, Any]:
    return {
        "signal_type": output.signal_type.value,
        "side": output.side.value,
        "confidence": str(output.confidence),
        "reason_codes": list(output.reason_codes),
        "human_summary": output.human_summary,
        "review_windows": list(output.review_plan.review_windows),
        "not_order": output.not_order,
        "not_execution_intent": output.not_execution_intent,
        "symbol": output.symbol,
    }


def _not_allowed_now() -> list[str]:
    return [
        "trial start",
        "execution intent creation",
        "order placement",
        "runtime start",
        "execution permission grant",
        "automatic strategy routing",
    ]


def _runtime_signal_planning_summary(
    candidates: list[StrategyGroupObservationCandidate],
) -> dict[str, Any]:
    readiness_items = [
        candidate.runtime_signal_planning_readiness
        for candidate in candidates
        if candidate.runtime_signal_planning_readiness
    ]
    statuses: dict[str, int] = {}
    blockers: set[str] = set()
    for item in readiness_items:
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        blockers.update(str(blocker) for blocker in item.get("blockers") or [])
    return {
        "source": "runtime_strategy_signal_scheduler_assembly",
        "scheduler_level_readiness": True,
        "candidate_count": len(readiness_items),
        "status_counts": statuses,
        "blockers": sorted(blockers),
        "planner_call_performed": False,
        "signal_evaluation_created": False,
        "order_candidate_created": False,
        "execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_called": False,
        "not_order": True,
        "not_execution_intent": True,
        "not_execution_authority": True,
    }


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]


def now_ms() -> int:
    return int(time.time() * 1000)
