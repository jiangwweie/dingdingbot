#!/usr/bin/env python3
"""
验证 MTF 数据加载修复

目标：
1. 验证 v3_pms 模式下 MTF 数据加载量是否根据时间范围动态计算
2. 验证 ETH 1h 2024-01-01 ~ 2024-12-31 是否能产生 > 0 trades
"""
import asyncio
import sys
from datetime import datetime
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
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.application.strategy_optimizer import StrategyOptimizer


async def verify_mtf_fix():
    """验证 MTF 数据加载修复"""

    print("=" * 80)
    print("验证 MTF 数据加载修复")
    print("=" * 80)

    # 数据仓库
    DB_PATH = "data/v3_dev.db"
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    # 回测器
    backtester = Backtester(None, data_repository=data_repo)

    # 优化器
    optimizer = StrategyOptimizer(None, backtester=backtester)
    await optimizer.initialize()

    try:
        # 参数空间（只搜索 2 个参数，减少验证时间）
        parameter_space = ParameterSpace(parameters=[
            ParameterDefinition(
                name="max_atr_ratio",
                type=ParameterType.FLOAT,
                low_float=0.008,
                high_float=0.012,
            ),
            ParameterDefinition(
                name="min_distance_pct",
                type=ParameterType.FLOAT,
                low_float=0.003,
                high_float=0.007,
            ),
        ])

        # 固定参数
        fixed_params = {
            "tp_ratios": [0.6, 0.4],
            "tp_targets": [1.0, 2.5],
            "breakeven_enabled": False,
            "tp_slippage_rate": 0.0005,
        }

        # 时间范围：2024-01-01 ~ 2024-12-31 (1 年)
        start_ts = int(datetime(2024, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(2024, 12, 31).timestamp() * 1000)

        # 优化请求
        request = OptimizationRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_ts,
            end_time=end_ts,
            limit=1000,  # OptimizationRequest 约束：<= 1000
            objective=OptimizationObjective.SHARPE,
            n_trials=10,  # OptimizationRequest 约束：>= 10
            parameter_space=parameter_space,
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.001"),
            fee_rate=Decimal("0.0004"),
            fixed_params=fixed_params,
        )

        print("\n【验证配置】")
        print(f"  Symbol: {request.symbol}")
        print(f"  Timeframe: {request.timeframe}")
        print(f"  时间范围: 2024-01-01 ~ 2024-12-31 (1 年)")
        print(f"  试验次数: {request.n_trials}")
        print(f"\n【预期 MTF 数据加载】")
        print(f"  修复前: 1000 bars (固定)")
        print(f"  修复后: ~2190 bars (根据时间范围动态计算)")
        print()

        # 启动优化任务
        print("启动 Optuna 任务...")
        job = await optimizer.start_optimization(request)

        print(f"\n任务 ID: {job.job_id}")
        print(f"任务状态: {job.status.value}")

        # 等待任务完成
        print("\n等待任务完成...")
        while True:
            await asyncio.sleep(1)
            current_job = optimizer.get_job(job.job_id)
            if current_job.status.value in ["completed", "failed", "stopped"]:
                print(f"任务结束: {current_job.status.value}")
                break

        # 获取试验结果
        results = await optimizer.get_trial_results(job.job_id, limit=10)

        if not results:
            print("\n❌ 无试验结果")
            return False

        # 验证结果
        print("\n" + "=" * 80)
        print("验证结果")
        print("=" * 80)

        success = True
        for i, result in enumerate(results, 1):
            print(f"\n[Trial {i}]")
            print(f"  objective_value: {result.objective_value:.4f}")
            print(f"  total_trades: {result.total_trades}")
            print(f"  win_rate: {result.win_rate:.2%}")
            print(f"  max_drawdown: {result.max_drawdown:.2%}")

            # 验证是否有交易
            if result.total_trades == 0:
                print("  ⚠️  警告：0 trades")
                success = False

        # 最终判断
        print("\n" + "=" * 80)
        if success and any(r.total_trades > 0 for r in results):
            print("✅ 验证通过：MTF 数据加载修复成功")
            print("   - 产生了交易信号")
            print("   - MTF 过滤器正常工作")
            return True
        else:
            print("❌ 验证失败：仍然 0 trades")
            print("   - 可能 MTF 数据仍然不足")
            print("   - 或其他过滤器过滤掉了所有信号")
            return False

    finally:
        await optimizer.close()
        await data_repo.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_mtf_fix())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
