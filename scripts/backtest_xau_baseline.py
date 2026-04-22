#!/usr/bin/env python3
"""
黄金（XAU）基准参数回测

使用 ETH 1h LONG-only 最优配置，验证黄金合约表现
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_backtest(
    gateway,
    start_date: str,
    end_date: str,
) -> dict:
    """运行回测"""

    start_time = int(datetime.fromisoformat(start_date + "T00:00:00+00:00").timestamp() * 1000)
    end_time = int(datetime.fromisoformat(end_date + "T23:59:59+00:00").timestamp() * 1000)

    request = BacktestRequest(
        symbol="XAU/USDT:USDT",
        timeframe="1h",
        start_time=start_time,
        end_time=end_time,
        limit=9000,
        mode="v3_pms",
        # BNB9 口径成本参数
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    # 结构冻结主线参数（来自 ETH 1h LONG-only 最优配置）
    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        # ATR 移除
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],  # LONG-only
    )

    # 风控配置（默认档）
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="xau_baseline",
        name="XAU Baseline Backtest",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    backtester = Backtester(gateway)
    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    return {
        "period": f"{start_date} ~ {end_date}",
        "pnl": float(report.total_pnl),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "max_drawdown": float(report.max_drawdown) * 100,
    }


async def main():
    """运行回测"""

    print("=" * 80)
    print("黄金（XAU）基准参数回测")
    print("=" * 80)
    print("\n基准参数（来自 ETH 1h LONG-only 最优配置）：")
    print("  Symbol: XAU/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  Direction: LONG-only")
    print("  ema_period: 50")
    print("  min_distance_pct: 0.005")
    print("  tp_ratios: [0.5, 0.5]")
    print("  tp_targets: [1.0, 3.5]")
    print("  breakeven_enabled: False")
    print("  ATR: 移除")
    print("  max_loss_percent: 1%")
    print("\nBNB9 成本参数：")
    print("  slippage_rate: 0.0001 (0.01%)")
    print("  tp_slippage_rate: 0 (0%)")
    print("  fee_rate: 0.000405 (0.0405%)")
    print("\n时间范围: 2026-01-01 ~ 2026-03-31")
    print("=" * 80)

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    try:
        print("\n运行回测...")
        result = await run_backtest(gateway, "2026-01-01", "2026-03-31")

        print("\n" + "=" * 80)
        print("回测结果")
        print("=" * 80)
        print(f"时间范围: {result['period']}")
        print(f"总 PnL: {result['pnl']:.2f} USDT")
        print(f"交易次数: {result['trades']}")
        print(f"胜率: {result['win_rate']:.2f}%")
        print(f"Sharpe: {result['sharpe']:.2f}")
        print(f"最大回撤: {result['max_drawdown']:.2f}%")
        print("=" * 80)

    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
