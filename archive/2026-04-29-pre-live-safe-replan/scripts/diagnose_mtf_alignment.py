#!/usr/bin/env python3
"""
诊断 pinbar 信号方向与 MTF 趋势方向的匹配情况

目标：
1. 检查 pinbar 信号方向分布
2. 检查 MTF 趋势方向分布
3. 检查两者是否匹配
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, TrendDirection, Direction
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester


async def diagnose_mtf_alignment():
    """诊断 pinbar 信号方向与 MTF 趋势方向的匹配情况"""

    print("=" * 80)
    print("诊断 pinbar 信号方向与 MTF 趋势方向的匹配情况")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 回测器
    backtester = Backtester(None, data_repository=data_repo)

    try:
        # 时间范围：2024-01-01 ~ 2024-03-31 (3 个月)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 3, 31).timestamp() * 1000)

        # 回测请求（只检测 pinbar + EMA trend）
        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_ts,
            end_time=end_ts,
            limit=1000,
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            mode="v2_classic",
            strategies=[{
                "name": "pinbar",
                "triggers": [{"type": "pinbar", "enabled": True}],
                "filters": [
                    {"type": "ema_trend", "enabled": True, "params": {}},
                ]
            }],
        )

        # 运行回测
        print("\n运行回测（pinbar + EMA trend）...")
        report = await backtester.run_backtest(request)

        print(f"\n【信号统计】")
        print(f"  总 attempts: {report.signal_stats.total_attempts}")
        print(f"  无形态 (no_pattern): {report.signal_stats.no_pattern}")
        print(f"  被过滤 (filtered_out): {report.signal_stats.filtered_out}")
        print(f"  信号触发 (signals_fired): {report.signal_stats.signals_fired}")
        print(f"  LONG: {report.signal_stats.long_signals}")
        print(f"  SHORT: {report.signal_stats.short_signals}")

        # 分析 attempts
        if hasattr(report, 'attempts') and report.attempts:
            print(f"\n【详细分析】")
            long_signals = []
            short_signals = []

            for attempt in report.attempts:
                if attempt.get('final_result') == 'SIGNAL_FIRED':
                    direction = attempt.get('direction')
                    if direction == 'LONG':
                        long_signals.append(attempt)
                    elif direction == 'SHORT':
                        short_signals.append(attempt)

            print(f"  LONG 信号: {len(long_signals)}")
            print(f"  SHORT 信号: {len(short_signals)}")

            # 检查 MTF 趋势分布（需要从 attempts 中提取）
            # 由于 v2_classic 模式不返回 MTF 数据，我们需要单独查询

        # 单独查询 MTF 趋势分布
        print(f"\n【MTF 趋势分布查询】")

        # 获取 4h K 线数据
        klines_4h = await data_repo.get_klines(
            symbol="ETH/USDT:USDT",
            timeframe="4h",
            start_time=start_ts,
            limit=1000,
        )

        bullish_count = sum(1 for k in klines_4h if k.close > k.open)
        bearish_count = sum(1 for k in klines_4h if k.close < k.open)

        print(f"  4h K 线总数: {len(klines_4h)}")
        print(f"  BULLISH: {bullish_count} ({bullish_count/len(klines_4h)*100:.1f}%)")
        print(f"  BEARISH: {bearish_count} ({bearish_count/len(klines_4h)*100:.1f}%)")

        # 结论
        print(f"\n【诊断结论】")
        if report.signal_stats.signals_fired > 0:
            print(f"✅ pinbar + EMA trend 有信号产生")
            print(f"   - 如果添加 MTF 过滤器后变成 0 trades")
            print(f"   - 说明 MTF 趋势方向与 pinbar 信号方向不匹配")
        else:
            print(f"❌ pinbar + EMA trend 无信号产生")
            print(f"   - 问题不在 MTF 过滤器")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(diagnose_mtf_alignment())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
