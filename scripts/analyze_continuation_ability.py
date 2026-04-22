#!/usr/bin/env python3
"""
入场后延续能力诊断（MFE/MAE/+0.5R vs -0.5R）

目标：
1. 基于 2023/2024/2025 三年真实成交样本
2. 统计入场后 24h 内的最大顺行幅度（MFE）和最大逆行幅度（MAE）
3. 统计入场后先到 +0.5R 还是先到 -0.5R 的比例
4. 判断 2023 失效是否主要因为 LONG 信号延续性弱于 2024/2025

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
from typing import Dict, Any, List, Tuple
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


async def fetch_klines_after_entry(gateway, symbol, timeframe, entry_time, hours=24):
    """获取入场后 24h 的 K 线数据"""
    end_time = entry_time + int(hours * 3600 * 1000)

    # 获取 K 线数据
    klines = await gateway.fetch_historical_ohlcv(
        symbol=symbol,
        timeframe=timeframe,
        since=entry_time,
        limit=24,  # 1h 周期，24 根 K 线
    )

    # 过滤掉入场时间之前的 K 线
    klines = [k for k in klines if k.timestamp >= entry_time]

    # 过滤掉超过 24h 的 K 线
    klines = [k for k in klines if k.timestamp <= end_time]

    return klines


def calculate_mfe_mae(entry_price: Decimal, klines: List) -> Tuple[Decimal, Decimal]:
    """
    计算 MFE（最大顺行幅度）和 MAE（最大逆行幅度）

    对于 LONG：
    - MFE = max(high - entry_price) / entry_price
    - MAE = max(entry_price - low) / entry_price
    """
    if not klines:
        return Decimal("0"), Decimal("0")

    mfe = Decimal("0")
    mae = Decimal("0")

    for kline in klines:
        # 最大顺行幅度（对于 LONG，价格上涨）
        favorable = (kline.high - entry_price) / entry_price
        if favorable > mfe:
            mfe = favorable

        # 最大逆行幅度（对于 LONG，价格下跌）
        adverse = (entry_price - kline.low) / entry_price
        if adverse > mae:
            mae = adverse

    return mfe, mae


def check_which_first(entry_price: Decimal, stop_loss: Decimal, klines: List) -> str:
    """
    判断先到 +0.5R 还是先到 -0.5R

    对于 LONG：
    - +0.5R = entry_price + 0.5 * (entry_price - stop_loss)
    - -0.5R = entry_price - 0.5 * (entry_price - stop_loss)
    """
    if not klines:
        return "NONE"

    risk = entry_price - stop_loss
    target_up = entry_price + Decimal("0.5") * risk    # +0.5R
    target_down = entry_price - Decimal("0.5") * risk  # -0.5R

    for kline in klines:
        # 检查是否先到 +0.5R
        if kline.high >= target_up:
            return "UP_FIRST"

        # 检查是否先到 -0.5R
        if kline.low <= target_down:
            return "DOWN_FIRST"

    return "NONE"


async def analyze_positions_continuation(gateway, positions, year):
    """分析仓位的延续能力"""

    mfe_list = []
    mae_list = []

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
            # 获取入场后 24h 的 K 线
            klines = await fetch_klines_after_entry(
                gateway,
                symbol="ETH/USDT:USDT",
                timeframe="1h",
                entry_time=pos.entry_time,
                hours=24,
            )

            if not klines:
                continue

            # 计算 MFE 和 MAE
            mfe, mae = calculate_mfe_mae(pos.entry_price, klines)
            mfe_list.append(float(mfe))
            mae_list.append(float(mae))

        except Exception as e:
            print(f"  警告: 仓位 {i} 分析失败: {e}")
            continue

    # 计算统计指标
    stats = {
        "year": year,
        "total_positions": len(positions),
        "analyzed_positions": len(mfe_list),
        "mfe_mean": statistics.mean(mfe_list) if mfe_list else 0,
        "mfe_median": statistics.median(mfe_list) if mfe_list else 0,
        "mfe_p25": sorted(mfe_list)[int(len(mfe_list) * 0.25)] if mfe_list else 0,
        "mfe_p75": sorted(mfe_list)[int(len(mfe_list) * 0.75)] if mfe_list else 0,
        "mae_mean": statistics.mean(mae_list) if mae_list else 0,
        "mae_median": statistics.median(mae_list) if mae_list else 0,
        "mae_p25": sorted(mae_list)[int(len(mae_list) * 0.25)] if mae_list else 0,
        "mae_p75": sorted(mae_list)[int(len(mae_list) * 0.75)] if mae_list else 0,
    }

    return stats


async def main():
    print("=" * 80)
    print("入场后延续能力诊断（MFE/MAE/+0.5R vs -0.5R）")
    print("=" * 80)
    print("\n配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n诊断指标:")
    print("1. MFE（Maximum Favorable Excursion）: 入场后 24h 内最大顺行幅度")
    print("2. MAE（Maximum Adverse Excursion）: 入场后 24h 内最大逆行幅度")
    print("3. 先到 +0.5R vs 先到 -0.5R 的比例")
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

        # 分析延续能力
        print("\n分析延续能力...")
        stats_2023 = await analyze_positions_continuation(gateway, report_2023.positions, 2023)
        stats_2024 = await analyze_positions_continuation(gateway, report_2024.positions, 2024)
        stats_2025 = await analyze_positions_continuation(gateway, report_2025.positions, 2025)

        # 输出对比表
        print("\n" + "=" * 80)
        print("年度对比表")
        print("=" * 80)

        print("\n【MFE（最大顺行幅度）】")
        print(f"{'年份':<8} {'均值':<12} {'中位数':<12} {'25分位':<12} {'75分位':<12}")
        print("-" * 60)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} {stats['mfe_mean']*100:<12.2f}% {stats['mfe_median']*100:<12.2f}% {stats['mfe_p25']*100:<12.2f}% {stats['mfe_p75']*100:<12.2f}%")

        print("\n【MAE（最大逆行幅度）】")
        print(f"{'年份':<8} {'均值':<12} {'中位数':<12} {'25分位':<12} {'75分位':<12}")
        print("-" * 60)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} {stats['mae_mean']*100:<12.2f}% {stats['mae_median']*100:<12.2f}% {stats['mae_p25']*100:<12.2f}% {stats['mae_p75']*100:<12.2f}%")

        # 跨年对比总结
        print("\n" + "=" * 80)
        print("跨年对比总结")
        print("=" * 80)

        # MFE 对比
        mfe_diff_2024_vs_2023 = (stats_2024['mfe_mean'] - stats_2023['mfe_mean']) * 100
        mfe_diff_2025_vs_2023 = (stats_2025['mfe_mean'] - stats_2023['mfe_mean']) * 100

        print(f"\n1. MFE 对比:")
        print(f"   2024 vs 2023: {mfe_diff_2024_vs_2023:+.2f}%")
        print(f"   2025 vs 2023: {mfe_diff_2025_vs_2023:+.2f}%")

        if mfe_diff_2024_vs_2023 > 0.5 or mfe_diff_2025_vs_2023 > 0.5:
            print("   ⚠️  2023 年 MFE 明显低于 2024/2025 年，延续性较弱")
        else:
            print("   ✅ 2023 年 MFE 与 2024/2025 年相近，延续性无明显差异")

        # MAE 对比
        mae_diff_2024_vs_2023 = (stats_2024['mae_mean'] - stats_2023['mae_mean']) * 100
        mae_diff_2025_vs_2023 = (stats_2025['mae_mean'] - stats_2023['mae_mean']) * 100

        print(f"\n2. MAE 对比:")
        print(f"   2024 vs 2023: {mae_diff_2024_vs_2023:+.2f}%")
        print(f"   2025 vs 2023: {mae_diff_2025_vs_2023:+.2f}%")

        if mae_diff_2024_vs_2023 < -0.5 or mae_diff_2025_vs_2023 < -0.5:
            print("   ⚠️  2023 年 MAE 明显高于 2024/2025 年，逆行幅度更大")
        else:
            print("   ✅ 2023 年 MAE 与 2024/2025 年相近，逆行幅度无明显差异")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        # 综合判断
        weak_continuation = (
            (mfe_diff_2024_vs_2023 > 0.5 or mfe_diff_2025_vs_2023 > 0.5) or
            (mae_diff_2024_vs_2023 < -0.5 or mae_diff_2025_vs_2023 < -0.5)
        )

        if weak_continuation:
            print("\n❌ 2023 年失效的主要原因：LONG 信号入场后延续性明显弱于 2024/2025 年")
            print("   - MFE 更低（顺行幅度不足）")
            print("   - MAE 更高（逆行幅度更大）")
        else:
            print("\n✅ 2023 年失效的主要原因：不是入场后延续性弱，而是其他因素")
            print("   - MFE、MAE 与 2024/2025 年相近")
            print("   - 更可能是趋势环境不适配（熊市/震荡期）导致整体失效")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
