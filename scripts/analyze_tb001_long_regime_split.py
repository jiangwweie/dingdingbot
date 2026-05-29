#!/usr/bin/env python3
"""One-off TB-001 long OHLCV regime split.

Research-only script. It reads local 1h candles, reuses the existing TB-001
smoke signal and forward-outcome logic, and writes one Markdown evidence file.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_directional_opportunity_smoke import (  # noqa: E402
    DEFAULT_TIMEFRAME,
    SMOKE_VERSION,
    _detect_signals,
    _ema_values,
    _load_symbol_bars,
)
from src.domain.forward_outcome_review import calculate_forward_outcomes  # noqa: E402
from src.domain.historical_signal_evaluation import HistoricalForwardOutcomeStatus  # noqa: E402
from src.domain.strategy_family_signal import SignalSide  # noqa: E402


SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
WINDOWS = {"72h": 72, "7d": 168}
BTC_UP = "btc_200h_up"
BTC_DOWN_OR_FLAT = "btc_200h_down_or_flat"
SYMBOL_ABOVE_EMA = "symbol_above_ema200"
SYMBOL_BELOW_OR_EQUAL_EMA = "symbol_below_or_equal_ema200"


def main() -> int:
    args = _parse_args()
    data_root = Path(args.data_root)
    sqlite_db = Path(args.sqlite_db)
    output_path = Path(args.output)

    bars_by_symbol: dict[str, list] = {}
    data_notes: dict[str, str] = {}
    for symbol in SYMBOLS:
        bars, data_note = _load_symbol_bars(
            root=data_root,
            sqlite_db=sqlite_db,
            symbol=symbol,
            timeframe=DEFAULT_TIMEFRAME,
        )
        bars_by_symbol[symbol] = bars
        data_notes[symbol] = data_note

    btc_regime_by_timestamp = _btc_200h_regime_by_timestamp(bars_by_symbol["BTC/USDT:USDT"])
    btc_rows: list[dict[str, str]] = []
    symbol_rows: list[dict[str, str]] = []

    for symbol in SYMBOLS:
        bars = bars_by_symbol[symbol]
        if not bars:
            btc_rows.extend(_missing_rows(symbol, [BTC_UP, BTC_DOWN_OR_FLAT], "missing local 1h data"))
            symbol_rows.extend(
                _missing_rows(symbol, [SYMBOL_ABOVE_EMA, SYMBOL_BELOW_OR_EQUAL_EMA], "missing local 1h data")
            )
            continue

        signals = _detect_signals(variant="TB-001", symbol=symbol, bars=bars, side=SignalSide.LONG)
        outcomes_by_signal_id = _outcomes_by_signal_id(signals=signals, bars=bars)
        signal_by_id = {signal.signal_output.signal_id: signal for signal in signals}

        btc_groups: dict[str, list[str]] = defaultdict(list)
        btc_missing = 0
        for signal in signals:
            regime = btc_regime_by_timestamp.get(signal.signal_output.timestamp_ms)
            if regime is None:
                btc_missing += 1
                continue
            btc_groups[regime].append(signal.signal_output.signal_id)
        for regime in [BTC_UP, BTC_DOWN_OR_FLAT]:
            btc_rows.append(
                _summary_row(
                    regime=regime,
                    symbol=symbol,
                    signal_ids=btc_groups.get(regime, []),
                    outcomes_by_signal_id=outcomes_by_signal_id,
                    note_suffix=_note_suffix(symbol=symbol, data_note=data_notes[symbol], missing_count=btc_missing),
                )
            )

        symbol_groups: dict[str, list[str]] = defaultdict(list)
        symbol_missing = 0
        ema200 = _ema_values([bar.close for bar in bars], 200)
        for signal_id, signal in signal_by_id.items():
            ema_value = ema200[signal.bar_index]
            if ema_value is None:
                symbol_missing += 1
                continue
            current_close = bars[signal.bar_index].close
            regime = SYMBOL_ABOVE_EMA if current_close > ema_value else SYMBOL_BELOW_OR_EQUAL_EMA
            symbol_groups[regime].append(signal_id)
        for regime in [SYMBOL_ABOVE_EMA, SYMBOL_BELOW_OR_EQUAL_EMA]:
            symbol_rows.append(
                _summary_row(
                    regime=regime,
                    symbol=symbol,
                    signal_ids=symbol_groups.get(regime, []),
                    outcomes_by_signal_id=outcomes_by_signal_id,
                    note_suffix=_note_suffix(symbol=symbol, data_note=data_notes[symbol], missing_count=symbol_missing),
                )
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(output_path, btc_rows, symbol_rows)
    print(f"wrote {output_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument(
        "--output",
        default="reports/directional-opportunity-smoke-20260529/tb001_long_regime_split.md",
    )
    return parser.parse_args()


def _btc_200h_regime_by_timestamp(btc_bars: list) -> dict[int, str]:
    regimes: dict[int, str] = {}
    for index in range(200, len(btc_bars)):
        current = btc_bars[index]
        prior = btc_bars[index - 200]
        btc_ret_200h = (current.close / prior.close) - Decimal("1")
        regimes[current.open_time_ms] = BTC_UP if btc_ret_200h > 0 else BTC_DOWN_OR_FLAT
    return regimes


def _outcomes_by_signal_id(*, signals: list, bars: list) -> dict[str, dict[str, object]]:
    outcomes_by_signal_id: dict[str, dict[str, object]] = {}
    max_window = max(WINDOWS.values())
    for signal in signals:
        future_bars = bars[signal.bar_index + 1 : signal.bar_index + 1 + max_window]
        outcomes = calculate_forward_outcomes(
            run_id=f"TB-001-{SMOKE_VERSION}-regime-split",
            signal_output=signal.signal_output,
            entry_bar=bars[signal.bar_index],
            future_bars=future_bars,
            created_at_ms=signal.signal_output.timestamp_ms,
            windows=WINDOWS,
        )
        outcomes_by_signal_id[signal.signal_output.signal_id] = {
            outcome.window_label: outcome for outcome in outcomes
        }
    return outcomes_by_signal_id


def _summary_row(
    *,
    regime: str,
    symbol: str,
    signal_ids: list[str],
    outcomes_by_signal_id: dict[str, dict[str, object]],
    note_suffix: str,
) -> dict[str, str]:
    metrics = {
        window: _window_metrics(
            [
                outcomes_by_signal_id[signal_id][window]
                for signal_id in signal_ids
                if signal_id in outcomes_by_signal_id and window in outcomes_by_signal_id[signal_id]
            ]
        )
        for window in WINDOWS
    }
    complete_notes = "; ".join(
        f"{window}_complete={metrics[window]['complete']}/{len(signal_ids)}" for window in WINDOWS
    )
    return {
        "regime": regime,
        "symbol": symbol,
        "signal_count": str(len(signal_ids)),
        "72h mean_forward_return": metrics["72h"]["mean"],
        "72h positive_rate": metrics["72h"]["positive_rate"],
        "7d mean_forward_return": metrics["7d"]["mean"],
        "7d positive_rate": metrics["7d"]["positive_rate"],
        "notes": f"{complete_notes}; no costs; {note_suffix}",
    }


def _window_metrics(outcomes: list) -> dict[str, str]:
    complete = [
        outcome
        for outcome in outcomes
        if outcome.status == HistoricalForwardOutcomeStatus.COMPLETE and outcome.return_time_curve
    ]
    returns = [Decimal(str(outcome.return_time_curve[-1]["return_pct"])) for outcome in complete]
    return {
        "complete": str(len(complete)),
        "mean": _fmt(_mean(returns)),
        "positive_rate": _fmt(_positive_rate(returns)),
    }


def _missing_rows(symbol: str, regimes: list[str], note: str) -> list[dict[str, str]]:
    return [
        {
            "regime": regime,
            "symbol": symbol,
            "signal_count": "missing",
            "72h mean_forward_return": "missing",
            "72h positive_rate": "missing",
            "7d mean_forward_return": "missing",
            "7d positive_rate": "missing",
            "notes": note,
        }
        for regime in regimes
    ]


def _note_suffix(*, symbol: str, data_note: str, missing_count: int) -> str:
    parts = [data_note]
    if missing_count:
        parts.append(f"regime_missing={missing_count}")
    if symbol == "BNB/USDT:USDT":
        parts.append("data coverage incomplete")
    return "; ".join(parts)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _positive_rate(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(sum(1 for value in values if value > 0)) / Decimal(len(values))


def _fmt(value: Decimal | None) -> str:
    if value is None:
        return "missing"
    return str(value.quantize(Decimal("0.0001")))


def _write_report(output_path: Path, btc_rows: list[dict[str, str]], symbol_rows: list[dict[str, str]]) -> None:
    columns = [
        "regime",
        "symbol",
        "signal_count",
        "72h mean_forward_return",
        "72h positive_rate",
        "7d mean_forward_return",
        "7d positive_rate",
        "notes",
    ]
    lines = [
        "# TB-001 Long Regime Split",
        "",
        "Research-only evidence. Candidate fixed to TB-001, side fixed to long, no costs, no baseline, no campaign replay.",
        "",
        "## BTC 200h regime split",
        "",
        *_table_lines(columns, btc_rows),
        "",
        "## Symbol EMA200 regime split",
        "",
        *_table_lines(columns, symbol_rows),
        "",
    ]
    output_path.write_text("\n".join(lines))


def _table_lines(columns: list[str], rows: list[dict[str, str]]) -> list[str]:
    return [
        " | ".join(columns),
        " | ".join("---" for _ in columns),
        *[" | ".join(row[column] for column in columns) for row in rows],
    ]


if __name__ == "__main__":
    raise SystemExit(main())
