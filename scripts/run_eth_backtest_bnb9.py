#!/usr/bin/env python3
"""
ETH/USDT:USDT 1h 回测脚本 (bnb9 口径)

参数配置:
- symbol: ETH/USDT:USDT
- timeframe: 1h
- 时间范围: 2024-01-01 ~ 2024-12-31
- breakeven_enabled: False
- max_atr_ratio: 0.01
- min_distance_pct: 0.005
- tp_ratios: [0.6, 0.4]
- tp_targets: [1.0, 2.5]

bnb9 口径:
- slippage_rate: 0.0001
- tp_slippage_rate: 0
- fee_rate: 0.000405
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

DB_PATH = "data/v3_dev.db"

# 锁定配置
ORDER_STRATEGY = {
    "id": "dual_tp_bnb9",
    "name": "Dual TP (BNB9)",
    "tp_levels": 2,
    "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
    "tp_targets": [Decimal("1.0"), Decimal("2.5")],
    "initial_stop_loss_rr": Decimal("-1.0"),
    "trailing_stop_enabled": False,
    "oco_enabled": True
}

STRATEGY_CONFIG = [{
    "name": "pinbar",
    "triggers": [{"type": "pinbar", "enabled": True}],
    "filters": [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": Decimal("0.005")}},
        {"type": "mtf", "enabled": True, "params": {}},
        {"type": "atr", "enabled": True, "params": {"max_atr_ratio": Decimal("0.01")}},
    ]
}]


async def run_backtest() -> dict:
    """运行 ETH 1h 回测（bnb9 口径）"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester
    from src.domain.models import (
        BacktestRequest,
        OrderStrategy,
        BacktestRuntimeOverrides,
    )

    # 时间范围
    start_ts = int(datetime.strptime("2024-01-01", "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime("2024-12-31", "%Y-%m-%d").timestamp() * 1000)

    print("=" * 60)
    print("ETH/USDT:USDT 1h 回测 (bnb9 口径)")
    print("=" * 60)
    print(f"时间范围: 2024-01-01 ~ 2024-12-31")
    print(f"策略: Pinbar + EMA(0.5%) + MTF + ATR(1%)")
    print(f"止盈: TP1@1R (60%), TP2@2.5R (40%)")
    print(f"Breakeven: False")
    print(f"滑点: 0.01%, TP滑点: 0%, 手续费: 0.0405%")
    print("=" * 60)

    # 初始化数据仓库
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    # bnb9 口径参数
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=Decimal("0.01"),
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.6"), Decimal("0.4")],
        tp_targets=[Decimal("1.0"), Decimal("2.5")],
        breakeven_enabled=False,
    )

    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        limit=10000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=STRATEGY_CONFIG,
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
        # bnb9 口径
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )
    await repo.close()

    return {
        "symbol": "ETH/USDT:USDT",
        "timeframe": "1h",
        "start_time": "2024-01-01",
        "end_time": "2024-12-31",
        "total_pnl": float(report.total_pnl),
        "total_trades": report.total_trades,
        "winning_trades": report.winning_trades,
        "losing_trades": report.losing_trades,
        "win_rate": float(report.win_rate * 100),
        "max_drawdown": float(report.max_drawdown * 100),
        "initial_balance": float(report.initial_balance),
        "final_balance": float(report.final_balance),
        "total_return": float(report.total_return * 100),
        "total_fees": float(report.total_fees_paid),
        "total_slippage": float(report.total_slippage_cost),
        "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else None,
    }


async def main():
    try:
        result = await run_backtest()

        print("\n" + "=" * 60)
        print("回测结果")
        print("=" * 60)
        print(f"总 PnL: {result['total_pnl']:.2f} USDT")
        print(f"总交易数: {result['total_trades']}")
        print(f"胜率: {result['win_rate']:.2f}%")
        print(f"最大回撤: {result['max_drawdown']:.2f}%")
        print(f"总收益率: {result['total_return']:.2f}%")
        print(f"夏普比率: {result['sharpe_ratio']:.4f}" if result['sharpe_ratio'] else "夏普比率: N/A")
        print(f"总手续费: {result['total_fees']:.2f} USDT")
        print(f"总滑点成本: {result['total_slippage']:.2f} USDT")
        print("=" * 60)

    except Exception as e:
        import traceback
        print(f"\n错误: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
