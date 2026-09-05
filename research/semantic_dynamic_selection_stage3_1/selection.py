"""Build Stage-3.1 revised feature ranks without outcome access."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from math import fsum
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
    positive_impulse_recency_12h,
    rank_feature_values,
    residual_extension_z_24h,
)
from research.semantic_dynamic_selection.selection import (
    _close_window,
    _log_returns,
    _simple_returns,
)
from research.semantic_dynamic_selection_stage3_1.core import (
    absolute_directional_efficiency_24h,
    persistent_leadership_score_6h,
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
    "CPM-RO-001": ("CPM_ABSOLUTE_DIRECTIONAL_EFFICIENCY_V1", 4),
    "MPG-001": ("MPG_PERSISTENT_LEADERSHIP_SCORE_V1", 1),
    "MI-001": ("MI_POSITIVE_IMPULSE_RECENCY_V0", 1),
    "BRF2-001": ("BRF2_RESIDUAL_EXTENSION_V0", 4),
}


@dataclass(frozen=True, slots=True)
class SelectionArtifacts:
    snapshots: pd.DataFrame
    decisions: pd.DataFrame
    rank_authority: pd.DataFrame


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _comparative_rank_authority(
    frames: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
    close_times: tuple[int, ...],
) -> pd.DataFrame:
    instruments = tuple(_instrument(symbol) for symbol in symbols)
    rows: list[dict[str, object]] = []
    for strategy, lookback in (("MPG-001", 8), ("MI-001", 12)):
        event_spec_id = (
            "event_spec:MPG-001:MPG-LONG:v3"
            if strategy == "MPG-001"
            else "event_spec:MI-001:MI-LONG:v3"
        )
        contract = strategy_contract_for(event_spec_id)
        for cutoff in close_times:
            projection = build_comparative_universe_projection(
                event_spec_id=contract.event_spec_id,
                universe_version_id="research:stage3-1:comparison24:v1",
                strategy_group_id=strategy,
                exchange_instrument_ids=instruments,
                closed_bar_time_ms=cutoff,
                lookback_bars=lookback,
                freshness_window_ms=HOUR_MS,
                member_windows=tuple(
                    ComparativeMemberWindow(
                        exchange_instrument_id=_instrument(symbol),
                        candles_1h=_last(frames[symbol], cutoff, lookback + 1),
                    )
                    for symbol in symbols
                ),
            )
            for member in projection.comparative_strength.members:
                rows.append(
                    {
                        "strategy": strategy,
                        "feature_cutoff_at_ms": cutoff,
                        "exchange_instrument_id": member.exchange_instrument_id,
                        "comparative_return_pct": str(member.return_pct),
                        "rank": member.rank,
                    }
                )
    return pd.DataFrame(rows)


def build_selection_artifacts(cache_dir: Path) -> SelectionArtifacts:
    instruments = tuple(CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS)
    symbols = tuple(_symbol(item) for item in instruments)
    frames = {symbol: _load(cache_dir, symbol, "1h") for symbol in symbols}
    all_cutoffs = tuple(
        int(value)
        for value in frames[symbols[0]]["close_time"]
        if SELECTION_START_MS - 5 * HOUR_MS <= int(value) < EVALUATION_END_MS
    )
    rank_authority = _comparative_rank_authority(frames, symbols, all_cutoffs)
    rank_lookup = rank_authority.set_index(
        ["strategy", "feature_cutoff_at_ms", "exchange_instrument_id"]
    )["rank"].to_dict()
    snapshots: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for strategy, (spec_id, cadence_hours) in SELECTION_SPECS.items():
        for cutoff in all_cutoffs:
            if cutoff < SELECTION_START_MS:
                continue
            if cadence_hours == 4 and (cutoff // HOUR_MS) % 24 % 4 != 0:
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
                    value = absolute_directional_efficiency_24h(
                        _close_window(frames[symbol], cutoff, 25)
                    )
                elif strategy == "MPG-001":
                    ranks = tuple(
                        int(
                            rank_lookup[
                                (
                                    strategy,
                                    cutoff - offset * HOUR_MS,
                                    instrument_id,
                                )
                            ]
                        )
                        for offset in range(5, -1, -1)
                    )
                    value = persistent_leadership_score_6h(ranks)
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
            ranked = rank_feature_values(values)
            snapshot_id = f"stage3-1:{strategy}:{cutoff}"
            member_payload = [
                {
                    "exchange_instrument_id": item.exchange_instrument_id,
                    "feature_value": str(item.feature_value),
                    "rank": item.rank,
                }
                for item in ranked
            ]
            snapshots.append(
                {
                    "selection_snapshot_id": snapshot_id,
                    "strategy": strategy,
                    "selection_spec_id": spec_id,
                    "feature_cutoff_at_ms": cutoff,
                    "effective_from_ms": cutoff + HOUR_MS,
                    "candidate_count": 24,
                    "unique_feature_value_count": len(set(values.values())),
                    "selection_semantic_digest": _digest(member_payload),
                }
            )
            decisions.extend(
                {
                    "selection_snapshot_id": snapshot_id,
                    "strategy": strategy,
                    "selection_spec_id": spec_id,
                    "feature_cutoff_at_ms": cutoff,
                    "effective_from_ms": cutoff + HOUR_MS,
                    **member,
                }
                for member in member_payload
            )
    return SelectionArtifacts(
        snapshots=pd.DataFrame(snapshots),
        decisions=pd.DataFrame(decisions),
        rank_authority=rank_authority,
    )
