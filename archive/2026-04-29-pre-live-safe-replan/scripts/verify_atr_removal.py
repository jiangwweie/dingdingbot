#!/usr/bin/env python3
"""
ATR 过滤器移除验证实验

对比两组：
1. 有 ATR 过滤 (max_atr_ratio=0.012)
2. 无 ATR 过滤 (max_atr_ratio=1.0，即不过滤)

固定其他参数：
- ema_period: 50
- min_distance_pct: 0.005

测试窗口：2024 + 2025 + 2023
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

FIXED_PARAMS = {
    "ema_period": 50,
    "min_distance_pct": Decimal("0.005"),
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


async def run_backtest(backtester, start, end, max_atr_ratio):
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=start, end_time=end,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    overrides = BacktestRuntimeOverrides(
        tp_ratios=FIXED_PARAMS["tp_ratios"],
        tp_targets=FIXED_PARAMS["tp_targets"],
        breakeven_enabled=FIXED_PARAMS["breakeven_enabled"],
        max_atr_ratio=Decimal(str(max_atr_ratio)),
        min_distance_pct=FIXED_PARAMS["min_distance_pct"],
        ema_period=FIXED_PARAMS["ema_period"],
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
    print("ATR 过滤器移除验证实验")
    print("=" * 70)

    print("\n固定参数:")
    print(f"  ema_period:       {FIXED_PARAMS['ema_period']}")
    print(f"  min_distance_pct: {FIXED_PARAMS['min_distance_pct']}")
    print(f"  tp_targets:       {FIXED_PARAMS['tp_targets']}")

    print("\n对比组:")
    print(f"  A: 有 ATR 过滤 (max_atr_ratio=0.012)")
    print(f"  B: 无 ATR 过滤 (max_atr_ratio=1.0)")

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
        # A: 有 ATR 过滤
        print("\n" + "=" * 70)
        print("A: 有 ATR 过滤 (max_atr_ratio=0.012)")
        print("=" * 70)

        results["with_atr"] = {}
        for name, start, end in windows:
            print(f"\n{name} ...", end="")
            r = await run_backtest(bt, start, end, 0.012)
            results["with_atr"][name] = r
            print(f" pnl={r['pnl']:+.2f}, trades={r['trades']}, dd={r['max_dd']:.2%}")

        # B: 无 ATR 过滤
        print("\n" + "=" * 70)
        print("B: 无 ATR 过滤 (max_atr_ratio=1.0)")
        print("=" * 70)

        results["without_atr"] = {}
        for name, start, end in windows:
            print(f"\n{name} ...", end="")
            r = await run_backtest(bt, start, end, 1.0)
            results["without_atr"][name] = r
            print(f" pnl={r['pnl']:+.2f}, trades={r['trades']}, dd={r['max_dd']:.2%}")

    finally:
        await repo.close()

    # 对比表格
    print("\n" + "=" * 70)
    print("对比结果")
    print("=" * 70)

    print("\n| 窗口 | ATR过滤 | PnL | Sharpe | Max DD | 交易数 | 胜率 |")
    print("|------|---------|-----|--------|--------|--------|------|")

    for name in ["2023", "2024", "2025"]:
        r_a = results["with_atr"][name]
        r_b = results["without_atr"][name]
        print(f"| {name} | 有 (0.012) | {r_a['pnl']:+.2f} | {r_a['sharpe']:.4f} | {r_a['max_dd']:.2%} | {r_a['trades']} | {r_a['win_rate']:.2%} |")
        print(f"| {name} | 无 (1.0) | {r_b['pnl']:+.2f} | {r_b['sharpe']:.4f} | {r_b['max_dd']:.2%} | {r_b['trades']} | {r_b['win_rate']:.2%} |")

    # 差异分析
    print("\n" + "=" * 70)
    print("差异分析")
    print("=" * 70)

    print(f"\n{'窗口':<8} {'PnL差异':>12} {'交易数差异':>10} {'Sharpe差异':>12}")
    print("-" * 50)

    for name in ["2023", "2024", "2025"]:
        r_a = results["with_atr"][name]
        r_b = results["without_atr"][name]
        pnl_diff = r_b["pnl"] - r_a["pnl"]
        trades_diff = r_b["trades"] - r_a["trades"]
        sharpe_diff = r_b["sharpe"] - r_a["sharpe"]
        print(f"{name:<8} {pnl_diff:>+12.2f} {trades_diff:>+10} {sharpe_diff:>+12.4f}")

    # 结论
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)

    # 检查差异是否显著
    max_pnl_diff = max(
        abs(results["without_atr"][name]["pnl"] - results["with_atr"][name]["pnl"])
        for name in ["2023", "2024", "2025"]
    )

    max_trades_diff = max(
        abs(results["without_atr"][name]["trades"] - results["with_atr"][name]["trades"])
        for name in ["2023", "2024", "2025"]
    )

    print(f"\n最大 PnL 差异: {max_pnl_diff:.2f}")
    print(f"最大交易数差异: {max_trades_diff}")

    if max_pnl_diff < 10 and max_trades_diff == 0:
        print("\n✅ **结论**: ATR 过滤器完全冗余，可以移除。")
        print("   有无 ATR 过滤，结果几乎完全相同。")
    elif max_pnl_diff < 100 and max_trades_diff < 3:
        print("\n⚠️ **结论**: ATR 过滤器影响很小，可以考虑移除。")
        print("   差异在可接受范围内。")
    else:
        print("\n❌ **结论**: ATR 过滤器有实际影响，不建议移除。")
        print("   需要进一步分析。")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
