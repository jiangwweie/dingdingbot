from __future__ import annotations

import pandas as pd

from research.multi_strategy_selection.cluster_robustness import (
    SUPPORTED_HYPOTHESES,
    bootstrap_cluster_effect,
    effect_by_cluster,
    high_minus_low_effect,
    leave_one_cluster_out,
)

HOUR_MS = 3_600_000


def _row(
    hour: int,
    bucket: str,
    label: str,
    *,
    strategy: str = "BRF2-001",
    feature: str = "market_rv_24h",
) -> dict[str, object]:
    return {
        "strategy": strategy,
        "trigger_candle_close_time_ms": 1_786_838_400_000 + hour * HOUR_MS,
        "path_label": label,
        f"{feature}_bucket": bucket,
    }


def test_supported_hypotheses_are_exactly_the_frozen_stage2_rows() -> None:
    assert SUPPORTED_HYPOTHESES == (
        ("BRF2-001", "avg_cross_asset_corr_24h"),
        ("BRF2-001", "market_rv_24h"),
        ("CPM-RO-001", "avg_cross_asset_corr_24h"),
        ("CPM-RO-001", "directional_efficiency_24h"),
    )


def test_trigger_hour_aggregation_does_not_count_a_cross_sectional_burst_as_independent() -> None:
    rows = [
        *[_row(1, "HIGH", "SIGNAL_TP1_FIRST") for _ in range(10)],
        _row(2, "HIGH", "SIGNAL_STOP_FIRST"),
        _row(3, "LOW", "SIGNAL_STOP_FIRST"),
        _row(4, "LOW", "SIGNAL_STOP_FIRST"),
    ]
    frame = pd.DataFrame(rows)

    event_weighted = high_minus_low_effect(frame, "market_rv_24h")
    hour_weighted = high_minus_low_effect(
        frame,
        "market_rv_24h",
        aggregate_by="trigger_hour",
    )

    assert event_weighted is not None
    assert hour_weighted is not None
    assert event_weighted > hour_weighted
    assert hour_weighted == 1.0


def test_leave_one_day_out_removes_the_whole_utc_day_cluster() -> None:
    frame = pd.DataFrame(
        [
            _row(1, "HIGH", "SIGNAL_TP1_FIRST"),
            _row(2, "LOW", "SIGNAL_STOP_FIRST"),
            _row(25, "HIGH", "SIGNAL_STOP_FIRST"),
            _row(26, "LOW", "SIGNAL_TP1_FIRST"),
        ]
    )

    result = leave_one_cluster_out(frame, "market_rv_24h", cluster="utc_day")

    assert len(result) == 2
    assert set(result["excluded_cluster"]) == {"2026-08-16", "2026-08-17"}
    assert set(result["remaining_effect"]) == {-2.0, 2.0}


def test_effect_by_cluster_excludes_mid_neither_and_incomplete_extremes() -> None:
    frame = pd.DataFrame(
        [
            _row(1, "HIGH", "SIGNAL_TP1_FIRST"),
            _row(2, "LOW", "SIGNAL_STOP_FIRST"),
            _row(3, "MID", "SIGNAL_TP1_FIRST"),
            _row(4, "HIGH", "NEITHER"),
            _row(25, "HIGH", "SIGNAL_TP1_FIRST"),
        ]
    )

    result = effect_by_cluster(frame, "market_rv_24h", cluster="utc_day")

    assert len(result) == 2
    first = result.loc[result["cluster"] == "2026-08-16"].iloc[0]
    second = result.loc[result["cluster"] == "2026-08-17"].iloc[0]
    assert first["effect"] == 2.0
    assert first["low_resolved_n"] == 1
    assert first["high_resolved_n"] == 1
    assert pd.isna(second["effect"])


def test_cluster_bootstrap_is_deterministic_for_a_fixed_seed() -> None:
    frame = pd.DataFrame(
        [
            _row(1, "HIGH", "SIGNAL_TP1_FIRST"),
            _row(2, "LOW", "SIGNAL_STOP_FIRST"),
            _row(25, "HIGH", "SIGNAL_TP1_FIRST"),
            _row(26, "LOW", "SIGNAL_TP1_FIRST"),
            _row(49, "HIGH", "SIGNAL_STOP_FIRST"),
            _row(50, "LOW", "SIGNAL_STOP_FIRST"),
        ]
    )

    first = bootstrap_cluster_effect(
        frame,
        "market_rv_24h",
        cluster="utc_day",
        replicates=1_000,
        seed=20260904,
    )
    second = bootstrap_cluster_effect(
        frame,
        "market_rv_24h",
        cluster="utc_day",
        replicates=1_000,
        seed=20260904,
    )

    assert first == second
    assert first.valid_replicates == 1_000
    assert first.ci_low <= first.median <= first.ci_high
