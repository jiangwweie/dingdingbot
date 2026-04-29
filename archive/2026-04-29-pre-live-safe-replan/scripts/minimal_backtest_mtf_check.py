#!/usr/bin/env python3
"""最小回测验证：确认日志中显示的 MTF EMA 周期与 live 一致"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.application.backtester import Backtester
from src.domain.models import BacktestRequest
from decimal import Decimal


async def main():
    print("=" * 60)
    print("最小回测 MTF 配置验证")
    print("=" * 60)

    # 创建最小回测请求
    request = BacktestRequest(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        start_time="2025-01-01",
        end_time="2025-01-02",
        limit=100,  # 最小数据量
        initial_balance=Decimal("10000.0"),
        strategies=[],
    )

    print(f"\n回测参数:")
    print(f"  币种: {request.symbol}")
    print(f"  周期: {request.timeframe}")
    print(f"  日期: {request.start_time} ~ {request.end_time}")
    print(f"  K线数: {request.limit}")

    # 运行回测
    print("\n开始回测...")
    backtester = Backtester()
    result = await backtester.run_backtest(request)

    print("\n回测完成！")
    print(f"  总信号数: {result.total_signals}")
    print(f"  总交易数: {result.total_trades}")

    print("\n" + "=" * 60)
    print("✅ 回测成功完成，请检查上方日志中的 MTF EMA 周期")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
