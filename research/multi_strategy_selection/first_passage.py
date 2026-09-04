"""Signal-R first-passage with exact post-trigger and ambiguity semantics."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class PathLabel(StrEnum):
    SIGNAL_TP1_FIRST = "SIGNAL_TP1_FIRST"
    SIGNAL_STOP_FIRST = "SIGNAL_STOP_FIRST"
    NEITHER = "NEITHER"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class PathBar:
    open_time_ms: int
    close_time_ms: int
    high: Decimal
    low: Decimal


@dataclass(frozen=True, slots=True)
class SignalPathResult:
    label: PathLabel
    first_path_at_ms: int | None
    time_to_first_path_minutes: Decimal | None
    mfe_signal_r: Decimal
    mae_signal_r: Decimal
    resolved_by_12h: bool
    resolved_by_24h: bool
    resolved_by_48h: bool
    ambiguous_15m_open_time_ms: int | None = None


def evaluate_signal_path(
    *,
    side: Literal["long", "short"],
    anchor: Decimal,
    stop: Decimal,
    trigger_close_ms: int,
    bars_15m: tuple[PathBar, ...],
    bars_1m_by_15m: dict[int, tuple[PathBar, ...]],
) -> SignalPathResult:
    risk = anchor - stop if side == "long" else stop - anchor
    if risk <= 0:
        raise ValueError("INVALID_SIGNAL_GEOMETRY")
    tp = anchor + risk if side == "long" else anchor - risk
    eligible = tuple(bar for bar in bars_15m if bar.open_time_ms >= trigger_close_ms)[:192]
    label = PathLabel.NEITHER
    first_at: int | None = None
    ambiguous_open: int | None = None
    highs = [bar.high for bar in eligible]
    lows = [bar.low for bar in eligible]
    for bar in eligible:
        tp_hit, stop_hit = _touches(side, bar, tp, stop)
        if not tp_hit and not stop_hit:
            continue
        if tp_hit and stop_hit:
            ambiguous_open = bar.open_time_ms
            resolution = _resolve_1m(
                side,
                bars_1m_by_15m.get(bar.open_time_ms, ()),
                tp,
                stop,
            )
            label, first_at = resolution
        else:
            label = PathLabel.SIGNAL_TP1_FIRST if tp_hit else PathLabel.SIGNAL_STOP_FIRST
            first_at = bar.close_time_ms
        break
    if highs:
        if side == "long":
            mfe = (max(highs) - anchor) / risk
            mae = (min(lows) - anchor) / risk
        else:
            mfe = (anchor - min(lows)) / risk
            mae = (anchor - max(highs)) / risk
    else:
        mfe = mae = Decimal(0)
    minutes = None if first_at is None else Decimal(first_at - trigger_close_ms) / Decimal(60_000)
    resolved = label in {PathLabel.SIGNAL_TP1_FIRST, PathLabel.SIGNAL_STOP_FIRST}
    return SignalPathResult(
        label=label,
        first_path_at_ms=first_at,
        time_to_first_path_minutes=minutes,
        mfe_signal_r=mfe,
        mae_signal_r=mae,
        resolved_by_12h=resolved and minutes is not None and minutes <= 720,
        resolved_by_24h=resolved and minutes is not None and minutes <= 1_440,
        resolved_by_48h=resolved and minutes is not None and minutes <= 2_880,
        ambiguous_15m_open_time_ms=ambiguous_open,
    )


def _touches(side: str, bar: PathBar, tp: Decimal, stop: Decimal) -> tuple[bool, bool]:
    return ((bar.high >= tp, bar.low <= stop) if side == "long" else (bar.low <= tp, bar.high >= stop))


def _resolve_1m(
    side: str,
    bars: tuple[PathBar, ...],
    tp: Decimal,
    stop: Decimal,
) -> tuple[PathLabel, int | None]:
    for bar in sorted(bars, key=lambda item: item.open_time_ms):
        tp_hit, stop_hit = _touches(side, bar, tp, stop)
        if tp_hit and stop_hit:
            return PathLabel.AMBIGUOUS, bar.close_time_ms
        if tp_hit:
            return PathLabel.SIGNAL_TP1_FIRST, bar.close_time_ms
        if stop_hit:
            return PathLabel.SIGNAL_STOP_FIRST, bar.close_time_ms
    return PathLabel.AMBIGUOUS, None
