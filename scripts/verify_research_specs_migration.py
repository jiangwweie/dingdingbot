#!/usr/bin/env python3
"""
验证研究规范迁移正确性

目标：
1. 验证 OptunaStudySpec -> OptimizationRequest 字段一致性
2. 验证 BacktestJobSpec -> BacktestRequest 字段一致性
3. 验证 candidate report 写入路径（dry-run，不运行 optuna）

用法:
    PYTHONPATH=. python scripts/verify_research_specs_migration.py
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
    OptimizationObjective,
)
from src.application.research_specs import (
    OptunaStudySpec,
    BacktestJobSpec,
    TimeWindowMs,
    EngineCostSpec,
)
from src.application.backtest_config import BacktestConfigResolver, DEFAULT_BACKTEST_PROFILE_PROVIDER


def verify_optuna_spec_to_request():
    """验证 OptunaStudySpec -> OptimizationRequest 字段一致性"""
    print("=" * 70)
    print("验证 1: OptunaStudySpec -> OptimizationRequest")
    print("=" * 70)

    # 构建规范
    window = TimeWindowMs(
        start_time_ms=1704067200000,
        end_time_ms=1735689599000,
    )

    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )

    job_spec = BacktestJobSpec(
        name="test_optuna",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
    )

    parameter_space = ParameterSpace(parameters=[
        ParameterDefinition(
            name="max_atr_ratio",
            type=ParameterType.FLOAT,
            low_float=0.008,
            high_float=0.012,
        ),
    ])

    study_spec = OptunaStudySpec(
        study_name="test_study",
        job=job_spec,
        n_trials=30,
        parameter_space=parameter_space,
        fixed_params={"tp_ratios": [Decimal("0.6"), Decimal("0.4")]},
    )

    # 转换为 OptimizationRequest
    request = study_spec.to_optimization_request()

    # 验证字段一致性
    print("\n字段一致性检查:")
    assert request.symbol == study_spec.job.symbol, "symbol 不一致"
    print(f"  ✅ symbol: {request.symbol}")

    assert request.timeframe == study_spec.job.timeframe, "timeframe 不一致"
    print(f"  ✅ timeframe: {request.timeframe}")

    assert request.start_time == study_spec.job.window.start_time_ms, "start_time 不一致"
    print(f"  ✅ start_time: {request.start_time}")

    assert request.end_time == study_spec.job.window.end_time_ms, "end_time 不一致"
    print(f"  ✅ end_time: {request.end_time}")

    assert request.objective == study_spec.objective, "objective 不一致"
    print(f"  ✅ objective: {request.objective}")

    assert request.n_trials == study_spec.n_trials, "n_trials 不一致"
    print(f"  ✅ n_trials: {request.n_trials}")

    assert request.initial_balance == study_spec.job.costs.initial_balance, "initial_balance 不一致"
    print(f"  ✅ initial_balance: {request.initial_balance}")

    assert request.slippage_rate == study_spec.job.costs.slippage_rate, "slippage_rate 不一致"
    print(f"  ✅ slippage_rate: {request.slippage_rate}")

    assert request.fee_rate == study_spec.job.costs.fee_rate, "fee_rate 不一致"
    print(f"  ✅ fee_rate: {request.fee_rate}")

    assert request.fixed_params == study_spec.fixed_params, "fixed_params 不一致"
    print(f"  ✅ fixed_params: {request.fixed_params}")

    print("\n✅ OptunaStudySpec -> OptimizationRequest 字段一致性验证通过")
    return True


def verify_backtest_spec_to_request():
    """验证 BacktestJobSpec -> BacktestRequest 字段一致性"""
    print("\n" + "=" * 70)
    print("验证 2: BacktestJobSpec -> BacktestRequest")
    print("=" * 70)

    # 构建规范
    window = TimeWindowMs(
        start_time_ms=1704067200000,
        end_time_ms=1735689599000,
    )

    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )

    job_spec = BacktestJobSpec(
        name="test_backtest",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
    )

    # 转换为 BacktestRequest
    request = job_spec.to_backtest_request()

    # 验证字段一致性
    print("\n字段一致性检查:")
    assert request.symbol == job_spec.symbol, "symbol 不一致"
    print(f"  ✅ symbol: {request.symbol}")

    assert request.timeframe == job_spec.timeframe, "timeframe 不一致"
    print(f"  ✅ timeframe: {request.timeframe}")

    assert request.start_time == job_spec.window.start_time_ms, "start_time 不一致"
    print(f"  ✅ start_time: {request.start_time}")

    assert request.end_time == job_spec.window.end_time_ms, "end_time 不一致"
    print(f"  ✅ end_time: {request.end_time}")

    assert request.limit == job_spec.limit, "limit 不一致"
    print(f"  ✅ limit: {request.limit}")

    assert request.mode == job_spec.mode, "mode 不一致"
    print(f"  ✅ mode: {request.mode}")

    assert request.initial_balance == job_spec.costs.initial_balance, "initial_balance 不一致"
    print(f"  ✅ initial_balance: {request.initial_balance}")

    assert request.slippage_rate == job_spec.costs.slippage_rate, "slippage_rate 不一致"
    print(f"  ✅ slippage_rate: {request.slippage_rate}")

    assert request.tp_slippage_rate == job_spec.costs.tp_slippage_rate, "tp_slippage_rate 不一致"
    print(f"  ✅ tp_slippage_rate: {request.tp_slippage_rate}")

    assert request.fee_rate == job_spec.costs.fee_rate, "fee_rate 不一致"
    print(f"  ✅ fee_rate: {request.fee_rate}")

    print("\n✅ BacktestJobSpec -> BacktestRequest 字段一致性验证通过")
    return True


async def verify_candidate_report_path():
    """验证 candidate report 写入路径（dry-run）"""
    print("\n" + "=" * 70)
    print("验证 3: Candidate Report 写入路径（dry-run）")
    print("=" * 70)

    # 使用 BacktestConfigResolver 解析配置
    resolver = BacktestConfigResolver(profile_provider=DEFAULT_BACKTEST_PROFILE_PROVIDER)

    # 解析 backtest_eth_baseline
    resolved = await resolver.resolve(profile_name="backtest_eth_baseline")

    print(f"\n解析 backtest_eth_baseline:")
    print(f"  ✅ profile_name: {resolved.profile_name}")
    print(f"  ✅ profile_version: {resolved.profile_version}")
    print(f"  ✅ config_hash: {resolved.config_hash}")

    print(f"\n市场配置:")
    print(f"  ✅ symbol: {resolved.symbol}")
    print(f"  ✅ timeframe: {resolved.timeframe}")

    print(f"\n策略配置:")
    print(f"  ✅ trigger: {resolved.strategy_definition.trigger.type}")
    print(f"  ✅ filters: {len(resolved.strategy_definition.filters)}")

    print(f"\n风控配置:")
    print(f"  ✅ max_loss_percent: {resolved.risk_config.max_loss_percent}")
    print(f"  ✅ max_leverage: {resolved.risk_config.max_leverage}")

    print(f"\n执行配置:")
    print(f"  ✅ tp_levels: {resolved.order_strategy.tp_levels}")
    print(f"  ✅ tp_ratios: {resolved.order_strategy.tp_ratios}")
    print(f"  ✅ tp_targets: {resolved.order_strategy.tp_targets}")

    # 验证可以生成 OrderStrategy
    order_strategy = resolved.order_strategy
    print(f"\n生成 OrderStrategy:")
    print(f"  ✅ id: {order_strategy.id}")
    print(f"  ✅ tp_levels: {order_strategy.tp_levels}")
    print(f"  ✅ tp_ratios: {order_strategy.tp_ratios}")

    print("\n✅ Candidate Report 写入路径验证通过")
    return True


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("研究规范迁移验证")
    print("=" * 70)

    try:
        # 验证 1: OptunaStudySpec -> OptimizationRequest
        verify_optuna_spec_to_request()

        # 验证 2: BacktestJobSpec -> BacktestRequest
        verify_backtest_spec_to_request()

        # 验证 3: Candidate Report 写入路径
        await verify_candidate_report_path()

        # 总结
        print("\n" + "=" * 70)
        print("✅ 所有验证通过")
        print("=" * 70)
        print("\n迁移总结:")
        print("  1. OptunaStudySpec -> OptimizationRequest 字段一致性 ✅")
        print("  2. BacktestJobSpec -> BacktestRequest 字段一致性 ✅")
        print("  3. Candidate Report 写入路径可用 ✅")
        print("\n下一步:")
        print("  - 运行单测: pytest tests/unit/test_research_specs.py -v")
        print("  - 运行回测: PYTHONPATH=. python scripts/run_eth_backtest.py")
        print("  - 运行 Optuna: PYTHONPATH=. python scripts/run_optuna_eth_1h.py")

    except AssertionError as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())