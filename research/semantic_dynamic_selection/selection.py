"""Build frozen Stage-3 pre-Detector Selection Snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from math import fsum, log
from pathlib import Path

import pandas as pd

from research.multi_strategy_selection.replay import (
    EVALUATION_END_MS,
    WARMUP_START_MS,
    _instrument,
    _last,
    _load,
    _symbol,
)
from research.semantic_dynamic_selection.features import (
    HOUR_MS,
    RankedMember,
    leader_occupancy_6h,
    positive_impulse_recency_12h,
    rank_feature_values,
    residual_extension_z_24h,
    signed_trend_efficiency_24h,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for

SELECTION_START_MS = WARMUP_START_MS - 4 * HOUR_MS
SELECTION_SPECS = {
    "CPM-RO-001": ("CPM_SIGNED_TREND_EFFICIENCY_V0", 4),
    "MPG-001": ("MPG_LEADER_OCCUPANCY_V0", 1),
    "MI-001": ("MI_POSITIVE_IMPULSE_RECENCY_V0", 1),
    "BRF2-001": ("BRF2_RESIDUAL_EXTENSION_V0", 4),
}


@dataclass(frozen=True, slots=True)
class SelectionArtifacts:
    snapshots: pd.DataFrame
    decisions: pd.DataFrame
    rank_history: pd.DataFrame


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _close_window(frame: pd.DataFrame, cutoff: int, count: int) -> tuple[Decimal, ...]:
    selected = frame.loc[frame["close_time"] <= cutoff].tail(count)
    expected = tuple(cutoff - (count - 1 - index) * HOUR_MS for index in range(count))
    actual = tuple(int(value) for value in selected["close_time"])
    if actual != expected:
        raise ValueError("semantic selector requires a contiguous point-in-time close window")
    closes = tuple(Decimal(str(value)) for value in selected["close"])
    if any(value <= 0 for value in closes):
        raise ValueError("semantic selector close values must be positive")
    return closes


def _simple_returns(closes: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    return tuple(
        closes[index] / closes[index - 1] - Decimal(1)
        for index in range(1, len(closes))
    )


def _log_returns(closes: tuple[Decimal, ...]) -> tuple[float, ...]:
    return tuple(log(float(closes[index] / closes[index - 1])) for index in range(1, len(closes)))


def _mpg_rank_history(
    frames: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
    close_times: tuple[int, ...],
) -> pd.DataFrame:
    contract = strategy_contract_for("event_spec:MPG-001:MPG-LONG:v3")
    rows: list[dict[str, object]] = []
    instruments = tuple(_instrument(symbol) for symbol in symbols)
    for cutoff in close_times:
        windows = tuple(
            ComparativeMemberWindow(
                exchange_instrument_id=_instrument(symbol),
                candles_1h=_last(frames[symbol], cutoff, 9),
            )
            for symbol in symbols
        )
        projection = build_comparative_universe_projection(
            event_spec_id=contract.event_spec_id,
            universe_version_id="research:stage3:comparison24:v1",
            strategy_group_id=contract.strategy_group_id,
            exchange_instrument_ids=instruments,
            closed_bar_time_ms=cutoff,
            lookback_bars=8,
            freshness_window_ms=HOUR_MS,
            member_windows=windows,
        )
        for member in projection.comparative_strength.members:
            rows.append(
                {
                    "feature_cutoff_at_ms": cutoff,
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "comparative_return_pct": str(member.return_pct),
                    "rank": member.rank,
                }
            )
    return pd.DataFrame(rows)


def _rank_rows(
    strategy: str,
    spec_id: str,
    cutoff: int,
    ranked: tuple[RankedMember, ...],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    members = [
        {
            "exchange_instrument_id": item.exchange_instrument_id,
            "feature_value": str(item.feature_value),
            "rank": item.rank,
            "member_state": item.state,
        }
        for item in ranked
    ]
    snapshot_digest = _digest(
        {
            "strategy": strategy,
            "selection_spec_id": spec_id,
            "feature_cutoff_at_ms": cutoff,
            "members": members,
        }
    )
    snapshot_id = f"stage3:{strategy}:{cutoff}"
    snapshot = {
        "selection_snapshot_id": snapshot_id,
        "strategy": strategy,
        "selection_spec_id": spec_id,
        "feature_cutoff_at_ms": cutoff,
        "effective_from_ms": cutoff + HOUR_MS,
        "candidate_count": 24,
        "selected_count": 16,
        "near_count": 4,
        "not_selected_count": 4,
        "selection_semantic_digest": snapshot_digest,
    }
    decisions = [
        {
            "selection_snapshot_id": snapshot_id,
            "strategy": strategy,
            "selection_spec_id": spec_id,
            "feature_cutoff_at_ms": cutoff,
            "effective_from_ms": cutoff + HOUR_MS,
            **member,
        }
        for member in members
    ]
    return snapshot, decisions


def build_selection_artifacts(cache_dir: Path) -> SelectionArtifacts:
    instruments = tuple(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    symbols = tuple(_symbol(item) for item in instruments)
    frames = {symbol: _load(cache_dir, symbol, "1h") for symbol in symbols}
    all_cutoffs = tuple(
        int(value)
        for value in frames[symbols[0]]["close_time"]
        if SELECTION_START_MS - 5 * HOUR_MS <= int(value) < EVALUATION_END_MS
    )
    rank_history = _mpg_rank_history(frames, symbols, all_cutoffs)
    rank_lookup = rank_history.set_index(
        ["feature_cutoff_at_ms", "exchange_instrument_id"]
    )["rank"].to_dict()
    snapshots: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for strategy, (spec_id, cadence_hours) in SELECTION_SPECS.items():
        for cutoff in all_cutoffs:
            if cutoff < SELECTION_START_MS:
                continue
            utc_hour = (cutoff // HOUR_MS) % 24
            if cadence_hours == 4 and utc_hour % 4 != 0:
                continue
            values: dict[str, Decimal] = {}
            if strategy == "BRF2-001":
                returns_by_symbol = {
                    symbol: _log_returns(_close_window(frames[symbol], cutoff, 73))
                    for symbol in symbols
                }
                market_returns = tuple(
                    fsum(returns_by_symbol[symbol][index] for symbol in symbols) / 24
                    for index in range(72)
                )
            for symbol in symbols:
                instrument_id = _instrument(symbol)
                if strategy == "CPM-RO-001":
                    value = signed_trend_efficiency_24h(
                        _close_window(frames[symbol], cutoff, 25)
                    )
                elif strategy == "MPG-001":
                    ranks = tuple(
                        int(rank_lookup[(cutoff - offset * HOUR_MS, instrument_id)])
                        for offset in range(5, -1, -1)
                    )
                    value = leader_occupancy_6h(ranks)
                elif strategy == "MI-001":
                    value = positive_impulse_recency_12h(
                        _simple_returns(_close_window(frames[symbol], cutoff, 13))
                    )
                else:
                    value = Decimal(
                        str(
                            residual_extension_z_24h(
                                returns_by_symbol[symbol],
                                market_returns,
                            )
                        )
                    )
                values[instrument_id] = value
            snapshot, member_rows = _rank_rows(
                strategy,
                spec_id,
                cutoff,
                rank_feature_values(values),
            )
            snapshots.append(snapshot)
            decisions.extend(member_rows)
    return SelectionArtifacts(
        snapshots=pd.DataFrame(snapshots),
        decisions=pd.DataFrame(decisions),
        rank_history=rank_history,
    )
