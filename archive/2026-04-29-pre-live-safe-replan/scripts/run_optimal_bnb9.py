#!/usr/bin/env python3
"""
最优配置 + BNB9 成本验证

最优参数（来自大区间搜索）:
- ema_period: 50
- min_distance_pct: 0.005
- max_atr_ratio: 移除 (设为 1.0)
- tp_ratios: [0.5, 0.5]
- tp_targets: [1.0, 3.5]
- breakeven_enabled: False

BNB9 成本配置:
- slippage_rate: 0.0001 (0.01%)
- tp_slippage_rate: 0 (0%)
- fee_rate: 0.000405 (0.0405%, BNB 9折)
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")

# BNB9 成本配置
SLIPPAGE_RATE = Decimal("0.0001")      # 0.01%
TP_SLIPPAGE_RATE = Decimal("0")        # 0%
FEE_RATE = Decimal("0.000405")         # 0.0405% (BNB 9折)

# 最优参数
OPTIMAL_PARAMS = {
    "ema_period": 50,
    "min_distance_pct": Decimal("0.005"),
    "max_atr_ratio": Decimal("1.0"),  # 移除 ATR 过滤
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "breakeven_enabled": False,
}

# 时间窗口
W2023_START = 1672531200000
W2023_END = 1704067199000
W2024_START = 1704067200000
W2024_END = 1735689599000
W2025_START = 1735689600000
W2025_END = 1767225599000


async def run_backtest(backtester, start, end) -> Dict[str, Any]:
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=start, end_time=end,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    overrides = BacktestRuntimeOverrides(
        tp_ratios=OPTIMAL_PARAMS["tp_ratios"],
        tp_targets=OPTIMAL_PARAMS["tp_targets"],
        breakeven_enabled=OPTIMAL_PARAMS["breakeven_enabled"],
        max_atr_ratio=OPTIMAL_PARAMS["max_atr_ratio"],
        min_distance_pct=OPTIMAL_PARAMS["min_distance_pct"],
        ema_period=OPTIMAL_PARAMS["ema_period"],
        allowed_directions=["LONG"],
    )

    result = await backtester.run_backtest(request, runtime_overrides=overrides)

    return {
        "pnl": float(result.total_pnl),
        "trades": result.total_trades,
        "win_rate": float(result.win_rate) / 100 if result.win_rate else 0.0,
        "max_dd": float(result.max_drawdown) if result.max_drawdown else 0.0,
        "sharpe": float(result.sharpe_ratio) if result.sharpe_ratio else 0.0,
    }


async def main():
    print("=" * 70)
    print("最优配置 + BNB9 成本验证")
    print("=" * 70)

    print("\n【最优参数】")
    print(f"  ema_period:        {OPTIMAL_PARAMS['ema_period']}")
    print(f"  min_distance_pct:  {OPTIMAL_PARAMS['min_distance_pct']}")
    print(f"  max_atr_ratio:     {OPTIMAL_PARAMS['max_atr_ratio']} (移除过滤)")
    print(f"  tp_ratios:         {OPTIMAL_PARAMS['tp_ratios']}")
    print(f"  tp_targets:        {OPTIMAL_PARAMS['tp_targets']}")
    print(f"  breakeven_enabled: {OPTIMAL_PARAMS['breakeven_enabled']}")

    print("\n【BNB9 成本配置】")
    print(f"  slippage_rate:     {SLIPPAGE_RATE} (0.01%)")
    print(f"  tp_slippage_rate:  {TP_SLIPPAGE_RATE} (0%)")
    print(f"  fee_rate:          {FEE_RATE} (0.0405%, BNB 9折)")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    windows = [
        ("2023", W2023_START, W2023_END),
        ("2024", W2024_START, W2024_END),
        ("2025", W2025_START, W2025_END),
    ]

    results = {}

    try:
        for name, start, end in windows:
            print(f"\n{name} ...", end="")
            r = await run_backtest(bt, start, end)
            results[name] = r
            print(f" pnl={r['pnl']:+.2f}, trades={r['trades']}, dd={r['max_dd']:.2%}, sharpe={r['sharpe']:.3f}")

    finally:
        await repo.close()

    # 汇总
    print("\n" + "=" * 70)
    print("结果汇总")
    print("=" * 70)

    total_pnl = sum(r["pnl"] for r in results.values())
    total_trades = sum(r["trades"] for r in results.values())
    avg_sharpe = sum(r["sharpe"] for r in results.values()) / len(results)

    print(f"\n| 年份 | PnL | 交易数 | 胜率 | Max DD | Sharpe |")
    print("|------|-----|--------|------|--------|--------|")
    for name in ["2023", "2024", "2025"]:
        r = results[name]
        print(f"| {name} | {r['pnl']:+.2f} | {r['trades']} | {r['win_rate']:.1%} | {r['max_dd']:.2%} | {r['sharpe']:.3f} |")

    print(f"\n**3年总计**: PnL = {total_pnl:+.2f}, 交易数 = {total_trades}, 平均 Sharpe = {avg_sharpe:.3f}")

    # 与之前 stress 配置对比
    print("\n" + "-" * 70)
    print("与 stress (悲观) 配置对比")
    print("-" * 70)
    print("\n| 配置 | 2024 PnL | 2025 PnL | 2024 DD | 2025 DD |")
    print("|------|----------|----------|---------|---------|")
    print(f"| BNB9 (最优) | {results['2024']['pnl']:+.0f} | {results['2025']['pnl']:+.0f} | {results['2024']['max_dd']:.1%} | {results['2025']['max_dd']:.1%} |")
    print("| stress (最优) | +5168 | +1645 | 17.6% | 13.3% |")

    pnl_diff_2024 = results['2024']['pnl'] - 5168
    pnl_diff_2025 = results['2025']['pnl'] - 1645
    print(f"\n2024 差异: {pnl_diff_2024:+.0f}")
    print(f"2025 差异: {pnl_diff_2025:+.0f}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
