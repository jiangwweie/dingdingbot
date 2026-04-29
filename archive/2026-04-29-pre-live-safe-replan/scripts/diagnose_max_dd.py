#!/usr/bin/env python3
"""
诊断 max_drawdown 计算问题
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")

# 2025 窗口
W2025_START = 1735689600000
W2025_END = 1767225599000

BASELINE = {
    "max_atr_ratio": Decimal("0.0059"),
    "min_distance_pct": Decimal("0.0080"),
    "ema_period": 111,
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "breakeven_enabled": False,
}


async def main():
    print("=" * 60)
    print("max_drawdown 诊断")
    print("=" * 60)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=W2025_START, end_time=W2025_END,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )
    overrides = BacktestRuntimeOverrides(
        tp_ratios=BASELINE["tp_ratios"], tp_targets=BASELINE["tp_targets"],
        breakeven_enabled=BASELINE["breakeven_enabled"],
        max_atr_ratio=BASELINE["max_atr_ratio"],
        min_distance_pct=BASELINE["min_distance_pct"],
        ema_period=BASELINE["ema_period"],
        allowed_directions=["LONG"],
    )

    result = await bt.run_backtest(request, runtime_overrides=overrides)

    print(f"\n结果:")
    print(f"  total_pnl: {float(result.total_pnl):+.2f}")
    print(f"  max_drawdown: {float(result.max_drawdown):.4f} ({float(result.max_drawdown)*100:.2f}%)")

    # 检查 debug 信息
    if hasattr(result, 'debug_max_drawdown_detail'):
        d = result.debug_max_drawdown_detail
        print(f"\nmax_drawdown 详情:")
        print(f"  peak: {d['peak']:.2f}")
        print(f"  peak_ts: {d['peak_ts']}")
        print(f"  trough: {d['trough']:.2f}")
        print(f"  trough_ts: {d['trough_ts']}")
        print(f"  drawdown: {d['drawdown']:.4f}")

    # 检查 equity_curve
    if hasattr(result, 'debug_equity_curve'):
        ec = result.debug_equity_curve
        print(f"\nequity_curve 统计:")
        print(f"  总点数: {len(ec)}")

        if ec:
            equities = [p['equity'] for p in ec]
            min_eq = min(equities)
            max_eq = max(equities)
            print(f"  最小值: {min_eq:.2f}")
            print(f"  最大值: {max_eq:.2f}")
            print(f"  范围: {max_eq - min_eq:.2f}")

            # 手动计算 max_drawdown
            peak = INITIAL_BALANCE
            max_dd = 0
            for p in ec:
                eq = p['equity']
                if eq > peak:
                    peak = eq
                if peak > 0:
                    dd = (peak - eq) / peak
                    if dd > max_dd:
                        max_dd = dd

            print(f"\n手动计算 max_drawdown: {max_dd:.4f} ({max_dd*100:.2f}%)")

            # 打印前 10 个点
            print(f"\n前 10 个 equity 点:")
            for i, p in enumerate(ec[:10]):
                print(f"  [{i}] ts={p['timestamp']}, equity={p['equity']:.2f}")

            # 打印最后 10 个点
            print(f"\n最后 10 个 equity 点:")
            for i, p in enumerate(ec[-10:]):
                print(f"  [{len(ec)-10+i}] ts={p['timestamp']}, equity={p['equity']:.2f}")

            # 找出最大回撤发生的位置
            peak = INITIAL_BALANCE
            max_dd = 0
            max_dd_peak = peak
            max_dd_trough = peak
            for p in ec:
                eq = p['equity']
                if eq > peak:
                    peak = eq
                if peak > 0:
                    dd = (peak - eq) / peak
                    if dd > max_dd:
                        max_dd = dd
                        max_dd_trough = eq

            print(f"\n最大回撤点:")
            print(f"  peak: {max_dd_peak:.2f}")
            print(f"  trough: {max_dd_trough:.2f}")
            print(f"  drawdown: {max_dd:.4f} ({max_dd*100:.2f}%)")

    await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
