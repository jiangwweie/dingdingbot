#!/usr/bin/env python3
"""One-off historical evidence tables for Directional Opportunity smoke variants.

This is a research spike only: it reads local historical candles, creates fixed
OHLCV-only smoke signals, and prints forward-outcome summaries.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Iterable
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.directional_opportunity_forward_outcome import pack_forward_outcome_windows
from src.domain.directional_opportunity_pack import btc_eth_sol_bnb_directional_opportunity_pack
from src.domain.forward_outcome_review import calculate_forward_outcomes
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_signal_evaluation import (
    HistoricalForwardOutcome,
    HistoricalForwardOutcomeStatus,
)
from src.domain.strategy_family_signal import (
    ExpectedRiskShape,
    SignalSide,
    SignalType,
    StrategyFamilySignalOutput,
)


CANDIDATE_FAMILY_ID = "TB-001"
SMOKE_VERSION = "smoke_v0"
TB_LOOKBACK_BARS = 20
TB_SLOW_LOOKBACK_BARS = 55
VB_BOLLINGER_LENGTH = 20
VB_BAND_STD = Decimal("2")
VB_SQUEEZE_LOOKBACK = 60
VB_SQUEEZE_RECENT_BARS = 5
PC_FAST_EMA = 20
PC_SLOW_EMA = 50
PC_SLOW_PULLBACK_EMA = 50
PC_TREND_EMA = 200
MR_BOLLINGER_LENGTH = 20
MR_BAND_STD = Decimal("2")
RB_LOOKBACK_BARS = 20
VI_LOOKBACK_BARS = 20
VI_VOLUME_MULTIPLIER = Decimal("2")
MI_LOOKBACK_BARS = 12
MI_RETURN_THRESHOLD = Decimal("3")
DEFAULT_TIMEFRAME = "1h"
HOUR_MS = 60 * 60 * 1000

VARIANT_LABELS = {
    "TB-001": SMOKE_VERSION,
    "TB-002": SMOKE_VERSION,
    "VB-001": SMOKE_VERSION,
    "PC-001": SMOKE_VERSION,
    "PC-002": SMOKE_VERSION,
    "MR-001": SMOKE_VERSION,
    "RB-001": SMOKE_VERSION,
    "VI-001": SMOKE_VERSION,
    "MI-001": SMOKE_VERSION,
}

SYMBOL_TO_BINANCE = {
    "BTC/USDT:USDT": "BTCUSDT",
    "ETH/USDT:USDT": "ETHUSDT",
    "SOL/USDT:USDT": "SOLUSDT",
    "BNB/USDT:USDT": "BNBUSDT",
}


@dataclass(frozen=True)
class SmokeSignal:
    signal_output: StrategyFamilySignalOutput
    bar_index: int


def main() -> int:
    args = _parse_args()
    pack = btc_eth_sol_bnb_directional_opportunity_pack()
    if args.tf != DEFAULT_TIMEFRAME:
        print("only --tf 1h is supported for this disposable evidence script", file=sys.stderr)
        return 2

    windows = _select_windows(pack_forward_outcome_windows(pack).windows, args.windows)
    symbols = _select_symbols(pack.canonical_symbols, args.symbols)
    sides = _select_sides(args.sides)
    variants = _select_variants(args.variants)
    root = Path(args.data_root)
    sqlite_db = Path(args.sqlite_db)
    rows: list[dict[str, str]] = []
    missing_symbols: list[str] = []

    for symbol in symbols:
        bars, data_note = _load_symbol_bars(root=root, sqlite_db=sqlite_db, symbol=symbol, timeframe=args.tf)
        if not bars:
            missing_symbols.append(symbol)
            continue
        for variant in variants:
            for side in sides:
                signals = _detect_signals(variant=variant, symbol=symbol, bars=bars, side=side)
                outcomes_by_window: dict[str, list[HistoricalForwardOutcome]] = defaultdict(list)
                for signal in signals:
                    future_bars = bars[signal.bar_index + 1 : signal.bar_index + 1 + max(windows.values())]
                    for outcome in calculate_forward_outcomes(
                        run_id=f"{variant}-{VARIANT_LABELS[variant]}",
                        signal_output=signal.signal_output,
                        entry_bar=bars[signal.bar_index],
                        future_bars=future_bars,
                        created_at_ms=signal.signal_output.timestamp_ms,
                        windows=windows,
                    ):
                        outcomes_by_window[outcome.window_label].append(outcome)

                for window_label in windows:
                    rows.append(
                        _summary_row(
                            candidate_family_id=variant,
                            variant_label=VARIANT_LABELS[variant],
                            symbol=symbol,
                            side=side,
                            signal_count=len(signals),
                            window_label=window_label,
                            outcomes=outcomes_by_window.get(window_label, []),
                            data_note=data_note,
                        )
                    )

    if missing_symbols:
        print(f"missing local {args.tf} data for: {', '.join(missing_symbols)}", file=sys.stderr)
    if not rows:
        print(
            f"no evidence rows; expected SQLite klines in {sqlite_db} or local Binance zip files under {root}",
            file=sys.stderr,
        )
        return 2

    _print_table(rows)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", nargs="+", default=["TB-001"], help="Smoke variants to run.")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to include.")
    parser.add_argument("--sides", nargs="+", default=["long", "short"], help="Sides to include.")
    parser.add_argument("--tf", default=DEFAULT_TIMEFRAME, help="Base timeframe. Only 1h is supported.")
    parser.add_argument("--windows", nargs="+", default=None, help="Forward windows to include.")
    parser.add_argument("--data-root", default="data", help="Repository-local data directory.")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db", help="Local SQLite OHLCV database.")
    return parser.parse_args()


def _select_windows(all_windows: dict[str, int], requested: list[str] | None) -> dict[str, int]:
    if not requested:
        return dict(all_windows)
    unknown = [window for window in requested if window not in all_windows]
    if unknown:
        raise SystemExit(f"unsupported windows: {', '.join(unknown)}")
    return {window: all_windows[window] for window in requested}


def _select_symbols(all_symbols: list[str], requested: list[str] | None) -> list[str]:
    if not requested:
        return list(all_symbols)
    unknown = [symbol for symbol in requested if symbol not in all_symbols]
    if unknown:
        raise SystemExit(f"unsupported symbols: {', '.join(unknown)}")
    return list(requested)


def _select_sides(requested: list[str]) -> list[SignalSide]:
    sides: list[SignalSide] = []
    for raw in requested:
        try:
            side = SignalSide(raw)
        except ValueError as exc:
            raise SystemExit(f"unsupported side: {raw}") from exc
        if side not in {SignalSide.LONG, SignalSide.SHORT}:
            raise SystemExit(f"unsupported side: {raw}")
        sides.append(side)
    return sides


def _select_variants(requested: list[str]) -> list[str]:
    unknown = [variant for variant in requested if variant not in VARIANT_LABELS]
    if unknown:
        raise SystemExit(f"unsupported variants: {', '.join(unknown)}")
    return list(requested)


def _load_symbol_bars(
    *,
    root: Path,
    sqlite_db: Path,
    symbol: str,
    timeframe: str,
) -> tuple[list[HistoricalOhlcvBar], str]:
    sqlite_bars = _load_symbol_bars_from_sqlite(sqlite_db=sqlite_db, symbol=symbol, timeframe=timeframe)
    if sqlite_bars:
        return sqlite_bars, f"sqlite:{sqlite_db}; bars={len(sqlite_bars)}"
    zip_bars = _load_symbol_bars_from_zips(root=root, symbol=symbol, timeframe=timeframe)
    return zip_bars, f"local_zip:{root}; bars={len(zip_bars)}"


def _load_symbol_bars_from_sqlite(
    *,
    sqlite_db: Path,
    symbol: str,
    timeframe: str,
) -> list[HistoricalOhlcvBar]:
    if not sqlite_db.exists():
        return []
    with sqlite3.connect(sqlite_db) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, open, high, low, close, volume, created_at
            FROM klines
            WHERE symbol = ? AND timeframe = ? AND is_closed = 1
            ORDER BY timestamp ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    return [
        HistoricalOhlcvBar(
            source="local_sqlite",
            market="um_futures",
            symbol=symbol,
            timeframe=timeframe,
            open_time_ms=int(timestamp),
            open=Decimal(str(open_price)),
            high=Decimal(str(high)),
            low=Decimal(str(low)),
            close=Decimal(str(close)),
            volume=Decimal(str(volume)),
            quote_volume=None,
            close_time_ms=int(timestamp) + HOUR_MS - 1,
            created_at_ms=int(created_at or timestamp),
        )
        for timestamp, open_price, high, low, close, volume, created_at in rows
    ]


def _load_symbol_bars_from_zips(*, root: Path, symbol: str, timeframe: str) -> list[HistoricalOhlcvBar]:
    exchange_symbol = SYMBOL_TO_BINANCE[symbol]
    paths = [
        root / "import_202604_downloads" / f"{exchange_symbol}-{timeframe}-2026-04.zip",
        *sorted((root / "import_202605_daily_downloads").glob(f"{exchange_symbol}-{timeframe}-2026-05-*.zip")),
    ]
    by_open_time: dict[int, HistoricalOhlcvBar] = {}
    for path in paths:
        if not path.exists():
            continue
        with ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".csv"):
                    continue
                with archive.open(name) as raw:
                    text = (line.decode("utf-8") for line in raw)
                    for row in csv.DictReader(text):
                        bar = HistoricalOhlcvBar(
                            source="binance_local_zip",
                            market="um_futures",
                            symbol=symbol,
                            timeframe=timeframe,
                            open_time_ms=int(row["open_time"]),
                            open=Decimal(row["open"]),
                            high=Decimal(row["high"]),
                            low=Decimal(row["low"]),
                            close=Decimal(row["close"]),
                            volume=Decimal(row["volume"]),
                            quote_volume=Decimal(row["quote_volume"]),
                            close_time_ms=int(row["close_time"]),
                            created_at_ms=int(row["open_time"]),
                        )
                        by_open_time[bar.open_time_ms] = bar
    return [by_open_time[key] for key in sorted(by_open_time)]


def _detect_signals(
    *,
    variant: str,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    if variant == "TB-001":
        return _detect_tb_signals(symbol=symbol, bars=bars, side=side, lookback_bars=TB_LOOKBACK_BARS)
    if variant == "TB-002":
        return _detect_tb_signals(symbol=symbol, bars=bars, side=side, lookback_bars=TB_SLOW_LOOKBACK_BARS)
    if variant == "VB-001":
        return _detect_vb_signals(symbol=symbol, bars=bars, side=side)
    if variant == "PC-001":
        return _detect_pc_signals(symbol=symbol, bars=bars, side=side)
    if variant == "PC-002":
        return _detect_pc_slow_pullback_signals(symbol=symbol, bars=bars, side=side)
    if variant == "MR-001":
        return _detect_mr_signals(symbol=symbol, bars=bars, side=side)
    if variant == "RB-001":
        return _detect_rb_signals(symbol=symbol, bars=bars, side=side)
    if variant == "VI-001":
        return _detect_vi_signals(symbol=symbol, bars=bars, side=side)
    if variant == "MI-001":
        return _detect_mi_signals(symbol=symbol, bars=bars, side=side)
    raise ValueError(f"unsupported variant: {variant}")


def _detect_breakout_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    return _detect_tb_signals(symbol=symbol, bars=bars, side=side, lookback_bars=TB_LOOKBACK_BARS)


def _detect_tb_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
    lookback_bars: int,
) -> list[SmokeSignal]:
    signals: list[SmokeSignal] = []
    variant = "TB-002" if lookback_bars == TB_SLOW_LOOKBACK_BARS else "TB-001"
    for index in range(lookback_bars, len(bars)):
        current = bars[index]
        prior = bars[index - lookback_bars : index]
        previous_high = max(bar.high for bar in prior)
        previous_low = min(bar.low for bar in prior)
        if side == SignalSide.LONG and current.close <= previous_high:
            continue
        if side == SignalSide.SHORT and current.close >= previous_low:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant=variant,
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"donchian_{lookback_bars}_break_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
                    human_summary=f"{variant} smoke_v0 fixed {lookback_bars}-bar breakout research signal.",
                    signal_snapshot={
                        "lookback_bars": lookback_bars,
                        "previous_high": str(previous_high),
                        "previous_low": str(previous_low),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_vb_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    bands = _bollinger_bands_excluding_current(bars, VB_BOLLINGER_LENGTH, VB_BAND_STD)
    squeeze_flags = _squeeze_flags(bands, VB_SQUEEZE_LOOKBACK)
    signals: list[SmokeSignal] = []
    start = VB_BOLLINGER_LENGTH + VB_SQUEEZE_LOOKBACK
    for index in range(start, len(bars)):
        band = bands[index]
        if band is None:
            continue
        middle, upper, lower, bandwidth = band
        recent_start = max(0, index - VB_SQUEEZE_RECENT_BARS)
        recent_squeeze = any(squeeze_flags[recent_start:index])
        if not recent_squeeze:
            continue
        current = bars[index]
        if side == SignalSide.LONG and current.close <= upper:
            continue
        if side == SignalSide.SHORT and current.close >= lower:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="VB-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"bollinger_squeeze_break_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
                    human_summary="VB-001 smoke_v0 simple Bollinger squeeze expansion research signal.",
                    signal_snapshot={
                        "bollinger_length": VB_BOLLINGER_LENGTH,
                        "band_std": str(VB_BAND_STD),
                        "squeeze_lookback": VB_SQUEEZE_LOOKBACK,
                        "squeeze_recent_bars": VB_SQUEEZE_RECENT_BARS,
                        "middle": str(middle),
                        "upper": str(upper),
                        "lower": str(lower),
                        "bandwidth": str(bandwidth),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_pc_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    closes = [bar.close for bar in bars]
    ema20 = _ema_values(closes, PC_FAST_EMA)
    ema50 = _ema_values(closes, PC_SLOW_EMA)
    signals: list[SmokeSignal] = []
    for index in range(PC_SLOW_EMA - 1, len(bars)):
        fast = ema20[index]
        slow = ema50[index]
        if fast is None or slow is None:
            continue
        current = bars[index]
        if side == SignalSide.LONG:
            matched = fast > slow and current.low <= fast and current.close > fast
        else:
            matched = fast < slow and current.high >= fast and current.close < fast
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="PC-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"ema{PC_FAST_EMA}_ema{PC_SLOW_EMA}_pullback_recovery_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
                    human_summary="PC-001 smoke_v0 EMA trend pullback recovery research signal.",
                    signal_snapshot={
                        "fast_ema": PC_FAST_EMA,
                        "slow_ema": PC_SLOW_EMA,
                        "ema20": str(fast),
                        "ema50": str(slow),
                        "high": str(current.high),
                        "low": str(current.low),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_pc_slow_pullback_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    closes = [bar.close for bar in bars]
    ema50 = _ema_values(closes, PC_SLOW_PULLBACK_EMA)
    ema200 = _ema_values(closes, PC_TREND_EMA)
    signals: list[SmokeSignal] = []
    for index in range(PC_TREND_EMA - 1, len(bars)):
        pullback = ema50[index]
        trend = ema200[index]
        if pullback is None or trend is None:
            continue
        current = bars[index]
        if side == SignalSide.LONG:
            matched = current.close > trend and current.low <= pullback and current.close > pullback
        else:
            matched = current.close < trend and current.high >= pullback and current.close < pullback
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="PC-002",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"ema{PC_SLOW_PULLBACK_EMA}_pullback_ema{PC_TREND_EMA}_trend_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.PULLBACK_CONTINUATION,
                    human_summary="PC-002 smoke_v0 slow EMA trend pullback recovery research signal.",
                    signal_snapshot={
                        "pullback_ema": PC_SLOW_PULLBACK_EMA,
                        "trend_ema": PC_TREND_EMA,
                        "ema50": str(pullback),
                        "ema200": str(trend),
                        "high": str(current.high),
                        "low": str(current.low),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_mr_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    bands = _bollinger_bands_excluding_current(bars, MR_BOLLINGER_LENGTH, MR_BAND_STD)
    signals: list[SmokeSignal] = []
    for index in range(MR_BOLLINGER_LENGTH, len(bars)):
        band = bands[index]
        if band is None:
            continue
        middle, upper, lower, bandwidth = band
        current = bars[index]
        if side == SignalSide.LONG:
            matched = current.close < lower
        else:
            matched = current.close > upper
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="MR-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"bollinger_outer_band_mean_reversion_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.UNKNOWN,
                    human_summary="MR-001 smoke_v0 simple Bollinger outer-band mean-reversion research signal.",
                    signal_snapshot={
                        "bollinger_length": MR_BOLLINGER_LENGTH,
                        "band_std": str(MR_BAND_STD),
                        "middle": str(middle),
                        "upper": str(upper),
                        "lower": str(lower),
                        "bandwidth": str(bandwidth),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_rb_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    signals: list[SmokeSignal] = []
    for index in range(RB_LOOKBACK_BARS, len(bars)):
        current = bars[index]
        prior = bars[index - RB_LOOKBACK_BARS : index]
        previous_high = max(bar.high for bar in prior)
        previous_low = min(bar.low for bar in prior)
        if side == SignalSide.LONG:
            matched = current.low < previous_low and current.close > previous_low
        else:
            matched = current.high > previous_high and current.close < previous_high
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="RB-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"range_boundary_rejection_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.BREAKOUT_FALSE_BREAKOUT_PRONE,
                    human_summary="RB-001 smoke_v0 20-bar range boundary rejection research signal.",
                    signal_snapshot={
                        "lookback_bars": RB_LOOKBACK_BARS,
                        "previous_high": str(previous_high),
                        "previous_low": str(previous_low),
                        "high": str(current.high),
                        "low": str(current.low),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_vi_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    signals: list[SmokeSignal] = []
    for index in range(VI_LOOKBACK_BARS, len(bars)):
        current = bars[index]
        prior = bars[index - VI_LOOKBACK_BARS : index]
        average_volume = _mean([bar.volume for bar in prior])
        if average_volume is None or average_volume <= 0:
            continue
        previous_high = max(bar.high for bar in prior)
        previous_low = min(bar.low for bar in prior)
        volume_expanded = current.volume >= average_volume * VI_VOLUME_MULTIPLIER
        if side == SignalSide.LONG:
            matched = volume_expanded and current.close > previous_high
        else:
            matched = volume_expanded and current.close < previous_low
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="VI-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"volume_impulse_break_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
                    human_summary="VI-001 smoke_v0 volume impulse breakout research signal.",
                    signal_snapshot={
                        "lookback_bars": VI_LOOKBACK_BARS,
                        "volume_multiplier": str(VI_VOLUME_MULTIPLIER),
                        "average_volume": str(average_volume),
                        "volume": str(current.volume),
                        "previous_high": str(previous_high),
                        "previous_low": str(previous_low),
                        "close": str(current.close),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _detect_mi_signals(
    *,
    symbol: str,
    bars: list[HistoricalOhlcvBar],
    side: SignalSide,
) -> list[SmokeSignal]:
    signals: list[SmokeSignal] = []
    for index in range(MI_LOOKBACK_BARS, len(bars)):
        current = bars[index]
        previous = bars[index - MI_LOOKBACK_BARS]
        if previous.close <= 0:
            continue
        return_pct = (current.close - previous.close) / previous.close * Decimal("100")
        if side == SignalSide.LONG:
            matched = return_pct >= MI_RETURN_THRESHOLD
        else:
            matched = return_pct <= -MI_RETURN_THRESHOLD
        if not matched:
            continue
        signals.append(
            SmokeSignal(
                signal_output=_signal_output(
                    variant="MI-001",
                    symbol=symbol,
                    side=side,
                    current=current,
                    reason_codes=[f"{MI_LOOKBACK_BARS}h_momentum_impulse_{side.value}"],
                    expected_risk_shape=ExpectedRiskShape.VOLATILITY_EXPANSION,
                    human_summary="MI-001 smoke_v0 12-hour momentum impulse research signal.",
                    signal_snapshot={
                        "lookback_bars": MI_LOOKBACK_BARS,
                        "return_threshold_pct": str(MI_RETURN_THRESHOLD),
                        "lookback_close": str(previous.close),
                        "close": str(current.close),
                        "return_pct": str(return_pct),
                    },
                ),
                bar_index=index,
            )
        )
    return signals


def _signal_output(
    *,
    variant: str,
    symbol: str,
    side: SignalSide,
    current: HistoricalOhlcvBar,
    reason_codes: list[str],
    expected_risk_shape: ExpectedRiskShape,
    human_summary: str,
    signal_snapshot: dict[str, str | int],
) -> StrategyFamilySignalOutput:
    variant_label = VARIANT_LABELS[variant]
    return StrategyFamilySignalOutput(
        signal_id=_signal_id(variant=variant, symbol=symbol, side=side, timestamp_ms=current.open_time_ms),
        evaluation_id=f"{variant}-{variant_label}",
        strategy_family_id=variant,
        strategy_family_version_id=f"{variant}-{variant_label}",
        symbol=symbol,
        timestamp_ms=current.open_time_ms,
        timeframe=DEFAULT_TIMEFRAME,
        signal_type=SignalType.WOULD_ENTER,
        side=side,
        confidence=Decimal("0.50"),
        reason_codes=reason_codes,
        human_summary=human_summary,
        expected_risk_shape=expected_risk_shape,
        signal_snapshot=signal_snapshot,
        evidence_payload={"candidate_label": f"{variant} {variant_label}"},
    )


def _bollinger_bands_excluding_current(
    bars: list[HistoricalOhlcvBar],
    length: int,
    band_std: Decimal,
) -> list[tuple[Decimal, Decimal, Decimal, Decimal] | None]:
    bands: list[tuple[Decimal, Decimal, Decimal, Decimal] | None] = [None] * len(bars)
    for index in range(length, len(bars)):
        closes = [bar.close for bar in bars[index - length : index]]
        middle = _mean(closes)
        if middle is None or middle == 0:
            continue
        variance = sum((close - middle) * (close - middle) for close in closes) / Decimal(length)
        stddev = variance.sqrt()
        upper = middle + band_std * stddev
        lower = middle - band_std * stddev
        bandwidth = (upper - lower) / middle * Decimal("100")
        bands[index] = (middle, upper, lower, bandwidth)
    return bands


def _squeeze_flags(
    bands: list[tuple[Decimal, Decimal, Decimal, Decimal] | None],
    lookback: int,
) -> list[bool]:
    flags = [False] * len(bands)
    for index in range(lookback, len(bands)):
        current = bands[index]
        if current is None:
            continue
        prior_widths = [band[3] for band in bands[index - lookback : index] if band is not None]
        if len(prior_widths) < lookback:
            continue
        threshold = _percentile_floor(prior_widths, Decimal("0.20"))
        flags[index] = current[3] <= threshold
    return flags


def _percentile_floor(values: list[Decimal], percentile: Decimal) -> Decimal:
    sorted_values = sorted(values)
    rank = int((Decimal(len(sorted_values)) * percentile).to_integral_value(rounding="ROUND_CEILING")) - 1
    return sorted_values[max(0, min(rank, len(sorted_values) - 1))]


def _ema_values(values: list[Decimal], length: int) -> list[Decimal | None]:
    ema: list[Decimal | None] = [None] * len(values)
    if len(values) < length:
        return ema
    seed = sum(values[:length], Decimal("0")) / Decimal(length)
    ema[length - 1] = seed
    multiplier = Decimal("2") / Decimal(length + 1)
    previous = seed
    for index in range(length, len(values)):
        current = (values[index] - previous) * multiplier + previous
        ema[index] = current
        previous = current
    return ema


def _summary_row(
    *,
    candidate_family_id: str,
    variant_label: str,
    symbol: str,
    side: SignalSide,
    signal_count: int,
    window_label: str,
    outcomes: Iterable[HistoricalForwardOutcome],
    data_note: str,
) -> dict[str, str]:
    complete = [outcome for outcome in outcomes if outcome.status == HistoricalForwardOutcomeStatus.COMPLETE]
    final_returns = [
        Decimal(str(outcome.return_time_curve[-1]["return_pct"]))
        for outcome in complete
        if outcome.return_time_curve
    ]
    mfe_values = [outcome.mfe_pct for outcome in complete if outcome.mfe_pct is not None]
    mae_values = [outcome.mae_pct for outcome in complete if outcome.mae_pct is not None]
    note = f"{variant_label}; complete={len(final_returns)}/{signal_count}; no costs; {data_note}"
    return {
        "candidate_family_id": candidate_family_id,
        "variant_label": variant_label,
        "symbol": symbol,
        "side": side.value,
        "signal_count": str(signal_count),
        "forward_window": window_label,
        "mean_forward_return": _fmt_decimal(_mean(final_returns)),
        "median_forward_return": _fmt_decimal(median(final_returns) if final_returns else None),
        "positive_rate": _fmt_decimal(_positive_rate(final_returns)),
        "mean_MFE": _fmt_decimal(_mean(mfe_values)),
        "mean_MAE": _fmt_decimal(_mean(mae_values)),
        "notes": note,
    }


def _signal_id(*, variant: str, symbol: str, side: SignalSide, timestamp_ms: int) -> str:
    compact_symbol = symbol.replace("/", "").replace(":", "")
    return f"{variant.lower()}-{SMOKE_VERSION}-{compact_symbol}-{side.value}-{timestamp_ms}"


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _positive_rate(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(sum(1 for value in values if value > 0)) / Decimal(len(values))


def _fmt_decimal(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    return str(value.quantize(Decimal("0.0001")))


def _print_table(rows: list[dict[str, str]]) -> None:
    columns = [
        "candidate_family_id",
        "variant_label",
        "symbol",
        "side",
        "signal_count",
        "forward_window",
        "mean_forward_return",
        "median_forward_return",
        "positive_rate",
        "mean_MFE",
        "mean_MAE",
        "notes",
    ]
    print(" | ".join(columns))
    print(" | ".join("---" for _ in columns))
    for row in rows:
        print(" | ".join(row[column] for column in columns))


if __name__ == "__main__":
    raise SystemExit(main())
