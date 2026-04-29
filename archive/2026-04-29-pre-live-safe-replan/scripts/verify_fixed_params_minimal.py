#!/usr/bin/env python3
"""
最小验证：检查 fixed_params 是否正确传递到 objective function

目标：
1. 创建 OptimizationRequest 并设置 fixed_params
2. 验证 fixed_params 通过 runtime overrides + profile resolver
3. 不初始化数据库、不运行完整优化，只验证参数装配链路
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    OptimizationRequest,
    OptimizationObjective,
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
)
from src.application.strategy_optimizer import StrategyOptimizer


async def verify_fixed_params_minimal():
    """最小验证：检查 fixed_params 是否正确传递"""

    print("=" * 80)
    print("最小验证：检查 fixed_params 是否正确传递到 objective function")
    print("=" * 80)

    optimizer = StrategyOptimizer(None, backtester=None)

    try:
        # 参数空间
        parameter_space = ParameterSpace(parameters=[
            ParameterDefinition(
                name="max_atr_ratio",
                type=ParameterType.FLOAT,
                low_float=0.008,
                high_float=0.012,
            ),
        ])

        # 固定参数
        fixed_params = {
            "tp_ratios": [0.6, 0.4],
            "tp_targets": [1.0, 2.5],
            "breakeven_enabled": False,
            "tp_slippage_rate": 0.0005,
        }

        # 优化请求
        request = OptimizationRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            limit=1000,
            objective=OptimizationObjective.SHARPE,
            n_trials=10,
            parameter_space=parameter_space,
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            fixed_params=fixed_params,
        )

        print("\n【验证步骤 1】检查 OptimizationRequest.fixed_params")
        print(f"  fixed_params: {request.fixed_params}")
        assert request.fixed_params == fixed_params, "❌ OptimizationRequest.fixed_params 不匹配"
        print("  ✅ OptimizationRequest.fixed_params 正确")

        print("\n【验证步骤 2】检查 _create_objective_function 是否接收 fixed_params")
        objective_func = optimizer._create_objective_function(request, "test_job", fixed_params=request.fixed_params)
        assert callable(objective_func), "❌ objective_func 不可调用"
        print("  ✅ _create_objective_function 返回可调用对象")

        print("\n【验证步骤 3】检查 _build_runtime_overrides 是否正确处理 fixed_params")
        # 模拟 Optuna trial 参数
        params = {"max_atr_ratio": 0.01}

        # 调用 _build_runtime_overrides
        runtime_overrides = optimizer._build_runtime_overrides(params, fixed_params)

        print(f"  runtime_overrides.tp_ratios: {runtime_overrides.tp_ratios}")
        print(f"  runtime_overrides.tp_targets: {runtime_overrides.tp_targets}")
        print(f"  runtime_overrides.breakeven_enabled: {runtime_overrides.breakeven_enabled}")

        # 验证 fixed_params 是否正确注入
        assert runtime_overrides.tp_ratios == [Decimal("0.6"), Decimal("0.4")], "❌ tp_ratios 不匹配"
        assert runtime_overrides.tp_targets == [Decimal("1.0"), Decimal("2.5")], "❌ tp_targets 不匹配"
        assert runtime_overrides.breakeven_enabled == False, "❌ breakeven_enabled 不匹配"
        print("  ✅ _build_runtime_overrides 正确处理 fixed_params")

        print("\n【验证步骤 4】检查 resolver trial inputs 是否正确处理 fixed_params")
        backtest_request, returned_overrides = await optimizer._build_trial_backtest_inputs(
            request,
            params=params,
            fixed_params=fixed_params,
            runtime_overrides=runtime_overrides,
        )

        print(f"  backtest_request.tp_slippage_rate: {backtest_request.tp_slippage_rate}")
        print(f"  backtest_request.order_strategy.tp_ratios: {backtest_request.order_strategy.tp_ratios}")
        print(f"  returned_overrides: {returned_overrides.model_dump(exclude_none=True)}")

        assert backtest_request.tp_slippage_rate == Decimal("0.0005"), "❌ tp_slippage_rate 不匹配"
        assert backtest_request.order_strategy.tp_ratios == [Decimal("0.6"), Decimal("0.4")], "❌ order_strategy.tp_ratios 不匹配"
        assert returned_overrides == runtime_overrides, "❌ runtime_overrides 未原样传递"
        print("  ✅ resolver trial inputs 正确处理 fixed_params")

        print("\n" + "=" * 80)
        print("✅ 所有验证步骤通过")
        print("   - OptimizationRequest.fixed_params 正确存储")
        print("   - _create_objective_function 正确接收 fixed_params")
        print("   - _build_runtime_overrides 正确处理 fixed_params")
        print("   - resolver trial inputs 正确处理 fixed_params")
        print("=" * 80)

        return True

    finally:
        await optimizer.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_fixed_params_minimal())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
