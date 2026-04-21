#!/usr/bin/env python3
"""
ETH/USDT:USDT 1h 回测脚本 (stress 口径)

使用 v3_pms 模式回测 ETH 1h 策略，stress 口径（更高滑点/手续费）。
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


async def main():
    """运行 ETH/USDT:USDT 1h 回测 (stress 口径)"""

    print("=" * 70)
    print("ETH/USDT:USDT 1h 回测 - stress 口径")
    print("=" * 70)

    # 初始化交易所网关 (无 API key 模式，仅拉取公开数据)
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    try:
        # 创建回测器
        backtester = Backtester(gateway)

        # 时间范围: 2024-01-01 ~ 2024-12-31
        start_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        # 回测请求
        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_time,  # 整数时间戳
            end_time=end_time,      # 整数时间戳
            limit=9000,  # 1年约 8760 小时
            mode="v3_pms",
            # stress 口径成本参数
            slippage_rate=Decimal("0.001"),      # 0.1%
            tp_slippage_rate=Decimal("0.0005"),  # 0.05%
            fee_rate=Decimal("0.0004"),          # 0.04%
            initial_balance=Decimal("10000"),
        )

        # 运行时参数覆盖
        runtime_overrides = BacktestRuntimeOverrides(
            # 策略参数
            max_atr_ratio=Decimal("0.01"),
            min_distance_pct=Decimal("0.005"),
            # 订单参数
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            # 风控参数
            breakeven_enabled=False,
        )

        # 风险配置
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=20,
        )
        request.risk_overrides = risk_config

        # 订单策略
        request.order_strategy = OrderStrategy(
            id="eth_stress_strategy",
            name="ETH Stress Strategy",
            tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        print("\n参数配置:")
        print(f"  Symbol: {request.symbol}")
        print(f"  Timeframe: {request.timeframe}")
        print(f"  时间范围: 2024-01-01 ~ 2024-12-31")
        print(f"  Mode: {request.mode}")
        print(f"\n策略参数:")
        print(f"  breakeven_enabled: False")
        print(f"  max_atr_ratio: 0.01")
        print(f"  min_distance_pct: 0.005")
        print(f"  tp_ratios: [0.6, 0.4]")
        print(f"  tp_targets: [1.0, 2.5]")
        print(f"\nstress 口径:")
        print(f"  slippage_rate: 0.001")
        print(f"  tp_slippage_rate: 0.0005")
        print(f"  fee_rate: 0.0004")
        print()

        # 运行回测
        report = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides,
        )

        # 输出结果
        print("\n" + "=" * 70)
        print("回测结果")
        print("=" * 70)
        print(f"total_pnl:     {report.total_pnl:.2f} USDT")
        print(f"total_trades:  {report.total_trades}")
        print(f"win_rate:      {float(report.win_rate) * 100:.2f}%")
        print(f"max_drawdown:  {float(report.max_drawdown) * 100:.2f}%")
        print()
        print(f"initial_balance: {float(report.initial_balance):.2f} USDT")
        print(f"final_balance:   {float(report.final_balance):.2f} USDT")
        print(f"total_return:    {float(report.total_return) * 100:.2f}%")
        print()
        print(f"winning_trades: {report.winning_trades}")
        print(f"losing_trades:  {report.losing_trades}")
        print(f"total_fees:     {float(report.total_fees_paid):.2f} USDT")
        print(f"total_slippage: {float(report.total_slippage_cost):.2f} USDT")
        print("=" * 70)

    finally:
        await gateway.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n回测中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
