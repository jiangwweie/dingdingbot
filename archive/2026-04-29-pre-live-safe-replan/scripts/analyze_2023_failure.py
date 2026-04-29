#!/usr/bin/env python3
"""
2023 年失效归因分析脚本

目标：
1. 2023 全年按月份拆分的 pnl/trades/win_rate/sharpe/max_drawdown
2. 多空/入场质量/TP1命中率/TP2命中率/SL占比/平均持仓时长
3. 2023 与 2024、2025 的关键对比
4. 回答：2023 失效更像是趋势环境不适配、信号质量下降、还是 exit 兑现失败

测试配置（冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False
- ATR 移除, MTF 用 system config
- max_loss_percent=1%
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


async def run_year_backtest(
    gateway: ExchangeGateway,
    backtester: Backtester,
    year: int,
) -> Dict[str, Any]:
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

    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    result = {
        "year": year,
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) if report.max_drawdown else 0.0,
        "positions": report.positions if hasattr(report, 'positions') else [],
    }

    return result


async def run_monthly_backtest(
    gateway: ExchangeGateway,
    backtester: Backtester,
    year: int,
) -> List[Dict[str, Any]]:
    """运行按月份拆分的回测"""

    results = []

    for month in range(1, 13):
        start_time = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)

        # 计算月末
        if month == 12:
            end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
        else:
            end_time = int(datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000 - 1)

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

        report = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides,
        )

        result = {
            "year": year,
            "month": month,
            "pnl": float(report.total_pnl),
            "trades": report.total_trades,
            "win_rate": float(report.win_rate),
            "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
            "max_drawdown": float(report.max_drawdown) if report.max_drawdown else 0.0,
            "positions": report.positions if hasattr(report, 'positions') else [],
        }

        results.append(result)

        print(f"  {year}-{month:02d}: PnL={result['pnl']:.2f}, Trades={result['trades']}, WinRate={result['win_rate']*100:.2f}%")

    return results


async def analyze_positions(positions: List[Any]) -> Dict[str, Any]:
    """分析仓位数据"""

    if not positions:
        return {}

    # 统计指标
    total_positions = len(positions)

    # TP1/TP2/SL 命中率
    tp1_count = 0
    tp2_count = 0
    sl_count = 0
    total_closed = 0

    # 平均持仓时长
    holding_times = []

    # 入场质量（估算：基于 pnl_ratio）
    entry_qualities = []

    for pos in positions:
        # 检查是否已平仓（有 exit_price 和 exit_time）
        if pos.exit_price is not None and pos.exit_time is not None:
            total_closed += 1

            # 检查平仓原因
            exit_reason = pos.exit_reason if hasattr(pos, 'exit_reason') else None

            if exit_reason == "TP1":
                tp1_count += 1
            elif exit_reason == "TP2":
                tp2_count += 1
            elif exit_reason == "SL":
                sl_count += 1

            # 持仓时长
            if hasattr(pos, 'entry_time') and hasattr(pos, 'exit_time'):
                holding_time = pos.exit_time - pos.entry_time
                holding_times.append(holding_time)

            # 入场质量（基于 realized_pnl）
            if hasattr(pos, 'realized_pnl') and hasattr(pos, 'entry_price'):
                pnl_ratio = float(pos.realized_pnl) / float(pos.entry_price)
                entry_qualities.append(pnl_ratio)

    # 计算命中率
    tp1_rate = tp1_count / total_closed if total_closed > 0 else 0
    tp2_rate = tp2_count / total_closed if total_closed > 0 else 0
    sl_rate = sl_count / total_closed if total_closed > 0 else 0

    # 平均持仓时长（小时）
    avg_holding_time = statistics.mean(holding_times) / 3600000 if holding_times else 0

    # 入场质量评分（基于 pnl_ratio 分布）
    avg_entry_quality = statistics.mean(entry_qualities) if entry_qualities else 0

    return {
        "total_positions": total_positions,
        "total_closed": total_closed,
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "tp1_rate": tp1_rate,
        "tp2_rate": tp2_rate,
        "sl_rate": sl_rate,
        "avg_holding_time_hours": avg_holding_time,
        "avg_entry_quality": avg_entry_quality,
    }


async def main():
    """主函数"""

    print("=" * 80)
    print("2023 年失效归因分析")
    print("=" * 80)
    print("\n测试配置（冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("\n目标：")
    print("1. 2023 全年按月份拆分")
    print("2. 多空/入场质量/TP命中率/SL占比/平均持仓时长")
    print("3. 2023 vs 2024/2025 关键对比")
    print("4. 失效原因归因")
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
        # 第一部分：2023 年按月份拆分
        print(f"\n{'=' * 80}")
        print("第一部分：2023 年按月份拆分")
        print(f"{'=' * 80}")

        monthly_results_2023 = await run_monthly_backtest(gateway, backtester, 2023)

        # 汇总 2023 年度数据
        year_result_2023 = await run_year_backtest(gateway, backtester, 2023)

        print(f"\n2023 年度汇总:")
        print(f"  PnL: {year_result_2023['pnl']:.2f} USDT")
        print(f"  Trades: {year_result_2023['trades']}")
        print(f"  Win Rate: {year_result_2023['win_rate'] * 100:.2f}%")
        print(f"  Sharpe: {year_result_2023['sharpe']:.3f}")
        print(f"  Max DD: {year_result_2023['max_drawdown'] * 100:.2f}%")

        # 第二部分：2023 年仓位分析
        print(f"\n{'=' * 80}")
        print("第二部分：2023 年仓位分析")
        print(f"{'=' * 80}")

        position_stats_2023 = await analyze_positions(year_result_2023['positions'])

        if position_stats_2023:
            print(f"\n仓位统计:")
            print(f"  总仓位数: {position_stats_2023['total_positions']}")
            print(f"  已平仓数: {position_stats_2023['total_closed']}")
            print(f"\n平仓方式分布:")
            print(f"  TP1 命中: {position_stats_2023['tp1_count']} ({position_stats_2023['tp1_rate']*100:.2f}%)")
            print(f"  TP2 命中: {position_stats_2023['tp2_count']} ({position_stats_2023['tp2_rate']*100:.2f}%)")
            print(f"  SL 命中: {position_stats_2023['sl_count']} ({position_stats_2023['sl_rate']*100:.2f}%)")
            print(f"\n持仓时长:")
            print(f"  平均持仓时长: {position_stats_2023['avg_holding_time_hours']:.2f} 小时")
            print(f"\n入场质量:")
            print(f"  平均入场质量（pnl_ratio）: {position_stats_2023['avg_entry_quality']*100:.2f}%")
        else:
            print(f"\n⚠️ 无法获取仓位详细数据")

        # 第三部分：对比 2024、2025
        print(f"\n{'=' * 80}")
        print("第三部分：2023 vs 2024/2025 关键对比")
        print(f"{'=' * 80}")

        year_result_2024 = await run_year_backtest(gateway, backtester, 2024)
        year_result_2025 = await run_year_backtest(gateway, backtester, 2025)

        print(f"\n年度对比:")
        print(f"{'指标':<15} {'2023':<15} {'2024':<15} {'2025':<15}")
        print(f"{'-' * 60}")
        print(f"{'PnL (USDT)':<15} {year_result_2023['pnl']:<15.2f} {year_result_2024['pnl']:<15.2f} {year_result_2025['pnl']:<15.2f}")
        print(f"{'Trades':<15} {year_result_2023['trades']:<15} {year_result_2024['trades']:<15} {year_result_2025['trades']:<15}")
        print(f"{'Win Rate (%)':<15} {year_result_2023['win_rate']*100:<15.2f} {year_result_2024['win_rate']*100:<15.2f} {year_result_2025['win_rate']*100:<15.2f}")
        print(f"{'Sharpe':<15} {year_result_2023['sharpe']:<15.3f} {year_result_2024['sharpe']:<15.3f} {year_result_2025['sharpe']:<15.3f}")
        print(f"{'Max DD (%)':<15} {year_result_2023['max_drawdown']*100:<15.2f} {year_result_2024['max_drawdown']*100:<15.2f} {year_result_2025['max_drawdown']*100:<15.2f}")

        # 仓位分析对比
        position_stats_2024 = await analyze_positions(year_result_2024['positions'])
        position_stats_2025 = await analyze_positions(year_result_2025['positions'])

        if position_stats_2024 and position_stats_2025:
            print(f"\n仓位分析对比:")
            print(f"{'指标':<20} {'2023':<15} {'2024':<15} {'2025':<15}")
            print(f"{'-' * 65}")
            print(f"{'TP1 命中率 (%)':<20} {position_stats_2023['tp1_rate']*100:<15.2f} {position_stats_2024['tp1_rate']*100:<15.2f} {position_stats_2025['tp1_rate']*100:<15.2f}")
            print(f"{'TP2 命中率 (%)':<20} {position_stats_2023['tp2_rate']*100:<15.2f} {position_stats_2024['tp2_rate']*100:<15.2f} {position_stats_2025['tp2_rate']*100:<15.2f}")
            print(f"{'SL 占比 (%)':<20} {position_stats_2023['sl_rate']*100:<15.2f} {position_stats_2024['sl_rate']*100:<15.2f} {position_stats_2025['sl_rate']*100:<15.2f}")
            print(f"{'平均持仓时长 (h)':<20} {position_stats_2023['avg_holding_time_hours']:<15.2f} {position_stats_2024['avg_holding_time_hours']:<15.2f} {position_stats_2025['avg_holding_time_hours']:<15.2f}")
            print(f"{'入场质量 (%)':<20} {position_stats_2023['avg_entry_quality']*100:<15.2f} {position_stats_2024['avg_entry_quality']*100:<15.2f} {position_stats_2025['avg_entry_quality']*100:<15.2f}")

        # 第四部分：失效原因归因
        print(f"\n{'=' * 80}")
        print("第四部分：失效原因归因")
        print(f"{'=' * 80}")

        # 计算关键差异
        pnl_diff_2024 = year_result_2024['pnl'] - year_result_2023['pnl']
        pnl_diff_2025 = year_result_2025['pnl'] - year_result_2023['pnl']

        win_rate_diff_2024 = year_result_2024['win_rate'] - year_result_2023['win_rate']
        win_rate_diff_2025 = year_result_2025['win_rate'] - year_result_2023['win_rate']

        sharpe_diff_2024 = year_result_2024['sharpe'] - year_result_2023['sharpe']
        sharpe_diff_2025 = year_result_2025['sharpe'] - year_result_2023['sharpe']

        print(f"\n关键差异分析:")
        print(f"  PnL 差异: 2024 vs 2023 = {pnl_diff_2024:+.2f} USDT, 2025 vs 2023 = {pnl_diff_2025:+.2f} USDT")
        print(f"  Win Rate 差异: 2024 vs 2023 = {win_rate_diff_2024*100:+.2f}%, 2025 vs 2023 = {win_rate_diff_2025*100:+.2f}%")
        print(f"  Sharpe 差异: 2024 vs 2023 = {sharpe_diff_2024:+.3f}, 2025 vs 2023 = {sharpe_diff_2025:+.3f}")

        # 归因分析
        print(f"\n归因分析:")

        # 1. 趋势环境不适配
        if year_result_2023['sharpe'] < 0.5 and year_result_2023['win_rate'] < 0.4:
            print(f"  ⚠️  趋势环境不适配：Sharpe < 0.5, Win Rate < 40%")
            print(f"     → 2023 年可能处于震荡或下跌趋势，不适合 LONG-only 策略")
        else:
            print(f"  ✅ 趋势环境适配：Sharpe >= 0.5 或 Win Rate >= 40%")

        # 2. 信号质量下降
        if position_stats_2023 and position_stats_2024 and position_stats_2025:
            entry_quality_diff = position_stats_2024['avg_entry_quality'] - position_stats_2023['avg_entry_quality']
            if entry_quality_diff > 0.01:  # 1% 差异
                print(f"  ⚠️  信号质量下降：入场质量差异 {entry_quality_diff*100:+.2f}%")
                print(f"     → 2023 年信号入场质量明显低于 2024 年")
            else:
                print(f"  ✅ 信号质量稳定：入场质量差异 < 1%")

        # 3. Exit 兑现失败
        if position_stats_2023 and position_stats_2024 and position_stats_2025:
            tp1_diff = position_stats_2024['tp1_rate'] - position_stats_2023['tp1_rate']
            tp2_diff = position_stats_2024['tp2_rate'] - position_stats_2023['tp2_rate']
            sl_diff = position_stats_2024['sl_rate'] - position_stats_2023['sl_rate']

            if sl_diff > 0.05:  # SL 占比差异 > 5%
                print(f"  ⚠️  Exit 兑现失败：SL 占比差异 {sl_diff*100:+.2f}%")
                print(f"     → 2023 年更多仓位被止损，TP 兑现率低")
            else:
                print(f"  ✅ Exit 兑现正常：SL 占比差异 < 5%")

        # 最终结论
        print(f"\n{'=' * 80}")
        print("最终结论")
        print(f"{'=' * 80}")

        # 综合判断
        if year_result_2023['sharpe'] < 0.5 and year_result_2023['win_rate'] < 0.4:
            print(f"\n❌ 这条策略在震荡或下跌趋势市场状态下不该开")
            print(f"   → 2023 年 ETH 可能处于熊市或震荡期，不适合 LONG-only Pinbar 策略")
            print(f"   → 建议：添加趋势环境识别，在熊市/震荡期关闭策略或切换为 SHORT-only")
        elif position_stats_2023 and position_stats_2023['sl_rate'] > 0.5:
            print(f"\n⚠️  这条策略在止损频繁的市场状态下不该开")
            print(f"   → 2023 年 SL 占比过高（{position_stats_2023['sl_rate']*100:.2f}%），exit 兑现失败")
            print(f"   → 建议：优化止损设置或调整 TP 目标")
        else:
            print(f"\n✅ 这条策略在 2023 年表现不佳，但无明显失效原因")
            print(f"   → 可能是综合因素（趋势环境 + 信号质量 + exit 兑现）共同影响")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())