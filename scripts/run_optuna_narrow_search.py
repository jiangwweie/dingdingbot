#!/usr/bin/env python3
"""
Optuna 第一轮窄搜索 - 验证 runtime_overrides 优化链路（使用 OptunaStudySpec）

目标：
1. 验证 Optuna → runtime_overrides → backtest 链路
2. 搜索 3 个参数：max_atr_ratio, min_distance_pct, ema_period
3. 不依赖 SQLite KV 写入

用法:
    PYTHONPATH=. python scripts/run_optuna_narrow_search.py
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
)
from src.application.research_specs import (
    OptunaStudySpec,
    BacktestJobSpec,
    TimeWindowMs,
    EngineCostSpec,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.application.strategy_optimizer import StrategyOptimizer


def format_timestamp(ts_ms: int) -> str:
    """格式化时间戳为人类可读"""
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S UTC")


async def main():
    """主函数"""
    print("=" * 60)
    print("Optuna 第一轮窄搜索 - runtime_overrides 链路验证")
    print("=" * 60)

    # ============================================================
    # 构建研究规范（所有配置集中在这里）
    # ============================================================

    # 时间窗口
    window = TimeWindowMs(
        start_time_ms=1704067200000,  # 2024-01-01 00:00:00 UTC
        end_time_ms=1735689599000,    # 2024-12-31 23:59:59 UTC
    )

    # 成本参数
    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )

    # 回测任务规范
    job_spec = BacktestJobSpec(
        name="eth_1h_narrow_search",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
    )

    # 参数空间（第一批只搜索这 3 个）
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

    # Optuna 研究规范
    study_spec = OptunaStudySpec(
        study_name="eth_1h_first_narrow_search",
        job=job_spec,
        n_trials=30,
        parameter_space=parameter_space,
        fixed_params={},
    )

    # ============================================================
    # 打印配置信息
    # ============================================================

    print(f"\n📍 实验配置:")
    print(f"   交易对: {study_spec.job.symbol}")
    print(f"   周期: {study_spec.job.timeframe}")
    print(f"   时间范围: {format_timestamp(study_spec.job.window.start_time_ms)} ~ {format_timestamp(study_spec.job.window.end_time_ms)}")
    print(f"   优化目标: {study_spec.objective.value}")
    print(f"   试验次数: {study_spec.n_trials}")
    print(f"   初始资金: {study_spec.job.costs.initial_balance}")
    print(f"   滑点率: {study_spec.job.costs.slippage_rate}")
    print(f"   手续费率: {study_spec.job.costs.fee_rate}")

    print(f"\n📐 参数空间:")
    for param in study_spec.parameter_space.parameters:
        if param.type == ParameterType.FLOAT:
            print(f"   {param.name}: [{param.low_float}, {param.high_float}]")
        else:
            print(f"   {param.name}: [{param.low}, {param.high}]")

    # ============================================================
    # 初始化组件
    # ============================================================

    print("\n🔧 初始化组件...")

    DB_PATH = "data/v3_dev.db"

    # 使用本地数据仓库（不需要 API key）
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    print(f"   ✅ 数据仓库: {DB_PATH}")

    # Backtester 使用本地数据
    backtester = Backtester(
        exchange_gateway=None,
        data_repository=data_repo,
    )
    print("   ✅ Backtester 初始化完成")

    # StrategyOptimizer（不需要 exchange_gateway，因为 backtester 用本地数据）
    optimizer = StrategyOptimizer(
        exchange_gateway=None,
        backtester=backtester,
    )
    await optimizer.initialize()
    print("   ✅ StrategyOptimizer 初始化完成")

    # ============================================================
    # 构建优化请求（使用 spec）
    # ============================================================

    request = study_spec.to_optimization_request()

    print("\n🚀 启动优化任务...")

    try:
        # 启动优化
        job = await optimizer.start_optimization(request)

        print(f"\n📋 任务信息:")
        print(f"   job_id: {job.job_id}")
        print(f"   status: {job.status.value}")
        print(f"   total_trials: {job.total_trials}")

        # 轮询任务状态
        print("\n⏳ 等待优化完成...")
        last_trial = 0

        while True:
            await asyncio.sleep(2)  # 每 2 秒检查一次

            current_job = optimizer.get_job(job.job_id)
            if current_job is None:
                print("   ❌ 任务丢失")
                break

            # 打印进度变化
            if current_job.current_trial != last_trial:
                print(f"   进度: {current_job.current_trial}/{current_job.total_trials}")
                last_trial = current_job.current_trial

            # 检查是否完成
            if current_job.status.value in ["completed", "failed", "stopped"]:
                print(f"\n✅ 任务结束: {current_job.status.value}")
                if current_job.error_message:
                    print(f"   错误: {current_job.error_message}")
                break

        # 获取试验结果
        print("\n📊 试验结果（前 10 名）:")
        print("-" * 60)

        results = await optimizer.get_trial_results(job.job_id, limit=10)

        if not results:
            print("   无试验结果")
        else:
            # 按目标值排序（降序）
            sorted_results = sorted(results, key=lambda x: x.objective_value, reverse=True)

            for i, result in enumerate(sorted_results[:10], 1):
                print(f"\n   [{i}] Trial #{result.trial_number}")
                print(f"       objective_value: {result.objective_value:.4f}")
                print(f"       params: {result.params}")
                print(f"       sharpe_ratio: {result.sharpe_ratio:.4f}")
                print(f"       total_return: {result.total_return:.2%}")
                print(f"       max_drawdown: {result.max_drawdown:.2%}")
                print(f"       win_rate: {result.win_rate:.2%}")
                print(f"       total_trades: {result.total_trades}")

        # 打印最佳结果
        final_job = optimizer.get_job(job.job_id)
        if final_job and final_job.best_trial:
            print("\n" + "=" * 60)
            print("🏆 最佳参数:")
            print(f"   best_trial: #{final_job.best_trial.trial_number}")
            print(f"   best_objective_value: {final_job.best_trial.objective_value:.4f}")
            print(f"   best_params: {final_job.best_trial.params}")
            candidate_path = await optimizer.write_candidate_report(final_job.job_id)
            print(f"   candidate_report: {candidate_path}")
            print("=" * 60)

    except Exception as e:
        print(f"\n❌ 优化失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理资源
        print("\n🧹 清理资源...")
        await optimizer.close()
        await data_repo.close()
        print("   ✅ 资源已释放")

    print("\n✨ 脚本执行完成")


if __name__ == "__main__":
    asyncio.run(main())