#!/usr/bin/env python3
"""严格复现上一轮 LONG-only + TP2=3.5R 结果"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides


DB = "data/v3_dev.db"
SYM = "ETH/USDT:USDT"
TF = "1h"
BAL = Decimal("10000")
SLIP = Decimal("0.001")
TP_SLIP = Decimal("0.0005")
FEE = Decimal("0.0004")

WINDOWS = [
    ("2024", 1704067200000, 1735689599000),
    ("2025", 1735689600000, 1767225599000),
]


async def run_window(bt, start, end, label):
    """运行单个时间窗口的回测"""
    print(f"\n{'='*60}")
    print(f"窗口: {label}")
    print(f"{'='*60}")
    
    req = BacktestRequest(
        symbol=SYM,
        timeframe=TF,
        start_time=start,
        end_time=end,
        mode="v3_pms",
        initial_balance=BAL,
        slippage_rate=SLIP,
        tp_slippage_rate=TP_SLIP,
        fee_rate=FEE,
    )
    
    ov = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        max_atr_ratio=Decimal("0.0059"),
        min_distance_pct=Decimal("0.0080"),
        ema_period=111,
        allowed_directions=["LONG"],
    )
    
    result = await bt.run_backtest(req, runtime_overrides=ov)
    
    # 修正 win_rate（如果是小数形式，转换为百分比）
    win_rate = float(result.win_rate)
    if win_rate < 1.0:
        win_rate = win_rate * 100
    
    # 输出关键指标
    print(f"\n结果:")
    print(f"  total_pnl:     {result.total_pnl:.2f} USDT")
    print(f"  total_trades:  {result.total_trades}")
    print(f"  win_rate:      {win_rate:.1f}%")
    print(f"  max_drawdown:  {result.max_drawdown:.2f}%")
    print(f"  sharpe:        {result.sharpe_ratio:.2f}" if result.sharpe_ratio else "  sharpe:        N/A")
    
    return {
        "label": label,
        "total_pnl": float(result.total_pnl),
        "total_trades": result.total_trades,
        "win_rate": win_rate,
        "max_drawdown": float(result.max_drawdown),
        "sharpe": float(result.sharpe_ratio) if result.sharpe_ratio else 0.0,
    }


async def main():
    print("="*60)
    print("严格复现上一轮 LONG-only + TP2=3.5R")
    print("="*60)
    print("\n固定条件:")
    print("  symbol:            ETH/USDT:USDT")
    print("  timeframe:         1h")
    print("  mode:              v3_pms")
    print("  direction:         LONG-only")
    print("  max_atr_ratio:     0.0059")
    print("  min_distance_pct:  0.0080")
    print("  ema_period:        111")
    print("  breakeven_enabled: False")
    print("  tp_ratios:         [0.5, 0.5]")
    print("  tp_targets:        [1.0, 3.5]")
    print("  slippage:          0.001")
    print("  tp_slippage:       0.0005")
    print("  fee:               0.0004")
    
    # 初始化数据仓库
    print("\n初始化 HistoricalDataRepository...")
    repo = HistoricalDataRepository(DB)
    await repo.initialize()
    
    bt = Backtester(exchange_gateway=None, data_repository=repo)
    
    # 运行两个窗口
    results = []
    try:
        for wname, ws, we in WINDOWS:
            r = await run_window(bt, ws, we, wname)
            results.append(r)
    finally:
        await repo.close()
    
    # 输出汇总表
    print("\n" + "="*60)
    print("两年结果汇总")
    print("="*60)
    print(f"{'年份':<10} {'总盈亏':<15} {'交易数':<10} {'胜率':<10} {'最大回撤':<12} {'夏普':<8}")
    print("-"*60)
    for r in results:
        print(f"{r['label']:<10} {r['total_pnl']:>13.2f}   {r['total_trades']:<8} {r['win_rate']:>7.1f}%   {r['max_drawdown']:>9.1f}%   {r['sharpe']:>6.2f}")
    
    # 判断是否都为正
    all_positive = all(r["total_pnl"] > 0 for r in results)
    
    print("\n" + "="*60)
    print("结论")
    print("="*60)
    print(f"1. 两年结果是否都为正: {'✅ 是' if all_positive else '❌ 否'}")
    print(f"2. 是否成功复现上一轮主线: {'✅ 成功' if all_positive else '❌ 失败'}")
    
    print("\n" + "="*60)
    if all_positive:
        print("✅ 主线可复现，LONG-only + TP2=3.5R 是稳定的基线")
    else:
        print("❌ 主线不可复现，需要进一步排查差异原因")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
