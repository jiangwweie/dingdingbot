#!/usr/bin/env python3
"""
Same-Bar Conflict 统计 + 多 Seed 验证

目标：
1. 统计 same-bar conflict 次数、占比、受影响交易数
2. 运行 10~20 个不同 seed，验证 PnL 分布
3. 判断 "+0.82% 是否只是单个 seed 偶然值"

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
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_backtest_with_stats(
    gateway: ExchangeGateway,
    backtester: Backtester,
    start_time: int,
    end_time: int,
    year_label: str,
    same_bar_policy: str,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """运行单次回测并收集冲突统计"""

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

    # 提取撮合引擎的冲突统计
    conflict_stats = {}
    if hasattr(backtester, '_last_matching_engine'):
        engine = backtester._last_matching_engine
        conflict_stats = engine.conflict_stats.copy()

    # 提取关键指标
    result = {
        "year": year_label,
        "policy": same_bar_policy,
        "seed": random_seed,
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) if report.max_drawdown else 0.0,
        "conflict_stats": conflict_stats,
    }

    return result


async def run_conflict_statistics(
    gateway: ExchangeGateway,
    backtester: Backtester,
):
    """第一部分：冲突统计"""

    print("=" * 80)
    print("第一部分：Same-Bar Conflict 统计")
    print("=" * 80)

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

    results = []

    for period in test_periods:
        print(f"\n{'=' * 80}")
        print(f"测试期间: {period['label']}")
        print(f"{'=' * 80}")

        # 运行 random 策略（seed=42）以收集冲突统计
        print(f"\n运行 random (seed=42) 收集冲突统计...")
        result = await run_single_backtest_with_stats(
            gateway=gateway,
            backtester=backtester,
            start_time=period["start"],
            end_time=period["end"],
            year_label=period["label"],
            same_bar_policy="random",
            random_seed=42,
        )
        results.append(result)

        # 输出冲突统计
        stats = result["conflict_stats"]
        if stats:
            print(f"\n冲突统计 ({period['label']}):")
            print(f"  总 K 线数: {stats.get('total_klines', 0)}")
            print(f"  有冲突的 K 线数: {stats.get('klines_with_conflicts', 0)}")
            print(f"  总冲突次数: {stats.get('total_conflicts', 0)}")
            print(f"  TP 优先次数: {stats.get('conflicts_tp_first', 0)}")
            print(f"  SL 优先次数: {stats.get('conflicts_sl_first', 0)}")

            # 计算占比
            total_klines = stats.get('total_klines', 0)
            klines_with_conflicts = stats.get('klines_with_conflicts', 0)
            total_conflicts = stats.get('total_conflicts', 0)

            if total_klines > 0:
                conflict_kline_pct = (klines_with_conflicts / total_klines) * 100
                print(f"  冲突 K 线占比: {conflict_kline_pct:.2f}%")

            # 受影响交易数（估算）
            trades = result["trades"]
            if total_conflicts > 0:
                affected_ratio = total_conflicts / trades if trades > 0 else 0
                print(f"  受影响交易数（估算）: {total_conflicts} ({affected_ratio * 100:.2f}% of trades)")
        else:
            print(f"\n⚠️ 未收集到冲突统计数据")

        print(f"\n回测结果:")
        print(f"  PnL: {result['pnl']:.2f} USDT")
        print(f"  Trades: {result['trades']}")
        print(f"  Win Rate: {result['win_rate'] * 100:.2f}%")

    # 汇总统计
    print(f"\n{'=' * 80}")
    print("两年汇总")
    print(f"{'=' * 80}")

    total_klines = sum(r["conflict_stats"].get("total_klines", 0) for r in results)
    total_conflict_klines = sum(r["conflict_stats"].get("klines_with_conflicts", 0) for r in results)
    total_conflicts = sum(r["conflict_stats"].get("total_conflicts", 0) for r in results)
    total_trades = sum(r["trades"] for r in results)

    print(f"总 K 线数: {total_klines}")
    print(f"有冲突的 K 线数: {total_conflict_klines}")
    print(f"总冲突次数: {total_conflicts}")
    print(f"总交易数: {total_trades}")

    if total_klines > 0:
        conflict_kline_pct = (total_conflict_klines / total_klines) * 100
        print(f"冲突 K 线占比: {conflict_kline_pct:.2f}%")

    if total_conflicts > 0:
        affected_ratio = total_conflicts / total_trades if total_trades > 0 else 0
        print(f"受影响交易占比: {affected_ratio * 100:.2f}%")

    return results


async def run_multi_seed_validation(
    gateway: ExchangeGateway,
    backtester: Backtester,
    n_seeds: int = 15,
):
    """第二部分：多 seed 验证"""

    print(f"\n{'=' * 80}")
    print(f"第二部分：多 Seed 验证 (n={n_seeds})")
    print(f"{'=' * 80}")

    # 定义测试期间（两年合计）
    start_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    # 先跑 pessimistic 作为基准
    print(f"\n运行 pessimistic（基准）...")
    result_pess = await run_single_backtest_with_stats(
        gateway=gateway,
        backtester=backtester,
        start_time=start_time,
        end_time=end_time,
        year_label="2024-2025",
        same_bar_policy="pessimistic",
        random_seed=0,  # pessimistic 不使用 seed
    )

    print(f"  PnL: {result_pess['pnl']:.2f} USDT")
    print(f"  Trades: {result_pess['trades']}")
    print(f"  Win Rate: {result_pess['win_rate'] * 100:.2f}%")

    # 运行多个 seed
    print(f"\n运行 random 策略（{n_seeds} 个不同 seed）...")
    random_results = []

    for i in range(n_seeds):
        seed = i + 1  # seed 从 1 开始
        print(f"\n  Seed {seed}/{n_seeds}...", end=" ")

        result = await run_single_backtest_with_stats(
            gateway=gateway,
            backtester=backtester,
            start_time=start_time,
            end_time=end_time,
            year_label="2024-2025",
            same_bar_policy="random",
            random_seed=seed,
        )

        random_results.append(result)
        print(f"PnL: {result['pnl']:.2f} USDT")

    # 统计分析
    print(f"\n{'=' * 80}")
    print("统计分析")
    print(f"{'=' * 80}")

    pnls = [r["pnl"] for r in random_results]

    mean_pnl = statistics.mean(pnls)
    min_pnl = min(pnls)
    max_pnl = max(pnls)
    std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 0

    print(f"\nRandom 策略 PnL 分布:")
    print(f"  均值: {mean_pnl:.2f} USDT")
    print(f"  最小值: {min_pnl:.2f} USDT")
    print(f"  最大值: {max_pnl:.2f} USDT")
    print(f"  标准差: {std_pnl:.2f} USDT")
    print(f"  变异系数: {(std_pnl / mean_pnl * 100) if mean_pnl != 0 else 0:.2f}%")

    # 对比 pessimistic
    pess_pnl = result_pess["pnl"]
    mean_diff = mean_pnl - pess_pnl
    mean_diff_pct = (mean_diff / abs(pess_pnl) * 100) if pess_pnl != 0 else 0

    print(f"\n对比 pessimistic:")
    print(f"  pessimistic PnL: {pess_pnl:.2f} USDT")
    print(f"  random 均值 PnL: {mean_pnl:.2f} USDT")
    print(f"  差异: {mean_diff:+.2f} USDT ({mean_diff_pct:+.2f}%)")

    # 判断结论
    print(f"\n{'=' * 80}")
    print("结论")
    print(f"{'=' * 80}")

    # 判断标准差是否显著
    if std_pnl < abs(pess_pnl) * 0.01:  # 标准差 < pessimistic PnL 的 1%
        print(f"✅ random 策略结果稳定（标准差 {std_pnl:.2f} USDT < 1% pessimistic PnL）")
        print(f"   → '+0.82%' 不是偶然值，random 策略改善幅度确实很小")
    else:
        print(f"⚠️  random 策略结果波动较大（标准差 {std_pnl:.2f} USDT）")
        print(f"   → 需要更多样本验证")

    # 判断均值差异是否显著
    if abs(mean_diff_pct) < 5:
        print(f"✅ random 策略仅带来小幅改善（均值差异 {mean_diff_pct:+.2f}% < 5%）")
        print(f"   → 当前主线结论稳健")
    else:
        print(f"⚠️  random 策略带来显著改善（均值差异 {mean_diff_pct:+.2f}%）")
        print(f"   → 需要重新评估主线结论")

    # 输出所有 seed 的结果
    print(f"\n所有 seed 结果:")
    for i, result in enumerate(random_results):
        diff = result["pnl"] - pess_pnl
        diff_pct = (diff / abs(pess_pnl) * 100) if pess_pnl != 0 else 0
        print(f"  Seed {i+1:2d}: PnL = {result['pnl']:8.2f} USDT (差异: {diff:+7.2f} / {diff_pct:+5.2f}%)")

    return {
        "pessimistic": result_pess,
        "random_results": random_results,
        "stats": {
            "mean": mean_pnl,
            "min": min_pnl,
            "max": max_pnl,
            "std": std_pnl,
        },
    }


async def main():
    """主函数"""

    print("=" * 80)
    print("Same-Bar Conflict 统计 + 多 Seed 验证")
    print("=" * 80)
    print("\n测试配置：")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n验证目标：")
    print("1. 统计 same-bar conflict 次数、占比、受影响交易数")
    print("2. 验证 '+0.82%' 是否只是单个 seed 偶然值")
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
        # 第一部分：冲突统计
        conflict_results = await run_conflict_statistics(gateway, backtester)

        # 第二部分：多 seed 验证
        multi_seed_results = await run_multi_seed_validation(gateway, backtester, n_seeds=15)

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
