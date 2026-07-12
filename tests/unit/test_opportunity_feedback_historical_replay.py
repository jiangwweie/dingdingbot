from __future__ import annotations

from datetime import datetime, timezone

from scripts.seed_runtime_control_state_foundation import build_seed_rows
from src.application.opportunity_feedback_historical_replay import (
    build_historical_replay_scopes,
    run_opportunity_feedback_historical_replay,
)


HOUR_MS = 3_600_000
FIFTEEN_MINUTES_MS = 900_000


def _candle(open_time_ms: int, close: str = "100") -> dict[str, object]:
    return {
        "open_time_ms": open_time_ms,
        "close_time_ms": open_time_ms + HOUR_MS - 1,
        "open": close,
        "high": str(float(close) + 1),
        "low": str(float(close) - 1),
        "close": close,
        "volume": "1000",
    }


def _fifteen_minute_candle(
    open_time_ms: int,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> dict[str, object]:
    return {
        "open_time_ms": open_time_ms,
        "close_time_ms": open_time_ms + FIFTEEN_MINUTES_MS - 1,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": "1000",
    }


def _scopes():
    rows = build_seed_rows(now_ms=1_800_000_000_000)
    return build_historical_replay_scopes(
        event_specs=rows["brc_strategy_side_event_specs"],
        candidate_scopes=rows["brc_strategy_group_candidate_scope"],
        bindings=rows["brc_candidate_scope_event_bindings"],
        event_fact_rows=rows["brc_strategy_event_required_facts"],
        evaluator_versions={
            group_id: f"{group_id}-v0"
            for group_id in (
                "CPM-RO-001",
                "MPG-001",
                "MI-001",
                "SOR-001",
                "BRF2-001",
            )
        },
    )


def test_pg_rows_build_exact_22_scope_six_event_spec_replay_universe() -> None:
    scopes = _scopes()

    assert len(scopes) == 22
    assert len({scope.event_spec.event_spec_id for scope in scopes}) == 6
    assert {scope.event_spec.strategy_group_id for scope in scopes} == {
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    }
    brf2 = next(scope for scope in scopes if scope.event_spec.strategy_group_id == "BRF2-001")
    assert brf2.event_spec.disable_fact_keys == ("strong_uptrend_disable",)
    assert "rally_failure_confirmed" in brf2.event_spec.required_fact_keys


def test_historical_replay_uses_aligned_windows_and_preserves_non_authority() -> None:
    scopes = [
        scope
        for scope in _scopes()
        if scope.event_spec.strategy_group_id == "CPM-RO-001"
        and scope.symbol == "ETHUSDT"
    ]
    start_ms = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    one_hour = [_candle(start_ms + index * HOUR_MS) for index in range(100)]
    four_hour = [
        {
            **_candle(start_ms + index * 4 * HOUR_MS),
            "close_time_ms": start_ms + (index + 1) * 4 * HOUR_MS - 1,
        }
        for index in range(25)
    ]
    as_of_ms = int(one_hour[-1]["close_time_ms"])

    result = run_opportunity_feedback_historical_replay(
        scopes=scopes,
        candles_by_symbol_timeframe={
            ("ETHUSDT", "1h"): one_hour,
            ("ETHUSDT", "4h"): four_hour,
        },
        as_of_ms=as_of_ms,
    )

    scope_result = result.scope_results[0]
    window = next(item for item in scope_result.calibration.windows if item.window_days == 90)
    assert window.replay.total_evaluations > 0
    assert window.replay.invalid_count == 0
    assert window.replay.near_miss_count > 0
    assert window.replay.failed_fact_counts["htf_trend_intact"] > 0
    assert result.pg_rows_written == 0
    assert result.runtime_authority_created is False
    assert result.exchange_write_called is False
    assert result.output_files_written == 0


def test_sor_replay_projects_one_session_breakout_to_each_event_side() -> None:
    scopes = [
        scope
        for scope in _scopes()
        if scope.event_spec.strategy_group_id == "SOR-001"
        and scope.symbol == "ETHUSDT"
    ]
    start_ms = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
    candles = [
        _fifteen_minute_candle(
            start_ms + index * FIFTEEN_MINUTES_MS,
            open_="100",
            high="101",
            low="99",
            close="100",
        )
        for index in range(4)
    ]
    candles.append(
        _fifteen_minute_candle(
            start_ms + 4 * FIFTEEN_MINUTES_MS,
            open_="100",
            high="104",
            low="100",
            close="103",
        )
    )
    candles.append(
        _fifteen_minute_candle(
            start_ms + 5 * FIFTEEN_MINUTES_MS,
            open_="103",
            high="105",
            low="102",
            close="104",
        )
    )
    as_of_ms = int(candles[-1]["close_time_ms"])

    result = run_opportunity_feedback_historical_replay(
        scopes=scopes,
        candles_by_symbol_timeframe={("ETHUSDT", "15m"): candles},
        as_of_ms=as_of_ms,
    )

    by_side = {item.side: item for item in result.scope_results}
    long_window = next(item for item in by_side["long"].calibration.windows if item.window_days == 90)
    short_window = next(item for item in by_side["short"].calibration.windows if item.window_days == 90)
    assert long_window.replay.signal_count == 1
    assert short_window.replay.signal_count == 0
    assert short_window.replay.near_miss_count == 2
    assert short_window.replay.failed_fact_counts == {
        "breakdown_confirmed": 2,
        "event_side_matched": 2,
        "opening_range_high_reference": 2,
    }
