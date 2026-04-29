#!/usr/bin/env python3
"""
最小特征对比分析：2023 坏交易的环境特征

目标：
1. 基于 2023/2024/2025 三年真实成交 LONG 样本
2. 计算两个简单特征：
   - 4h EMA 斜率：ema_slope_4h = (EMA4h_t - EMA4h_t-1) / EMA4h_t-1
   - 价格相对 1h EMA 距离：ema_distance_1h = (entry_price - EMA1h_t) / EMA1h_t
3. 对比 2023 vs 2024/2025，区分盈利 vs 亏损交易
4. 判断是否有明显迹象可作为"不开仓条件"候选

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
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple, Optional
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


async def fetch_4h_klines(gateway, symbol, entry_time, lookback_bars=10):
    """获取入场前的 4h K 线数据（用于计算 EMA 斜率）"""
    # 入场时间往前推 lookback_bars * 4h
    since = entry_time - int(lookback_bars * 4 * 3600 * 1000)

    klines = await gateway.fetch_historical_ohlcv(
        symbol=symbol,
        timeframe="4h",
        since=since,
        limit=lookback_bars + 5,  # 多取几根确保有足够数据
    )

    # 过滤掉入场时间之后的 K 线
    klines = [k for k in klines if k.timestamp < entry_time]

    # 按时间排序（从旧到新）
    klines = sorted(klines, key=lambda k: k.timestamp)

    return klines


def calculate_ema_slope_4h(klines_4h: List, ema_period: int = 50) -> Optional[Decimal]:
    """
    计算 4h EMA 斜率

    公式：ema_slope_4h = (EMA4h_t - EMA4h_t-1) / EMA4h_t-1

    其中：
    - EMA4h_t = 入场时刻之前最近一根已闭合 4h K 线对应的 EMA
    - EMA4h_t-1 = 再前一根已闭合 4h K 线对应的 EMA
    """
    if len(klines_4h) < ema_period + 2:
        return None

    # 计算 EMA 流
    ema_calculator = EMACalculator(period=ema_period)

    # 预热 EMA
    for kline in klines_4h[:-1]:  # 不包括最后一根
        ema_calculator.update(kline.close)

    # 获取最近两根已闭合 K 线的 EMA
    # 注意：我们需要的是 t 和 t-1 两根 K 线的 EMA
    # EMA 流在更新最后一根 K 线后，current_value 就是 EMA_t
    # 我们需要保存 EMA_t-1

    if not ema_calculator.is_ready:
        return None

    # 获取 EMA_t-1（倒数第二根 K 线更新后的 EMA）
    ema_t_minus_1 = None
    for i, kline in enumerate(klines_4h[:-1]):
        ema_calculator.update(kline.close)
        if i == len(klines_4h) - 2:
            ema_t_minus_1 = ema_calculator.value

    # 获取 EMA_t（最后一根 K 线更新后的 EMA）
    ema_calculator.update(klines_4h[-1].close)
    ema_t = ema_calculator.value

    if ema_t_minus_1 is None or ema_t is None:
        return None

    if ema_t_minus_1 == 0:
        return None

    # 计算斜率
    slope = (ema_t - ema_t_minus_1) / ema_t_minus_1

    return slope


def calculate_ema_distance_1h(entry_price: Decimal, ema_1h: Decimal) -> Optional[Decimal]:
    """
    计算价格相对 1h EMA 的距离

    公式：ema_distance_1h = (entry_price - EMA1h_t) / EMA1h_t
    """
    if ema_1h == 0:
        return None

    distance = (entry_price - ema_1h) / ema_1h
    return distance


async def analyze_positions_features(gateway, positions, year):
    """分析仓位的环境特征"""

    # 区分盈利和亏损交易
    profitable_features = {
        "ema_slope_4h": [],
        "ema_distance_1h": [],
    }

    losing_features = {
        "ema_slope_4h": [],
        "ema_distance_1h": [],
    }

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
            # 获取 4h K 线数据
            klines_4h = await fetch_4h_klines(
                gateway,
                symbol="ETH/USDT:USDT",
                entry_time=pos.entry_time,
                lookback_bars=60,  # 多取一些用于 EMA 预热
            )

            # 计算 4h EMA 斜率
            ema_slope_4h = calculate_ema_slope_4h(klines_4h, ema_period=50)

            # 计算 1h EMA 距离（需要从回测结果中获取 EMA 值）
            # 注意：PositionSummary 没有 ema_value 属性
            # 我们需要从回测过程中获取，或者重新计算
            # 这里简化处理：从 entry_price 和 min_distance_pct 反推近似 EMA
            # 更准确的方法是在回测时保存 EMA 值

            # 简化方法：获取入场时刻的 1h K 线，重新计算 EMA
            klines_1h = await gateway.fetch_historical_ohlcv(
                symbol="ETH/USDT:USDT",
                timeframe="1h",
                since=pos.entry_time - int(60 * 3600 * 1000),
                limit=60,
            )
            klines_1h = [k for k in klines_1h if k.timestamp < pos.entry_time]
            klines_1h = sorted(klines_1h, key=lambda k: k.timestamp)

            if len(klines_1h) < 50:
                missing_count += 1
                continue

            ema_calculator_1h = EMACalculator(period=50)
            for kline in klines_1h:
                ema_calculator_1h.update(kline.close)

            if not ema_calculator_1h.is_ready:
                missing_count += 1
                continue

            ema_1h = ema_calculator_1h.value
            ema_distance_1h = calculate_ema_distance_1h(pos.entry_price, ema_1h)

            if ema_slope_4h is None or ema_distance_1h is None:
                missing_count += 1
                continue

            total_analyzed += 1

            # 判断盈利还是亏损
            is_profitable = pos.realized_pnl > 0

            features = profitable_features if is_profitable else losing_features
            features["ema_slope_4h"].append(float(ema_slope_4h))
            features["ema_distance_1h"].append(float(ema_distance_1h))

        except Exception as e:
            print(f"  警告: 仓位 {i} 分析失败: {e}")
            missing_count += 1
            continue

    # 计算统计指标
    def calc_stats(values: List[float]) -> Dict[str, float]:
        if not values:
            return {
                "count": 0,
                "mean": 0,
                "median": 0,
                "p25": 0,
                "p75": 0,
            }
        sorted_values = sorted(values)
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "p25": sorted_values[int(len(values) * 0.25)],
            "p75": sorted_values[int(len(values) * 0.75)],
        }

    stats = {
        "year": year,
        "total_positions": len(positions),
        "analyzed_positions": total_analyzed,
        "missing_count": missing_count,
        "profitable": {
            "ema_slope_4h": calc_stats(profitable_features["ema_slope_4h"]),
            "ema_distance_1h": calc_stats(profitable_features["ema_distance_1h"]),
        },
        "losing": {
            "ema_slope_4h": calc_stats(losing_features["ema_slope_4h"]),
            "ema_distance_1h": calc_stats(losing_features["ema_distance_1h"]),
        },
    }

    return stats


async def main():
    print("=" * 80)
    print("最小特征对比分析：2023 坏交易的环境特征")
    print("=" * 80)
    print("\n配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n分析特征:")
    print("1. 4h EMA 斜率：ema_slope_4h = (EMA4h_t - EMA4h_t-1) / EMA4h_t-1")
    print("2. 价格相对 1h EMA 距离：ema_distance_1h = (entry_price - EMA1h_t) / EMA1h_t")
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

        # 分析环境特征
        print("\n分析环境特征...")
        stats_2023 = await analyze_positions_features(gateway, report_2023.positions, 2023)
        stats_2024 = await analyze_positions_features(gateway, report_2024.positions, 2024)
        stats_2025 = await analyze_positions_features(gateway, report_2025.positions, 2025)

        # 输出对比表
        print("\n" + "=" * 80)
        print("年度对比表")
        print("=" * 80)

        # 输出缺失样本数
        print("\n【样本统计】")
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']} 年: 分析 {stats['analyzed_positions']} 笔，缺失 {stats['missing_count']} 笔")

        # 输出 4h EMA 斜率对比
        print("\n【4h EMA 斜率对比】")
        print("\n盈利交易：")
        print(f"{'年份':<8} {'样本数':<10} {'均值':<15} {'中位数':<15} {'25分位':<15} {'75分位':<15}")
        print("-" * 80)
        for stats in [stats_2023, stats_2024, stats_2025]:
            s = stats['profitable']['ema_slope_4h']
            print(f"{stats['year']:<8} {s['count']:<10} {s['mean']*100:<15.4f}% {s['median']*100:<15.4f}% {s['p25']*100:<15.4f}% {s['p75']*100:<15.4f}%")

        print("\n亏损交易：")
        print(f"{'年份':<8} {'样本数':<10} {'均值':<15} {'中位数':<15} {'25分位':<15} {'75分位':<15}")
        print("-" * 80)
        for stats in [stats_2023, stats_2024, stats_2025]:
            s = stats['losing']['ema_slope_4h']
            print(f"{stats['year']:<8} {s['count']:<10} {s['mean']*100:<15.4f}% {s['median']*100:<15.4f}% {s['p25']*100:<15.4f}% {s['p75']*100:<15.4f}%")

        # 输出 1h EMA 距离对比
        print("\n【价格相对 1h EMA 距离对比】")
        print("\n盈利交易：")
        print(f"{'年份':<8} {'样本数':<10} {'均值':<15} {'中位数':<15} {'25分位':<15} {'75分位':<15}")
        print("-" * 80)
        for stats in [stats_2023, stats_2024, stats_2025]:
            s = stats['profitable']['ema_distance_1h']
            print(f"{stats['year']:<8} {s['count']:<10} {s['mean']*100:<15.4f}% {s['median']*100:<15.4f}% {s['p25']*100:<15.4f}% {s['p75']*100:<15.4f}%")

        print("\n亏损交易：")
        print(f"{'年份':<8} {'样本数':<10} {'均值':<15} {'中位数':<15} {'25分位':<15} {'75分位':<15}")
        print("-" * 80)
        for stats in [stats_2023, stats_2024, stats_2025]:
            s = stats['losing']['ema_distance_1h']
            print(f"{stats['year']:<8} {s['count']:<10} {s['mean']*100:<15.4f}% {s['median']*100:<15.4f}% {s['p25']*100:<15.4f}% {s['p75']*100:<15.4f}%")

        # 跨年对比总结
        print("\n" + "=" * 80)
        print("跨年对比总结")
        print("=" * 80)

        # 分析 4h EMA 斜率
        print("\n【4h EMA 斜率分析】")
        print("\n盈利交易对比：")
        slope_profit_2023 = stats_2023['profitable']['ema_slope_4h']['mean']
        slope_profit_2024 = stats_2024['profitable']['ema_slope_4h']['mean']
        slope_profit_2025 = stats_2025['profitable']['ema_slope_4h']['mean']
        print(f"  2023: {slope_profit_2023*100:.4f}%")
        print(f"  2024: {slope_profit_2024*100:.4f}% (vs 2023: {(slope_profit_2024 - slope_profit_2023)*100:+.4f}%)")
        print(f"  2025: {slope_profit_2025*100:.4f}% (vs 2023: {(slope_profit_2025 - slope_profit_2023)*100:+.4f}%)")

        print("\n亏损交易对比：")
        slope_lose_2023 = stats_2023['losing']['ema_slope_4h']['mean']
        slope_lose_2024 = stats_2024['losing']['ema_slope_4h']['mean']
        slope_lose_2025 = stats_2025['losing']['ema_slope_4h']['mean']
        print(f"  2023: {slope_lose_2023*100:.4f}%")
        print(f"  2024: {slope_lose_2024*100:.4f}% (vs 2023: {(slope_lose_2024 - slope_lose_2023)*100:+.4f}%)")
        print(f"  2025: {slope_lose_2025*100:.4f}% (vs 2023: {(slope_lose_2025 - slope_lose_2023)*100:+.4f}%)")

        # 分析 1h EMA 距离
        print("\n【价格相对 1h EMA 距离分析】")
        print("\n盈利交易对比：")
        dist_profit_2023 = stats_2023['profitable']['ema_distance_1h']['mean']
        dist_profit_2024 = stats_2024['profitable']['ema_distance_1h']['mean']
        dist_profit_2025 = stats_2025['profitable']['ema_distance_1h']['mean']
        print(f"  2023: {dist_profit_2023*100:.4f}%")
        print(f"  2024: {dist_profit_2024*100:.4f}% (vs 2023: {(dist_profit_2024 - dist_profit_2023)*100:+.4f}%)")
        print(f"  2025: {dist_profit_2025*100:.4f}% (vs 2023: {(dist_profit_2025 - dist_profit_2023)*100:+.4f}%)")

        print("\n亏损交易对比：")
        dist_lose_2023 = stats_2023['losing']['ema_distance_1h']['mean']
        dist_lose_2024 = stats_2024['losing']['ema_distance_1h']['mean']
        dist_lose_2025 = stats_2025['losing']['ema_distance_1h']['mean']
        print(f"  2023: {dist_lose_2023*100:.4f}%")
        print(f"  2024: {dist_lose_2024*100:.4f}% (vs 2023: {(dist_lose_2024 - dist_lose_2023)*100:+.4f}%)")
        print(f"  2025: {dist_lose_2025*100:.4f}% (vs 2023: {(dist_lose_2025 - dist_lose_2023)*100:+.4f}%)")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        # 判断是否有明显差异
        slope_diff_profit = abs(slope_profit_2024 - slope_profit_2023) + abs(slope_profit_2025 - slope_profit_2023)
        slope_diff_lose = abs(slope_lose_2024 - slope_lose_2023) + abs(slope_lose_2025 - slope_lose_2023)
        dist_diff_profit = abs(dist_profit_2024 - dist_profit_2023) + abs(dist_profit_2025 - dist_profit_2023)
        dist_diff_lose = abs(dist_lose_2024 - dist_lose_2023) + abs(dist_lose_2025 - dist_lose_2023)

        # 判断 2023 亏损交易的特征是否明显不同
        slope_2023_lose_different = (
            abs(slope_lose_2023 - slope_profit_2023) > 0.001 or  # 亏损 vs 盈利差异
            slope_diff_lose > 0.002  # 与 2024/2025 亏损交易差异
        )

        dist_2023_lose_different = (
            abs(dist_lose_2023 - dist_profit_2023) > 0.001 or  # 亏损 vs 盈利差异
            dist_diff_lose > 0.002  # 与 2024/2025 亏损交易差异
        )

        print("\n【特征差异分析】")
        print(f"\n4h EMA 斜率：")
        print(f"  2023 亏损交易均值: {slope_lose_2023*100:.4f}%")
        print(f"  2023 盈利交易均值: {slope_profit_2023*100:.4f}%")
        print(f"  差异: {(slope_lose_2023 - slope_profit_2023)*100:.4f}%")
        if abs(slope_lose_2023 - slope_profit_2023) > 0.001:
            print("  ⚠️  2023 亏损交易与盈利交易的 4h EMA 斜率有明显差异")
        else:
            print("  ✅ 2023 亏损交易与盈利交易的 4h EMA 斜率无明显差异")

        print(f"\n价格相对 1h EMA 距离：")
        print(f"  2023 亏损交易均值: {dist_lose_2023*100:.4f}%")
        print(f"  2023 盈利交易均值: {dist_profit_2023*100:.4f}%")
        print(f"  差异: {(dist_lose_2023 - dist_profit_2023)*100:.4f}%")
        if abs(dist_lose_2023 - dist_profit_2023) > 0.001:
            print("  ⚠️  2023 亏损交易与盈利交易的价格相对 EMA 距离有明显差异")
        else:
            print("  ✅ 2023 亏损交易与盈利交易的价格相对 EMA 距离无明显差异")

        # 最终答案
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        if slope_2023_lose_different or dist_2023_lose_different:
            print("\n⚠️  这两个特征里，有明显迹象可作为下一步'不开仓条件'候选：")
            if slope_2023_lose_different:
                print(f"   - 4h EMA 斜率：2023 亏损交易均值为 {slope_lose_2023*100:.4f}%，与盈利交易差异明显")
            if dist_2023_lose_different:
                print(f"   - 价格相对 1h EMA 距离：2023 亏损交易均值为 {dist_lose_2023*100:.4f}%，与盈利交易差异明显")
        else:
            print("\n✅ 这两个特征里，没有明显迹象可作为下一步'不开仓条件'候选。")
            print("   2023 亏损交易与盈利交易在这两个特征上无明显差异。")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
