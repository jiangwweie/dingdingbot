"""Manual in-memory historical replay through production evaluator semantics."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from src.application.opportunity_feedback_calibration_service import (
    EventSpecCalibrationIdentity,
    SignalEvaluationService,
    evaluate_calibration_observation,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeStrategySignalEvaluationService,
)
from src.domain.comparative_strength import (
    ComparativeStrengthError,
    ComparativeStrengthSnapshot,
    compute_comparative_strength,
)
from src.domain.opportunity_feedback_calibration import (
    OpportunityCalibrationResult,
    OpportunityEvaluation,
    OpportunityResult,
    OpportunitySource,
    calibrate_opportunity_feedback,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    StrategyFamilySignalInput,
)


HOUR_MS = 3_600_000
FIFTEEN_MINUTES_MS = 900_000
WINDOW_1H = 25
WINDOW_4H = 25


class HistoricalReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HistoricalReplayScope(HistoricalReplayModel):
    candidate_scope_id: str = Field(min_length=1, max_length=256)
    symbol: str = Field(min_length=1, max_length=128)
    exchange_symbol: str = Field(min_length=1, max_length=128)
    priority_rank: int = Field(ge=1)
    event_spec: EventSpecCalibrationIdentity


class HistoricalReplayScopeResult(HistoricalReplayModel):
    candidate_scope_id: str
    strategy_group_id: str
    event_spec_id: str
    symbol: str
    side: Literal["long", "short"]
    timeframe: str
    calibration: OpportunityCalibrationResult


class OpportunityHistoricalReplayResult(HistoricalReplayModel):
    as_of_ms: int = Field(ge=0)
    scope_count: int = Field(ge=0)
    event_spec_count: int = Field(ge=0)
    strategy_group_count: int = Field(ge=0)
    scope_results: list[HistoricalReplayScopeResult]
    pg_rows_written: Literal[0] = 0
    output_files_written: Literal[0] = 0
    runtime_authority_created: Literal[False] = False
    finalgate_called: Literal[False] = False
    operation_layer_called: Literal[False] = False
    exchange_write_called: Literal[False] = False
    order_created: Literal[False] = False
    live_profile_changed: Literal[False] = False
    order_sizing_changed: Literal[False] = False


def build_historical_replay_scopes(
    *,
    event_specs: Sequence[Mapping[str, Any]],
    candidate_scopes: Sequence[Mapping[str, Any]],
    bindings: Sequence[Mapping[str, Any]],
    event_fact_rows: Sequence[Mapping[str, Any]],
    evaluator_versions: Mapping[str, str],
) -> list[HistoricalReplayScope]:
    current_events = {
        str(row.get("event_spec_id") or ""): dict(row)
        for row in event_specs
        if str(row.get("status") or "current") == "current"
    }
    active_scopes = {
        str(row.get("candidate_scope_id") or ""): dict(row)
        for row in candidate_scopes
        if str(row.get("status") or "active") == "active"
    }
    facts_by_event: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"required": [], "disable": []}
    )
    for row in event_fact_rows:
        if str(row.get("status") or "current") != "current":
            continue
        event_spec_id = str(row.get("event_spec_id") or "")
        role = (
            "disable"
            if row.get("disable_on_match") is True
            or str(row.get("fact_role") or "") == "disable"
            else "required"
        )
        facts_by_event[event_spec_id][role].append(str(row.get("fact_key") or ""))

    scopes: list[HistoricalReplayScope] = []
    for binding in bindings:
        if str(binding.get("status") or "active") != "active":
            continue
        scope = active_scopes.get(str(binding.get("candidate_scope_id") or ""))
        event = current_events.get(str(binding.get("event_spec_id") or ""))
        if scope is None or event is None:
            continue
        group_id = str(event.get("strategy_group_id") or "")
        evaluator_version = str(evaluator_versions.get(group_id) or "")
        if not evaluator_version:
            raise ValueError(f"evaluator_version_missing:{group_id}")
        facts = facts_by_event[str(event["event_spec_id"])]
        identity_row = {
            **event,
            "required_fact_keys": sorted(set(facts["required"])),
            "disable_fact_keys": sorted(set(facts["disable"])),
        }
        scopes.append(
            HistoricalReplayScope(
                candidate_scope_id=str(scope["candidate_scope_id"]),
                symbol=_canonical_symbol(scope.get("symbol")),
                exchange_symbol=str(scope.get("exchange_symbol") or ""),
                priority_rank=int(scope.get("priority_rank") or 1),
                event_spec=EventSpecCalibrationIdentity.from_pg_event_spec(
                    identity_row,
                    evaluator_version_id=evaluator_version,
                ),
            )
        )
    return sorted(
        scopes,
        key=lambda item: (
            item.event_spec.strategy_group_id,
            item.event_spec.event_id,
            item.priority_rank,
            item.symbol,
        ),
    )


def run_opportunity_feedback_historical_replay(
    *,
    scopes: Sequence[HistoricalReplayScope],
    candles_by_symbol_timeframe: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
    as_of_ms: int,
    evaluator_service: SignalEvaluationService | None = None,
) -> OpportunityHistoricalReplayResult:
    evaluator = evaluator_service or RuntimeStrategySignalEvaluationService()
    candles = {
        (_canonical_symbol(symbol), timeframe): _normalized_candles(rows, as_of_ms=as_of_ms)
        for (symbol, timeframe), rows in candles_by_symbol_timeframe.items()
    }
    close_times = {
        key: [int(item["close_time_ms"]) for item in rows]
        for key, rows in candles.items()
    }
    universes = _comparative_universes(scopes)
    scope_results: list[HistoricalReplayScopeResult] = []
    for scope in scopes:
        observations = _scope_observations(
            scope,
            candles=candles,
            close_times=close_times,
            universes=universes,
            evaluator=evaluator,
            as_of_ms=as_of_ms,
        )
        scope_results.append(
            HistoricalReplayScopeResult(
                candidate_scope_id=scope.candidate_scope_id,
                strategy_group_id=scope.event_spec.strategy_group_id,
                event_spec_id=scope.event_spec.event_spec_id,
                symbol=scope.symbol,
                side=scope.event_spec.side,
                timeframe=scope.event_spec.timeframe,
                calibration=calibrate_opportunity_feedback(
                    observations,
                    as_of_ms=as_of_ms,
                ),
            )
        )
    return OpportunityHistoricalReplayResult(
        as_of_ms=as_of_ms,
        scope_count=len(scope_results),
        event_spec_count=len({item.event_spec_id for item in scope_results}),
        strategy_group_count=len({item.strategy_group_id for item in scope_results}),
        scope_results=scope_results,
    )


def _scope_observations(
    scope: HistoricalReplayScope,
    *,
    candles: Mapping[tuple[str, str], list[dict[str, Any]]],
    close_times: Mapping[tuple[str, str], list[int]],
    universes: Mapping[str, tuple[str, ...]],
    evaluator: SignalEvaluationService,
    as_of_ms: int,
) -> list[OpportunityEvaluation]:
    if scope.event_spec.timeframe == "15m":
        return _sor_observations(
            scope,
            candles=candles.get((scope.symbol, "15m"), []),
            evaluator=evaluator,
            as_of_ms=as_of_ms,
        )
    if scope.event_spec.timeframe != "1h":
        raise ValueError(f"unsupported_historical_timeframe:{scope.event_spec.timeframe}")
    return _one_hour_observations(
        scope,
        candles=candles,
        close_times=close_times,
        universes=universes,
        evaluator=evaluator,
        as_of_ms=as_of_ms,
    )


def _one_hour_observations(
    scope: HistoricalReplayScope,
    *,
    candles: Mapping[tuple[str, str], list[dict[str, Any]]],
    close_times: Mapping[tuple[str, str], list[int]],
    universes: Mapping[str, tuple[str, ...]],
    evaluator: SignalEvaluationService,
    as_of_ms: int,
) -> list[OpportunityEvaluation]:
    one_hour = candles.get((scope.symbol, "1h"), [])
    four_hour = candles.get((scope.symbol, "4h"), [])
    four_hour_closes = [int(item["close_time_ms"]) for item in four_hour]
    start_ms = max(0, as_of_ms - 365 * 86_400_000)
    observations: list[OpportunityEvaluation] = []
    for index, trigger in enumerate(one_hour):
        trigger_ms = int(trigger["close_time_ms"])
        if trigger_ms < start_ms or trigger_ms > as_of_ms:
            continue
        one_hour_window = one_hour[max(0, index - WINDOW_1H + 1) : index + 1]
        four_end = bisect_right(four_hour_closes, trigger_ms)
        four_hour_window = four_hour[max(0, four_end - WINDOW_4H) : four_end]
        minimum_1h, minimum_4h = _minimum_windows(
            scope.event_spec.strategy_group_id
        )
        if (
            len(one_hour_window) < minimum_1h
            or len(four_hour_window) < minimum_4h
        ):
            continue
        comparative = _comparative_snapshot(
            scope,
            candles=candles,
            close_times=close_times,
            universe=universes.get(scope.event_spec.strategy_group_id, ()),
            trigger_ms=trigger_ms,
        )
        if scope.event_spec.strategy_group_id in {"MPG-001", "MI-001"} and comparative is None:
            continue
        signal_input = _signal_input(
            scope,
            trigger_ms=trigger_ms,
            windows={"1h": one_hour_window, "4h": four_hour_window},
            comparative=comparative,
        )
        observations.append(
            evaluate_calibration_observation(
                signal_input=signal_input,
                event_spec=scope.event_spec,
                source=OpportunitySource.REPLAY,
                evaluator_service=evaluator,
            )
        )
    return observations


def _sor_observations(
    scope: HistoricalReplayScope,
    *,
    candles: Sequence[Mapping[str, Any]],
    evaluator: SignalEvaluationService,
    as_of_ms: int,
) -> list[OpportunityEvaluation]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    start_ms = max(0, as_of_ms - 365 * 86_400_000)
    for candle in candles:
        trigger_ms = int(candle["close_time_ms"])
        if trigger_ms < start_ms or trigger_ms > as_of_ms:
            continue
        day = datetime.fromtimestamp(
            int(candle["open_time_ms"]) / 1000,
            tz=timezone.utc,
        ).date().isoformat()
        by_day[day].append(dict(candle))
    observations: list[OpportunityEvaluation] = []
    for day in sorted(by_day):
        session = sorted(by_day[day], key=lambda item: int(item["open_time_ms"]))
        for index in range(4, len(session)):
            window = session[: index + 1]
            trigger_ms = int(window[-1]["close_time_ms"])
            observation = evaluate_calibration_observation(
                signal_input=_signal_input(
                    scope,
                    trigger_ms=trigger_ms,
                    windows={"15m": window},
                    comparative=None,
                ),
                event_spec=scope.event_spec,
                source=OpportunitySource.REPLAY,
                evaluator_service=evaluator,
            )
            observations.append(observation)
            # A session breakout is one opportunity per EventSpec side.  Later
            # candles may remain beyond the opening range, but they are the
            # same setup rather than fresh opportunity supply.
            if observation.result == OpportunityResult.SIGNAL:
                break
    return observations


def _signal_input(
    scope: HistoricalReplayScope,
    *,
    trigger_ms: int,
    windows: Mapping[str, Sequence[Mapping[str, Any]]],
    comparative: ComparativeStrengthSnapshot | None,
) -> StrategyFamilySignalInput:
    primary = list(windows[scope.event_spec.timeframe])
    return StrategyFamilySignalInput(
        evaluation_id=(
            f"ofc:{scope.event_spec.event_id}:{scope.symbol}:{trigger_ms}"
        ),
        strategy_family_id=scope.event_spec.strategy_group_id,
        strategy_family_version_id=scope.event_spec.evaluator_version_id,
        symbol=scope.exchange_symbol,
        timestamp_ms=trigger_ms,
        trigger_candle_close_time_ms=trigger_ms,
        primary_timeframe=scope.event_spec.timeframe,
        context_timeframes=[key for key in windows if key != scope.event_spec.timeframe],
        market_snapshot=MarketSnapshot(
            symbol=scope.exchange_symbol,
            timestamp_ms=trigger_ms,
            source="binance_usdm_public_historical_closed_candles",
            freshness="historical_replay",
            last_price=Decimal(str(primary[-1]["close"])),
            timeframe=scope.event_spec.timeframe,
            candle_context={
                "windows": {key: list(value) for key, value in windows.items()},
                "closed_bar": True,
            },
        ),
        comparative_strength_snapshot=comparative,
        account_facts_snapshot=AccountFactsSnapshot(
            source="historical_replay_no_private_facts",
            truth_level="not_loaded",
            timestamp_ms=trigger_ms,
            freshness="not_applicable",
            limitations=["historical opportunity calibration is market-facts only"],
        ),
        source="ofc_historical_replay",
        freshness="historical_replay",
        input_quality=SignalDataQuality(status=SignalDataQualityStatus.OK),
    )


def _comparative_snapshot(
    scope: HistoricalReplayScope,
    *,
    candles: Mapping[tuple[str, str], list[dict[str, Any]]],
    close_times: Mapping[tuple[str, str], list[int]],
    universe: tuple[str, ...],
    trigger_ms: int,
) -> ComparativeStrengthSnapshot | None:
    group_id = scope.event_spec.strategy_group_id
    lookback = {"MPG-001": 8, "MI-001": 12}.get(group_id)
    if lookback is None:
        return None
    aligned: dict[str, list[dict[str, Any]]] = {}
    for symbol in universe:
        rows = candles.get((symbol, "1h"), [])
        symbol_close_times = close_times.get((symbol, "1h"), [])
        end = bisect_right(symbol_close_times, trigger_ms)
        window = rows[max(0, end - lookback - 1) : end]
        if len(window) < lookback + 1:
            return None
        aligned[symbol] = window
    try:
        return compute_comparative_strength(
            strategy_group_id=group_id,
            universe_symbols=universe,
            timeframe="1h",
            lookback_bars=lookback,
            candles_by_symbol=aligned,
            observed_at_ms=trigger_ms,
            valid_until_ms=trigger_ms + HOUR_MS,
            source_ref=f"ofc:historical:comparative:{group_id}:{trigger_ms}",
        )
    except ComparativeStrengthError:
        return None


def _comparative_universes(
    scopes: Sequence[HistoricalReplayScope],
) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for scope in scopes:
        if scope.event_spec.strategy_group_id in {"MPG-001", "MI-001"}:
            grouped[scope.event_spec.strategy_group_id].add(scope.symbol)
    return {key: tuple(sorted(values)) for key, values in grouped.items()}


def _minimum_windows(strategy_group_id: str) -> tuple[int, int]:
    return {
        "CPM-RO-001": (21, 21),
        "MPG-001": (16, 4),
        "MI-001": (13, 1),
        "BRF2-001": (12, 2),
    }[strategy_group_id]


def _normalized_candles(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of_ms: int,
) -> list[dict[str, Any]]:
    by_open: dict[int, dict[str, Any]] = {}
    for row in rows:
        open_ms = int(row["open_time_ms"])
        close_ms = int(row["close_time_ms"])
        if close_ms > as_of_ms:
            continue
        by_open[open_ms] = {
            "open_time_ms": open_ms,
            "close_time_ms": close_ms,
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume": str(row.get("volume") or "0"),
        }
    return [by_open[key] for key in sorted(by_open)]


def _canonical_symbol(value: Any) -> str:
    return str(value or "").upper().replace("/", "").replace(":USDT", "")
