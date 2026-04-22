#!/usr/bin/env python3
"""
验证 tp_target[1]=4.5 + max_loss_percent=2% 配置

对比：
- 原配置：tp_targets=[1.0, 3.5], max_loss_percent=1%
- 新配置：tp_targets=[1.0, 4.5], max_loss_percent=2%
"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import BacktestRequest, BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_backtest(gateway, backtester, year, tp_target_2, max_loss_pct):
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
        tp_targets=[Decimal("1.0"), Decimal(str(tp_target_2))],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
        same_bar_policy="pessimistic",
        max_loss_percent=Decimal(str(max_loss_pct)),
    )

    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)
    return report


async def main():
    print("=" * 80)
    print("验证 tp_target[1]=4.5 + max_loss_percent=2%")
    print("=" * 80)

    gateway = ExchangeGateway(exchange_name="binance", api_key=None, api_secret=None, testnet=False)
    await gateway.initialize()
    backtester = Backtester(exchange_gateway=gateway)

    try:
        # 原配置
        print("\n【原配置】tp_targets=[1.0, 3.5], max_loss_percent=1%")
        print("-" * 80)

        report_2024_old = await run_backtest(gateway, backtester, 2024, 3.5, 0.01)
        report_2025_old = await run_backtest(gateway, backtester, 2025, 3.5, 0.01)

        print(f"2024: PnL={float(report_2024_old.total_pnl):.2f}, Trades={report_2024_old.total_trades}, WinRate={float(report_2024_old.win_rate)*100:.2f}%, Sharpe={float(report_2024_old.sharpe_ratio):.3f}, MaxDD={float(report_2024_old.max_drawdown)*100:.2f}%")
        print(f"2025: PnL={float(report_2025_old.total_pnl):.2f}, Trades={report_2025_old.total_trades}, WinRate={float(report_2025_old.win_rate)*100:.2f}%, Sharpe={float(report_2025_old.sharpe_ratio):.3f}, MaxDD={float(report_2025_old.max_drawdown)*100:.2f}%")

        total_pnl_old = float(report_2024_old.total_pnl) + float(report_2025_old.total_pnl)
        print(f"两年合计: PnL={total_pnl_old:.2f}")

        # 新配置
        print("\n【新配置】tp_targets=[1.0, 4.5], max_loss_percent=2%")
        print("-" * 80)

        report_2024_new = await run_backtest(gateway, backtester, 2024, 4.5, 0.02)
        report_2025_new = await run_backtest(gateway, backtester, 2025, 4.5, 0.02)

        print(f"2024: PnL={float(report_2024_new.total_pnl):.2f}, Trades={report_2024_new.total_trades}, WinRate={float(report_2024_new.win_rate)*100:.2f}%, Sharpe={float(report_2024_new.sharpe_ratio):.3f}, MaxDD={float(report_2024_new.max_drawdown)*100:.2f}%")
        print(f"2025: PnL={float(report_2025_new.total_pnl):.2f}, Trades={report_2025_new.total_trades}, WinRate={float(report_2025_new.win_rate)*100:.2f}%, Sharpe={float(report_2025_new.sharpe_ratio):.3f}, MaxDD={float(report_2025_new.max_drawdown)*100:.2f}%")

        total_pnl_new = float(report_2024_new.total_pnl) + float(report_2025_new.total_pnl)
        print(f"两年合计: PnL={total_pnl_new:.2f}")

        # 对比
        print("\n" + "=" * 80)
        print("对比分析")
        print("=" * 80)

        pnl_diff = total_pnl_new - total_pnl_old
        pnl_pct = (pnl_diff / abs(total_pnl_old) * 100) if total_pnl_old != 0 else 0

        print(f"PnL 差异: {pnl_diff:+.2f} USDT ({pnl_pct:+.2f}%)")

        if pnl_diff > 0:
            print("✅ 新配置更优")
        else:
            print("❌ 原配置更优")

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())