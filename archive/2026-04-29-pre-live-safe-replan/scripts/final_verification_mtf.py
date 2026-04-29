#!/usr/bin/env python3
"""
最终验证：检查每个信号被 MTF 过滤的具体原因

目标：
1. 运行 pinbar + EMA trend + MTF 回测
2. 输出每个信号的详细过滤信息
3. 确认是否是"顺大逆小"矛盾
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


async def final_verification():
    """最终验证"""

    print("=" * 80)
    print("最终验证：检查每个信号被 MTF 过滤的具体原因")
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

        # 回测请求（pinbar + EMA trend + MTF）
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
                    {"type": "mtf", "enabled": True, "params": {}},
                ]
            }],
        )

        # 运行回测
        print("\n运行回测（pinbar + EMA trend + MTF）...")
        report = await backtester.run_backtest(request)

        print(f"\n【信号统计】")
        print(f"  总 attempts: {report.signal_stats.total_attempts}")
        print(f"  无形态 (no_pattern): {report.signal_stats.no_pattern}")
        print(f"  被过滤 (filtered_out): {report.signal_stats.filtered_out}")
        print(f"  信号触发 (signals_fired): {report.signal_stats.signals_fired}")

        if report.signal_stats.filtered_by_filters:
            print(f"\n【过滤器统计】")
            for filter_name, count in report.signal_stats.filtered_by_filters.items():
                print(f"  {filter_name}: {count} 次过滤")

        # 分析 attempts（如果有详细信息）
        if hasattr(report, 'attempts') and report.attempts:
            print(f"\n【详细分析】（前 10 个被过滤的信号）")

            filtered_attempts = [
                a for a in report.attempts
                if a.get('final_result') == 'FILTERED_OUT'
            ]

            for i, attempt in enumerate(filtered_attempts[:10], 1):
                print(f"\n  [{i}] {attempt.get('strategy_name', 'unknown')}")
                print(f"      方向: {attempt.get('direction', 'unknown')}")
                print(f"      时间: {datetime.fromtimestamp(attempt.get('timestamp', 0)/1000) if attempt.get('timestamp') else 'unknown'}")

                # 检查过滤结果
                filter_results = attempt.get('filter_results', [])
                for filter_name, result in filter_results:
                    passed = result.get('passed', False)
                    reason = result.get('reason', 'unknown')
                    print(f"      {filter_name}: {'✅' if passed else '❌'} {reason}")

                    # 如果是 MTF 过滤器，输出详细信息
                    if filter_name == 'mtf' and not passed:
                        higher_tf = result.get('metadata', {}).get('higher_timeframe')
                        higher_trend = result.get('metadata', {}).get('higher_trend')
                        pattern_dir = result.get('metadata', {}).get('pattern_direction')
                        print(f"        4h 趋势: {higher_trend}")
                        print(f"        信号方向: {pattern_dir}")
                        print(f"        矛盾: {'是' if (pattern_dir == 'LONG' and higher_trend == 'bearish') or (pattern_dir == 'SHORT' and higher_trend == 'bullish') else '否'}")

        # 结论
        print(f"\n{'=' * 80}")
        print(f"【最终结论】")
        print(f"{'=' * 80}")

        if report.signal_stats.signals_fired == 0:
            print(f"❌ 所有信号被 MTF 过滤器过滤")
            print(f"\n根本原因：")
            print(f"  Pinbar 是反转形态（逆小），MTF 过滤器要求顺大")
            print(f"  - 看涨 Pinbar 出现在下跌趋势末端 → 期望 4h BEARISH")
            print(f"  - 但 MTF 过滤器要求 4h BULLISH → 矛盾！")
            print(f"\n解决方案：")
            print(f"  1. 移除 MTF 过滤器（Pinbar 不适合与 MTF 组合）")
            print(f"  2. 或使用顺势形态（如 Engulfing）+ MTF")
            print(f"  3. 或修改 MTF 过滤器逻辑（允许反转形态）")
        else:
            print(f"✅ 有信号产生，问题不在 MTF 过滤器")

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(final_verification())
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
