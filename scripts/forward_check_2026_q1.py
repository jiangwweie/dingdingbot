#!/usr/bin/env python3
"""
2026 Q1 Forward Check

目标：
1. 用最终冻结主线跑 2026 Q1 回测
2. 输出关键指标：pnl / trades / win_rate / sharpe / max_drawdown
3. 判断是否保持正收益、可接受回撤和正向 Sharpe

配置（最终冻结主线）：
- ETH/USDT:USDT, 1h, v3_pms, LONG-only
- ema_period=50, min_distance_pct=0.005
- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]
- breakeven_enabled=False, ATR 移除
- max_loss_percent=1%
- 时间范围：2026-01-01 ~ 2026-03-31
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import math

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def main():
    print("=" * 80)
    print("2026 Q1 Forward Check")
    print("=" * 80)
    print("\n配置（最终冻结主线）:")
    print("- ETH/USDT:USDT, 1h, v3_pms, LONG-only")
    print("- ema_period=50, min_distance_pct=0.005")
    print("- tp_ratios=[0.5, 0.5], tp_targets=[1.0, 3.5]")
    print("- breakeven_enabled=False, ATR 移除")
    print("- max_loss_percent=1%")
    print("- 时间范围：2026-01-01 ~ 2026-03-31")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 运行 2026 Q1 回测
        print("\n运行回测...")

        start_time = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

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

        # 提取关键指标
        print("\n" + "=" * 80)
        print("2026 Q1 回测结果")
        print("=" * 80)

        print(f"\n【关键指标】")
        print(f"  PnL: {report.total_pnl:.2f} USDT")
        print(f"  Trades: {report.total_trades}")
        print(f"  Win Rate: {report.win_rate * 100:.1f}%")
        print(f"  Sharpe: {report.sharpe_ratio:.3f}")
        print(f"  Max Drawdown (True Equity): {report.max_drawdown * 100:.2f}%")

        # 判断是否保持正收益、可接受回撤和正向 Sharpe
        print("\n" + "=" * 80)
        print("最终答案")
        print("=" * 80)

        is_profitable = report.total_pnl > 0
        is_drawdown_acceptable = report.max_drawdown < 0.30  # 30% 以内
        is_sharpe_positive = report.sharpe_ratio > 0

        print(f"\n【判断标准】")
        print(f"  正收益: {'✅' if is_profitable else '❌'} (PnL > 0)")
        print(f"  可接受回撤: {'✅' if is_drawdown_acceptable else '❌'} (Max DD < 30%)")
        print(f"  正向 Sharpe: {'✅' if is_sharpe_positive else '❌'} (Sharpe > 0)")

        if is_profitable and is_drawdown_acceptable and is_sharpe_positive:
            print(f"\n✅ 这条最终主线在 2026 Q1 仍保持正收益、可接受回撤和正向 Sharpe。")
        else:
            print(f"\n❌ 这条最终主线在 2026 Q1 未能保持正收益、可接受回撤和正向 Sharpe。")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
