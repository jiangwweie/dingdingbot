#!/usr/bin/env python3
"""One-off analysis for Directional Opportunity smoke evidence.

Reads the existing smoke evidence table and local 1h OHLCV, then writes two
compact Markdown artifacts. Research-only; no persistence or runtime wiring.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_directional_opportunity_smoke import (  # noqa: E402
    DEFAULT_TIMEFRAME,
    SMOKE_VERSION,
    _detect_signals,
    _load_symbol_bars,
)
from src.domain.forward_outcome_review import calculate_forward_outcomes  # noqa: E402
from src.domain.historical_signal_evaluation import HistoricalForwardOutcomeStatus  # noqa: E402
from src.domain.strategy_family_signal import SignalSide  # noqa: E402


SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
VARIANTS = ["TB-001", "VB-001", "PC-001"]
SIDES = ["long", "short"]
WINDOWS = {"72h": 72, "7d": 168}


def main() -> int:
    args = _parse_args()
    evidence_rows = _read_markdown_table(Path(args.evidence))
    compact_rows = _compact_summary_rows(evidence_rows)
    year_rows = _tb001_long_year_rows(data_root=Path(args.data_root), sqlite_db=Path(args.sqlite_db))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    compact_path = output_dir / "compact_summary.md"
    year_path = output_dir / "tb001_long_year_split.md"

    _write_table(
        compact_path,
        [
            "candidate_family_id",
            "symbol",
            "side",
            "signal_count",
            "72h mean_forward_return",
            "72h positive_rate",
            "7d mean_forward_return",
            "7d positive_rate",
        ],
        compact_rows,
    )
    _write_table(
        year_path,
        [
            "year",
            "symbol",
            "signal_count",
            "72h mean_forward_return",
            "72h positive_rate",
            "7d mean_forward_return",
            "7d positive_rate",
            "notes",
        ],
        year_rows,
    )

    print(f"wrote {compact_path}")
    print(f"wrote {year_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        default="reports/directional-opportunity-smoke-20260529/evidence.md",
    )
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument(
        "--output-dir",
        default="reports/directional-opportunity-smoke-20260529",
    )
    return parser.parse_args()


def _read_markdown_table(path: Path) -> list[dict[str, str]]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    header = [part.strip() for part in lines[0].split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        values = [part.strip() for part in line.split("|")]
        if len(values) != len(header):
            continue
        rows.append(dict(zip(header, values)))
    return rows


def _compact_summary_rows(evidence_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for row in evidence_rows:
        window = row.get("forward_window", "")
        if window not in WINDOWS:
            continue
        key = (row["candidate_family_id"], row["symbol"], row["side"], window)
        by_key[key] = row

    rows: list[dict[str, str]] = []
    for variant in VARIANTS:
        for symbol in SYMBOLS:
            for side in SIDES:
                row_72h = by_key.get((variant, symbol, side, "72h"))
                row_7d = by_key.get((variant, symbol, side, "7d"))
                rows.append(
                    {
                        "candidate_family_id": variant,
                        "symbol": symbol,
                        "side": side,
                        "signal_count": _first_present(row_72h, row_7d, "signal_count"),
                        "72h mean_forward_return": _field_or_missing(row_72h, "mean_forward_return"),
                        "72h positive_rate": _field_or_missing(row_72h, "positive_rate"),
                        "7d mean_forward_return": _field_or_missing(row_7d, "mean_forward_return"),
                        "7d positive_rate": _field_or_missing(row_7d, "positive_rate"),
                    }
                )
    return rows


def _tb001_long_year_rows(*, data_root: Path, sqlite_db: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for symbol in SYMBOLS:
        bars, data_note = _load_symbol_bars(
            root=data_root,
            sqlite_db=sqlite_db,
            symbol=symbol,
            timeframe=DEFAULT_TIMEFRAME,
        )
        if not bars:
            rows.append(_missing_year_row(symbol, "missing local 1h data"))
            continue

        signals = _detect_signals(variant="TB-001", symbol=symbol, bars=bars, side=SignalSide.LONG)
        by_year: dict[int, list] = defaultdict(list)
        for signal in signals:
            year = datetime.fromtimestamp(signal.signal_output.timestamp_ms / 1000, tz=timezone.utc).year
            by_year[year].append(signal)

        for year in sorted(by_year):
            year_signals = by_year[year]
            outcomes_by_window = {window: [] for window in WINDOWS}
            max_window = max(WINDOWS.values())
            for signal in year_signals:
                future_bars = bars[signal.bar_index + 1 : signal.bar_index + 1 + max_window]
                outcomes = calculate_forward_outcomes(
                    run_id=f"TB-001-{SMOKE_VERSION}-year-split",
                    signal_output=signal.signal_output,
                    entry_bar=bars[signal.bar_index],
                    future_bars=future_bars,
                    created_at_ms=signal.signal_output.timestamp_ms,
                    windows=WINDOWS,
                )
                for outcome in outcomes:
                    outcomes_by_window[outcome.window_label].append(outcome)
            rows.append(_year_summary_row(year, symbol, len(year_signals), outcomes_by_window, data_note))
    return rows


def _year_summary_row(
    year: int,
    symbol: str,
    signal_count: int,
    outcomes_by_window: dict[str, list],
    data_note: str,
) -> dict[str, str]:
    metrics = {window: _window_metrics(outcomes_by_window[window]) for window in WINDOWS}
    notes = "; ".join(
        [
            f"{window}_complete={metrics[window]['complete']}/{signal_count}"
            for window in WINDOWS
        ]
    )
    return {
        "year": str(year),
        "symbol": symbol,
        "signal_count": str(signal_count),
        "72h mean_forward_return": metrics["72h"]["mean"],
        "72h positive_rate": metrics["72h"]["positive_rate"],
        "7d mean_forward_return": metrics["7d"]["mean"],
        "7d positive_rate": metrics["7d"]["positive_rate"],
        "notes": f"{notes}; no costs; {data_note}",
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


def _missing_year_row(symbol: str, note: str) -> dict[str, str]:
    return {
        "year": "missing",
        "symbol": symbol,
        "signal_count": "missing",
        "72h mean_forward_return": "missing",
        "72h positive_rate": "missing",
        "7d mean_forward_return": "missing",
        "7d positive_rate": "missing",
        "notes": note,
    }


def _field_or_missing(row: dict[str, str] | None, field: str) -> str:
    if row is None:
        return "missing"
    return row.get(field) or "missing"


def _first_present(row_a: dict[str, str] | None, row_b: dict[str, str] | None, field: str) -> str:
    return _field_or_missing(row_a, field) if row_a is not None else _field_or_missing(row_b, field)


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


def _write_table(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    lines = [" | ".join(columns), " | ".join("---" for _ in columns)]
    lines.extend(" | ".join(row[column] for column in columns) for row in rows)
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
