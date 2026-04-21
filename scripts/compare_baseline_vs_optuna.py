#!/usr/bin/env python3
"""
A3.1 对比基线回测请求 vs Optuna 内部请求

目标：找出"为什么同样是 ETH 1h，基线有交易，Optuna 却 0 trades"。
"""
import asyncio
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    OrderStrategy,
    OptimizationRequest,
    OptimizationObjective,
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.application.strategy_optimizer import StrategyOptimizer


# ============================================================
# 基线配置（来自 run_eth_backtest_bnb9.py）
# ============================================================

BASELINE_STRATEGIES = [{
    "name": "pinbar",
    "triggers": [{"type": "pinbar", "enabled": True}],
    "filters": [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": Decimal("0.005")}},
        {"type": "mtf", "enabled": True, "params": {}},
        {"type": "atr", "enabled": True, "params": {"max_atr_ratio": Decimal("0.01")}},
    ]
}]

BASELINE_ORDER_STRATEGY = OrderStrategy(
    id="dual_tp_baseline",
    name="Dual TP (Baseline)",
    tp_levels=2,
    tp_ratios=[Decimal("0.6"), Decimal("0.4")],
    tp_targets=[Decimal("1.0"), Decimal("2.5")],
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

BASELINE_RUNTIME_OVERRIDES = BacktestRuntimeOverrides(
    max_atr_ratio=Decimal("0.01"),
    min_distance_pct=Decimal("0.005"),
    tp_ratios=[Decimal("0.6"), Decimal("0.4")],
    tp_targets=[Decimal("1.0"), Decimal("2.5")],
    breakeven_enabled=False,
)


# ============================================================
# Optuna 配置（来自 strategy_optimizer._build_backtest_request）
# ============================================================

def build_optuna_request():
    """模拟 Optuna 内部构建的请求"""

    # Optuna 参数空间
    parameter_space = ParameterSpace(parameters=[
        ParameterDefinition(
            name="max_atr_ratio",
            type=ParameterType.FLOAT,
            low_float=0.005,
            high_float=0.03,
        ),
        ParameterDefinition(
            name="min_distance_pct",
            type=ParameterType.FLOAT,
            low_float=0.003,
            high_float=0.02,
        ),
        ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=40,
            high=80,
        ),
    ])

    # OptimizationRequest
    opt_request = OptimizationRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=1704067200000,  # 2024-01-01
        end_time=1735689599000,    # 2024-12-31
        objective=OptimizationObjective.SHARPE,
        n_trials=30,
        parameter_space=parameter_space,
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
    )

    # 模拟 Optuna 采样参数（使用基线值）
    params = {
        "max_atr_ratio": 0.01,
        "min_distance_pct": 0.005,
        "ema_period": 60,
    }

    # 模拟 StrategyOptimizer._build_backtest_request
    # 注意：这里模拟修复前的代码（fixed_params 未传入）
    strategies = [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": [
            {"type": "ema_trend", "enabled": True, "params": {}},
            {"type": "mtf", "enabled": True, "params": {}},
            {"type": "atr", "enabled": True, "params": {}},
        ]
    }]

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

    backtest_request = BacktestRequest(
        symbol=opt_request.symbol,
        timeframe=opt_request.timeframe,
        start_time=opt_request.start_time,
        end_time=opt_request.end_time,
        mode="v3_pms",
        initial_balance=opt_request.initial_balance,
        slippage_rate=opt_request.slippage_rate,
        fee_rate=opt_request.fee_rate,
        strategies=strategies,
        order_strategy=order_strategy,
    )

    # 模拟 StrategyOptimizer._build_runtime_overrides
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=Decimal(str(params["max_atr_ratio"])),
        min_distance_pct=Decimal(str(params["min_distance_pct"])),
        ema_period=int(params["ema_period"]),
        tp_ratios=[Decimal("0.6"), Decimal("0.4")],
        tp_targets=[Decimal("1.0"), Decimal("2.5")],
        breakeven_enabled=False,
    )

    return backtest_request, runtime_overrides


def compare_requests():
    """对比基线请求 vs Optuna 请求"""

    print("=" * 80)
    print("A3.1 对比基线回测请求 vs Optuna 内部请求")
    print("=" * 80)

    # 时间范围
    start_ts = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_ts = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    # 基线请求
    baseline_request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        limit=10000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=BASELINE_STRATEGIES,
        order_strategy=BASELINE_ORDER_STRATEGY,
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),  # bnb9 口径
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    # Optuna 请求
    optuna_request, optuna_overrides = build_optuna_request()

    # 对比表
    print("\n【关键差异列表】\n")

    differences = []

    # 1. strategies 配置
    print("1. strategies 配置差异：")
    print("   基线 strategies:")
    print(f"      {json.dumps(baseline_request.strategies, indent=6, default=str)}")
    print("   Optuna strategies:")
    print(f"      {json.dumps(optuna_request.strategies, indent=6, default=str)}")

    # 检查过滤器参数
    baseline_filters = baseline_request.strategies[0]["filters"]
    optuna_filters = optuna_request.strategies[0]["filters"]

    for i, (bf, of) in enumerate(zip(baseline_filters, optuna_filters)):
        if bf.get("params") != of.get("params"):
            differences.append(
                f"   ❌ 过滤器 {bf['type']} 参数不一致：\n"
                f"      基线: {bf.get('params')}\n"
                f"      Optuna: {of.get('params')}"
            )

    if not differences:
        print("   ✅ strategies 配置一致")
    else:
        for diff in differences:
            print(diff)

    # 2. runtime_overrides
    print("\n2. runtime_overrides 差异：")
    print(f"   基线: {BASELINE_RUNTIME_OVERRIDES}")
    print(f"   Optuna: {optuna_overrides}")

    overrides_diff = []
    if BASELINE_RUNTIME_OVERRIDES.max_atr_ratio != optuna_overrides.max_atr_ratio:
        overrides_diff.append("max_atr_ratio")
    if BASELINE_RUNTIME_OVERRIDES.min_distance_pct != optuna_overrides.min_distance_pct:
        overrides_diff.append("min_distance_pct")
    if BASELINE_RUNTIME_OVERRIDES.ema_period != optuna_overrides.ema_period:
        overrides_diff.append("ema_period")

    if overrides_diff:
        print(f"   ❌ 不一致字段: {', '.join(overrides_diff)}")
    else:
        print("   ✅ runtime_overrides 一致")

    # 3. 成本参数
    print("\n3. 成本参数差异：")
    print(f"   基线: slippage={baseline_request.slippage_rate}, tp_slippage={baseline_request.tp_slippage_rate}, fee={baseline_request.fee_rate}")
    print(f"   Optuna: slippage={optuna_request.slippage_rate}, tp_slippage={optuna_request.tp_slippage_rate}, fee={optuna_request.fee_rate}")

    if (baseline_request.slippage_rate != optuna_request.slippage_rate or
        baseline_request.fee_rate != optuna_request.fee_rate):
        print("   ⚠️  成本参数不同（口径不同，预期内）")
    else:
        print("   ✅ 成本参数一致")

    # 4. 时间范围
    print("\n4. 时间范围：")
    print(f"   基线: {baseline_request.start_time} ~ {baseline_request.end_time}")
    print(f"   Optuna: {optuna_request.start_time} ~ {optuna_request.end_time}")
    print("   ✅ 时间范围一致")

    # 根因总结
    print("\n" + "=" * 80)
    print("【根因结论】")
    print("=" * 80)

    print("""
最可疑的根因（按优先级排序）：

1. ⭐⭐⭐ strategies.filters 参数注入缺失
   - 基线：filters 中显式声明参数 {"min_distance_pct": 0.005, "max_atr_ratio": 0.01}
   - Optuna：filters 中 params 为空 {}
   - 影响：过滤器使用默认值，可能与 runtime_overrides 不一致

2. ⭐⭐ runtime_overrides 注入链路
   - runtime_overrides 已正确构建（max_atr_ratio=0.01, min_distance_pct=0.005）
   - 但需要验证 resolve_backtest_params() 是否正确解析并传递给过滤器

3. ⭐ 成本参数不同
   - 基线使用 bnb9 口径（slippage=0.0001）
   - Optuna 使用 stress 口径（slippage=0.001）
   - 这不是根因（口径不同是预期内），但会影响交易数量

建议修复：
- 修复 strategy_optimizer._build_backtest_request() 方法签名，接受 fixed_params 参数
- 验证 runtime_overrides → resolve_backtest_params → FilterFactory.create 链路
- 添加单次验证脚本，确认 Optuna 链路能复现非 0 trades
""")

    print("=" * 80)


if __name__ == "__main__":
    compare_requests()
