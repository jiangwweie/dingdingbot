#!/usr/bin/env python3
"""
详细诊断每个过滤器的过滤情况

目标：
1. 检查 pinbar 形态检测
2. 检查每个过滤器的过滤统计
3. 找出导致 0 trades 的根本原因
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    StrategyDefinition,
    TriggerConfig,
    FilterConfig,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester


async def diagnose_filters():
    """详细诊断每个过滤器"""

    print("=" * 80)
    print("详细诊断每个过滤器的过滤情况")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 回测器
    backtester = Backtester(None, data_repository=data_repo)

    try:
        # 时间范围：2024-01-01 ~ 2024-03-31 (3 个月，加快验证)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 3, 31).timestamp() * 1000)

        # 测试场景：逐步添加过滤器
        test_cases = [
            {
                "name": "只检测 pinbar（无过滤器）",
                "filters": []
            },
            {
                "name": "pinbar + EMA trend",
                "filters": [
                    {"type": "ema_trend", "enabled": True, "params": {}},
                ]
            },
            {
                "name": "pinbar + EMA trend + MTF",
                "filters": [
                    {"type": "ema_trend", "enabled": True, "params": {}},
                    {"type": "mtf", "enabled": True, "params": {}},
                ]
            },
            {
                "name": "pinbar + EMA trend + MTF + ATR",
                "filters": [
                    {"type": "ema_trend", "enabled": True, "params": {}},
                    {"type": "mtf", "enabled": True, "params": {}},
                    {"type": "atr", "enabled": True, "params": {}},
                ]
            },
        ]

        for case in test_cases:
            print(f"\n{'=' * 80}")
            print(f"测试场景: {case['name']}")
            print(f"{'=' * 80}")

            # 构建策略
            strategies = [{
                "name": "pinbar",
                "triggers": [{"type": "pinbar", "enabled": True}],
                "filters": case["filters"]
            }]

            # 回测请求
            request = BacktestRequest(
                symbol="ETH/USDT:USDT",
                timeframe="1h",
                start_time=start_ts,
                end_time=end_ts,
                limit=1000,
                initial_balance=Decimal("10000"),
                slippage_rate=Decimal("0.001"),
                fee_rate=Decimal("0.0004"),
                mode="v2_classic",  # 使用 v2_classic 模式，更快
                strategies=strategies,
            )

            # 运行回测
            report = await backtester.run_backtest(request)

            # 输出统计
            print(f"\n【信号统计】")
            print(f"  总 attempts: {report.signal_stats.total_attempts}")
            print(f"  无形态 (no_pattern): {report.signal_stats.no_pattern}")
            print(f"  被过滤 (filtered_out): {report.signal_stats.filtered_out}")
            print(f"  信号触发 (signals_fired): {report.signal_stats.signals_fired}")

            if report.signal_stats.filtered_by_filters:
                print(f"\n【过滤器统计】")
                for filter_name, count in report.signal_stats.filtered_by_filters.items():
                    print(f"  {filter_name}: {count} 次过滤")

            if report.signal_stats.signals_fired > 0:
                print(f"\n✅ 此场景有信号产生")
            else:
                print(f"\n❌ 此场景无信号产生")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_filters())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
