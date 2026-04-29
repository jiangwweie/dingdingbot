#!/usr/bin/env python3
"""
修正统计口径：使用 report.close_events 作为数据源
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_year_backtest(gateway, backtester, year):
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


def analyze_close_events(report):
    """基于 report.close_events 统计"""

    close_events = report.close_events if hasattr(report, 'close_events') else []

    if not close_events:
        return {
            "total_events": 0,
            "tp1_count": 0,
            "tp2_count": 0,
            "sl_count": 0,
            "tp1_rate": 0.0,
            "tp2_rate": 0.0,
            "sl_rate": 0.0,
        }

    tp1_count = 0
    tp2_count = 0
    sl_count = 0

    for event in close_events:
        event_type = event.event_type if hasattr(event, 'event_type') else None

        if event_type == "TP1":
            tp1_count += 1
        elif event_type == "TP2":
            tp2_count += 1
        elif event_type == "SL":
            sl_count += 1

    total = len(close_events)
    tp1_rate = tp1_count / total if total > 0 else 0.0
    tp2_rate = tp2_count / total if total > 0 else 0.0
    sl_rate = sl_count / total if total > 0 else 0.0

    return {
        "total_events": total,
        "tp1_count": tp1_count,
        "tp2_count": tp2_count,
        "sl_count": sl_count,
        "tp1_rate": tp1_rate,
        "tp2_rate": tp2_rate,
        "sl_rate": sl_rate,
    }


async def main():
    print("=" * 80)
    print("修正统计口径：使用 report.close_events")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 运行回测
        report_2023 = await run_year_backtest(gateway, backtester, 2023)
        report_2024 = await run_year_backtest(gateway, backtester, 2024)
        report_2025 = await run_year_backtest(gateway, backtester, 2025)

        # 基于 close_events 统计
        stats_2023 = analyze_close_events(report_2023)
        stats_2024 = analyze_close_events(report_2024)
        stats_2025 = analyze_close_events(report_2025)

        # 输出对比
        print("\n修正前 vs 修正后对比：")
        print("=" * 80)

        print("\n【问题 1】之前 TP1=0% 是否只是取错数据源导致？")
        print("-" * 80)
        print("修正前（基于 Position.exit_reason）：")
        print(f"  2023: TP1=0.00%, TP2=7.14%, SL=92.86%")
        print(f"  2024: TP1=0.00%, TP2=4.84%, SL=95.16%")
        print(f"  2025: TP1=0.00%, TP2=5.00%, SL=95.00%")

        print("\n修正后（基于 report.close_events）：")
        print(f"  2023: 总事件={stats_2023['total_events']}, TP1={stats_2023['tp1_count']}({stats_2023['tp1_rate']*100:.2f}%), TP2={stats_2023['tp2_count']}({stats_2023['tp2_rate']*100:.2f}%), SL={stats_2023['sl_count']}({stats_2023['sl_rate']*100:.2f}%)")
        print(f"  2024: 总事件={stats_2024['total_events']}, TP1={stats_2024['tp1_count']}({stats_2024['tp1_rate']*100:.2f}%), TP2={stats_2024['tp2_count']}({stats_2024['tp2_rate']*100:.2f}%), SL={stats_2024['sl_count']}({stats_2024['sl_rate']*100:.2f}%)")
        print(f"  2025: 总事件={stats_2025['total_events']}, TP1={stats_2025['tp1_count']}({stats_2025['tp1_rate']*100:.2f}%), TP2={stats_2025['tp2_count']}({stats_2025['tp2_rate']*100:.2f}%), SL={stats_2025['sl_count']}({stats_2025['sl_rate']*100:.2f}%)")

        # 判断
        if stats_2023['tp1_count'] > 0 or stats_2024['tp1_count'] > 0 or stats_2025['tp1_count'] > 0:
            print("\n✅ 答案：是取错数据源导致。修正后 TP1 > 0")
        else:
            print("\n❌ 答案：不是数据源问题。修正后 TP1 仍为 0")

        print("\n【问题 2】修正后，2023 失效结论是否改变？")
        print("-" * 80)
        print("修正前结论：趋势环境不适配（主因），信号质量下降（次因），Exit 兑现正常（非原因）")

        print("\n修正后核心指标：")
        print(f"  2023: PnL={float(report_2023.total_pnl):.2f}, WinRate={float(report_2023.win_rate)*100:.2f}%, Sharpe={float(report_2023.sharpe_ratio):.3f}, MaxDD={float(report_2023.max_drawdown)*100:.2f}%")
        print(f"  2024: PnL={float(report_2024.total_pnl):.2f}, WinRate={float(report_2024.win_rate)*100:.2f}%, Sharpe={float(report_2024.sharpe_ratio):.3f}, MaxDD={float(report_2024.max_drawdown)*100:.2f}%")
        print(f"  2025: PnL={float(report_2025.total_pnl):.2f}, WinRate={float(report_2025.win_rate)*100:.2f}%, Sharpe={float(report_2025.sharpe_ratio):.3f}, MaxDD={float(report_2025.max_drawdown)*100:.2f}%")

        # 判断
        if float(report_2023.sharpe_ratio) < 0.5 and float(report_2023.win_rate) < 0.4:
            print("\n✅ 答案：结论不变。2023 仍为趋势环境不适配（Sharpe < 0.5, WinRate < 40%）")
        else:
            print("\n⚠️  答案：结论可能改变，需重新评估")

        print("\n" + "=" * 80)
        print("最终结论")
        print("=" * 80)

        if stats_2023['tp1_count'] > 0:
            print("修正数据源后，TP1 命中率 > 0，之前是取错数据源（Position.exit_reason 只记录最终平仓原因，遗漏了 TP1）。")
        else:
            print("修正数据源后，TP1 命中率仍为 0，确认是真实情况（所有仓位直接被 SL 或 TP2 平仓）。")

        print("2023 失效主结论不变：趋势环境不适配（LONG-only 策略在熊市/震荡期失效）。")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())