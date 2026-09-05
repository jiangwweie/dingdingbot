"""Cardinality-sensitive Dynamic Detector replay with real rank parity checks."""

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
from research.semantic_dynamic_selection_stage3_1.core import CARDINALITIES
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


def _rank_lookup(decisions: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, object]]:
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
    lookup = _rank_lookup(decisions)
    cadence = {"CPM-RO-001": 4, "BRF2-001": 4, "MPG-001": 1, "MI-001": 1}
    rows: list[dict[str, object]] = []
    for raw in baseline_events.to_dict("records"):
        event = cast(dict[str, object], raw)
        strategy = str(event["strategy"])
        trigger = int(str(event["trigger_candle_close_time_ms"]))
        cutoff = active_selection_cutoff(trigger, cadence_hours=cadence[strategy])
        decision = lookup[(strategy, cutoff, str(event["exchange_instrument_id"]))]
        rank = int(str(decision["rank"]))
        for cardinality in CARDINALITIES:
            rows.append(
                {
                    **event,
                    "cardinality": cardinality,
                    "active_selection_cutoff_ms": cutoff,
                    "selection_snapshot_id": decision["selection_snapshot_id"],
                    "selection_feature_value": decision["feature_value"],
                    "selection_rank": rank,
                    "selection_cohort": (
                        "SELECTED" if rank <= cardinality else "EXCLUDED"
                    ),
                }
            )
    return pd.DataFrame(rows)


def replay_dynamic_detectors(
    cache_dir: Path,
    decisions: pd.DataFrame,
    rank_authority: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    decision_lookup = _rank_lookup(decisions)
    authority_lookup = rank_authority.set_index(
        ["strategy", "feature_cutoff_at_ms", "exchange_instrument_id"]
    )["rank"].to_dict()
    cadence = {"CPM-RO-001": 4, "BRF2-001": 4, "MPG-001": 1, "MI-001": 1}
    close_times = tuple(
        int(value)
        for value in frames_1h[symbols[0]]["close_time"]
        if WARMUP_START_MS <= int(value) < EVALUATION_END_MS
    )
    episode_states: dict[tuple[int, str, str], ExposureEpisodeState] = {}
    events: list[dict[str, object]] = []
    evaluations: list[dict[str, object]] = []
    rank_rows: list[dict[str, object]] = []
    for cutoff in close_times:
        in_evaluation = EVALUATION_START_MS <= cutoff < EVALUATION_END_MS
        one_hour_windows = {
            symbol: _last(frames_1h[symbol], cutoff, 25) for symbol in symbols
        }
        projections = {
            group: build_comparative_universe_projection(
                event_spec_id=by_group[group].event_spec_id,
                universe_version_id="research:stage3-1:dynamic-comparison24:v1",
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
        for cardinality in CARDINALITIES:
            for contract in contracts:
                selection_cutoff = active_selection_cutoff(
                    cutoff,
                    cadence_hours=cadence[contract.strategy_group_id],
                )
                for symbol in symbols:
                    instrument_id = _instrument(symbol)
                    decision = decision_lookup[
                        (contract.strategy_group_id, selection_cutoff, instrument_id)
                    ]
                    if int(str(decision["rank"])) > cardinality:
                        continue
                    snapshot = _snapshot(
                        contract,
                        instrument_id,
                        cutoff,
                        one_hour_windows[symbol],
                        frames_4h[symbol],
                        projections,
                    )
                    if contract.strategy_group_id in {"MPG-001", "MI-001"}:
                        if snapshot.comparative_strength is None:
                            raise RuntimeError("comparative Detector snapshot is missing")
                        replay_rank = snapshot.comparative_strength.member(
                            instrument_id
                        ).rank
                        authority_rank = int(
                            authority_lookup[
                                (contract.strategy_group_id, cutoff, instrument_id)
                            ]
                        )
                        if in_evaluation:
                            rank_rows.append(
                                {
                                    "strategy": contract.strategy_group_id,
                                    "cardinality": cardinality,
                                    "trigger_candle_close_time_ms": cutoff,
                                    "exchange_instrument_id": instrument_id,
                                    "replay_rank": replay_rank,
                                    "authority_rank": authority_rank,
                                    "rank_match": replay_rank == authority_rank,
                                }
                            )
                    result = evaluate_strategy_snapshot(contract, snapshot)
                    if result.status is DetectorStatus.INVALID:
                        if in_evaluation:
                            evaluations.append(
                                {
                                    "strategy": contract.strategy_group_id,
                                    "cardinality": cardinality,
                                    "trigger_candle_close_time_ms": cutoff,
                                    "exchange_instrument_id": instrument_id,
                                    "detector_status": result.status.value,
                                    "created_replay_event": False,
                                }
                            )
                        continue
                    key = (cardinality, contract.event_spec_id, symbol)
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
                        evaluations.append(
                            {
                                "strategy": contract.strategy_group_id,
                                "cardinality": cardinality,
                                "trigger_candle_close_time_ms": cutoff,
                                "exchange_instrument_id": instrument_id,
                                "detector_status": result.status.value,
                                "created_replay_event": transition.created_new_episode,
                            }
                        )
                    if not in_evaluation or not transition.created_new_episode:
                        continue
                    stop_fact = next(
                        fact
                        for fact in result.facts
                        if fact.role == "protection_reference"
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
                            "cardinality": cardinality,
                            "trigger_candle_close_time_ms": cutoff,
                            "signal_anchor_price": str(anchor),
                            "signal_stop_reference": str(stop),
                            "signal_risk_per_unit": str(risk),
                            "signal_tp1_price": str(
                                anchor + risk
                                if contract.position_side == "long"
                                else anchor - risk
                            ),
                            "detector_fact_digest": build_signal_fact_digest(
                                result.facts
                            ),
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
                            "selection_snapshot_id": decision[
                                "selection_snapshot_id"
                            ],
                            "selection_feature_value": decision["feature_value"],
                            "selection_rank": decision["rank"],
                        }
                    )
    return pd.DataFrame(events), pd.DataFrame(evaluations), pd.DataFrame(rank_rows)
