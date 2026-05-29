#!/usr/bin/env python3
"""Fast broad OHLCV-only smoke screen for trial-candidate triage.

Research-only: reads local historical candles, evaluates fixed signal variants,
and writes Markdown evidence. It does not persist to PG, call an exchange,
create campaign/admission facts, or authorize runtime use.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_directional_opportunity_smoke import (  # noqa: E402
    DEFAULT_TIMEFRAME,
    VARIANT_LABELS,
    _detect_signals,
    _load_symbol_bars,
)
from src.domain.historical_ohlcv import HistoricalOhlcvBar  # noqa: E402
from src.domain.strategy_family_signal import SignalSide  # noqa: E402


SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
VARIANTS = [
    "TB-001",
    "TB-002",
    "VB-001",
    "PC-001",
    "PC-002",
    "MR-001",
    "RB-001",
    "VI-001",
    "MI-001",
]
SIDES = [SignalSide.LONG, SignalSide.SHORT]
WINDOWS = {"24h": 24, "72h": 72, "7d": 168}
MIN_CANDIDATE_SIGNALS = 100


@dataclass(frozen=True)
class WindowStats:
    complete: int
    mean_return: Decimal | None
    median_return: Decimal | None
    positive_rate: Decimal | None
    mean_mfe: Decimal | None
    mean_mae: Decimal | None


@dataclass(frozen=True)
class ComboStats:
    variant: str
    symbol: str
    side: str
    signal_count: int
    windows: dict[str, WindowStats]
    score: Decimal
    data_note: str


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    combo_stats = _run_smoke(data_root=Path(args.data_root), sqlite_db=Path(args.sqlite_db))
    _write_evidence(output_dir / "evidence.md", combo_stats)
    _write_ranked_summary(output_dir / "ranked_summary.md", combo_stats)
    _write_candidate_report(output_dir / "trial_candidate_with_known_risks.md", combo_stats)

    print(f"wrote {output_dir / 'evidence.md'}")
    print(f"wrote {output_dir / 'ranked_summary.md'}")
    print(f"wrote {output_dir / 'trial_candidate_with_known_risks.md'}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument("--output-dir", default="reports/directional-opportunity-broad-smoke-20260529")
    return parser.parse_args()


def _run_smoke(*, data_root: Path, sqlite_db: Path) -> list[ComboStats]:
    rows: list[ComboStats] = []
    for symbol in SYMBOLS:
        bars, data_note = _load_symbol_bars(
            root=data_root,
            sqlite_db=sqlite_db,
            symbol=symbol,
            timeframe=DEFAULT_TIMEFRAME,
        )
        if not bars:
            continue
        for variant in VARIANTS:
            for side in SIDES:
                signals = _detect_signals(variant=variant, symbol=symbol, bars=bars, side=side)
                signal_indices = [signal.bar_index for signal in signals]
                windows = {
                    label: _window_stats(
                        bars=bars,
                        signal_indices=signal_indices,
                        side=side,
                        bars_ahead=bars_ahead,
                    )
                    for label, bars_ahead in WINDOWS.items()
                }
                rows.append(
                    ComboStats(
                        variant=variant,
                        symbol=symbol,
                        side=side.value,
                        signal_count=len(signals),
                        windows=windows,
                        score=_score(windows),
                        data_note=data_note,
                    )
                )
    return rows


def _window_stats(
    *,
    bars: list[HistoricalOhlcvBar],
    signal_indices: list[int],
    side: SignalSide,
    bars_ahead: int,
) -> WindowStats:
    final_returns: list[Decimal] = []
    mfe_values: list[Decimal] = []
    mae_values: list[Decimal] = []
    for index in signal_indices:
        if index + bars_ahead >= len(bars):
            continue
        entry_close = bars[index].close
        future = bars[index + 1 : index + 1 + bars_ahead]
        if not future or entry_close <= 0:
            continue
        if side == SignalSide.LONG:
            final_returns.append(_pct(future[-1].close - entry_close, entry_close))
            mfe_values.append(_pct(max(bar.high for bar in future) - entry_close, entry_close))
            mae_values.append(_pct(min(bar.low for bar in future) - entry_close, entry_close))
        else:
            final_returns.append(_pct(entry_close - future[-1].close, entry_close))
            mfe_values.append(_pct(entry_close - min(bar.low for bar in future), entry_close))
            mae_values.append(_pct(entry_close - max(bar.high for bar in future), entry_close))
    return WindowStats(
        complete=len(final_returns),
        mean_return=_mean(final_returns),
        median_return=median(final_returns) if final_returns else None,
        positive_rate=_positive_rate(final_returns),
        mean_mfe=_mean(mfe_values),
        mean_mae=_mean(mae_values),
    )


def _score(windows: dict[str, WindowStats]) -> Decimal:
    stats_72h = windows["72h"]
    stats_7d = windows["7d"]
    mean_72h = stats_72h.mean_return or Decimal("0")
    mean_7d = stats_7d.mean_return or Decimal("0")
    positive_72h = stats_72h.positive_rate or Decimal("0")
    positive_bonus = (positive_72h - Decimal("0.50")) * Decimal("2")
    mae_penalty = abs(stats_72h.mean_mae or Decimal("0")) * Decimal("0.15")
    return (mean_7d * Decimal("0.55")) + (mean_72h * Decimal("0.35")) + positive_bonus - mae_penalty


def _write_evidence(path: Path, combo_stats: list[ComboStats]) -> None:
    columns = [
        "candidate_family_id",
        "variant_label",
        "symbol",
        "side",
        "signal_count",
        "forward_window",
        "complete",
        "mean_forward_return",
        "median_forward_return",
        "positive_rate",
        "mean_MFE",
        "mean_MAE",
        "score",
        "notes",
    ]
    lines = [" | ".join(columns), " | ".join("---" for _ in columns)]
    for row in combo_stats:
        for window_label, stats in row.windows.items():
            values = {
                "candidate_family_id": row.variant,
                "variant_label": VARIANT_LABELS[row.variant],
                "symbol": row.symbol,
                "side": row.side,
                "signal_count": str(row.signal_count),
                "forward_window": window_label,
                "complete": f"{stats.complete}/{row.signal_count}",
                "mean_forward_return": _fmt(stats.mean_return),
                "median_forward_return": _fmt(stats.median_return),
                "positive_rate": _fmt(stats.positive_rate),
                "mean_MFE": _fmt(stats.mean_mfe),
                "mean_MAE": _fmt(stats.mean_mae),
                "score": _fmt(row.score),
                "notes": f"{VARIANT_LABELS[row.variant]}; no costs; {row.data_note}",
            }
            lines.append(" | ".join(values[column] for column in columns))
    path.write_text("\n".join(lines) + "\n")


def _write_ranked_summary(path: Path, combo_stats: list[ComboStats]) -> None:
    columns = [
        "rank",
        "candidate_family_id",
        "symbol",
        "side",
        "signal_count",
        "72h_mean",
        "72h_positive_rate",
        "72h_MFE",
        "72h_MAE",
        "7d_mean",
        "7d_positive_rate",
        "score",
    ]
    ranked = sorted(combo_stats, key=lambda row: row.score, reverse=True)
    lines = [" | ".join(columns), " | ".join("---" for _ in columns)]
    for index, row in enumerate(ranked, start=1):
        stats_72h = row.windows["72h"]
        stats_7d = row.windows["7d"]
        values = {
            "rank": str(index),
            "candidate_family_id": row.variant,
            "symbol": row.symbol,
            "side": row.side,
            "signal_count": str(row.signal_count),
            "72h_mean": _fmt(stats_72h.mean_return),
            "72h_positive_rate": _fmt(stats_72h.positive_rate),
            "72h_MFE": _fmt(stats_72h.mean_mfe),
            "72h_MAE": _fmt(stats_72h.mean_mae),
            "7d_mean": _fmt(stats_7d.mean_return),
            "7d_positive_rate": _fmt(stats_7d.positive_rate),
            "score": _fmt(row.score),
        }
        lines.append(" | ".join(values[column] for column in columns))
    path.write_text("\n".join(lines) + "\n")


def _write_candidate_report(path: Path, combo_stats: list[ComboStats]) -> None:
    ranked = [
        row
        for row in sorted(combo_stats, key=lambda item: item.score, reverse=True)
        if row.signal_count >= MIN_CANDIDATE_SIGNALS and (row.windows["72h"].positive_rate or Decimal("0")) >= Decimal("0.50")
    ]
    selected = _diversified_top(ranked, limit=3)
    lines = [
        "# Broad Directional Opportunity Smoke - Trial Candidates With Known Risks",
        "",
        "Scope: historical OHLCV-only broad smoke over BTC/ETH/SOL/BNB 1h local data. This is evidence triage only: no PG persistence, no admission/campaign creation, no runtime start, no exchange call, no live authorization.",
        "",
        f"Variants screened: {', '.join(VARIANTS)}.",
        f"Candidate filter: signal_count >= {MIN_CANDIDATE_SIGNALS}, 72h positive_rate >= 0.50, then score-ranked with symbol diversification.",
        "",
        "## Selected Candidates",
        "",
    ]
    for index, row in enumerate(selected, start=1):
        stats_24h = row.windows["24h"]
        stats_72h = row.windows["72h"]
        stats_7d = row.windows["7d"]
        lines.extend(
            [
                f"### {index}. {row.variant} {row.symbol} {row.side}",
                "",
                "- Evidence summary: "
                f"signals={row.signal_count}; 24h mean={_fmt(stats_24h.mean_return)} / win={_fmt(stats_24h.positive_rate)}; "
                f"72h mean={_fmt(stats_72h.mean_return)} / win={_fmt(stats_72h.positive_rate)} / MFE={_fmt(stats_72h.mean_mfe)} / MAE={_fmt(stats_72h.mean_mae)}; "
                f"7d mean={_fmt(stats_7d.mean_return)} / win={_fmt(stats_7d.positive_rate)}.",
                f"- Known risks: {_known_risks(row)}",
                "- Unknown risks: no cost/slippage/funding/liquidation modeling in this smoke; no rolling campaign ruin-rate yet; no random-entry or buy-and-hold baseline here; no owner-reviewed event examples yet.",
                f"- Recommended symbol / side: {row.symbol} / {row.side}.",
                f"- Suitable for bounded trial: {_bounded_trial_verdict(row)}",
                f"- Suggested max trial boundary: {_trial_boundary(row)}",
                "",
            ]
        )
    lines.extend(
        [
            "## Immediate Parks",
            "",
            "Short-side variants are generally weak in this OHLCV smoke and should not be promoted from this run alone. Treat negative 72h or 7d mean-return rows as park/revise, not candidate material.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def _diversified_top(rows: list[ComboStats], *, limit: int) -> list[ComboStats]:
    selected: list[ComboStats] = []
    used_symbols: set[str] = set()
    for row in rows:
        if row.symbol in used_symbols:
            continue
        selected.append(row)
        used_symbols.add(row.symbol)
        if len(selected) >= limit:
            return selected
    for row in rows:
        if row not in selected:
            selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def _known_risks(row: ComboStats) -> str:
    by_variant = {
        "TB-001": "fast breakout is false-breakout prone and can overtrade chop.",
        "TB-002": "slow breakout has sparse but regime-concentrated trend exposure.",
        "VB-001": "squeeze breakout can chase expansion after move exhaustion.",
        "PC-001": "EMA pullback can silently become generic long-beta continuation.",
        "PC-002": "slow EMA pullback may be late and can suffer large giveback.",
        "MR-001": "mean reversion can catch trend continuation against the position.",
        "RB-001": "range rejection can fail hard when boundary breaks turn real.",
        "VI-001": "volume impulse can enter after liquidation/news spikes.",
        "MI-001": "momentum impulse can buy/short local exhaustion after crowded move.",
    }
    return by_variant.get(row.variant, "variant risk not classified.")


def _bounded_trial_verdict(row: ComboStats) -> str:
    stats_72h = row.windows["72h"]
    stats_7d = row.windows["7d"]
    if row.score > Decimal("1") and (stats_72h.mean_return or Decimal("0")) > 0 and (stats_7d.mean_return or Decimal("0")) > 0:
        return "yes, only as trial_candidate_with_known_risks after Owner risk acceptance and Operation Layer gates."
    return "borderline; prefer continued fine screen before any bounded trial."


def _trial_boundary(row: ComboStats) -> str:
    if row.symbol.startswith("SOL") or row.symbol.startswith("BNB"):
        notional = "100 USDT"
    else:
        notional = "150 USDT"
    return (
        f"one symbol/side only, max notional {notional}, max realized loss 25 USDT, max 3 attempts, "
        "no add-to-loser, no symbol/side/leverage expansion, mandatory kill switch on cap breach or missing review evidence."
    )


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator * Decimal("100")).quantize(Decimal("0.0001"))


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


if __name__ == "__main__":
    raise SystemExit(main())
