#!/usr/bin/env python3
"""One-off TB-001 long year x regime evidence slice for ETH and SOL."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_tb001_long_regime_split import (  # noqa: E402
    BTC_DOWN_OR_FLAT,
    BTC_UP,
    SYMBOL_ABOVE_EMA,
    SYMBOL_BELOW_OR_EQUAL_EMA,
    _btc_200h_regime_by_timestamp,
)
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


SYMBOLS = ["ETH/USDT:USDT", "SOL/USDT:USDT"]
WINDOWS = {"72h": 72, "7d": 168}


def main() -> int:
    args = _parse_args()
    data_root = Path(args.data_root)
    sqlite_db = Path(args.sqlite_db)
    output_path = Path(args.output)

    btc_bars, _ = _load_symbol_bars(
        root=data_root,
        sqlite_db=sqlite_db,
        symbol="BTC/USDT:USDT",
        timeframe=DEFAULT_TIMEFRAME,
    )
    btc_regime_by_timestamp = _btc_200h_regime_by_timestamp(btc_bars)

    btc_rows: list[dict[str, str]] = []
    symbol_rows: list[dict[str, str]] = []
    rf1_rows: list[dict[str, str]] = []

    for symbol in SYMBOLS:
        bars, data_note = _load_symbol_bars(
            root=data_root,
            sqlite_db=sqlite_db,
            symbol=symbol,
            timeframe=DEFAULT_TIMEFRAME,
        )
        if not bars:
            continue

        signals = _detect_signals(variant="TB-001", symbol=symbol, bars=bars, side=SignalSide.LONG)
        outcomes_by_signal_id = _outcomes_by_signal_id(signals=signals, bars=bars)
        ema200 = _ema_values([bar.close for bar in bars], 200)
        years = sorted({year_of(signal.signal_output.timestamp_ms) for signal in signals})

        btc_groups: dict[tuple[int, str], list[str]] = defaultdict(list)
        symbol_groups: dict[tuple[int, str], list[str]] = defaultdict(list)
        rf1_groups: dict[int, list[str]] = defaultdict(list)
        btc_missing_by_year: dict[int, int] = defaultdict(int)
        symbol_missing_by_year: dict[int, int] = defaultdict(int)
        rf1_missing_by_year: dict[int, int] = defaultdict(int)

        for signal in signals:
            year = year_of(signal.signal_output.timestamp_ms)
            signal_id = signal.signal_output.signal_id

            btc_regime = btc_regime_by_timestamp.get(signal.signal_output.timestamp_ms)
            if btc_regime is None:
                btc_missing_by_year[year] += 1
            else:
                btc_groups[(year, btc_regime)].append(signal_id)

            ema_value = ema200[signal.bar_index]
            if ema_value is None:
                symbol_missing_by_year[year] += 1
                symbol_regime = None
            else:
                current_close = bars[signal.bar_index].close
                symbol_regime = SYMBOL_ABOVE_EMA if current_close > ema_value else SYMBOL_BELOW_OR_EQUAL_EMA
                symbol_groups[(year, symbol_regime)].append(signal_id)

            if btc_regime is None or symbol_regime is None:
                rf1_missing_by_year[year] += 1
            elif btc_regime == BTC_UP and symbol_regime == SYMBOL_ABOVE_EMA:
                rf1_groups[year].append(signal_id)

        for year in years:
            for regime in [BTC_UP, BTC_DOWN_OR_FLAT]:
                btc_rows.append(
                    _summary_row(
                        year=year,
                        symbol=symbol,
                        regime_field="btc_regime",
                        regime=regime,
                        signal_ids=btc_groups.get((year, regime), []),
                        outcomes_by_signal_id=outcomes_by_signal_id,
                        note_suffix=_note_suffix(
                            data_note=data_note,
                            missing_count=btc_missing_by_year.get(year, 0),
                        ),
                    )
                )
            for regime in [SYMBOL_ABOVE_EMA, SYMBOL_BELOW_OR_EQUAL_EMA]:
                symbol_rows.append(
                    _summary_row(
                        year=year,
                        symbol=symbol,
                        regime_field="symbol_regime",
                        regime=regime,
                        signal_ids=symbol_groups.get((year, regime), []),
                        outcomes_by_signal_id=outcomes_by_signal_id,
                        note_suffix=_note_suffix(
                            data_note=data_note,
                            missing_count=symbol_missing_by_year.get(year, 0),
                        ),
                    )
                )
            rf1_rows.append(
                _rf1_row(
                    year=year,
                    symbol=symbol,
                    signal_ids=rf1_groups.get(year, []),
                    outcomes_by_signal_id=outcomes_by_signal_id,
                    note_suffix=_note_suffix(
                        data_note=data_note,
                        missing_count=rf1_missing_by_year.get(year, 0),
                    ),
                )
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_report(output_path, btc_rows, symbol_rows, rf1_rows)
    print(f"wrote {output_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument(
        "--output",
        default="reports/directional-opportunity-smoke-20260529/tb001_long_year_regime_cross.md",
    )
    return parser.parse_args()


def year_of(timestamp_ms: int) -> int:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).year


def _outcomes_by_signal_id(*, signals: list, bars: list) -> dict[str, dict[str, object]]:
    outcomes_by_signal_id: dict[str, dict[str, object]] = {}
    max_window = max(WINDOWS.values())
    for signal in signals:
        future_bars = bars[signal.bar_index + 1 : signal.bar_index + 1 + max_window]
        outcomes = calculate_forward_outcomes(
            run_id=f"TB-001-{SMOKE_VERSION}-year-regime-cross",
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
    year: int,
    symbol: str,
    regime_field: str,
    regime: str,
    signal_ids: list[str],
    outcomes_by_signal_id: dict[str, dict[str, object]],
    note_suffix: str,
) -> dict[str, str]:
    row = _metrics_row(
        year=year,
        symbol=symbol,
        signal_ids=signal_ids,
        outcomes_by_signal_id=outcomes_by_signal_id,
        note_suffix=note_suffix,
    )
    row[regime_field] = regime
    return row


def _rf1_row(
    *,
    year: int,
    symbol: str,
    signal_ids: list[str],
    outcomes_by_signal_id: dict[str, dict[str, object]],
    note_suffix: str,
) -> dict[str, str]:
    return _metrics_row(
        year=year,
        symbol=symbol,
        signal_ids=signal_ids,
        outcomes_by_signal_id=outcomes_by_signal_id,
        note_suffix=f"RF1=btc_200h_up+symbol_above_ema200; {note_suffix}",
    )


def _metrics_row(
    *,
    year: int,
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
        "year": str(year),
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


def _note_suffix(*, data_note: str, missing_count: int) -> str:
    if missing_count:
        return f"{data_note}; regime_missing={missing_count}"
    return data_note


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


def _write_report(
    output_path: Path,
    btc_rows: list[dict[str, str]],
    symbol_rows: list[dict[str, str]],
    rf1_rows: list[dict[str, str]],
) -> None:
    common = [
        "year",
        "symbol",
        "signal_count",
        "72h mean_forward_return",
        "72h positive_rate",
        "7d mean_forward_return",
        "7d positive_rate",
        "notes",
    ]
    btc_columns = ["year", "symbol", "btc_regime", *common[2:]]
    symbol_columns = ["year", "symbol", "symbol_regime", *common[2:]]
    lines = [
        "# TB-001 Long Year x Regime Cross",
        "",
        "Research-only evidence. Candidate fixed to TB-001, side fixed to long, ETH/SOL only, no costs, no baseline, no campaign replay.",
        "",
        "## Year x BTC 200h regime",
        "",
        *_table_lines(btc_columns, btc_rows),
        "",
        "## Year x symbol EMA200 regime",
        "",
        *_table_lines(symbol_columns, symbol_rows),
        "",
        "## TB-001-RF1 slice",
        "",
        *_table_lines(common, rf1_rows),
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
