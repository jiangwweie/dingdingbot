#!/usr/bin/env python3
"""
最小阈值验证：ema_distance_1h 的 gating 效果

目标：
1. 基于 2023/2024/2025 三年真实成交 LONG 样本
2. 对比 4 组阈值：无阈值、<= 1.6%、<= 1.8%、<= 2.0%
3. 分别统计保留交易数/保留比例/保留后 pnl/win_rate
4. 判断哪个阈值能明显改善 2023，同时不过度伤害 2024/2025

配置（冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False, ATR 移除
- max_loss_percent=1%
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import statistics

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.indicators import EMACalculator


async def run_year_backtest(gateway, backtester, year):
    """运行单年回测"""
    start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

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
        same_bar_policy="pessimistic",
    )

    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)
    return report


async def calculate_ema_distance_1h(gateway, entry_time, entry_price):
    """计算价格相对 1h EMA 的距离"""
    # 获取入场前的 1h K 线数据
    klines_1h = await gateway.fetch_historical_ohlcv(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        since=entry_time - int(60 * 3600 * 1000),
        limit=60,
    )
    klines_1h = [k for k in klines_1h if k.timestamp < entry_time]
    klines_1h = sorted(klines_1h, key=lambda k: k.timestamp)

    if len(klines_1h) < 50:
        return None

    # 计算 EMA
    ema_calculator = EMACalculator(period=50)
    for kline in klines_1h:
        ema_calculator.update(kline.close)

    if not ema_calculator.is_ready:
        return None

    ema_1h = ema_calculator.value

    # 计算距离
    distance = (entry_price - ema_1h) / ema_1h
    return distance


async def analyze_positions_with_threshold(gateway, positions, year, threshold: Optional[Decimal]):
    """分析仓位在给定阈值下的表现"""

    total_count = 0
    retained_count = 0
    retained_pnl = Decimal("0")
    retained_wins = 0

    print(f"\n分析 {year} 年 {len(positions)} 笔仓位...")

    for i, pos in enumerate(positions):
        if i % 10 == 0:
            print(f"  进度: {i}/{len(positions)}")

        # 只分析 LONG 仓位
        if pos.direction != "LONG":
            continue

        # 只分析已平仓的仓位
        if pos.exit_price is None or pos.exit_time is None:
            continue

        total_count += 1

        try:
            # 计算 ema_distance_1h
            ema_distance = await calculate_ema_distance_1h(
                gateway,
                pos.entry_time,
                pos.entry_price
            )

            if ema_distance is None:
                continue

            # 判断是否满足阈值条件
            if threshold is None or ema_distance <= threshold:
                retained_count += 1
                retained_pnl += pos.realized_pnl
                if pos.realized_pnl > 0:
                    retained_wins += 1

        except Exception as e:
            print(f"  警告: 仓位 {i} 分析失败: {e}")
            continue

    # 计算统计指标
    stats = {
        "year": year,
        "threshold": str(threshold) if threshold else "None",
        "total_count": total_count,
        "retained_count": retained_count,
        "retained_ratio": retained_count / total_count if total_count > 0 else 0,
        "retained_pnl": float(retained_pnl),
        "win_rate": retained_wins / retained_count if retained_count > 0 else 0,
    }

    return stats


async def main():
    print("=" * 80)
    print("最小阈值验证：ema_distance_1h 的 gating 效果")
    print("=" * 80)
    print("\n配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n验证阈值:")
    print("1. 无阈值（baseline）")
    print("2. ema_distance_1h <= 1.6%")
    print("3. ema_distance_1h <= 1.8%")
    print("4. ema_distance_1h <= 2.0%")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 运行三年回测
        print("\n运行回测...")
        report_2023 = await run_year_backtest(gateway, backtester, 2023)
        report_2024 = await run_year_backtest(gateway, backtester, 2024)
        report_2025 = await run_year_backtest(gateway, backtester, 2025)

        # 定义阈值组
        thresholds = [
            None,  # 无阈值
            Decimal("0.016"),  # <= 1.6%
            Decimal("0.018"),  # <= 1.8%
            Decimal("0.020"),  # <= 2.0%
        ]

        threshold_labels = ["无阈值", "<= 1.6%", "<= 1.8%", "<= 2.0%"]

        # 分析每个阈值
        all_stats = {}

        for threshold, label in zip(thresholds, threshold_labels):
            print(f"\n{'=' * 80}")
            print(f"验证阈值: {label}")
            print(f"{'=' * 80}")

            stats_2023 = await analyze_positions_with_threshold(gateway, report_2023.positions, 2023, threshold)
            stats_2024 = await analyze_positions_with_threshold(gateway, report_2024.positions, 2024, threshold)
            stats_2025 = await analyze_positions_with_threshold(gateway, report_2025.positions, 2025, threshold)

            all_stats[label] = {
                "2023": stats_2023,
                "2024": stats_2024,
                "2025": stats_2025,
            }

        # 输出对比表
        print("\n" + "=" * 80)
        print("阈值对比表")
        print("=" * 80)

        # 输出每年的对比
        for year in [2023, 2024, 2025]:
            print(f"\n【{year} 年】")
            print(f"{'阈值':<12} {'保留交易数':<12} {'保留比例':<12} {'保留后 PnL':<15} {'Win Rate':<12}")
            print("-" * 70)

            for label in threshold_labels:
                stats = all_stats[label][str(year)]
                print(f"{label:<12} {stats['retained_count']:<12} "
                      f"{stats['retained_ratio']*100:<12.1f}% "
                      f"{stats['retained_pnl']:<15.2f} "
                      f"{stats['win_rate']*100:<12.1f}%")

        # 跨年对比总结
        print("\n" + "=" * 80)
        print("跨年对比总结")
        print("=" * 80)

        # 分析 2023 年的改善
        print("\n【2023 年改善分析】")
        baseline_2023 = all_stats["无阈值"]["2023"]

        for label in ["<= 1.6%", "<= 1.8%", "<= 2.0%"]:
            stats = all_stats[label]["2023"]

            pnl_improvement = stats['retained_pnl'] - baseline_2023['retained_pnl']
            wr_improvement = (stats['win_rate'] - baseline_2023['win_rate']) * 100

            print(f"\n{label}:")
            print(f"  保留交易数: {stats['retained_count']} ({stats['retained_ratio']*100:.1f}%)")
            print(f"  PnL: {stats['retained_pnl']:.2f} (vs baseline: {pnl_improvement:+.2f})")
            print(f"  Win Rate: {stats['win_rate']*100:.1f}% (vs baseline: {wr_improvement:+.1f}%)")

            if pnl_improvement > 0 and wr_improvement > 0:
                print("  ✅ 明显改善")
            elif pnl_improvement > 0 or wr_improvement > 0:
                print("  ⚠️  部分改善")
            else:
                print("  ❌ 未改善")

        # 分析对 2024/2025 年的影响
        print("\n【对 2024/2025 年的影响】")

        for year in [2024, 2025]:
            print(f"\n{year} 年:")
            baseline = all_stats["无阈值"][str(year)]

            for label in ["<= 1.6%", "<= 1.8%", "<= 2.0%"]:
                stats = all_stats[label][str(year)]

                pnl_loss = stats['retained_pnl'] - baseline['retained_pnl']
                wr_loss = (stats['win_rate'] - baseline['win_rate']) * 100
                retained_ratio = stats['retained_ratio'] * 100

                print(f"  {label}:")
                print(f"    保留比例: {retained_ratio:.1f}%")
                print(f"    PnL 变化: {pnl_loss:+.2f}")
                print(f"    Win Rate 变化: {wr_loss:+.1f}%")

                if retained_ratio < 70:
                    print("    ⚠️  过度伤害（保留比例 < 70%）")
                elif retained_ratio < 80:
                    print("    ⚠️  中度伤害（保留比例 < 80%）")
                else:
                    print("    ✅ 轻微影响")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        # 找出最佳阈值
        best_threshold = None
        best_score = -float('inf')

        for label in ["<= 1.6%", "<= 1.8%", "<= 2.0%"]:
            stats_2023 = all_stats[label]["2023"]
            stats_2024 = all_stats[label]["2024"]
            stats_2025 = all_stats[label]["2025"]

            # 计算综合得分
            # 2023 改善（PnL + Win Rate）
            pnl_improvement = stats_2023['retained_pnl'] - baseline_2023['retained_pnl']
            wr_improvement = (stats_2023['win_rate'] - baseline_2023['win_rate']) * 100
            improvement_score = pnl_improvement / 100 + wr_improvement

            # 2024/2025 保留比例
            retention_score = (stats_2024['retained_ratio'] + stats_2025['retained_ratio']) / 2 * 100

            # 综合得分 = 改善得分 * 保留得分
            total_score = improvement_score * retention_score

            print(f"\n{label}:")
            print(f"  2023 改善得分: {improvement_score:.2f}")
            print(f"  2024/2025 保留得分: {retention_score:.1f}")
            print(f"  综合得分: {total_score:.2f}")

            if total_score > best_score:
                best_score = total_score
                best_threshold = label

        # 最终答案
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        # 判断是否值得进入下一轮验证
        stats_best_2023 = all_stats[best_threshold]["2023"]
        stats_best_2024 = all_stats[best_threshold]["2024"]
        stats_best_2025 = all_stats[best_threshold]["2025"]

        pnl_improvement = stats_best_2023['retained_pnl'] - baseline_2023['retained_pnl']
        wr_improvement = (stats_best_2023['win_rate'] - baseline_2023['win_rate']) * 100

        avg_retention = (stats_best_2024['retained_ratio'] + stats_best_2025['retained_ratio']) / 2 * 100

        if pnl_improvement > 0 and wr_improvement > 0 and avg_retention > 70:
            print(f"\n✅ ema_distance_1h 值得进入下一轮更正式验证。")
            print(f"   当前最优先测试的阈值：{best_threshold}")
            print(f"   理由：")
            print(f"   - 2023 年 PnL 改善：{pnl_improvement:+.2f}")
            print(f"   - 2023 年 Win Rate 改善：{wr_improvement:+.1f}%")
            print(f"   - 2024/2025 年平均保留比例：{avg_retention:.1f}%")
        else:
            print(f"\n❌ ema_distance_1h 不值得进入下一轮验证。")
            print(f"   理由：")
            if pnl_improvement <= 0:
                print(f"   - 2023 年 PnL 未改善：{pnl_improvement:+.2f}")
            if wr_improvement <= 0:
                print(f"   - 2023 年 Win Rate 未改善：{wr_improvement:+.1f}%")
            if avg_retention <= 70:
                print(f"   - 2024/2025 年保留比例过低：{avg_retention:.1f}%")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
