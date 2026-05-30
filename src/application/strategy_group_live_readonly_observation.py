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
from typing import Any, Literal

from pydantic import BaseModel, Field

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


class StrategyGroupLiveReadOnlyObservationResponse(BaseModel):
    generated_from: str = OBSERVATION_V1_SOURCE
    candidates: list[StrategyGroupObservationCandidate]
    runner_mapping: dict[str, Any] = Field(default_factory=dict)
    observation_chain_summary: dict[str, Any] = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(default_factory=dict)
    live_observation_active: Literal[False] = False
    live_ready: Literal[False] = False


@dataclass(frozen=True)
class RecentCandle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")


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


def build_strategy_group_live_readonly_observation_v1() -> StrategyGroupLiveReadOnlyObservationResponse:
    """Return current observation v1 status without running observation."""

    mi_preview = MI001MomentumImpulseReadOnlyEvaluator().evaluate(
        _sample_signal_input(
            family_id=MI001_FAMILY_ID,
            version_id=MI001_VERSION_ID,
            playbook_id="MI-001-SOL-LONG-BT-001",
            symbol="SOL/USDT:USDT",
            side=SignalSide.LONG,
            market_snapshot=_market_snapshot(
                symbol="SOL/USDT:USDT",
                candles=_sample_mi_candles(),
                timestamp_ms=1770000000000,
            ),
        )
    )
    cpm_preview = CPMRO001LiveReadOnlyEvaluator().evaluate(
        _sample_signal_input(
            family_id=CPM_FAMILY_ID,
            version_id=CPM_VERSION_ID,
            playbook_id="CPM-RO-001",
            symbol="ETH/USDT:USDT",
            side=SignalSide.NONE,
            market_snapshot=_market_snapshot(
                symbol="ETH/USDT:USDT",
                candles=_sample_cpm_candles_1h(),
                four_hour_candles=_sample_cpm_candles_4h(),
                timestamp_ms=1770000000000,
            ),
        )
    )

    candidates = [
        StrategyGroupObservationCandidate(
            candidate_id="MI-001-SOL-LONG",
            strategy_group_id=MI001_FAMILY_ID,
            symbol="SOL/USDT:USDT",
            side="long",
            observation_role="primary_chain_sample",
            evaluator_glue_status="wired_read_only_v1",
            latest_signal_preview=_signal_preview(mi_preview),
            evidence_payload_fields=[
                "lookback_bars",
                "return_threshold_pct",
                "lookback_close",
                "latest_close",
                "impulse_return_pct",
            ],
            readiness_status="evaluator_ready_requires_runner_binding",
            blockers=["live observation runner is not started", "observation sink is not bound to scheduler"],
            not_allowed_now=_not_allowed_now(),
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md",
            ],
        ),
        StrategyGroupObservationCandidate(
            candidate_id="MI-001-BNB-LONG",
            strategy_group_id=MI001_FAMILY_ID,
            symbol="BNB/USDT:USDT",
            side="long",
            observation_role="strong_repaired_coverage_observation_candidate",
            evaluator_glue_status="wired_read_only_v1",
            latest_signal_preview=_signal_preview(mi_preview).copy() | {"symbol": "BNB/USDT:USDT", "candidate_note": "same MI evaluator; BNB observation not active"},
            evidence_payload_fields=[
                "lookback_bars",
                "return_threshold_pct",
                "lookback_close",
                "latest_close",
                "impulse_return_pct",
            ],
            readiness_status="evaluator_ready_requires_runner_binding",
            blockers=["live observation runner is not started", "Owner review of repaired BNB evidence remains pending"],
            not_allowed_now=_not_allowed_now(),
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md",
            ],
        ),
        StrategyGroupObservationCandidate(
            candidate_id="CPM-RO-001",
            strategy_group_id=CPM_FAMILY_ID,
            symbol="ETH/USDT:USDT",
            side="long_or_short_observation",
            observation_role="owner_special_observation",
            evaluator_glue_status="wired_read_only_v1",
            review_windows=["4h", "24h", "72h", "7d"],
            latest_signal_preview=_signal_preview(cpm_preview),
            evidence_payload_fields=[
                "htf_trend",
                "primary_trend",
                "pullback_depth_pct",
                "entry_pattern",
                "long_reclaim_confirmed",
                "short_loss_confirmed",
            ],
            readiness_status="evaluator_ready_requires_runner_binding",
            blockers=["live observation runner is not started", "CPM remains not proven alpha and not runtime eligible by default"],
            not_allowed_now=_not_allowed_now(),
            source_refs=[
                "src/domain/cpm_historical_evaluator.py",
                "docs/ops/crypto-pullback-module-v1-oos-failure-classification.md",
            ],
        ),
    ]

    return StrategyGroupLiveReadOnlyObservationResponse(
        candidates=candidates,
        runner_mapping={
            "existing_runner": "brc_live_read_only_detection_runner",
            "runner_source": "src/application/brc_live_read_only_detection_runner.py",
            "can_record_metadata_and_evidence_without_orders": True,
            "strategy_specific_signal_evaluator_glue_wired": True,
            "observation_sink_wiring_status": "metadata_mapping_ready_not_scheduled",
            "live_runner_started_by_this_endpoint": False,
            "live_observation_active": False,
        },
        observation_chain_summary={
            "MI-001": "MI evaluator glue ready for read-only candle snapshots; live observation not active.",
            "CPM-RO-001": "CPM evaluator glue ready for read-only candle snapshots; live observation not active.",
            "active_live_readonly_observation": False,
            "main_blocker": "runner_binding_and_observation_sink_scheduler_not_started",
        },
        non_permissions={
            "no_trial_start": True,
            "no_execution_intent": True,
            "no_order_permission": True,
            "no_runtime_start": True,
            "no_automatic_strategy_routing": True,
            "no_exchange_write": True,
        },
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
            source="read_only_observation_preview",
            truth_level="summary",
            timestamp_ms=timestamp_ms,
            freshness="sample_preview",
            account_status="not_checked",
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "not_checked"},
            read_only_provider=OBSERVATION_V1_SOURCE,
            limitations=["sample preview does not read account facts"],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "not_checked"},
        runtime_safety_snapshot={"runtime_started": False, "strategy_execution_started": False},
        execution_permission_resolution={"requested": "none", "granted": False},
        trial_constraints_snapshot={"observation_only": True, "side": side.value},
        playbook_snapshot={"playbook_id": playbook_id, "runtime_eligible": False},
        strategy_family_metadata={"family_id": family_id, "owner_review_only": True},
        source=OBSERVATION_V1_SOURCE,
        freshness="sample_preview",
        input_quality=SignalDataQuality(status=SignalDataQualityStatus.OK),
    )


def _market_snapshot(
    *,
    symbol: str,
    candles: list[dict[str, Any]],
    timestamp_ms: int,
    four_hour_candles: list[dict[str, Any]] | None = None,
) -> MarketSnapshot:
    latest = Decimal(str(candles[-1]["close"]))
    windows: dict[str, list[dict[str, Any]]] = {"1h": candles}
    if four_hour_candles is not None:
        windows["4h"] = four_hour_candles
    return MarketSnapshot(
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        source="read_only_observation_preview",
        freshness="sample_preview",
        last_price=latest,
        mark_price=latest,
        timeframe="1h",
        candle_context={"windows": windows, "closed_bar": True},
    )


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


def _stable_suffix(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:24]


def now_ms() -> int:
    return int(time.time() * 1000)
