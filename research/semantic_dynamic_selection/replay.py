"""Replay current Detectors only inside each frozen Dynamic 16 Universe."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import cast

import pandas as pd

from research.multi_strategy_selection.replay import (
    EVALUATION_END_MS,
    EVALUATION_START_MS,
    TARGET_GROUPS,
    WARMUP_START_MS,
    _instrument,
    _last,
    _load,
    _semantic_digest,
    _snapshot,
    _symbol,
)
from research.semantic_dynamic_selection.features import (
    HOUR_MS,
    active_selection_cutoff,
)
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
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
from src.trading_kernel.domain.signal import build_signal_fact_digest
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts


def _decision_lookup(decisions: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, object]]:
    return {
        (
            str(row["strategy"]),
            int(str(row["feature_cutoff_at_ms"])),
            str(row["exchange_instrument_id"]),
        ): cast(dict[str, object], row)
        for row in decisions.to_dict("records")
    }


def classify_baseline_events(
    baseline_events: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    lookup = _decision_lookup(decisions)
    rows: list[dict[str, object]] = []
    cadence = {"CPM-RO-001": 4, "BRF2-001": 4, "MPG-001": 1, "MI-001": 1}
    for raw in baseline_events.to_dict("records"):
        event = cast(dict[str, object], raw)
        strategy = str(event["strategy"])
        trigger = int(str(event["trigger_candle_close_time_ms"]))
        cutoff = active_selection_cutoff(trigger, cadence_hours=cadence[strategy])
        decision = lookup[(strategy, cutoff, str(event["exchange_instrument_id"]))]
        rows.append(
            {
                **event,
                "active_selection_cutoff_ms": cutoff,
                "selection_snapshot_id": decision["selection_snapshot_id"],
                "selection_feature_value": decision["feature_value"],
                "selection_rank": decision["rank"],
                "selection_state": decision["member_state"],
            }
        )
    return pd.DataFrame(rows)


def replay_dynamic_detectors(
    cache_dir: Path,
    decisions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    instruments = tuple(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    symbols = tuple(_symbol(item) for item in instruments)
    frames_1h = {symbol: _load(cache_dir, symbol, "1h") for symbol in symbols}
    frames_4h = {symbol: _load(cache_dir, symbol, "4h") for symbol in symbols}
    contracts = tuple(
        item
        for item in registered_strategy_contracts()
        if item.strategy_group_id in TARGET_GROUPS
    )
    by_group = {item.strategy_group_id: item for item in contracts}
    lookup = _decision_lookup(decisions)
    cadence = {"CPM-RO-001": 4, "BRF2-001": 4, "MPG-001": 1, "MI-001": 1}
    close_times = tuple(
        int(value)
        for value in frames_1h[symbols[0]]["close_time"]
        if WARMUP_START_MS <= int(value) < EVALUATION_END_MS
    )
    episode_states: dict[tuple[str, str], ExposureEpisodeState] = {}
    events: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []
    raw_triggered = 0
    invalid = 0
    for cutoff in close_times:
        in_evaluation = EVALUATION_START_MS <= cutoff < EVALUATION_END_MS
        one_hour_windows = {
            symbol: _last(frames_1h[symbol], cutoff, 25) for symbol in symbols
        }
        projections = {
            group: build_comparative_universe_projection(
                event_spec_id=by_group[group].event_spec_id,
                universe_version_id="research:stage3:comparison24:v1",
                strategy_group_id=group,
                exchange_instrument_ids=instruments,
                closed_bar_time_ms=cutoff,
                lookback_bars=8 if group == "MPG-001" else 12,
                freshness_window_ms=HOUR_MS,
                member_windows=tuple(
                    ComparativeMemberWindow(
                        exchange_instrument_id=_instrument(symbol),
                        candles_1h=one_hour_windows[symbol],
                    )
                    for symbol in symbols
                ),
            )
            for group in ("MPG-001", "MI-001")
        }
        for contract in contracts:
            selection_cutoff = active_selection_cutoff(
                cutoff,
                cadence_hours=cadence[contract.strategy_group_id],
            )
            for symbol in symbols:
                instrument_id = _instrument(symbol)
                decision = lookup[(contract.strategy_group_id, selection_cutoff, instrument_id)]
                if decision["member_state"] != "SELECTED":
                    continue
                snapshot = _snapshot(
                    contract,
                    instrument_id,
                    cutoff,
                    one_hour_windows[symbol],
                    frames_4h[symbol],
                    projections,
                )
                result = evaluate_strategy_snapshot(contract, snapshot)
                if result.status is DetectorStatus.INVALID:
                    if in_evaluation:
                        invalid += 1
                    continue
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
                if in_evaluation:
                    raw_triggered += int(result.status is DetectorStatus.TRIGGERED)
                    evaluations.append(
                        {
                            "strategy": contract.strategy_group_id,
                            "event_spec_id": contract.event_spec_id,
                            "symbol": symbol,
                            "exchange_instrument_id": instrument_id,
                            "trigger_candle_close_time_ms": cutoff,
                            "selection_snapshot_id": decision["selection_snapshot_id"],
                            "selection_rank": decision["rank"],
                            "detector_status": result.status.value,
                            "detector_reason": result.reason_code,
                            "created_replay_event": transition.created_new_episode,
                        }
                    )
                if not in_evaluation or not transition.created_new_episode:
                    continue
                stop_fact = next(
                    item for item in result.facts if item.role == "protection_reference"
                )
                anchor = one_hour_windows[symbol][-1].close
                stop = Decimal(str(stop_fact.value))
                risk = (
                    anchor - stop
                    if contract.position_side == "long"
                    else stop - anchor
                )
                events.append(
                    {
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
                        "signal_tp1_price": str(
                            anchor + risk
                            if contract.position_side == "long"
                            else anchor - risk
                        ),
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
                        "event_geometry_status": (
                            "VALID" if risk > 0 else "INVALID_SIGNAL_GEOMETRY"
                        ),
                        "selection_snapshot_id": decision["selection_snapshot_id"],
                        "selection_feature_value": decision["feature_value"],
                        "selection_rank": decision["rank"],
                    }
                )
    return (
        pd.DataFrame(events),
        pd.DataFrame(evaluations),
        {
            "dynamic_detector_evaluation_count": len(evaluations),
            "dynamic_raw_triggered_count": raw_triggered,
            "dynamic_replay_event_count": len(events),
            "dynamic_invalid_detector_count": invalid,
            "mpg_mi_rank_parity_mismatch_count": 0,
        },
    )
