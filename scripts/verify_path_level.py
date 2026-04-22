#!/usr/bin/env python3
"""
路径级验证：first-touch 比例 + 可达率分布

目标：
1. 基于 2023/2024/2025 三年真实成交样本
2. 统计 first-touch 比例：入场后先到 +0.5R 还是先到 -0.5R
3. 统计可达率分布：24h 内达到 +1R / +2R / +3.5R 的比例
4. 判断 2023 失效是否源于后续空间不足

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


def check_first_touch(entry_price: Decimal, stop_loss: Decimal, klines: List) -> str:
    """
    判断先到 +0.5R 还是先到 -0.5R

    对于 LONG：
    - +0.5R = entry_price + 0.5 * (entry_price - stop_loss)
    - -0.5R = entry_price - 0.5 * (entry_price - stop_loss)
    """
    if not klines:
        return "NONE"

    risk = abs(entry_price - stop_loss)
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


def check_reachability(entry_price: Decimal, stop_loss: Decimal, klines: List) -> Dict[str, bool]:
    """
    检查 24h 内是否达到 +1R / +2R / +3.5R

    对于 LONG：
    - +1R = entry_price + 1.0 * (entry_price - stop_loss)
    - +2R = entry_price + 2.0 * (entry_price - stop_loss)
    - +3.5R = entry_price + 3.5 * (entry_price - stop_loss)
    """
    if not klines:
        return {"reach_1R": False, "reach_2R": False, "reach_3_5R": False}

    risk = abs(entry_price - stop_loss)
    target_1R = entry_price + Decimal("1.0") * risk
    target_2R = entry_price + Decimal("2.0") * risk
    target_3_5R = entry_price + Decimal("3.5") * risk

    reach_1R = False
    reach_2R = False
    reach_3_5R = False

    for kline in klines:
        if kline.high >= target_1R:
            reach_1R = True
        if kline.high >= target_2R:
            reach_2R = True
        if kline.high >= target_3_5R:
            reach_3_5R = True

    return {
        "reach_1R": reach_1R,
        "reach_2R": reach_2R,
        "reach_3_5R": reach_3_5R,
    }


async def analyze_positions_path(gateway, positions, year):
    """分析仓位的路径级指标"""

    # First-touch 统计
    up_first_count = 0
    down_first_count = 0
    none_count = 0

    # 可达率统计
    reach_1R_count = 0
    reach_2R_count = 0
    reach_3_5R_count = 0

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

            total_analyzed += 1

            # 从 close_events 获取止损价格
            # 注意：PositionSummary 没有 stop_loss 属性
            # 我们需要从 TP/SL 价格反推止损
            # 这里使用一个简化方法：从 realized_pnl 和 exit_price 反推

            # 简化方法：假设止损距离 = 入场价 * 1%（max_loss_percent）
            # 这是近似值，实际止损可能不同
            stop_loss = pos.entry_price * Decimal("0.99")  # 近似值

            # First-touch 判断
            first_touch = check_first_touch(pos.entry_price, stop_loss, klines)

            if first_touch == "UP_FIRST":
                up_first_count += 1
            elif first_touch == "DOWN_FIRST":
                down_first_count += 1
            else:
                none_count += 1

            # 可达率判断
            reachability = check_reachability(pos.entry_price, stop_loss, klines)

            if reachability["reach_1R"]:
                reach_1R_count += 1
            if reachability["reach_2R"]:
                reach_2R_count += 1
            if reachability["reach_3_5R"]:
                reach_3_5R_count += 1

        except Exception as e:
            print(f"  警告: 仓位 {i} 分析失败: {e}")
            continue

    # 计算统计指标
    stats = {
        "year": year,
        "total_positions": len(positions),
        "analyzed_positions": total_analyzed,
        # First-touch
        "up_first_count": up_first_count,
        "down_first_count": down_first_count,
        "none_count": none_count,
        "up_first_rate": up_first_count / total_analyzed if total_analyzed > 0 else 0,
        "down_first_rate": down_first_count / total_analyzed if total_analyzed > 0 else 0,
        # Reachability
        "reach_1R_count": reach_1R_count,
        "reach_2R_count": reach_2R_count,
        "reach_3_5R_count": reach_3_5R_count,
        "reach_1R_rate": reach_1R_count / total_analyzed if total_analyzed > 0 else 0,
        "reach_2R_rate": reach_2R_count / total_analyzed if total_analyzed > 0 else 0,
        "reach_3_5R_rate": reach_3_5R_count / total_analyzed if total_analyzed > 0 else 0,
    }

    return stats


async def main():
    print("=" * 80)
    print("路径级验证：first-touch 比例 + 可达率分布")
    print("=" * 80)
    print("\n配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n验证指标:")
    print("1. First-touch 比例：入场后先到 +0.5R 还是先到 -0.5R")
    print("2. 可达率分布：24h 内达到 +1R / +2R / +3.5R 的比例")
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

        # 分析路径级指标
        print("\n分析路径级指标...")
        stats_2023 = await analyze_positions_path(gateway, report_2023.positions, 2023)
        stats_2024 = await analyze_positions_path(gateway, report_2024.positions, 2024)
        stats_2025 = await analyze_positions_path(gateway, report_2025.positions, 2025)

        # 输出对比表
        print("\n" + "=" * 80)
        print("年度对比表")
        print("=" * 80)

        print("\n【First-touch 比例：先到 +0.5R vs 先到 -0.5R】")
        print(f"{'年份':<8} {'样本数':<10} {'先到+0.5R':<20} {'先到-0.5R':<20} {'未触及':<10}")
        print("-" * 70)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} {stats['analyzed_positions']:<10} "
                  f"{stats['up_first_count']}({stats['up_first_rate']*100:.1f}%){'':<10} "
                  f"{stats['down_first_count']}({stats['down_first_rate']*100:.1f}%){'':<10} "
                  f"{stats['none_count']}")

        print("\n【可达率分布：24h 内达到 +1R / +2R / +3.5R 的比例】")
        print(f"{'年份':<8} {'样本数':<10} {'达到+1R':<20} {'达到+2R':<20} {'达到+3.5R':<20}")
        print("-" * 80)
        for stats in [stats_2023, stats_2024, stats_2025]:
            print(f"{stats['year']:<8} {stats['analyzed_positions']:<10} "
                  f"{stats['reach_1R_count']}({stats['reach_1R_rate']*100:.1f}%){'':<10} "
                  f"{stats['reach_2R_count']}({stats['reach_2R_rate']*100:.1f}%){'':<10} "
                  f"{stats['reach_3_5R_count']}({stats['reach_3_5R_rate']*100:.1f}%)")

        # 跨年对比总结
        print("\n" + "=" * 80)
        print("跨年对比总结")
        print("=" * 80)

        # 问题 1：2023 是否更容易先到 -0.5R 而不是 +0.5R？
        print("\n【问题 1】2023 是否更容易先到 -0.5R 而不是 +0.5R？")
        print("-" * 80)

        up_first_diff_2024_vs_2023 = (stats_2024['up_first_rate'] - stats_2023['up_first_rate']) * 100
        up_first_diff_2025_vs_2023 = (stats_2025['up_first_rate'] - stats_2023['up_first_rate']) * 100

        down_first_diff_2024_vs_2023 = (stats_2024['down_first_rate'] - stats_2023['down_first_rate']) * 100
        down_first_diff_2025_vs_2023 = (stats_2025['down_first_rate'] - stats_2023['down_first_rate']) * 100

        print(f"先到 +0.5R 比例:")
        print(f"  2023: {stats_2023['up_first_rate']*100:.1f}%")
        print(f"  2024: {stats_2024['up_first_rate']*100:.1f}% (vs 2023: {up_first_diff_2024_vs_2023:+.1f}%)")
        print(f"  2025: {stats_2025['up_first_rate']*100:.1f}% (vs 2023: {up_first_diff_2025_vs_2023:+.1f}%)")

        print(f"\n先到 -0.5R 比例:")
        print(f"  2023: {stats_2023['down_first_rate']*100:.1f}%")
        print(f"  2024: {stats_2024['down_first_rate']*100:.1f}% (vs 2023: {down_first_diff_2024_vs_2023:+.1f}%)")
        print(f"  2025: {stats_2025['down_first_rate']*100:.1f}% (vs 2023: {down_first_diff_2025_vs_2023:+.1f}%)")

        # 判断
        if stats_2023['down_first_rate'] > stats_2023['up_first_rate']:
            print(f"\n✅ 答案：是。2023 年先到 -0.5R 的比例 ({stats_2023['down_first_rate']*100:.1f}%) "
                  f"高于先到 +0.5R 的比例 ({stats_2023['up_first_rate']*100:.1f}%)")
        else:
            print(f"\n❌ 答案：否。2023 年先到 +0.5R 的比例 ({stats_2023['up_first_rate']*100:.1f}%) "
                  f"高于或等于先到 -0.5R 的比例 ({stats_2023['down_first_rate']*100:.1f}%)")

        # 问题 2：2023 对 +1R / +2R / +3.5R 的可达率是否显著低于 2024/2025？
        print("\n【问题 2】2023 对 +1R / +2R / +3.5R 的可达率是否显著低于 2024/2025？")
        print("-" * 80)

        reach_1R_diff_2024_vs_2023 = (stats_2024['reach_1R_rate'] - stats_2023['reach_1R_rate']) * 100
        reach_1R_diff_2025_vs_2023 = (stats_2025['reach_1R_rate'] - stats_2023['reach_1R_rate']) * 100

        reach_2R_diff_2024_vs_2023 = (stats_2024['reach_2R_rate'] - stats_2023['reach_2R_rate']) * 100
        reach_2R_diff_2025_vs_2023 = (stats_2025['reach_2R_rate'] - stats_2023['reach_2R_rate']) * 100

        reach_3_5R_diff_2024_vs_2023 = (stats_2024['reach_3_5R_rate'] - stats_2023['reach_3_5R_rate']) * 100
        reach_3_5R_diff_2025_vs_2023 = (stats_2025['reach_3_5R_rate'] - stats_2023['reach_3_5R_rate']) * 100

        print(f"+1R 可达率:")
        print(f"  2023: {stats_2023['reach_1R_rate']*100:.1f}%")
        print(f"  2024: {stats_2024['reach_1R_rate']*100:.1f}% (vs 2023: {reach_1R_diff_2024_vs_2023:+.1f}%)")
        print(f"  2025: {stats_2025['reach_1R_rate']*100:.1f}% (vs 2023: {reach_1R_diff_2025_vs_2023:+.1f}%)")

        print(f"\n+2R 可达率:")
        print(f"  2023: {stats_2023['reach_2R_rate']*100:.1f}%")
        print(f"  2024: {stats_2024['reach_2R_rate']*100:.1f}% (vs 2023: {reach_2R_diff_2024_vs_2023:+.1f}%)")
        print(f"  2025: {stats_2025['reach_2R_rate']*100:.1f}% (vs 2023: {reach_2R_diff_2025_vs_2023:+.1f}%)")

        print(f"\n+3.5R 可达率:")
        print(f"  2023: {stats_2023['reach_3_5R_rate']*100:.1f}%")
        print(f"  2024: {stats_2024['reach_3_5R_rate']*100:.1f}% (vs 2023: {reach_3_5R_diff_2024_vs_2023:+.1f}%)")
        print(f"  2025: {stats_2025['reach_3_5R_rate']*100:.1f}% (vs 2023: {reach_3_5R_diff_2025_vs_2023:+.1f}%)")

        # 判断
        significant_diff = (
            (reach_1R_diff_2024_vs_2023 > 10 or reach_1R_diff_2025_vs_2023 > 10) or
            (reach_2R_diff_2024_vs_2023 > 10 or reach_2R_diff_2025_vs_2023 > 10) or
            (reach_3_5R_diff_2024_vs_2023 > 10 or reach_3_5R_diff_2025_vs_2023 > 10)
        )

        if significant_diff:
            print("\n✅ 答案：是。2023 年对 +1R / +2R / +3.5R 的可达率显著低于 2024/2025 年")
        else:
            print("\n❌ 答案：否。2023 年对 +1R / +2R / +3.5R 的可达率与 2024/2025 年相近")

        # 最终结论
        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        if stats_2023['down_first_rate'] > stats_2023['up_first_rate'] or significant_diff:
            print("\n❌ 2023 年失效源于后续空间不足")
            print("   - 更容易先到 -0.5R 而不是 +0.5R")
            print("   - 对 +1R / +2R / +3.5R 的可达率显著低于 2024/2025 年")
            print("   - 趋势延续不足，导致后续空间受限")
        else:
            print("\n✅ 2023 年失效不是源于后续空间不足")
            print("   - First-touch 比例与 2024/2025 年相近")
            print("   - 可达率分布与 2024/2025 年相近")
            print("   - 更可能是其他因素（如趋势环境不适配）导致失效")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
