"""Frozen univariate Discovery/Holdout screening for Protocol V2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from research.multi_strategy_selection.replay import DISCOVERY_END_MS

MARKET_FEATURES = (
    "cross_sectional_dispersion_24h",
    "avg_cross_asset_corr_24h",
    "market_breadth_24h",
    "market_rv_24h",
    "market_return_24h",
)
CPM_FEATURES = (*MARKET_FEATURES, "directional_efficiency_24h")
RESOLVED = {"SIGNAL_TP1_FIRST", "SIGNAL_STOP_FIRST"}


@dataclass(frozen=True, slots=True)
class Cutoffs:
    low: float
    high: float


def freeze_cutoffs(market: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, Cutoffs]:
    discovery = market.loc[market["feature_cutoff_at_ms"] < DISCOVERY_END_MS]
    result = {
        feature: Cutoffs(*np.quantile(discovery[feature].astype(float), [1 / 3, 2 / 3]))
        for feature in MARKET_FEATURES
    }
    candidate_discovery = candidate.loc[candidate["feature_cutoff_at_ms"] < DISCOVERY_END_MS]
    result["directional_efficiency_24h"] = Cutoffs(
        *np.quantile(candidate_discovery["directional_efficiency_24h"].astype(float), [1 / 3, 2 / 3])
    )
    return result


def apply_buckets(events: pd.DataFrame, cutoffs: dict[str, Cutoffs]) -> pd.DataFrame:
    result = events.copy()
    for feature, cutoff in cutoffs.items():
        values = pd.to_numeric(result[feature], errors="coerce")
        result[f"{feature}_bucket"] = np.where(
            values <= cutoff.low,
            "LOW",
            np.where(values <= cutoff.high, "MID", "HIGH"),
        )
    return result


def _stats(frame: pd.DataFrame) -> dict[str, object]:
    labels = frame["path_label"]
    resolved = frame.loc[labels.isin(RESOLVED)]
    count = len(resolved)
    tp = int((labels == "SIGNAL_TP1_FIRST").sum())
    stop = int((labels == "SIGNAL_STOP_FIRST").sum())
    return {
        "n_events": len(frame),
        "n_tp1_first": tp,
        "n_stop_first": stop,
        "n_neither": int((labels == "NEITHER").sum()),
        "n_ambiguous": int((labels == "AMBIGUOUS").sum()),
        "n_resolved_non_ambiguous": count,
        "tp1_first_rate": None if count == 0 else tp / count,
        "stop_first_rate": None if count == 0 else stop / count,
        "net_path_rate": None if count == 0 else (tp - stop) / count,
        "median_mfe_signal_r": None if frame.empty else float(pd.to_numeric(frame["mfe_signal_r"]).median()),
        "median_mae_signal_r": None if frame.empty else float(pd.to_numeric(frame["mae_signal_r"]).median()),
        "median_time_to_first_path": None if resolved.empty else float(pd.to_numeric(resolved["time_to_first_path_minutes"]).median()),
    }


def _effect(frame: pd.DataFrame, feature: str, *, ambiguity: str | None = None) -> tuple[float | None, int, int]:
    local = frame.copy()
    if ambiguity is not None:
        local.loc[local["path_label"] == "AMBIGUOUS", "path_label"] = ambiguity

    def net_path(bucket: str) -> tuple[float | None, int]:
        labels = local.loc[local[f"{feature}_bucket"] == bucket, "path_label"]
        tp = int((labels == "SIGNAL_TP1_FIRST").sum())
        stop = int((labels == "SIGNAL_STOP_FIRST").sum())
        count = tp + stop
        return (None if count == 0 else (tp - stop) / count), count

    low_rate, low_count = net_path("LOW")
    high_rate, high_count = net_path("HIGH")
    if low_rate is None or high_rate is None:
        return None, low_count, high_count
    return high_rate - low_rate, low_count, high_count


def screen(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    details: list[dict[str, object]] = []
    screening: list[dict[str, object]] = []
    for strategy in sorted(events["strategy"].unique()):
        features = CPM_FEATURES if strategy == "CPM-RO-001" else MARKET_FEATURES
        strategy_frame = events.loc[events["strategy"] == strategy]
        for feature in features:
            for period, mask in (
                ("Discovery", strategy_frame["trigger_candle_close_time_ms"] < DISCOVERY_END_MS),
                ("Holdout", strategy_frame["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS),
                ("Full", pd.Series(True, index=strategy_frame.index)),
            ):
                period_frame = strategy_frame.loc[mask]
                for bucket in ("LOW", "MID", "HIGH"):
                    details.append({"strategy": strategy, "feature": feature, "period": period, "bucket": bucket, **_stats(period_frame.loc[period_frame[f"{feature}_bucket"] == bucket])})
            discovery = strategy_frame.loc[strategy_frame["trigger_candle_close_time_ms"] < DISCOVERY_END_MS]
            holdout = strategy_frame.loc[strategy_frame["trigger_candle_close_time_ms"] >= DISCOVERY_END_MS]
            discovery_effect, _, _ = _effect(discovery, feature)
            holdout_effect, low_n, high_n = _effect(holdout, feature)
            loso_effects: list[float] = []
            for symbol in sorted(strategy_frame["symbol"].unique()):
                effect, _, _ = _effect(holdout.loc[holdout["symbol"] != symbol], feature)
                if effect is not None:
                    loso_effects.append(effect)
            base_sign = 0 if holdout_effect is None else int(np.sign(holdout_effect))
            same_sign = sum(int(np.sign(value)) == base_sign for value in loso_effects) if base_sign else 0
            same_ratio = None if not loso_effects else same_sign / len(loso_effects)
            optimistic, _, _ = _effect(holdout, feature, ambiguity="SIGNAL_TP1_FIRST")
            pessimistic, _, _ = _effect(holdout, feature, ambiguity="SIGNAL_STOP_FIRST")
            ambiguity_stable = bool(
                holdout_effect is not None
                and optimistic is not None
                and pessimistic is not None
                and np.sign(optimistic) == np.sign(holdout_effect)
                and np.sign(pessimistic) == np.sign(holdout_effect)
            )
            sole_source = bool(holdout_effect and any(value == 0 for value in loso_effects))
            max_contribution = None if not holdout_effect or not loso_effects else max(abs(holdout_effect - value) / abs(holdout_effect) for value in loso_effects)
            reversed_direction = bool(discovery_effect and holdout_effect and np.sign(discovery_effect) != np.sign(holdout_effect))
            supported = bool(
                discovery_effect
                and holdout_effect
                and np.sign(discovery_effect) == np.sign(holdout_effect)
                and low_n >= 15
                and high_n >= 15
                and abs(holdout_effect) >= 0.10
                and same_ratio is not None
                and same_ratio >= 0.80
                and not sole_source
                and ambiguity_stable
            )
            if supported:
                classification, reason = "SUPPORTED_FOR_SHADOW", "all_frozen_gates_pass"
            elif reversed_direction or (same_ratio is not None and same_ratio < 0.60) or sole_source:
                classification, reason = "REJECTED", "direction_or_loso_instability"
            else:
                classification, reason = "INCONCLUSIVE", "one_or_more_support_gates_not_met"
            screening.append(
                {
                    "strategy": strategy,
                    "feature": feature,
                    "discovery_high_minus_low_net_path_rate": discovery_effect,
                    "holdout_high_minus_low_net_path_rate": holdout_effect,
                    "holdout_low_resolved_n": low_n,
                    "holdout_high_resolved_n": high_n,
                    "same_sign_loso_count": same_sign,
                    "valid_loso_count": len(loso_effects),
                    "same_sign_ratio": same_ratio,
                    "max_single_symbol_effect_contribution": max_contribution,
                    "ambiguity_optimistic_effect": optimistic,
                    "ambiguity_pessimistic_effect": pessimistic,
                    "ambiguity_direction_stable": ambiguity_stable,
                    "classification": classification,
                    "reason": reason,
                }
            )
    return pd.DataFrame(screening), pd.DataFrame(details)


def write_cutoffs(path: Path, cutoffs: dict[str, Cutoffs]) -> None:
    path.write_text(json.dumps({key: {"low": value.low, "high": value.high} for key, value in cutoffs.items()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
