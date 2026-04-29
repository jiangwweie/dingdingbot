#!/usr/bin/env python3
"""
Optuna ETH/USDT 1h 小规模优化（使用 OptunaStudySpec）

目标：
1. 搜索 3 个参数：max_atr_ratio, min_distance_pct, ema_period
2. 固定 TP 配置：tp_ratios=[0.6, 0.4], tp_targets=[1.0, 2.5]
3. 使用 realistic 滑点：slippage_rate=0.0002
4. breakeven_enabled=False

用法:
    PYTHONPATH=. python scripts/run_optuna_eth_1h.py
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
    print("Optuna ETH/USDT 1h 小规模优化（OptunaStudySpec）")
    print("=" * 60)

    # ============================================================
    # 构建研究规范（所有配置集中在这里）
    # ============================================================

    # 时间窗口
    window = TimeWindowMs(
        start_time_ms=1704067200000,  # 2024-01-01 00:00:00 UTC
        end_time_ms=1735689599000,    # 2024-12-31 23:59:59 UTC
    )

    # 成本参数（realistic）
    costs = EngineCostSpec(
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )

    # 回测任务规范
    job_spec = BacktestJobSpec(
        name="eth_1h_optuna_realistic",
        profile_name="backtest_eth_baseline",
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        window=window,
        limit=9000,
        mode="v3_pms",
        costs=costs,
    )

    # 参数空间（只搜索这 3 个，窄范围）
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
        ParameterDefinition(
            name="ema_period",
            type=ParameterType.INT,
            low=150,
            high=250,
        ),
    ])

    # Optuna 研究规范
    study_spec = OptunaStudySpec(
        study_name="eth_1h_narrow_search",
        job=job_spec,
        n_trials=30,
        parameter_space=parameter_space,
        fixed_params={
            "tp_ratios": [Decimal("0.6"), Decimal("0.4")],
            "tp_targets": [Decimal("1.0"), Decimal("2.5")],
            "breakeven_enabled": False,
        },
    )

    # ============================================================
    # 打印配置信息
    # ============================================================

    print(f"\n实验配置:")
    print(f"   交易对: {study_spec.job.symbol}")
    print(f"   周期: {study_spec.job.timeframe}")
    print(f"   时间范围: {format_timestamp(study_spec.job.window.start_time_ms)} ~ {format_timestamp(study_spec.job.window.end_time_ms)}")
    print(f"   优化目标: {study_spec.objective.value}")
    print(f"   试验次数: {study_spec.n_trials}")
    print(f"   初始资金: {study_spec.job.costs.initial_balance}")

    print(f"\n成本参数 (realistic):")
    print(f"   入场滑点率: {study_spec.job.costs.slippage_rate}")
    print(f"   止盈滑点率: {study_spec.job.costs.tp_slippage_rate}")
    print(f"   手续费率: {study_spec.job.costs.fee_rate}")

    print(f"\n固定订单参数:")
    print(f"   TP ratios: {study_spec.fixed_params.get('tp_ratios')}")
    print(f"   TP targets: {study_spec.fixed_params.get('tp_targets')}")
    print(f"   Breakeven: {study_spec.fixed_params.get('breakeven_enabled')}")

    print(f"\n参数空间:")
    for param in study_spec.parameter_space.parameters:
        if param.type == ParameterType.FLOAT:
            print(f"   {param.name}: [{param.low_float}, {param.high_float}]")
        else:
            print(f"   {param.name}: [{param.low}, {param.high}]")

    # ============================================================
    # 初始化组件
    # ============================================================

    print("\n初始化组件...")

    DB_PATH = "data/v3_dev.db"

    # 使用本地数据仓库（不需要 API key）
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    print(f"   数据仓库: {DB_PATH}")

    # Backtester 使用本地数据
    backtester = Backtester(
        exchange_gateway=None,
        data_repository=data_repo,
    )
    print("   Backtester 初始化完成")

    # StrategyOptimizer
    optimizer = StrategyOptimizer(
        exchange_gateway=None,
        backtester=backtester,
    )
    await optimizer.initialize()
    print("   StrategyOptimizer 初始化完成")

    # ============================================================
    # 构建优化请求（使用 spec）
    # ============================================================

    request = study_spec.to_optimization_request()

    print("\n启动优化任务...")

    # 用于存储试验结果
    trial_results = []

    try:
        # 启动优化
        job = await optimizer.start_optimization(request)

        print(f"\n任务信息:")
        print(f"   job_id: {job.job_id}")
        print(f"   status: {job.status.value}")
        print(f"   total_trials: {job.total_trials}")

        # 轮询任务状态
        print("\n等待优化完成...")
        last_trial = 0

        while True:
            await asyncio.sleep(2)  # 每 2 秒检查一次

            current_job = optimizer.get_job(job.job_id)
            if current_job is None:
                print("   任务丢失")
                break

            # 打印进度变化
            if current_job.current_trial != last_trial:
                print(f"   进度: {current_job.current_trial}/{current_job.total_trials}")
                last_trial = current_job.current_trial

            # 检查是否完成
            if current_job.status.value in ["completed", "failed", "stopped"]:
                print(f"\n任务结束: {current_job.status.value}")
                if current_job.error_message:
                    print(f"   错误: {current_job.error_message}")
                break

        # 获取试验结果
        print("\n" + "=" * 60)
        print("试验结果（按目标值排序）:")
        print("-" * 60)

        results = await optimizer.get_trial_results(job.job_id, limit=100)

        if not results:
            print("   无试验结果")
        else:
            # 按目标值排序（降序）
            sorted_results = sorted(results, key=lambda x: x.objective_value, reverse=True)

            # 检查是否有大量 0 trades
            zero_trades_count = sum(1 for r in sorted_results if r.total_trades == 0)
            if zero_trades_count > study_spec.n_trials * 0.5:
                print(f"\n警告: {zero_trades_count}/{study_spec.n_trials} 次试验无交易！")
                print("   可能原因: 参数空间过于严格")
                print("   建议: 检查 max_atr_ratio 和 min_distance_pct 范围")

            # 打印 Top 3 简表
            print("\nTop 3 试验:")
            for i, result in enumerate(sorted_results[:3], 1):
                print(f"\n   [{i}] Trial #{result.trial_number}")
                print(f"       objective (sharpe): {result.objective_value:.4f}")
                print(f"       max_atr_ratio: {result.params.get('max_atr_ratio', 'N/A'):.4f}")
                print(f"       min_distance_pct: {result.params.get('min_distance_pct', 'N/A'):.4f}")
                print(f"       ema_period: {result.params.get('ema_period', 'N/A')}")
                print(f"       total_return: {result.total_return:.2%}")
                print(f"       max_drawdown: {result.max_drawdown:.2%}")
                print(f"       win_rate: {result.win_rate:.2%}")
                print(f"       total_trades: {result.total_trades}")

            # 分析稳定区间
            print("\n" + "=" * 60)
            print("参数稳定区间分析:")
            print("-" * 60)

            # 只分析有交易的结果
            valid_results = [r for r in sorted_results if r.total_trades > 0]

            if len(valid_results) >= 3:
                # 取 top 30% 的结果
                top_n = max(3, len(valid_results) // 3)
                top_results = valid_results[:top_n]

                # 统计参数范围
                atr_values = [r.params.get('max_atr_ratio', 0) for r in top_results]
                dist_values = [r.params.get('min_distance_pct', 0) for r in top_results]
                ema_values = [r.params.get('ema_period', 0) for r in top_results]

                print(f"\nTop {top_n} 结果参数范围:")
                print(f"   max_atr_ratio: {min(atr_values):.4f} ~ {max(atr_values):.4f}")
                print(f"   min_distance_pct: {min(dist_values):.4f} ~ {max(dist_values):.4f}")
                print(f"   ema_period: {min(ema_values)} ~ {max(ema_values)}")

                # 判断稳定性
                atr_range = max(atr_values) - min(atr_values)
                dist_range = max(dist_values) - min(dist_values)

                if atr_range < 0.005 and dist_range < 0.003:
                    print("\n稳定区间判断: 参数收敛良好，建议在当前范围内细化搜索")
                else:
                    print("\n稳定区间判断: 参数分散，建议扩大 trial 或检查策略逻辑")
            else:
                print("有效试验结果不足，无法分析稳定区间")

            # 存储结果用于后续分析
            trial_results = valid_results

        # 打印最佳结果
        final_job = optimizer.get_job(job.job_id)
        if final_job and final_job.best_trial:
            print("\n" + "=" * 60)
            print("最佳参数:")
            print(f"   Trial: #{final_job.best_trial.trial_number}")
            print(f"   Best Objective (Sharpe): {final_job.best_trial.objective_value:.4f}")
            print(f"   Best Params: {final_job.best_trial.params}")
            candidate_path = await optimizer.write_candidate_report(final_job.job_id)
            print(f"   Candidate Report: {candidate_path}")
            print("=" * 60)

        # 总结和建议
        print("\n" + "=" * 60)
        print("总结和建议:")
        print("-" * 60)

        if results:
            valid_count = len([r for r in results if r.total_trades > 0])
            print(f"有效试验（有交易）: {valid_count}/{len(results)}")

            if valid_count >= len(results) * 0.7:
                print("建议: 可以继续扩大 trial 次数进行更精细搜索")
            elif valid_count >= len(results) * 0.3:
                print("建议: 当前参数空间适中，建议保持 trial 次数")
            else:
                print("建议: 参数空间过于严格，建议放宽 max_atr_ratio 或 min_distance_pct")

    except Exception as e:
        print(f"\n优化失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理资源
        print("\n清理资源...")
        await optimizer.close()
        await data_repo.close()
        print("   资源已释放")

    print("\n脚本执行完成")


if __name__ == "__main__":
    asyncio.run(main())
