"""Protocol V2 Signal-R outcome projection with on-demand 1m evidence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, cast

import pandas as pd

from research.multi_strategy_selection.first_passage import (
    PathBar,
    PathLabel,
    SignalPathResult,
    evaluate_signal_path,
)
from research.multi_strategy_selection.market_data import (
    download_daily_1m,
    load_daily_1m,
)

HOUR_MS = 3_600_000


def _bars(frame: pd.DataFrame) -> tuple[PathBar, ...]:
    return tuple(
        PathBar(
            open_time_ms=int(row["open_time"]),
            close_time_ms=int(row["close_time"]),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
        )
        for _, row in frame.iterrows()
    )


def compute_first_passage(cache_dir: Path, events: pd.DataFrame) -> pd.DataFrame:
    frames_15m = {
        symbol: pd.read_parquet(cache_dir / "normalized" / f"{symbol}_15m.parquet")
        for symbol in sorted(set(events["symbol"]))
    }
    preliminary: list[tuple[dict[str, object], SignalPathResult]] = []
    symbol_days: set[tuple[str, str]] = set()
    for raw_record in events.to_dict("records"):
        record = cast(dict[str, object], raw_record)
        if record["event_geometry_status"] != "VALID":
            continue
        trigger = int(str(record["trigger_candle_close_time_ms"]))
        frame = frames_15m[str(record["symbol"])]
        selected = frame.loc[
            (frame["open_time"] >= trigger)
            & (frame["open_time"] < trigger + 48 * HOUR_MS)
        ].head(192)
        result = evaluate_signal_path(
            side=cast(Literal["long", "short"], str(record["direction"])),
            anchor=Decimal(str(record["signal_anchor_price"])),
            stop=Decimal(str(record["signal_stop_reference"])),
            trigger_close_ms=trigger,
            bars_15m=_bars(selected),
            bars_1m_by_15m={},
        )
        preliminary.append((record, result))
        if result.label is PathLabel.AMBIGUOUS and result.ambiguous_15m_open_time_ms is not None:
            day = datetime.fromtimestamp(result.ambiguous_15m_open_time_ms / 1000, UTC).date().isoformat()
            symbol_days.add((str(record["symbol"]), day))
    if symbol_days:
        download_daily_1m(cache_dir, symbol_days)
    one_minute = {(symbol, day): load_daily_1m(cache_dir, symbol, day) for symbol, day in symbol_days}
    rows: list[dict[str, object]] = []
    for record, initial in preliminary:
        result = initial
        if initial.label is PathLabel.AMBIGUOUS and initial.ambiguous_15m_open_time_ms is not None:
            open_ms = initial.ambiguous_15m_open_time_ms
            day = datetime.fromtimestamp(open_ms / 1000, UTC).date().isoformat()
            minute_frame = one_minute[(str(record["symbol"]), day)]
            minute_selected = minute_frame.loc[
                (minute_frame["open_time"] >= open_ms)
                & (minute_frame["open_time"] < open_ms + 15 * 60_000)
            ]
            frame = frames_15m[str(record["symbol"])]
            trigger = int(str(record["trigger_candle_close_time_ms"]))
            selected = frame.loc[
                (frame["open_time"] >= trigger)
                & (frame["open_time"] < trigger + 48 * HOUR_MS)
            ].head(192)
            result = evaluate_signal_path(
                side=cast(Literal["long", "short"], str(record["direction"])),
                anchor=Decimal(str(record["signal_anchor_price"])),
                stop=Decimal(str(record["signal_stop_reference"])),
                trigger_close_ms=trigger,
                bars_15m=_bars(selected),
                bars_1m_by_15m={open_ms: _bars(minute_selected)},
            )
        rows.append(
            {
                "event_spec_id": record["event_spec_id"],
                "strategy": record["strategy"],
                "symbol": record["symbol"],
                "direction": record["direction"],
                "trigger_candle_close_time_ms": record["trigger_candle_close_time_ms"],
                "path_label": result.label.value,
                "first_path_at_ms": result.first_path_at_ms,
                "time_to_first_path_minutes": None if result.time_to_first_path_minutes is None else str(result.time_to_first_path_minutes),
                "mfe_signal_r": str(result.mfe_signal_r),
                "mae_signal_r": str(result.mae_signal_r),
                "resolved_by_12h": result.resolved_by_12h,
                "resolved_by_24h": result.resolved_by_24h,
                "resolved_by_48h": result.resolved_by_48h,
            }
        )
    return pd.DataFrame(rows)
