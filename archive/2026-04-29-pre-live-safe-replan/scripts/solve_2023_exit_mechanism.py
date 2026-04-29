#!/usr/bin/env python3
"""
解谜 2023 实验：验证出场/防守机制对 2023 年亏损的影响

假说：2023 年并非入场逻辑失效，而是 3.5R 高止盈目标 + 无保本机制在震荡市失效。

实验设计：
- 锁定所有入场参数
- 仅改变出场参数（TP targets / Breakeven）
- 对比 4 组变体在 2023 年的表现

Var 0 (基线):     tp_targets=[1.0, 3.5], breakeven_enabled=False
Var 1 (测试保本): tp_targets=[1.0, 3.5], breakeven_enabled=True
Var 2 (降预期):   tp_targets=[1.0, 1.5], breakeven_enabled=False
Var 3 (极限防守): tp_targets=[1.0, 1.5], breakeven_enabled=True
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

# 固定配置
DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

# 锁定的入场参数
LOCKED_PARAMS = {
    "ema_period": 55,
    "min_distance_pct": Decimal("0.007"),
    "max_atr_ratio": Decimal("0.006"),
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
}

# 2023 年窗口
W2023_START = 1672531200000   # 2023-01-01
W2023_END = 1704067199000     # 2023-12-31 23:59:59

# 4 组变体
VARIANTS = [
    {"name": "Var 0 (基线)", "tp_targets": [Decimal("1.0"), Decimal("3.5")], "breakeven_enabled": False},
    {"name": "Var 1 (保本)", "tp_targets": [Decimal("1.0"), Decimal("3.5")], "breakeven_enabled": True},
    {"name": "Var 2 (降预期)", "tp_targets": [Decimal("1.0"), Decimal("1.5")], "breakeven_enabled": False},
    {"name": "Var 3 (极限防守)", "tp_targets": [Decimal("1.0"), Decimal("1.5")], "breakeven_enabled": True},
]


async def run_variant(backtester, tp_targets, breakeven_enabled):
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=W2023_START, end_time=W2023_END,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    overrides = BacktestRuntimeOverrides(
        tp_ratios=LOCKED_PARAMS["tp_ratios"],
        tp_targets=tp_targets,
        breakeven_enabled=breakeven_enabled,
        max_atr_ratio=LOCKED_PARAMS["max_atr_ratio"],
        min_distance_pct=LOCKED_PARAMS["min_distance_pct"],
        ema_period=LOCKED_PARAMS["ema_period"],
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
    print("解谜 2023 实验：出场/防守机制验证")
    print("=" * 70)

    print("\n锁定入场参数:")
    print(f"  ema_period:       {LOCKED_PARAMS['ema_period']}")
    print(f"  min_distance_pct: {LOCKED_PARAMS['min_distance_pct']}")
    print(f"  max_atr_ratio:    {LOCKED_PARAMS['max_atr_ratio']}")
    print(f"  tp_ratios:        {LOCKED_PARAMS['tp_ratios']}")
    print(f"  direction:        LONG-only")
    print(f"  mode:             v3_pms (stress)")

    print("\n测试窗口: 2023 全年")

    print("\n变体设计:")
    for v in VARIANTS:
        be = "ON" if v["breakeven_enabled"] else "OFF"
        print(f"  {v['name']}: TP={v['tp_targets']}, BE={be}")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    results = []

    try:
        for i, v in enumerate(VARIANTS):
            print(f"\n[{i+1}/4] {v['name']} ...")
            r = await run_variant(bt, v["tp_targets"], v["breakeven_enabled"])
            results.append({
                "name": v["name"],
                "tp_targets": v["tp_targets"],
                "breakeven_enabled": v["breakeven_enabled"],
                **r
            })
            print(f"  pnl={r['pnl']:+.2f}, sharpe={r['sharpe']:.4f}, dd={r['max_dd']:.2%}, trades={r['trades']}, win_rate={r['win_rate']:.2%}")

    finally:
        await repo.close()

    # 输出对比表格
    print("\n" + "=" * 70)
    print("2023 年对比结果")
    print("=" * 70)

    print("\n| 变体 | TP Targets | Breakeven | 总 PnL | Max DD | 交易数 | 胜率 | Sharpe |")
    print("|------|------------|-----------|--------|--------|--------|------|--------|")

    for r in results:
        tp = f"[{r['tp_targets'][0]}, {r['tp_targets'][1]}]"
        be = "ON" if r["breakeven_enabled"] else "OFF"
        print(f"| {r['name']} | {tp} | {be} | {r['pnl']:+.2f} | {r['max_dd']:.2%} | {r['trades']} | {r['win_rate']:.2%} | {r['sharpe']:.4f} |")

    # 定性结论
    print("\n" + "=" * 70)
    print("定性结论")
    print("=" * 70)

    baseline = results[0]
    best = min(results, key=lambda x: abs(x["pnl"]) if x["pnl"] < 0 else x["pnl"])

    # 分析各变体改善程度
    improvements = []
    for i, r in enumerate(results[1:], 1):
        pnl_improve = r["pnl"] - baseline["pnl"]
        dd_improve = baseline["max_dd"] - r["max_dd"]
        improvements.append({
            "name": r["name"],
            "pnl_improve": pnl_improve,
            "dd_improve": dd_improve,
        })

    # 判断
    print(f"\n基线 (Var 0): PnL = {baseline['pnl']:+.2f}")

    for imp in improvements:
        pnl_dir = "改善" if imp["pnl_improve"] > 0 else "恶化"
        dd_dir = "降低" if imp["dd_improve"] > 0 else "升高"
        print(f"{imp['name']}: PnL {pnl_dir} {abs(imp['pnl_improve']):+.2f}, Max DD {dd_dir} {abs(imp['dd_improve']):.2%}")

    # 最终结论
    print("\n" + "-" * 70)

    # 找最有效的变体
    best_improve = max(improvements, key=lambda x: x["pnl_improve"])

    if best_improve["pnl_improve"] > 1000:
        print(f"✅ **结论**: {best_improve['name']} 能有效切断 2023 年失血，PnL 改善 {best_improve['pnl_improve']:+.2f}")
        print(f"   假说成立：2023 年亏损主因是出场机制而非入场逻辑。")
    elif best_improve["pnl_improve"] > 0:
        print(f"⚠️ **结论**: {best_improve['name']} 有一定改善 (+{best_improve['pnl_improve']:.2f})，但不足以扭转亏损。")
        print(f"   可能需要同时调整入场参数。")
    else:
        print(f"❌ **结论**: 所有出场变体均无法改善 2023 年表现。")
        print(f"   假说不成立：问题可能在入场逻辑或其他因素。")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
