"""Exact current-dev Detector replay using Protocol V2 Signal-R geometry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast

import pandas as pd

from research.multi_strategy_selection.context_features import (
    HourlyClose,
    compute_market_context,
    directional_efficiency_24h,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    ComparativeUniverseProjection,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    ExposureEpisodeState,
    advance_exposure_episode,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.signal import build_signal_fact_digest
from src.trading_kernel.domain.strategy_registry import (
    RegisteredStrategyContract,
    registered_strategy_contracts,
)

EVALUATION_START_MS = 1_785_456_000_000
EVALUATION_END_MS = 1_788_134_400_000
DISCOVERY_END_MS = 1_786_838_400_000
WARMUP_START_MS = 1_781_481_600_000
TARGET_GROUPS = ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001")


@dataclass(frozen=True, slots=True)
class ReplayCounters:
    candidate_hour_count: int
    valid_detector_evaluation_count: int
    invalid_detector_evaluation_count: int
    raw_triggered_count: int
    replay_event_count: int
    invalid_reasons: dict[str, int]


def _instrument(symbol: str) -> str:
    return f"binance-usdm:{symbol}:perpetual"


def _symbol(instrument_id: str) -> str:
    return instrument_id.split(":", 2)[1]


def _load(cache_dir: Path, symbol: str, interval: str) -> pd.DataFrame:
    frame = pd.read_parquet(cache_dir / "normalized" / f"{symbol}_{interval}.parquet")
    return frame.sort_values("close_time").reset_index(drop=True)


def _closed(row: pd.Series) -> ClosedCandle:
    return ClosedCandle(
        open_time_ms=int(row["open_time"]),
        close_time_ms=int(row["close_time"]),
        open=Decimal(str(row["open"])),
        high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])),
        close=Decimal(str(row["close"])),
        volume=Decimal(str(row["volume"])),
    )


def _last(frame: pd.DataFrame, cutoff: int, limit: int) -> tuple[ClosedCandle, ...]:
    selected = frame.loc[frame["close_time"] <= cutoff].tail(limit)
    return tuple(_closed(row) for _, row in selected.iterrows())


def _semantic_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def build_context_datasets(cache_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = tuple(_symbol(item) for item in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    frames = {symbol: _load(cache_dir, symbol, "1h") for symbol in symbols}
    close_times = tuple(
        int(value)
        for value in frames[symbols[0]]["close_time"]
        if EVALUATION_START_MS <= int(value) < EVALUATION_END_MS
    )
    market_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    for cutoff in close_times:
        histories: dict[str, tuple[HourlyClose, ...]] = {}
        for symbol in symbols:
            selected = frames[symbol].loc[frames[symbol]["close_time"] <= cutoff].tail(25)
            histories[symbol] = tuple(
                HourlyClose(symbol=symbol, close_time_ms=int(row["close_time"]), close=Decimal(str(row["close"])))
                for _, row in selected.iterrows()
            )
        context = compute_market_context(histories, cutoff_ms=cutoff)
        row = asdict(context)
        row["semantic_digest"] = _semantic_digest(row)
        market_rows.append(row)
        for symbol in symbols:
            candidate_rows.append(
                {
                    "feature_cutoff_at_ms": cutoff,
                    "symbol": symbol,
                    "directional_efficiency_24h": str(directional_efficiency_24h(histories[symbol], cutoff_ms=cutoff)),
                }
            )
    return pd.DataFrame(market_rows), pd.DataFrame(candidate_rows)


def replay_detectors(
    cache_dir: Path,
    market_context: pd.DataFrame,
    candidate_context: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, ReplayCounters]:
    symbols = tuple(_symbol(item) for item in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    frames_1h = {symbol: _load(cache_dir, symbol, "1h") for symbol in symbols}
    frames_4h = {symbol: _load(cache_dir, symbol, "4h") for symbol in symbols}
    contracts = tuple(item for item in registered_strategy_contracts() if item.strategy_group_id in TARGET_GROUPS)
    by_group = {item.strategy_group_id: item for item in contracts}
    context_by_time = market_context.set_index("feature_cutoff_at_ms").to_dict("index")
    efficiency = candidate_context.set_index(["feature_cutoff_at_ms", "symbol"])["directional_efficiency_24h"].to_dict()
    close_times = tuple(
        int(value)
        for value in frames_1h[symbols[0]]["close_time"]
        if WARMUP_START_MS <= int(value) < EVALUATION_END_MS
    )
    episode_states: dict[tuple[str, str], ExposureEpisodeState] = {}
    events: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []
    invalid_reasons: dict[str, int] = {}
    valid = invalid = raw_triggered = 0
    for cutoff in close_times:
        in_evaluation = EVALUATION_START_MS <= cutoff < EVALUATION_END_MS
        one_hour_windows = {
            symbol: _last(frames_1h[symbol], cutoff, 25) for symbol in symbols
        }
        projections = {
            group: build_comparative_universe_projection(
                event_spec_id=by_group[group].event_spec_id,
                universe_version_id="research:fixed-24:v1",
                strategy_group_id=group,
                exchange_instrument_ids=tuple(_instrument(symbol) for symbol in symbols),
                closed_bar_time_ms=cutoff,
                lookback_bars=8 if group == "MPG-001" else 12,
                freshness_window_ms=3_600_000,
                member_windows=tuple(
                    ComparativeMemberWindow(exchange_instrument_id=_instrument(symbol), candles_1h=one_hour_windows[symbol])
                    for symbol in symbols
                ),
            )
            for group in ("MPG-001", "MI-001")
        }
        for contract in contracts:
            for symbol in symbols:
                instrument_id = _instrument(symbol)
                snapshot = _snapshot(contract, instrument_id, cutoff, one_hour_windows[symbol], frames_4h[symbol], projections)
                result = evaluate_strategy_snapshot(contract, snapshot)
                if result.status is DetectorStatus.INVALID:
                    if in_evaluation:
                        invalid += 1
                        invalid_reasons[result.reason_code] = invalid_reasons.get(result.reason_code, 0) + 1
                        evaluations.append(
                            {
                                "strategy": contract.strategy_group_id,
                                "event_spec_id": contract.event_spec_id,
                                "symbol": symbol,
                                "exchange_instrument_id": instrument_id,
                                "trigger_candle_close_time_ms": cutoff,
                                "detector_status": result.status.value,
                                "detector_reason": result.reason_code,
                                "created_replay_event": False,
                            }
                        )
                    continue
                if in_evaluation:
                    valid += 1
                key = (contract.event_spec_id, symbol)
                transition = advance_exposure_episode(
                    contract=contract,
                    current=episode_states.get(key),
                    detector_status=result.status,
                    occurred_at_ms=result.occurred_at_ms,
                    observed_at_ms=cutoff,
                    exchange_instrument_id=instrument_id,
                )
                episode_states[key] = transition.current
                if in_evaluation and result.status is DetectorStatus.TRIGGERED:
                    raw_triggered += 1
                if in_evaluation:
                    evaluations.append(
                        {
                            "strategy": contract.strategy_group_id,
                            "event_spec_id": contract.event_spec_id,
                            "symbol": symbol,
                            "exchange_instrument_id": instrument_id,
                            "trigger_candle_close_time_ms": cutoff,
                            "detector_status": result.status.value,
                            "detector_reason": result.reason_code,
                            "created_replay_event": transition.created_new_episode,
                        }
                    )
                if not in_evaluation:
                    continue
                if not transition.created_new_episode:
                    continue
                stop_fact = next(item for item in result.facts if item.role == "protection_reference")
                anchor = one_hour_windows[symbol][-1].close
                stop = Decimal(str(stop_fact.value))
                risk = anchor - stop if contract.position_side == "long" else stop - anchor
                row: dict[str, object] = {
                    "strategy": contract.strategy_group_id,
                    "strategy_version": contract.strategy_version_id,
                    "event_spec_id": contract.event_spec_id,
                    "symbol": symbol,
                    "exchange_instrument_id": instrument_id,
                    "direction": contract.position_side,
                    "trigger_candle_close_time_ms": cutoff,
                    "signal_anchor_price": str(anchor),
                    "signal_stop_reference": str(stop),
                    "signal_risk_per_unit": str(risk),
                    "signal_tp1_price": str(anchor + risk if contract.position_side == "long" else anchor - risk),
                    "detector_fact_digest": build_signal_fact_digest(result.facts),
                    "detector_fact_semantic_digest": _semantic_digest(
                        [
                            {
                                "fact_definition_id": fact.fact_definition_id,
                                "role": fact.role,
                                "value": fact.value,
                                "satisfied": fact.satisfied,
                            }
                            for fact in result.facts
                        ]
                    ),
                    "detector_facts_json": json.dumps(
                        [
                            {
                                "fact_definition_id": fact.fact_definition_id,
                                "role": fact.role,
                                "value": fact.value,
                                "satisfied": fact.satisfied,
                            }
                            for fact in result.facts
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "detector_reason": result.reason_code,
                    "event_geometry_status": "VALID" if risk > 0 else "INVALID_SIGNAL_GEOMETRY",
                    **cast(dict[str, object], context_by_time[cutoff]),
                    "directional_efficiency_24h": efficiency[(cutoff, symbol)] if contract.strategy_group_id == "CPM-RO-001" else None,
                }
                events.append(row)
    evaluation_hour_count = len(context_by_time)
    return pd.DataFrame(events), pd.DataFrame(evaluations), ReplayCounters(
        candidate_hour_count=evaluation_hour_count * len(symbols),
        valid_detector_evaluation_count=valid,
        invalid_detector_evaluation_count=invalid,
        raw_triggered_count=raw_triggered,
        replay_event_count=len(events),
        invalid_reasons=invalid_reasons,
    )


def _snapshot(
    contract: RegisteredStrategyContract,
    instrument_id: str,
    cutoff: int,
    one_hour: tuple[ClosedCandle, ...],
    frame_4h: pd.DataFrame,
    projections: dict[str, ComparativeUniverseProjection],
) -> MarketSnapshot:
    if contract.strategy_group_id in {"MPG-001", "MI-001"}:
        projection = projections[contract.strategy_group_id]
        return MarketSnapshot(
            exchange_instrument_id=instrument_id,
            trigger_candle_close_time_ms=cutoff,
            candles_1h=projection.candles_for(instrument_id),
            candles_4h=_last(frame_4h, cutoff, 25) if contract.strategy_group_id == "MPG-001" else (),
            comparative_strength=projection.comparative_strength,
        )
    return MarketSnapshot(
        exchange_instrument_id=instrument_id,
        trigger_candle_close_time_ms=cutoff,
        candles_1h=one_hour,
        candles_4h=_last(frame_4h, cutoff, 25),
    )
