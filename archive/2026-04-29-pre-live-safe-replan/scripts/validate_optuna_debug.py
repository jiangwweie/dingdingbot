#!/usr/bin/env python3
"""
A3.2 单次 ETH 基线验证（调试版）

目标：添加调试日志，定位为什么 0 trades。
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
from src.domain.filter_factory import FilterFactory
from src.domain.strategy_engine import create_dynamic_runner


async def run_debug_validation():
    """调试验证：检查过滤器创建和参数注入"""

    print("=" * 80)
    print("A3.2 单次 ETH 基线验证（调试版）")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 回测器
    backtester = Backtester(None, data_repository=data_repo)

    # 时间范围
    start_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    # 策略配置
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

    # 回测请求
    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=start_ts,
        end_time=end_ts,
        mode="v3_pms",
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        strategies=strategies,
        order_strategy=order_strategy,
    )

    # 运行时参数覆盖
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=Decimal("0.01"),
        min_distance_pct=Decimal("0.005"),
        ema_period=60,
        tp_ratios=[Decimal("0.6"), Decimal("0.4")],
        tp_targets=[Decimal("1.0"), Decimal("2.5")],
        breakeven_enabled=False,
    )

    # 手动解析参数（模拟 resolve_backtest_params）
    from src.domain.models import ResolvedBacktestParams, BACKTEST_PARAM_DEFAULTS

    resolved_params = ResolvedBacktestParams(
        max_atr_ratio=runtime_overrides.max_atr_ratio,
        min_distance_pct=runtime_overrides.min_distance_pct,
        ema_period=runtime_overrides.ema_period,
        tp_ratios=runtime_overrides.tp_ratios,
        tp_targets=runtime_overrides.tp_targets,
        breakeven_enabled=runtime_overrides.breakeven_enabled,
        slippage_rate=request.slippage_rate,
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=request.fee_rate,
        initial_balance=request.initial_balance,
    )

    print("\n【调试：resolved_params】")
    print(f"  max_atr_ratio: {resolved_params.max_atr_ratio}")
    print(f"  min_distance_pct: {resolved_params.min_distance_pct}")
    print(f"  ema_period: {resolved_params.ema_period}")

    # 手动创建过滤器链（调试）
    filters_config = strategies[0]["filters"]
    filters = FilterFactory.create_chain(filters_config, resolved_params=resolved_params)

    print("\n【调试：过滤器创建】")
    for f in filters:
        print(f"  {f.name}:")
        print(f"    enabled: {f._enabled}")
        if hasattr(f, '_min_distance_pct'):
            print(f"    min_distance_pct: {f._min_distance_pct}")
        if hasattr(f, '_period'):
            print(f"    period: {f._period}")
        if hasattr(f, '_max_atr_ratio'):
            print(f"    max_atr_ratio: {f._max_atr_ratio}")

    # 运行回测
    print("\n运行回测...")
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
    print("=" * 80)

    if report.total_trades > 0:
        print("\n✅ Optuna 链路已修通")
        return True
    else:
        print("\n❌ 仍然是 0 trades")
        return False

    await data_repo.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(run_debug_validation())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
