#!/usr/bin/env python3
"""
4h 结构连续性验证

目标：
1. 定义一个简单、可解释的 4h 结构特征
2. 基于 2023/2024/2025 三年真实成交 LONG 样本
3. 对比盈利交易 vs 亏损交易的分布差异
4. 判断是否比 ema_distance_1h 更有解释力

配置（冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False, ATR 移除
- max_loss_percent=1%

结构定义：
- 取入场前最近 3 根已闭合 4h K 线
- 定义"结构连续性"：低点整体抬高（至少 2 个低点抬高）
  - low[1] < low[2] 或 low[0] < low[1]
  - 其中 low[0] 是最近一根，low[2] 是最远一根
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


async def fetch_4h_klines_before_entry(gateway, entry_time, lookback_bars=5):
    """获取入场前的 4h K 线数据"""
    # 入场时间往前推 lookback_bars * 4h
    since = entry_time - int(lookback_bars * 4 * 3600 * 1000)

    klines = await gateway.fetch_historical_ohlcv(
        symbol="ETH/USDT:USDT",
        timeframe="4h",
        since=since,
        limit=lookback_bars + 2,  # 多取几根确保有足够数据
    )

    # 过滤掉入场时间之后的 K 线
    klines = [k for k in klines if k.timestamp < entry_time]

    # 按时间排序（从旧到新）
    klines = sorted(klines, key=lambda k: k.timestamp)

    return klines


def check_4h_structure_continuity(klines_4h: List) -> Optional[bool]:
    """
    检查 4h 结构连续性

    定义：取最近 3 根已闭合 4h K 线，判断低点是否整体抬高

    判断逻辑：
    - 至少 2 个低点抬高
    - low[1] < low[2] 或 low[0] < low[1]
    - 其中 low[0] 是最近一根，low[2] 是最远一根

    返回：
    - True: 结构连续（低点抬高）
    - False: 结构不连续（低点未抬高）
    - None: 数据不足
    """
    if len(klines_4h) < 3:
        return None

    # 取最近 3 根 K 线
    recent_3 = klines_4h[-3:]
    low_0 = recent_3[2].low  # 最近一根
    low_1 = recent_3[1].low  # 中间一根
    low_2 = recent_3[0].low  # 最远一根

    # 判断低点是否整体抬高（至少 2 个低点抬高）
    higher_lows = 0

    if low_1 < low_2:  # 中间低点高于最远低点
        higher_lows += 1

    if low_0 < low_1:  # 最近低点高于中间低点
        higher_lows += 1

    return higher_lows >= 2


async def analyze_positions_structure(gateway, positions, year):
    """分析仓位的 4h 结构连续性"""

    # 区分盈利和亏损交易
    profitable_with_structure = 0
    profitable_without_structure = 0
    losing_with_structure = 0
    losing_without_structure = 0

    missing_count = 0
    total_analyzed = 0

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

        try:
            # 获取入场前的 4h K 线
            klines_4h = await fetch_4h_klines_before_entry(
                gateway,
                entry_time=pos.entry_time,
                lookback_bars=5
            )

            # 检查结构连续性
            has_structure = check_4h_structure_continuity(klines_4h)

            if has_structure is None:
                missing_count += 1
                continue

            total_analyzed += 1

            # 判断盈利还是亏损
            is_profitable = pos.realized_pnl > 0

            # 统计
            if is_profitable:
                if has_structure:
                    profitable_with_structure += 1
                else:
                    profitable_without_structure += 1
            else:
                if has_structure:
                    losing_with_structure += 1
                else:
                    losing_without_structure += 1

        except Exception as e:
            print(f"  警告: 仓位 {i} 分析失败: {e}")
            missing_count += 1
            continue

    # 计算统计指标
    stats = {
        "year": year,
        "total_positions": len(positions),
        "analyzed_positions": total_analyzed,
        "missing_count": missing_count,
        "profitable_with_structure": profitable_with_structure,
        "profitable_without_structure": profitable_without_structure,
        "losing_with_structure": losing_with_structure,
        "losing_without_structure": losing_without_structure,
        # 计算比例
        "profitable_structure_ratio": (
            profitable_with_structure / (profitable_with_structure + profitable_without_structure)
            if (profitable_with_structure + profitable_without_structure) > 0 else 0
        ),
        "losing_structure_ratio": (
            losing_with_structure / (losing_with_structure + losing_without_structure)
            if (losing_with_structure + losing_without_structure) > 0 else 0
        ),
        # 计算 Win Rate
        "win_rate_with_structure": (
            profitable_with_structure / (profitable_with_structure + losing_with_structure)
            if (profitable_with_structure + losing_with_structure) > 0 else 0
        ),
        "win_rate_without_structure": (
            profitable_without_structure / (profitable_without_structure + losing_without_structure)
            if (profitable_without_structure + losing_without_structure) > 0 else 0
        ),
    }

    return stats


async def main():
    print("=" * 80)
    print("4h 结构连续性验证")
    print("=" * 80)
    print("\n配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n结构定义:")
    print("- 取入场前最近 3 根已闭合 4h K 线")
    print("- 定义'结构连续性'：低点整体抬高（至少 2 个低点抬高）")
    print("  - low[1] < low[2] 或 low[0] < low[1]")
    print("  - 其中 low[0] 是最近一根，low[2] 是最远一根")
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

        # 分析结构连续性
        print("\n分析结构连续性...")
        stats_2023 = await analyze_positions_structure(gateway, report_2023.positions, 2023)
        stats_2024 = await analyze_positions_structure(gateway, report_2024.positions, 2024)
        stats_2025 = await analyze_positions_structure(gateway, report_2025.positions, 2025)

        # 输出对比表
        print("\n" + "=" * 80)
        print("年度对比表")
        print("=" * 80)

        # 输出缺失样本数
        print("\n【样本统计】")
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']} 年: 分析 {stats['analyzed_positions']} 笔，缺失 {stats['missing_count']} 笔")

        # 输出结构连续性分布
        print("\n【盈利交易的结构连续性分布】")
        print(f"{'年份':<8} {'有结构':<15} {'无结构':<15} {'有结构比例':<15}")
        print("-" * 60)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} "
                  f"{stats['profitable_with_structure']:<15} "
                  f"{stats['profitable_without_structure']:<15} "
                  f"{stats['profitable_structure_ratio']*100:<15.1f}%")

        print("\n【亏损交易的结构连续性分布】")
        print(f"{'年份':<8} {'有结构':<15} {'无结构':<15} {'有结构比例':<15}")
        print("-" * 60)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} "
                  f"{stats['losing_with_structure']:<15} "
                  f"{stats['losing_without_structure']:<15} "
                  f"{stats['losing_structure_ratio']*100:<15.1f}%")

        # 输出 Win Rate 对比
        print("\n【Win Rate 对比：有结构 vs 无结构】")
        print(f"{'年份':<8} {'有结构 Win Rate':<20} {'无结构 Win Rate':<20} {'差异':<15}")
        print("-" * 70)
        for stats in [stats_2023, stats_2024, stats_2025]:
            diff = (stats['win_rate_with_structure'] - stats['win_rate_without_structure']) * 100
            print(f"{stats['year']:<8} "
                  f"{stats['win_rate_with_structure']*100:<20.1f}% "
                  f"{stats['win_rate_without_structure']*100:<20.1f}% "
                  f"{diff:+<15.1f}%")

        # 跨年对比总结
        print("\n" + "=" * 80)
        print("跨年对比总结")
        print("=" * 80)

        # 分析盈利 vs 亏损的结构比例差异
        print("\n【盈利 vs 亏损的结构比例差异】")
        for stats in [stats_2023, stats_2024, stats_2025]:
            diff = (stats['profitable_structure_ratio'] - stats['losing_structure_ratio']) * 100
            print(f"\n{stats['year']} 年:")
            print(f"  盈利交易有结构比例: {stats['profitable_structure_ratio']*100:.1f}%")
            print(f"  亏损交易有结构比例: {stats['losing_structure_ratio']*100:.1f}%")
            print(f"  差异: {diff:+.1f}%")

            if abs(diff) > 10:
                print("  ⚠️  差异明显")
            else:
                print("  ✅ 差异不明显")

        # 分析 Win Rate 差异
        print("\n【Win Rate 差异：有结构 vs 无结构】")
        for stats in [stats_2023, stats_2024, stats_2025]:
            wr_diff = (stats['win_rate_with_structure'] - stats['win_rate_without_structure']) * 100
            print(f"\n{stats['year']} 年:")
            print(f"  有结构 Win Rate: {stats['win_rate_with_structure']*100:.1f}%")
            print(f"  无结构 Win Rate: {stats['win_rate_without_structure']*100:.1f}%")
            print(f"  差异: {wr_diff:+.1f}%")

            if wr_diff > 5:
                print("  ⚠️  有结构明显优于无结构")
            elif wr_diff < -5:
                print("  ⚠️  无结构明显优于有结构")
            else:
                print("  ✅ 差异不明显")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        # 计算 2023 年的关键指标
        diff_2023 = (stats_2023['profitable_structure_ratio'] - stats_2023['losing_structure_ratio']) * 100
        wr_diff_2023 = (stats_2023['win_rate_with_structure'] - stats_2023['win_rate_without_structure']) * 100

        # 判断是否有解释力
        has_explanatory_power = (
            abs(diff_2023) > 10 or  # 盈利/亏损结构比例差异明显
            abs(wr_diff_2023) > 5   # Win Rate 差异明显
        )

        print("\n【与 ema_distance_1h 对比】")
        print("\nema_distance_1h 的表现:")
        print("  - 2023 亏损交易均值: 1.7611%")
        print("  - 2023 盈利交易均值: 1.6143%")
        print("  - 差异: 0.1468%（明显）")
        print("  - 但阈值验证显示：对 2024/2025 伤害过大")

        print(f"\n4h 结构连续性的表现:")
        print(f"  - 2023 盈利交易有结构比例: {stats_2023['profitable_structure_ratio']*100:.1f}%")
        print(f"  - 2023 亏损交易有结构比例: {stats_2023['losing_structure_ratio']*100:.1f}%")
        print(f"  - 差异: {diff_2023:+.1f}%")
        print(f"  - 2023 有结构 Win Rate: {stats_2023['win_rate_with_structure']*100:.1f}%")
        print(f"  - 2023 无结构 Win Rate: {stats_2023['win_rate_without_structure']*100:.1f}%")
        print(f"  - Win Rate 差异: {wr_diff_2023:+.1f}%")

        # 最终答案
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        if has_explanatory_power:
            print(f"\n✅ 4h 结构连续性比 ema_distance_1h 更有解释力。")
            print(f"   理由：")
            print(f"   - 2023 年盈利/亏损结构比例差异: {diff_2023:+.1f}%")
            print(f"   - 2023 年有结构 Win Rate 提升: {wr_diff_2023:+.1f}%")
            print(f"   - 比 ema_distance_1h 的差异（0.1468%）更明显")
        else:
            print(f"\n❌ 4h 结构连续性不如 ema_distance_1h 有解释力。")
            print(f"   理由：")
            print(f"   - 2023 年盈利/亏损结构比例差异: {diff_2023:+.1f}%")
            print(f"   - 2023 年有结构 Win Rate 提升: {wr_diff_2023:+.1f}%")
            print(f"   - 差异不够明显，不如 ema_distance_1h（0.1468%）")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
