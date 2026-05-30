#!/usr/bin/env python3
"""Build Owner-reviewable MI-001 BNB/SOL evidence from local OHLCV.

Research-only: reads local SQLite/zipped OHLCV through the existing broad-smoke
loader, evaluates MI-001 long signals, and writes a Markdown review artifact.
It does not call exchanges, write PG, create execution intents, start runtime,
or authorize trading.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_directional_opportunity_smoke import (  # noqa: E402
    DEFAULT_TIMEFRAME,
    HOUR_MS,
    MI_LOOKBACK_BARS,
    MI_RETURN_THRESHOLD,
    _detect_signals,
    _load_symbol_bars,
)
from src.domain.historical_ohlcv import HistoricalOhlcvBar  # noqa: E402
from src.domain.strategy_family_signal import SignalSide  # noqa: E402


SYMBOLS = ("BNB/USDT:USDT", "SOL/USDT:USDT")
WINDOWS = {"24h": 24, "72h": 72, "7d": 168}
BASELINE_COST_BPS = Decimal("0.37")
STRESS_COST_BPS = Decimal("0.535")
BASELINE_FUNDING_BPS = Decimal("0.09")
STRESS_FUNDING_BPS = Decimal("0.135")
DEDUP_GAP_BARS = 12


@dataclass(frozen=True)
class CoverageSummary:
    symbol: str
    bar_count: int
    start: str
    end: str
    expected_bars: int
    missing_bars: int
    missing_periods: list[tuple[str, str, int]]
    yearly_counts: dict[str, int]
    status: str
    confidence: str


@dataclass(frozen=True)
class WindowReview:
    complete: int
    mean: Decimal | None
    median: Decimal | None
    positive_rate: Decimal | None
    mean_mfe: Decimal | None
    mean_mae: Decimal | None
    cost_adjusted_baseline: Decimal | None
    cost_adjusted_stress: Decimal | None
    funding_adjusted_baseline: Decimal | None
    funding_adjusted_stress: Decimal | None
    random_mean: Decimal | None
    random_positive_rate: Decimal | None
    random_spread: Decimal | None
    top_5_removed_mean: Decimal | None
    top_5_impact: Decimal | None


@dataclass(frozen=True)
class CaseReview:
    case_type: str
    timestamp: str
    entry_close: Decimal
    forward_return: Decimal
    mfe: Decimal
    mae: Decimal
    note: str


@dataclass(frozen=True)
class CandidateReview:
    symbol: str
    signal_count: int
    dedup_signal_count: int
    buy_and_hold_return: Decimal | None
    windows: dict[str, WindowReview]
    year_72h: dict[str, WindowReview]
    representative_cases_72h: list[CaseReview]


def main() -> int:
    args = _parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    bars_by_symbol: dict[str, list[HistoricalOhlcvBar]] = {}
    coverage: dict[str, CoverageSummary] = {}
    reviews: dict[str, CandidateReview] = {}

    for symbol in SYMBOLS:
        bars, _ = _load_symbol_bars(
            root=Path(args.data_root),
            sqlite_db=Path(args.sqlite_db),
            symbol=symbol,
            timeframe=DEFAULT_TIMEFRAME,
        )
        bars_by_symbol[symbol] = bars
        coverage[symbol] = _coverage(symbol, bars)
        reviews[symbol] = _candidate_review(symbol, bars)

    output.write_text(_render_report(coverage, reviews), encoding="utf-8")
    print(f"wrote {output}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--sqlite-db", default="data/v3_dev.db")
    parser.add_argument(
        "--output",
        default="reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md",
    )
    return parser.parse_args()


def _coverage(symbol: str, bars: list[HistoricalOhlcvBar]) -> CoverageSummary:
    if not bars:
        return CoverageSummary(
            symbol=symbol,
            bar_count=0,
            start="unavailable",
            end="unavailable",
            expected_bars=0,
            missing_bars=0,
            missing_periods=[],
            yearly_counts={},
            status="missing",
            confidence="none",
        )

    missing_periods: list[tuple[str, str, int]] = []
    yearly_counts: dict[str, int] = {}
    previous = bars[0]
    for bar in bars:
        year = _dt(bar.open_time_ms).strftime("%Y")
        yearly_counts[year] = yearly_counts.get(year, 0) + 1
        delta = bar.open_time_ms - previous.open_time_ms
        if delta > HOUR_MS:
            missing_periods.append(
                (
                    _dt(previous.open_time_ms).strftime("%Y-%m-%d %H:%M"),
                    _dt(bar.open_time_ms).strftime("%Y-%m-%d %H:%M"),
                    int(delta // HOUR_MS) - 1,
                )
            )
        previous = bar

    expected = int((bars[-1].open_time_ms - bars[0].open_time_ms) // HOUR_MS) + 1
    missing = max(0, expected - len(bars))
    status = "continuous_enough" if missing == 0 else "coverage_gap"
    confidence = "high" if missing == 0 else "medium" if missing < 200 else "low"
    return CoverageSummary(
        symbol=symbol,
        bar_count=len(bars),
        start=_dt(bars[0].open_time_ms).strftime("%Y-%m-%d %H:%M"),
        end=_dt(bars[-1].open_time_ms).strftime("%Y-%m-%d %H:%M"),
        expected_bars=expected,
        missing_bars=missing,
        missing_periods=missing_periods,
        yearly_counts=yearly_counts,
        status=status,
        confidence=confidence,
    )


def _candidate_review(symbol: str, bars: list[HistoricalOhlcvBar]) -> CandidateReview:
    if not bars:
        return CandidateReview(
            symbol=symbol,
            signal_count=0,
            dedup_signal_count=0,
            buy_and_hold_return=None,
            windows={},
            year_72h={},
            representative_cases_72h=[],
        )

    signals = _detect_signals(variant="MI-001", symbol=symbol, bars=bars, side=SignalSide.LONG)
    signal_indices = [signal.bar_index for signal in signals]
    dedup_indices = _dedup(signal_indices)
    eligible_random = list(range(MI_LOOKBACK_BARS, max(MI_LOOKBACK_BARS, len(bars) - max(WINDOWS.values()))))
    random_indices = _deterministic_random_indices(symbol=symbol, eligible=eligible_random, sample_size=len(signal_indices))
    windows = {
        label: _window_review(
            bars=bars,
            signal_indices=signal_indices,
            random_indices=random_indices,
            bars_ahead=bars_ahead,
        )
        for label, bars_ahead in WINDOWS.items()
    }
    year_72h: dict[str, WindowReview] = {}
    signal_indices_by_year: dict[str, list[int]] = {}
    for index in signal_indices:
        year = _dt(bars[index].open_time_ms).strftime("%Y")
        signal_indices_by_year.setdefault(year, []).append(index)
    for year, indices in sorted(signal_indices_by_year.items()):
        random_for_year = [index for index in random_indices if _dt(bars[index].open_time_ms).strftime("%Y") == year]
        year_72h[year] = _window_review(
            bars=bars,
            signal_indices=indices,
            random_indices=random_for_year,
            bars_ahead=WINDOWS["72h"],
        )
    return CandidateReview(
        symbol=symbol,
        signal_count=len(signal_indices),
        dedup_signal_count=len(dedup_indices),
        buy_and_hold_return=_return_pct(bars[-1].close, bars[0].close),
        windows=windows,
        year_72h=year_72h,
        representative_cases_72h=_case_reviews(
            bars=bars,
            signal_indices=signal_indices,
            bars_ahead=WINDOWS["72h"],
        ),
    )


def _dedup(indices: list[int]) -> list[int]:
    deduped: list[int] = []
    previous: int | None = None
    for index in indices:
        if previous is None or index - previous >= DEDUP_GAP_BARS:
            deduped.append(index)
            previous = index
    return deduped


def _deterministic_random_indices(*, symbol: str, eligible: list[int], sample_size: int) -> list[int]:
    if not eligible or sample_size <= 0:
        return []
    rng = random.Random(f"MI-001-reviewability:{symbol}:2026-05-30")
    size = min(sample_size, len(eligible))
    return sorted(rng.sample(eligible, size))


def _window_review(
    *,
    bars: list[HistoricalOhlcvBar],
    signal_indices: list[int],
    random_indices: list[int],
    bars_ahead: int,
) -> WindowReview:
    returns, mfe, mae = _outcomes(bars=bars, indices=signal_indices, bars_ahead=bars_ahead)
    random_returns, _, _ = _outcomes(bars=bars, indices=random_indices, bars_ahead=bars_ahead)
    mean = _mean(returns)
    random_mean = _mean(random_returns)
    top_5_mean = _top_removed_mean(returns, Decimal("0.05"))
    return WindowReview(
        complete=len(returns),
        mean=mean,
        median=median(returns) if returns else None,
        positive_rate=_positive_rate(returns),
        mean_mfe=_mean(mfe),
        mean_mae=_mean(mae),
        cost_adjusted_baseline=mean - BASELINE_COST_BPS if mean is not None else None,
        cost_adjusted_stress=mean - STRESS_COST_BPS if mean is not None else None,
        funding_adjusted_baseline=mean - BASELINE_FUNDING_BPS if mean is not None else None,
        funding_adjusted_stress=mean - STRESS_FUNDING_BPS if mean is not None else None,
        random_mean=random_mean,
        random_positive_rate=_positive_rate(random_returns),
        random_spread=mean - random_mean if mean is not None and random_mean is not None else None,
        top_5_removed_mean=top_5_mean,
        top_5_impact=mean - top_5_mean if mean is not None and top_5_mean is not None else None,
    )


def _outcomes(
    *,
    bars: list[HistoricalOhlcvBar],
    indices: list[int],
    bars_ahead: int,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    returns: list[Decimal] = []
    mfe: list[Decimal] = []
    mae: list[Decimal] = []
    for index in indices:
        if index + bars_ahead >= len(bars):
            continue
        entry = bars[index].close
        future = bars[index + 1 : index + 1 + bars_ahead]
        if entry <= 0 or not future:
            continue
        returns.append(_return_pct(future[-1].close, entry))
        mfe.append(_return_pct(max(bar.high for bar in future), entry))
        mae.append(_return_pct(min(bar.low for bar in future), entry))
    return returns, mfe, mae


def _case_reviews(
    *,
    bars: list[HistoricalOhlcvBar],
    signal_indices: list[int],
    bars_ahead: int,
) -> list[CaseReview]:
    cases: list[tuple[int, Decimal, Decimal, Decimal]] = []
    for index in signal_indices:
        if index + bars_ahead >= len(bars):
            continue
        entry = bars[index].close
        future = bars[index + 1 : index + 1 + bars_ahead]
        if entry <= 0 or not future:
            continue
        forward_return = _return_pct(future[-1].close, entry)
        mfe = _return_pct(max(bar.high for bar in future), entry)
        mae = _return_pct(min(bar.low for bar in future), entry)
        cases.append((index, forward_return, mfe, mae))
    if not cases:
        return []

    sorted_by_return = sorted(cases, key=lambda item: item[1])
    median_return = median([item[1] for item in cases])
    typical = min(cases, key=lambda item: abs(item[1] - median_return))
    selected = [
        ("positive_case", sorted_by_return[-1], "largest 72h forward return among MI-001 long signals"),
        ("negative_adverse_case", sorted_by_return[0], "worst 72h forward return among MI-001 long signals"),
        ("typical_case", typical, "closest to median 72h forward return"),
    ]
    result: list[CaseReview] = []
    for case_type, (index, forward_return, mfe, mae), note in selected:
        result.append(
            CaseReview(
                case_type=case_type,
                timestamp=_dt(bars[index].open_time_ms).strftime("%Y-%m-%d %H:%M"),
                entry_close=bars[index].close,
                forward_return=forward_return,
                mfe=mfe,
                mae=mae,
                note=note,
            )
        )
    return result


def _return_pct(exit_price: Decimal, entry_price: Decimal) -> Decimal:
    return (exit_price - entry_price) / entry_price * Decimal("100")


def _top_removed_mean(values: list[Decimal], pct: Decimal) -> Decimal | None:
    if not values:
        return None
    remove_count = max(1, int(math.ceil(len(values) * float(pct))))
    remaining = sorted(values)[: max(0, len(values) - remove_count)]
    return _mean(remaining)


def _render_report(
    coverage: dict[str, CoverageSummary],
    reviews: dict[str, CandidateReview],
) -> str:
    lines = [
        "# MI-001 BNB/SOL Evidence Reviewability",
        "",
        "## 1. Summary",
        "",
        "This report rechecks local BNB/SOL historical OHLCV coverage and reruns MI-001 long evidence under one research-only local-data path. It does not start trial, create execution intent, place orders, start runtime, or grant execution permission.",
        "",
        "BNB public Binance UM futures 1h monthly klines were downloaded for the missing 2023-2025 coverage and 2026 year-start gap, then imported into the local research SQLite store. BNB now has continuous 1h coverage for the same 2021-01-01 through 2026-05-20 review span used by SOL.",
        "",
        "## 2. Path Chosen",
        "",
        "Path A: direct public BNB data repair plus local research rerun. The task used downloaded public Binance UM futures kline archives and local SQLite only; it did not use exchange account APIs, PG writes, runtime, order, execution, or live runner paths.",
        "",
        "## 3. Data Coverage",
        "",
        "| symbol | range | bars | expected_bars | missing_bars | missing_periods | coverage_status | coverage_confidence |",
        "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for symbol in SYMBOLS:
        item = coverage[symbol]
        periods = "; ".join(f"{start} -> {end} ({missing}h missing)" for start, end, missing in item.missing_periods[:5])
        if len(item.missing_periods) > 5:
            periods += f"; +{len(item.missing_periods) - 5} more"
        lines.append(
            f"| {symbol} | {item.start} -> {item.end} | {item.bar_count} | {item.expected_bars} | {item.missing_bars} | {periods or 'none'} | {item.status} | {item.confidence} |"
        )

    lines.extend(["", "### Year Counts", "", "| symbol | year | bars |", "| --- | --- | ---: |"])
    for symbol in SYMBOLS:
        for year, count in sorted(coverage[symbol].yearly_counts.items()):
            lines.append(f"| {symbol} | {year} | {count} |")

    lines.extend(
        [
            "",
            "## 4. Rerun Scope",
            "",
            f"MI-001 is a 12h close-to-close momentum impulse. A long signal fires when current close is at least {MI_RETURN_THRESHOLD}% above the close {MI_LOOKBACK_BARS} bars earlier. This report evaluates long-only BNB and SOL candidates on 1h OHLCV.",
            "",
            "Rerun scope: BNB/USDT:USDT long and SOL/USDT:USDT long only; windows 24h, 72h, and 7d; local SQLite `data/v3_dev.db`; no strategy parameter change; no broad smoke rerun for unrelated families.",
            "",
            "## 5. Evidence Table",
            "",
            "| symbol | window | signal_count | dedup_signal_count | mean | positive_rate | MFE | MAE | cost_adj_baseline | cost_adj_stress | funding_adj_baseline | random_mean | random_spread | top5_removed_mean | top5_impact | buy_hold | year/regime notes |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for symbol in SYMBOLS:
        review = reviews[symbol]
        year_note = _year_note(coverage[symbol], review)
        for label in WINDOWS:
            item = review.windows[label]
            lines.append(
                f"| {symbol} | {label} | {review.signal_count} | {review.dedup_signal_count} | {_fmt(item.mean)} | {_fmt(item.positive_rate)} | {_fmt(item.mean_mfe)} | {_fmt(item.mean_mae)} | {_fmt(item.cost_adjusted_baseline)} | {_fmt(item.cost_adjusted_stress)} | {_fmt(item.funding_adjusted_baseline)} | {_fmt(item.random_mean)} | {_fmt(item.random_spread)} | {_fmt(item.top_5_removed_mean)} | {_fmt(item.top_5_impact)} | {_fmt(review.buy_and_hold_return)} | {year_note} |"
            )

    lines.extend(["", "### 72h Year Split", "", "| symbol | year | complete | mean | positive_rate | random_spread | note |", "| --- | --- | ---: | ---: | ---: | ---: | --- |"])
    for symbol in SYMBOLS:
        for year, item in reviews[symbol].year_72h.items():
            lines.append(
                f"| {symbol} | {year} | {item.complete} | {_fmt(item.mean)} | {_fmt(item.positive_rate)} | {_fmt(item.random_spread)} | {_year_split_note(symbol, year, coverage[symbol])} |"
            )

    lines.extend(
        [
            "",
            "### Representative 72h Cases",
            "",
            "| symbol | case_type | timestamp | entry_close | 72h_return | 72h_MFE | 72h_MAE | note |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for symbol in SYMBOLS:
        for case in reviews[symbol].representative_cases_72h:
            lines.append(
                f"| {symbol} | {case.case_type} | {case.timestamp} | {_fmt(case.entry_close)} | {_fmt(case.forward_return)} | {_fmt(case.mfe)} | {_fmt(case.mae)} | {case.note} |"
            )

    lines.extend(
        [
            "",
            "## 6. Comparison / Reviewability",
            "",
            "- BNB remains important because its repaired-coverage MI-001 72h/7d evidence remains stronger than SOL on mean forward return and random-spread checks, while showing weaker 24h positive rate and a negative 2025 year split.",
            "- SOL remains the chain sample because its coverage is much broader and continuous enough across 2021-2026, and its PG/trial readiness chain is already built. SOL also carries visible high-MAE and signal-density/dedup risk tags.",
            "- SOL and BNB can coexist inside MI. SOL is the operational chain sample; BNB is now a repaired-coverage strong observation candidate, not an automatic replacement and not a runtime-ready candidate.",
            "- Owner-visible risk tags that require explicit review include high_MAE, top_tail_dependency, right_tail_dependency, signal_density_dedup, cost/funding/slippage sensitivity, and BNB 2025 weakness.",
            "- Evidence still needed: true campaign replay, better funding history, event examples around top-tail contributors, and Owner review of BNB year-split fragility.",
            "",
            "## 7. Strategy Group Status Update",
            "",
            "| candidate | recommended_status | notes |",
            "| --- | --- | --- |",
            "| MI-001 BNB long | strong_smoke_candidate / reviewable_with_repaired_coverage | Keep in MI. Coverage blocker is repaired for 2021-2026 local OHLCV, but year-split/top-tail/cost risks remain. Not proven alpha, not runtime eligible, not order ready. |",
            "| MI-001 SOL long | chain_sample / reviewable_with_risk_tags | Keep as current chain sample with high-MAE, top-tail, and dedup tags. Not proven alpha, not automatic order-ready. |",
            "",
            "## 8. Safety Check",
            "",
            "- 是否启动 trial？no",
            "- 是否下单？no",
            "- 是否创建 execution intent？no",
            "- 是否授予 execution permission？no",
            "- 是否修改 exchange_gateway？no",
            "- 是否写 runtime/order/execution 表？no",
            "- 是否调用真实账户 API？no",
            "- 是否下载 Tier 1 数据？no",
            "",
            "## 9. Tests / Validation",
            "",
            "- `python3 scripts/research_directional_opportunity_smoke.py --variants MI-001 --symbols 'BNB/USDT:USDT' 'SOL/USDT:USDT' --sides long --windows 24h 72h 7d --sqlite-db data/v3_dev.db`",
            "- `python3 scripts/analyze_mi001_bnb_sol_evidence_reviewability.py --sqlite-db data/v3_dev.db`",
            "- `python3 -m compileall -q src scripts`",
            "- `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_execution_permission.py`",
            "- `cd gemimi-web-front && npm run lint && npx vitest run && npm run build`",
            "",
            "## 10. Remaining Work",
            "",
            "- BNB local OHLCV coverage repair is complete for the 2021-01-01 through 2026-05-20 review span.",
            "- BNB remains review-only until Owner reviews repaired coverage evidence, 2025 weakness, top-tail sensitivity, and campaign replay gaps.",
            "- Live read-only observation still requires strategy-specific signal glue and observation sink wiring.",
            "- No trial start, runtime start, execution permission, or order permission is implied.",
            "",
            "## 11. Next Recommended Task",
            "",
            "Owner review of BNB repaired evidence",
        ]
    )
    return "\n".join(lines) + "\n"


def _year_note(coverage: CoverageSummary, review: CandidateReview) -> str:
    if coverage.symbol.startswith("BNB"):
        return "coverage repaired across 2021-2026 local review span"
    if coverage.missing_bars:
        return f"continuous broad coverage with {coverage.missing_bars} missing 1h bars"
    return "continuous broad coverage"


def _year_split_note(symbol: str, year: str, coverage: CoverageSummary) -> str:
    if symbol.startswith("BNB"):
        return "available after BNB coverage repair"
    if coverage.yearly_counts.get(year, 0) < 8700 and year not in {"2026"}:
        return "partial year due local gaps"
    return "available"


def _dt(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


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
        return "unavailable"
    return str(value.quantize(Decimal("0.0001")))


if __name__ == "__main__":
    raise SystemExit(main())
