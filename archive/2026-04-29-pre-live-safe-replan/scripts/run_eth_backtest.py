#!/usr/bin/env python3
"""
ETH/USDT:USDT 1h 回测脚本 (stress 口径，使用 BacktestJobSpec)

使用 v3_pms 模式回测 ETH 1h 策略，stress 口径（更高滑点/手续费）。
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.research_specs import (
    BacktestJobSpec,
    TimeWindowMs,
    EngineCostSpec,
)
from src.application.backtest_config import BacktestConfigResolver, DEFAULT_BACKTEST_PROFILE_PROVIDER
from src.domain.models import BacktestRuntimeOverrides
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def main():
    """运行 ETH/USDT:USDT 1h 回测 (stress 口径)"""

    print("=" * 70)
    print("ETH/USDT:USDT 1h 回测 - stress 口径 (BacktestJobSpec)")
    print("=" * 70)

    # ============================================================
    # 构建研究规范（所有配置集中在这里）
    # ============================================================

    # 时间窗口
    window = TimeWindowMs(
        start_time_ms=int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
        end_time_ms=int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000),
    )

    # 成本参数（stress 口径）
    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),      # 0.1%
        tp_slippage_rate=Decimal("0.0005"),  # 0.05%
        fee_rate=Decimal("0.0004"),          # 0.04%
    )

    # 回测任务规范
    job_spec = BacktestJobSpec(
        name="eth_1h_stress_backtest",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
        # 运行时覆盖（最高优先级）
        runtime_overrides=BacktestRuntimeOverrides(
            # 策略参数
            max_atr_ratio=Decimal("0.01"),
            min_distance_pct=Decimal("0.005"),
            # 订单参数
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            # 风控参数
            breakeven_enabled=False,
        ),
    )

    # ============================================================
    # 打印配置信息
    # ============================================================

    print("\n参数配置:")
    print(f"  Symbol: {job_spec.symbol}")
    print(f"  Timeframe: {job_spec.timeframe}")
    print(f"  时间范围: 2024-01-01 ~ 2024-12-31")
    print(f"  Mode: {job_spec.mode}")
    print(f"\n策略参数:")
    if job_spec.runtime_overrides:
        print(f"  breakeven_enabled: {job_spec.runtime_overrides.breakeven_enabled}")
        print(f"  max_atr_ratio: {job_spec.runtime_overrides.max_atr_ratio}")
        print(f"  min_distance_pct: {job_spec.runtime_overrides.min_distance_pct}")
        print(f"  tp_ratios: {job_spec.runtime_overrides.tp_ratios}")
        print(f"  tp_targets: {job_spec.runtime_overrides.tp_targets}")
    print(f"\nstress 口径:")
    print(f"  slippage_rate: {job_spec.costs.slippage_rate}")
    print(f"  tp_slippage_rate: {job_spec.costs.tp_slippage_rate}")
    print(f"  fee_rate: {job_spec.costs.fee_rate}")
    print()

    # ============================================================
    # 初始化组件
    # ============================================================

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

        # 使用 BacktestConfigResolver 解析配置（profile + request + overrides）
        resolver = BacktestConfigResolver(profile_provider=DEFAULT_BACKTEST_PROFILE_PROVIDER)

        request = job_spec.to_backtest_request()
        resolved_config = await resolver.resolve(
            profile_name=job_spec.profile_name,
            request=request,
            runtime_overrides=job_spec.runtime_overrides,
        )

        # Fill missing strategy/risk/execution from the resolved baseline.
        request = resolved_config.to_backtest_request(request)

        # 运行回测
        report = await backtester.run_backtest(
            request,
            runtime_overrides=job_spec.runtime_overrides,
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
