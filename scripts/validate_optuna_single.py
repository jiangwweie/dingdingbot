#!/usr/bin/env python3
"""
A3.2 单次 ETH 基线验证（通过 Optuna 链路）

目标：不做搜索，先证明 Optuna 那条内部链路本身能跑出交易。
"""
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    OrderStrategy,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester


async def run_single_validation():
    """单次验证：使用 Optuna 内部链路跑 ETH 基线"""

    print("=" * 80)
    print("A3.2 单次 ETH 基线验证（通过 Optuna 链路）")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    try:
        # 回测器
        backtester = Backtester(None, data_repository=data_repo)

        # 时间范围
        start_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_ts = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        # 策略配置（与 Optuna 一致，但参数通过 runtime_overrides 注入）
        strategies = [{
            "name": "pinbar",
            "triggers": [{"type": "pinbar", "enabled": True}],
            "filters": [
                {"type": "ema_trend", "enabled": True, "params": {}},
                {"type": "mtf", "enabled": True, "params": {}},
                {"type": "atr", "enabled": True, "params": {}},
            ]
        }]

        # 订单策略
        order_strategy = OrderStrategy(
            id="optuna_locked",
            name="Optuna Locked TP",
            tp_levels=2,
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        # 回测请求（stress 口径）
        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            limit=10000,  # ⭐ 关键修复：确保 MTF 数据充足
            start_time=start_ts,
            end_time=end_ts,
            mode="v3_pms",
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.001"),      # stress 口径
            fee_rate=Decimal("0.0004"),
            strategies=strategies,
            order_strategy=order_strategy,
        )

        # 运行时参数覆盖（基线参数）
        runtime_overrides = BacktestRuntimeOverrides(
            max_atr_ratio=Decimal("0.01"),
            min_distance_pct=Decimal("0.005"),
            ema_period=60,  # 默认值
            tp_ratios=[Decimal("0.6"), Decimal("0.4")],
            tp_targets=[Decimal("1.0"), Decimal("2.5")],
            breakeven_enabled=False,
        )

        print("\n参数配置：")
        print(f"  Symbol: {request.symbol}")
        print(f"  Timeframe: {request.timeframe}")
        print(f"  时间范围: 2024-01-01 ~ 2024-12-31")
        print(f"  Mode: {request.mode}")
        print(f"\n策略参数（runtime_overrides）：")
        print(f"  max_atr_ratio: {runtime_overrides.max_atr_ratio}")
        print(f"  min_distance_pct: {runtime_overrides.min_distance_pct}")
        print(f"  ema_period: {runtime_overrides.ema_period}")
        print(f"  breakeven_enabled: {runtime_overrides.breakeven_enabled}")
        print(f"  tp_ratios: {runtime_overrides.tp_ratios}")
        print(f"  tp_targets: {runtime_overrides.tp_targets}")
        print(f"\nstress 口径：")
        print(f"  slippage_rate: {request.slippage_rate}")
        print(f"  fee_rate: {request.fee_rate}")
        print()

        # 运行回测
        print("运行回测...")
        report = await backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides,
        )

        # 输出结果
        print("\n" + "=" * 80)
        print("回测结果")
        print("=" * 80)
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
        print("=" * 80)

        # 判断是否成功
        if report.total_trades > 0:
            print("\n✅ Optuna 链路已修通，可以恢复小规模搜索")
            return True
        else:
            print("\n❌ 仍然是 0 trades，需要继续定位")
            return False

    finally:
        await data_repo.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(run_single_validation())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n回测中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
