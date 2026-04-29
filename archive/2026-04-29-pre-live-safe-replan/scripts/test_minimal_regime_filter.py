#!/usr/bin/env python3
"""
最小 regime filter 候选验证（研究层外部 gating）

不修改回测引擎：
1. 先跑当前结构冻结主线回测
2. 再用本地 1d 数据计算 EMA60
3. 用“上一根已闭合 1d close > 1d EMA60”对交易做外部过滤

注意：
- 这是研究层 proxy 分析，不是引擎内正式回测结果
- 过滤后的 PnL / Trades / Win Rate 是准确的
- Max DD / Sharpe 为基于仓位 realized_pnl 的 proxy，不等同于 true_equity 口径
"""
import asyncio
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.backtester import Backtester
from src.domain.indicators import EMACalculator
from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    OrderStrategy,
    RiskConfig,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository


SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"

BNB9_SLIPPAGE = Decimal("0.0001")
BNB9_TP_SLIPPAGE = Decimal("0")
BNB9_FEE = Decimal("0.000405")
INITIAL_BALANCE = Decimal("10000")

DAY_MS = 24 * 60 * 60 * 1000
EMA_PERIOD = 60
EMA_WARMUP_BARS = 2 * EMA_PERIOD


def year_range(year: int) -> tuple[int, int]:
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    return start, end


def fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


async def run_backtest(
    backtester: Backtester,
    year: int,
) -> Any:
    start_time, end_time = year_range(year)

    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=start_time,
        end_time=end_time,
        limit=10000,
        mode="v3_pms",
        slippage_rate=BNB9_SLIPPAGE,
        tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE,
        initial_balance=INITIAL_BALANCE,
    )
    request.risk_overrides = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
    request.order_strategy = OrderStrategy(
        id="eth_regime_filter_research",
        name="ETH regime filter research",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
    )

    return await backtester.run_backtest(request, runtime_overrides=overrides)


async def load_daily_regime_map(
    repo: HistoricalDataRepository,
    year: int,
) -> Dict[int, bool]:
    start_time, end_time = year_range(year)
    warmup_start = start_time - EMA_WARMUP_BARS * DAY_MS
    klines = await repo.get_klines(
        symbol=SYMBOL,
        timeframe="1d",
        start_time=warmup_start,
        end_time=end_time,
        limit=1000,
    )

    ema = EMACalculator(period=EMA_PERIOD)
    regime_map: Dict[int, bool] = {}

    for k in klines:
        ema.update(k.close)
        if ema.is_ready and ema.value is not None:
            candle_close_time = k.timestamp + DAY_MS
            regime_map[candle_close_time] = k.close > ema.value

    return regime_map


def is_regime_allowed(entry_time: int, regime_map: Dict[int, bool]) -> bool:
    eligible_close_times = [ts for ts in regime_map.keys() if ts <= entry_time]
    if not eligible_close_times:
        return False
    last_close_time = max(eligible_close_times)
    return regime_map[last_close_time]


def compute_proxy_metrics(positions: List[Any]) -> Dict[str, float]:
    closed = [p for p in positions if p.exit_time is not None]
    pnls = [float(p.realized_pnl) for p in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in [float(p.realized_pnl) for p in sorted(closed, key=lambda x: x.exit_time or 0)]:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    # Trade-level Sharpe proxy: mean/std * sqrt(n)
    sharpe_proxy = 0.0
    if len(pnls) >= 2:
        std = pstdev(pnls)
        if std > 0:
            sharpe_proxy = (mean(pnls) / std) * (len(pnls) ** 0.5)

    return {
        "pnl": sum(pnls),
        "trades": len(closed),
        "win_rate": (len(wins) / len(closed)) if closed else 0.0,
        "max_dd_proxy": max_dd,
        "sharpe_proxy": sharpe_proxy,
        "avg_win": mean(wins) if wins else 0.0,
        "avg_loss": mean(losses) if losses else 0.0,
    }


def filter_positions_by_regime(
    positions: List[Any],
    regime_map: Dict[int, bool],
) -> tuple[List[Any], int]:
    kept = []
    filtered_out = 0

    for pos in positions:
        if is_regime_allowed(pos.entry_time, regime_map):
            kept.append(pos)
        else:
            filtered_out += 1

    return kept, filtered_out


async def analyze_year(
    backtester: Backtester,
    repo: HistoricalDataRepository,
    year: int,
) -> Dict[str, Any]:
    report = await run_backtest(backtester, year)
    regime_map = await load_daily_regime_map(repo, year)

    baseline_positions = [p for p in report.positions if p.exit_time is not None]
    filtered_positions, filtered_out = filter_positions_by_regime(report.positions, regime_map)
    filtered_positions = [p for p in filtered_positions if p.exit_time is not None]

    baseline_metrics = compute_proxy_metrics(baseline_positions)
    filtered_metrics = compute_proxy_metrics(filtered_positions)

    return {
        "year": year,
        "baseline": baseline_metrics,
        "filtered": filtered_metrics,
        "filtered_out": filtered_out,
        "baseline_report_pnl": float(report.total_pnl),
        "baseline_report_trades": report.total_trades,
        "baseline_report_win_rate": float(report.win_rate) / 100 if float(report.win_rate) > 1 else float(report.win_rate),
        "baseline_report_sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "baseline_report_max_dd": float(report.max_drawdown) if report.max_drawdown else 0.0,
    }


def print_year_result(result: Dict[str, Any]) -> None:
    base = result["baseline"]
    filt = result["filtered"]
    print(f"\n=== {result['year']} ===")
    print(
        f"baseline(proxy): pnl={base['pnl']:.2f}, trades={base['trades']}, "
        f"win_rate={base['win_rate']*100:.2f}%, sharpe_proxy={base['sharpe_proxy']:.2f}, "
        f"max_dd_proxy={base['max_dd_proxy']:.2f}"
    )
    print(
        f"regime-filter(proxy): pnl={filt['pnl']:.2f}, trades={filt['trades']}, "
        f"win_rate={filt['win_rate']*100:.2f}%, sharpe_proxy={filt['sharpe_proxy']:.2f}, "
        f"max_dd_proxy={filt['max_dd_proxy']:.2f}, filtered_out={result['filtered_out']}"
    )
    pnl_diff = filt["pnl"] - base["pnl"]
    print(f"delta pnl={pnl_diff:+.2f}")
    print(
        f"official baseline reference: pnl={result['baseline_report_pnl']:.2f}, "
        f"trades={result['baseline_report_trades']}, "
        f"win_rate={result['baseline_report_win_rate']*100:.2f}%, "
        f"sharpe={result['baseline_report_sharpe']:.2f}, "
        f"max_dd={result['baseline_report_max_dd']*100:.2f}%"
    )


async def main() -> None:
    repo = HistoricalDataRepository()
    await repo.initialize()
    backtester = Backtester(exchange_gateway=None, data_repository=repo)

    try:
        results = []
        for year in [2023, 2024, 2025]:
            results.append(await analyze_year(backtester, repo, year))

        print("=" * 80)
        print("Minimal Regime Filter Research (external gating, proxy metrics)")
        print("=" * 80)
        print("Filter: allow 1h LONG only when last closed 1d candle has close > EMA60")
        print("Fixed baseline: ETH 1h, BNB9, LONG-only, ema=50, dist=0.005, tp=[1.0,3.5], BE=False")
        print("Important: filtered metrics are proxy metrics derived from kept positions, not true_equity backtest reruns.")

        total_base_pnl = 0.0
        total_filt_pnl = 0.0
        for result in results:
            print_year_result(result)
            total_base_pnl += result["baseline"]["pnl"]
            total_filt_pnl += result["filtered"]["pnl"]

        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"3y baseline proxy pnl: {total_base_pnl:.2f}")
        print(f"3y filtered proxy pnl: {total_filt_pnl:.2f}")
        print(f"3y delta: {total_filt_pnl - total_base_pnl:+.2f}")

        y2023 = next(r for r in results if r["year"] == 2023)
        y2024 = next(r for r in results if r["year"] == 2024)
        y2025 = next(r for r in results if r["year"] == 2025)

        print("\nDecision framing:")
        print(f"- 2023 improved? {'YES' if y2023['filtered']['pnl'] > y2023['baseline']['pnl'] else 'NO'}")
        print(f"- 2024 harmed materially? {'YES' if y2024['filtered']['pnl'] < y2024['baseline']['pnl'] else 'NO'}")
        print(f"- 2025 harmed materially? {'YES' if y2025['filtered']['pnl'] < y2025['baseline']['pnl'] else 'NO'}")
    finally:
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
