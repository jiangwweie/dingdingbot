#!/usr/bin/env python3
"""
诊断为什么 ETH 1h 2024-01-01 ~ 2024-12-31 没有 SIGNAL_FIRED

目标：
1. 检查 pinbar 形态检测是否工作
2. 检查过滤器是否过于严格
3. 输出详细的过滤统计
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester


async def diagnose_zero_trades():
    """诊断为什么没有 SIGNAL_FIRED"""

    print("=" * 80)
    print("诊断 ETH 1h 2024-01-01 ~ 2024-12-31 为什么没有 SIGNAL_FIRED")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 回测器
    backtester = Backtester(None, data_repository=data_repo)

    try:
        # 时间范围：2024-01-01 ~ 2024-12-31 (1 年)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 12, 31).timestamp() * 1000)

        # 回测请求（使用 Optuna 的中间参数）
        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_ts,
            end_time=end_ts,
            limit=1000,
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            mode="v3_pms",
            # 使用 Optuna 的策略配置
            strategies=[{
                "name": "pinbar",
                "triggers": [{"type": "pinbar", "enabled": True}],
                "filters": [
                    {"type": "ema_trend", "enabled": True, "params": {}},
                    {"type": "mtf", "enabled": True, "params": {}},
                    {"type": "atr", "enabled": True, "params": {}},
                ]
            }],
            # 使用 Optuna 的中间参数
            risk_overrides={
                "max_atr_ratio": Decimal("0.01"),
                "min_distance_pct": Decimal("0.005"),
                "ema_period": 60,
            }
        )

        print("\n【诊断配置】")
        print(f"  Symbol: {request.symbol}")
        print(f"  Timeframe: {request.timeframe}")
        print(f"  时间范围: 2024-01-01 ~ 2024-12-31 (1 年)")
        print(f"  Mode: {request.mode}")
        print(f"  策略: pinbar")
        print(f"  过滤器: ema_trend + mtf + atr")
        print(f"  max_atr_ratio: 0.01")
        print(f"  min_distance_pct: 0.005")
        print(f"  ema_period: 60")
        print()

        # 运行回测
        print("运行回测...")
        report = await backtester.run_backtest(request)

        # 输出详细统计
        print("\n" + "=" * 80)
        print("诊断结果")
        print("=" * 80)

        print(f"\n【数据加载】")
        print(f"  主时间框架 K 线: {report.candles_analyzed} bars")

        print(f"\n【信号统计】")
        print(f"  总 attempts: {report.signal_stats.total_attempts}")
        print(f"  无形态 (no_pattern): {report.signal_stats.no_pattern}")
        print(f"  被过滤 (filtered_out): {report.signal_stats.filtered_out}")
        print(f"  信号触发 (signals_fired): {report.signal_stats.signals_fired}")
        print(f"  LONG: {report.signal_stats.long_signals}")
        print(f"  SHORT: {report.signal_stats.short_signals}")

        print(f"\n【过滤器统计】")
        for filter_name, count in report.signal_stats.filtered_by_filters.items():
            print(f"  {filter_name}: {count} 次过滤")

        print(f"\n【拒绝原因分布】")
        for reason, count in report.reject_reasons.items():
            print(f"  {reason}: {count}")

        # 诊断结论
        print("\n" + "=" * 80)
        if report.signal_stats.no_pattern > 0:
            print("⚠️  发现 pinbar 形态，但被过滤器过滤")
            print(f"   - 检测到 {report.signal_stats.no_pattern} 个 pinbar 形态")
            print(f"   - 但全部被过滤（{report.signal_stats.filtered_out} 次）")
            print("\n建议：")
            print("   1. 放宽过滤器参数（如 max_atr_ratio, min_distance_pct）")
            print("   2. 或禁用部分过滤器进行测试")
        elif report.signal_stats.total_attempts == 0:
            print("❌ 没有检测到任何 pinbar 形态")
            print("\n建议：")
            print("   1. 检查 pinbar 配置参数是否过于严格")
            print("   2. 检查数据质量")
        else:
            print("✅ 有信号产生，问题可能在订单执行阶段")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_zero_trades())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
