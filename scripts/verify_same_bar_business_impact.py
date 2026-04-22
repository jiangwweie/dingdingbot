#!/usr/bin/env python3
"""
Same-Bar 业务验证脚本

对比 pessimistic vs random 策略对主线结论的影响

测试配置：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False
- ATR 移除, MTF 用 system config
- max_loss_percent=1%

测试期间：
- 2024 年全年
- 2025 年全年
- 两年合计

对比指标：
- PnL
- Trades
- Win Rate
- Sharpe Ratio
- Max Drawdown (true_equity)

核心问题：random 是否只是小幅改善，还是会实质改变当前主线结论？
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_backtest(
    gateway: ExchangeGateway,
    backtester: Backtester,
    start_time: int,
    end_time: int,
    year_label: str,
    same_bar_policy: str,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """运行单次回测"""

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_time,
        end_time=end_time,
        limit=10000,
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
        same_bar_policy=same_bar_policy,
        same_bar_tp_first_prob=Decimal("0.5"),
        random_seed=random_seed if same_bar_policy == "random" else None,
    )

    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    # 提取关键指标
    result = {
        "year": year_label,
        "policy": same_bar_policy,
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) if report.max_drawdown else 0.0,
    }

    return result


async def main():
    """主函数"""

    print("=" * 80)
    print("Same-Bar 业务验证")
    print("=" * 80)
    print("\n测试配置：")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n对比策略：")
    print("- pessimistic (默认，SL > TP)")
    print("- random (TP 优先概率 0.5, seed=42)")
    print("=" * 80)

    # 初始化 gateway
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 定义测试期间
        test_periods = [
            {
                "label": "2024",
                "start": int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
                "end": int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000),
            },
            {
                "label": "2025",
                "start": int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
                "end": int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000),
            },
        ]

        # 存储结果
        results = []

        # 运行所有组合
        for period in test_periods:
            print(f"\n{'=' * 80}")
            print(f"测试期间: {period['label']}")
            print(f"{'=' * 80}")

            # pessimistic
            print(f"\n运行 pessimistic...")
            result_pess = await run_single_backtest(
                gateway=gateway,
                backtester=backtester,
                start_time=period["start"],
                end_time=period["end"],
                year_label=period["label"],
                same_bar_policy="pessimistic",
            )
            results.append(result_pess)

            print(f"  PnL: {result_pess['pnl']:.2f} USDT")
            print(f"  Trades: {result_pess['trades']}")
            print(f"  Win Rate: {result_pess['win_rate'] * 100:.2f}%")
            print(f"  Sharpe: {result_pess['sharpe']:.3f}")
            print(f"  Max DD: {result_pess['max_drawdown'] * 100:.2f}%")

            # random
            print(f"\n运行 random (seed=42)...")
            result_rand = await run_single_backtest(
                gateway=gateway,
                backtester=backtester,
                start_time=period["start"],
                end_time=period["end"],
                year_label=period["label"],
                same_bar_policy="random",
                random_seed=42,
            )
            results.append(result_rand)

            print(f"  PnL: {result_rand['pnl']:.2f} USDT")
            print(f"  Trades: {result_rand['trades']}")
            print(f"  Win Rate: {result_rand['win_rate'] * 100:.2f}%")
            print(f"  Sharpe: {result_rand['sharpe']:.3f}")
            print(f"  Max DD: {result_rand['max_drawdown'] * 100:.2f}%")

            # 计算差异
            pnl_diff = result_rand["pnl"] - result_pess["pnl"]
            pnl_pct = (pnl_diff / abs(result_pess["pnl"]) * 100) if result_pess["pnl"] != 0 else 0

            print(f"\n差异分析 ({period['label']}):")
            print(f"  PnL 差异: {pnl_diff:+.2f} USDT ({pnl_pct:+.2f}%)")
            print(f"  Trades 差异: {result_rand['trades'] - result_pess['trades']:+d}")
            print(f"  Win Rate 差异: {(result_rand['win_rate'] - result_pess['win_rate']) * 100:+.2f}%")

        # 计算两年合计
        print(f"\n{'=' * 80}")
        print("两年合计")
        print(f"{'=' * 80}")

        pess_total = {
            "pnl": sum(r["pnl"] for r in results if r["policy"] == "pessimistic"),
            "trades": sum(r["trades"] for r in results if r["policy"] == "pessimistic"),
        }
        pess_total["win_rate"] = pess_total["pnl"] / pess_total["trades"] if pess_total["trades"] > 0 else 0

        rand_total = {
            "pnl": sum(r["pnl"] for r in results if r["policy"] == "random"),
            "trades": sum(r["trades"] for r in results if r["policy"] == "random"),
        }
        rand_total["win_rate"] = rand_total["pnl"] / rand_total["trades"] if rand_total["trades"] > 0 else 0

        print(f"\npessimistic:")
        print(f"  总 PnL: {pess_total['pnl']:.2f} USDT")
        print(f"  总 Trades: {pess_total['trades']}")
        print(f"  平均 Win Rate: {pess_total['win_rate'] * 100:.2f}%")

        print(f"\nrandom:")
        print(f"  总 PnL: {rand_total['pnl']:.2f} USDT")
        print(f"  总 Trades: {rand_total['trades']}")
        print(f"  平均 Win Rate: {rand_total['win_rate'] * 100:.2f}%")

        total_pnl_diff = rand_total["pnl"] - pess_total["pnl"]
        total_pnl_pct = (total_pnl_diff / abs(pess_total["pnl"]) * 100) if pess_total["pnl"] != 0 else 0

        print(f"\n总体差异:")
        print(f"  PnL 差异: {total_pnl_diff:+.2f} USDT ({total_pnl_pct:+.2f}%)")
        print(f"  Trades 差异: {rand_total['trades'] - pess_total['trades']:+d}")

        # 最终结论
        print(f"\n{'=' * 80}")
        print("结论")
        print(f"{'=' * 80}")

        if abs(total_pnl_pct) < 5:
            print(f"✅ random 策略仅带来小幅改善（PnL 差异 {total_pnl_pct:+.2f}% < 5%）")
            print("   → 当前主线结论稳健，same-bar 冲突对整体结果影响有限")
        elif abs(total_pnl_pct) < 15:
            print(f"⚠️  random 策略带来中等改善（PnL 差异 {total_pnl_pct:+.2f}%）")
            print("   → 建议进一步分析 same-bar 冲突频率和影响")
        else:
            print(f"❌ random 策略带来显著改善（PnL 差异 {total_pnl_pct:+.2f}% ≥ 15%）")
            print("   → 当前主线结论可能受 same-bar 悲观假设影响较大")
            print("   → 建议采用 Monte Carlo 模拟评估真实市场不确定性")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
