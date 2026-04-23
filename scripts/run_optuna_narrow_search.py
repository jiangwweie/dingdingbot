#!/usr/bin/env python3
"""
Optuna 第一轮窄搜索 - 验证 runtime_overrides 优化链路

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
# 实验配置（锁定，不扩展）
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
START_TIME = 1704067200000  # 2024-01-01 00:00:00 UTC
END_TIME = 1735689599000    # 2024-12-31 23:59:59 UTC
OBJECTIVE = OptimizationObjective.SHARPE
N_TRIALS = 30
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
FEE_RATE = Decimal("0.0004")

DB_PATH = "data/v3_dev.db"

# 参数空间（第一批只搜索这 3 个）
PARAMETER_SPACE = ParameterSpace(parameters=[
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


def format_timestamp(ts_ms: int) -> str:
    """格式化时间戳为人类可读"""
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S UTC")


async def main():
    """主函数"""
    print("=" * 60)
    print("Optuna 第一轮窄搜索 - runtime_overrides 链路验证")
    print("=" * 60)

    print(f"\n📍 实验配置:")
    print(f"   交易对: {SYMBOL}")
    print(f"   周期: {TIMEFRAME}")
    print(f"   时间范围: {format_timestamp(START_TIME)} ~ {format_timestamp(END_TIME)}")
    print(f"   优化目标: {OBJECTIVE.value}")
    print(f"   试验次数: {N_TRIALS}")
    print(f"   初始资金: {INITIAL_BALANCE}")
    print(f"   滑点率: {SLIPPAGE_RATE}")
    print(f"   手续费率: {FEE_RATE}")

    print(f"\n📐 参数空间:")
    for param in PARAMETER_SPACE.parameters:
        if param.type == ParameterType.FLOAT:
            print(f"   {param.name}: [{param.low_float}, {param.high_float}]")
        else:
            print(f"   {param.name}: [{param.low}, {param.high}]")

    # 初始化组件
    print("\n🔧 初始化组件...")

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

    # 构建优化请求
    request = OptimizationRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_TIME,
        end_time=END_TIME,
        objective=OBJECTIVE,
        n_trials=N_TRIALS,
        parameter_space=PARAMETER_SPACE,
        initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

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
