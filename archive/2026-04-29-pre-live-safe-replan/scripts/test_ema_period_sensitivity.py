#!/usr/bin/env python3
"""
EMA Period 敏感性测试 - LONG-only 基线

固定条件：
- ETH/USDT:USDT, 1h, v3_pms 模式
- direction = LONG-only
- 成本口径 = stress (slippage=0.001, tp_slippage=0.0005, fee=0.0004)
- max_atr_ratio = 0.0059, min_distance_pct = 0.0080
- breakeven_enabled = False
- tp_ratios = [0.5, 0.5], TP1 = 1.0R, TP2 = 3.5R

测试矩阵：
- ema_period: 90 / 111 / 130
- 时间窗口: 2024 全年 / 2025 全年
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway


async def run_single_test(gateway, ema_period, year):
    """运行单个测试配置"""

    # 时间范围
    start_time = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    # 回测请求
    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_time,
        end_time=end_time,
        limit=9000,
        mode="v3_pms",
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
        initial_balance=Decimal("10000"),
    )

    # 运行时参数覆盖 - LONG-only 基线
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=Decimal("0.0059"),
        min_distance_pct=Decimal("0.0080"),
        ema_period=ema_period,  # 测试变量
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        direction="LONG",  # LONG-only
    )

    # 风险配置
    risk_config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )
    request.risk_overrides = risk_config

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="eth_long_only_baseline",
        name="ETH LONG-only Baseline",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    # 运行回测
    backtester = Backtester(gateway)
    report = await backtester.run_backtest(
        request,
        runtime_overrides=runtime_overrides,
    )

    return {
        "ema_period": ema_period,
        "year": year,
        "total_pnl": float(report.total_pnl),
        "total_trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "max_drawdown": float(report.max_drawdown) * 100,
        "sharpe": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
    }


async def main():
    """执行 EMA Period 敏感性测试"""

    print("=" * 80)
    print("EMA Period 敏感性测试 - LONG-only 基线")
    print("=" * 80)
    print("\n固定条件:")
    print("  Symbol: ETH/USDT:USDT")
    print("  Timeframe: 1h")
    print("  Mode: v3_pms")
    print("  Direction: LONG-only")
    print("  max_atr_ratio: 0.0059")
    print("  min_distance_pct: 0.0080")
    print("  breakeven_enabled: False")
    print("  tp_ratios: [0.5, 0.5]")
    print("  TP1: 1.0R, TP2: 3.5R")
    print("\n测试矩阵:")
    print("  ema_period: 90 / 111 / 130")
    print("  时间窗口: 2024 / 2025")
    print("=" * 80)

    # 初始化交易所网关
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    results = []

    try:
        # 测试矩阵
        ema_periods = [90, 111, 130]
        years = [2024, 2025]

        for ema_period in ema_periods:
            for year in years:
                print(f"\n[{ema_period}/{year}] 运行中...")
                result = await run_single_test(gateway, ema_period, year)
                results.append(result)
                print(f"  total_pnl: {result['total_pnl']:.2f}")
                print(f"  total_trades: {result['total_trades']}")
                print(f"  win_rate: {result['win_rate']:.2f}%")
                print(f"  max_drawdown: {result['max_drawdown']:.2f}%")
                print(f"  sharpe: {result['sharpe']:.2f}")

    finally:
        await gateway.close()

    # 输出对比表
    print("\n" + "=" * 80)
    print("结果对比表")
    print("=" * 80)
    print(f"{'EMA Period':<12} {'Year':<6} {'Total PnL':>12} {'Trades':>8} {'Win Rate':>10} {'Max DD':>10} {'Sharpe':>8}")
    print("-" * 80)

    for r in results:
        print(f"{r['ema_period']:<12} {r['year']:<6} {r['total_pnl']:>12.2f} {r['total_trades']:>8} {r['win_rate']:>9.2f}% {r['max_drawdown']:>9.2f}% {r['sharpe']:>8.2f}")

    print("=" * 80)

    # 分析结论
    print("\n分析结论:")
    print("-" * 80)

    # 按 ema_period 分组
    by_ema = {}
    for r in results:
        key = r['ema_period']
        if key not in by_ema:
            by_ema[key] = []
        by_ema[key].append(r)

    # 计算每个 ema_period 的 2024+2025 综合表现
    print("\n1. EMA Period 对 LONG-only 基线的影响:")
    for ema_period in ema_periods:
        data = by_ema[ema_period]
        pnl_2024 = data[0]['total_pnl'] if data[0]['year'] == 2024 else data[1]['total_pnl']
        pnl_2025 = data[1]['total_pnl'] if data[1]['year'] == 2025 else data[0]['total_pnl']
        total_pnl = pnl_2024 + pnl_2025

        sharpe_2024 = data[0]['sharpe'] if data[0]['year'] == 2024 else data[1]['sharpe']
        sharpe_2025 = data[1]['sharpe'] if data[1]['year'] == 2025 else data[0]['sharpe']
        avg_sharpe = (sharpe_2024 + sharpe_2025) / 2

        print(f"  ema_period={ema_period}: 2024 PnL={pnl_2024:.2f}, 2025 PnL={pnl_2025:.2f}, Total={total_pnl:.2f}, Avg Sharpe={avg_sharpe:.2f}")

    # 找出最平衡的 ema_period
    print("\n2. 2024/2025 平衡性分析:")
    best_balance = None
    min_diff = float('inf')

    for ema_period in ema_periods:
        data = by_ema[ema_period]
        pnl_2024 = data[0]['total_pnl'] if data[0]['year'] == 2024 else data[1]['total_pnl']
        pnl_2025 = data[1]['total_pnl'] if data[1]['year'] == 2025 else data[0]['total_pnl']

        # 计算差异度（绝对值）
        diff = abs(pnl_2024 - pnl_2025)
        total = pnl_2024 + pnl_2025

        print(f"  ema_period={ema_period}: |2024-2025|={diff:.2f}, Total={total:.2f}")

        if diff < min_diff and total > 0:  # 优先考虑差异小且总收益为正
            min_diff = diff
            best_balance = ema_period

    print(f"\n  最平衡: ema_period={best_balance}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
