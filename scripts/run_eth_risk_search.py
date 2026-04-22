#!/usr/bin/env python3
"""
ETH 风控参数搜索

搜索空间：
- max_loss_percent: [0.015, 0.02, 0.025, 0.03] (1.5% - 3%)
- max_total_exposure: [1.0, 1.5, 2.0, 2.5, 3.0] (100% - 300%)

策略参数保持基准：
- ema_period: 50
- min_distance_pct: 0.005
- tp_ratios: [0.5, 0.5]
- tp_targets: [1.0, 3.5]
- breakeven_enabled: False
- ATR: 移除
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    OptimizationRequest,
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
    OptimizationObjective,
)
from src.application.strategy_optimizer import StrategyOptimizer
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.backtester import Backtester


async def main():
    """运行风控参数搜索"""

    print("=" * 80)
    print("ETH 风控参数搜索")
    print("=" * 80)

    # 初始化
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key=None,
        api_secret=None,
        testnet=False,
    )
    await gateway.initialize()

    backtester = Backtester(gateway)
    optimizer = StrategyOptimizer(gateway, backtester)
    await optimizer.initialize()

    try:
        # 定义参数空间（风控参数）
        parameter_space = ParameterSpace(parameters=[
            # 风控参数
            ParameterDefinition(
                name="max_loss_percent",
                type=ParameterType.FLOAT,
                low_float=0.015,
                high_float=0.03,
            ),
            ParameterDefinition(
                name="max_total_exposure",
                type=ParameterType.FLOAT,
                low_float=1.0,
                high_float=3.0,
            ),
        ])

        # 固定参数（策略参数）
        fixed_params = {
            # 策略过滤参数
            "ema_period": 50,
            "min_distance_pct": Decimal("0.005"),
            # TP 参数
            "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
            "tp_targets": [Decimal("1.0"), Decimal("3.5")],
            "breakeven_enabled": False,
            # 成本参数
            "slippage_rate": Decimal("0.0001"),
            "tp_slippage_rate": Decimal("0"),
            "fee_rate": Decimal("0.000405"),
        }

        # 时间范围：2024 年
        start_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

        # 构建优化请求
        request = OptimizationRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            start_time=start_time,
            end_time=end_time,
            limit=9000,
            parameter_space=parameter_space,
            objective=OptimizationObjective.SHARPE,
            n_trials=20,  # 4 × 5 = 20 种组合
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.0001"),
            fee_rate=Decimal("0.000405"),
            fixed_params=fixed_params,
        )

        print("\n搜索空间：")
        print("  max_loss_percent: [0.015, 0.02, 0.025, 0.03] (1.5% - 3%)")
        print("  max_total_exposure: [1.0, 1.5, 2.0, 2.5, 3.0] (100% - 300%)")
        print("\n固定策略参数：")
        print("  ema_period: 50")
        print("  min_distance_pct: 0.005")
        print("  tp_ratios: [0.5, 0.5]")
        print("  tp_targets: [1.0, 3.5]")
        print("  breakeven_enabled: False")
        print("\n优化目标: Sharpe Ratio")
        print("试验次数: 20")
        print("时间范围: 2024 全年")
        print("=" * 80)

        # 启动优化
        job = await optimizer.start_optimization(request)
        print(f"\n优化任务已启动: {job.job_id}")

        # 等待完成
        while True:
            await asyncio.sleep(5)
            job = optimizer.get_job(job.job_id)
            if job is None:
                print("任务不存在")
                break

            status_emoji = {
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "stopped": "⏹️",
            }.get(job.status.value, "❓")

            print(f"[{status_emoji}] 状态: {job.status.value}, 进度: {job.current_trial}/{job.total_trials}")

            if job.status.value in ["completed", "failed", "stopped"]:
                break

        # 输出结果
        if job and job.status.value == "completed":
            print("\n" + "=" * 80)
            print("优化完成")
            print("=" * 80)

            if job.best_trial:
                print(f"\n最佳试验 #{job.best_trial.trial_number}")
                print(f"  目标值: {job.best_trial.objective_value:.4f}")
                print(f"  参数: {job.best_trial.params}")

            # 获取所有试验结果
            trials = await optimizer.get_trial_results(job.job_id, limit=100)
            if trials:
                print("\n所有试验结果（按目标值排序）：")
                print("-" * 80)
                print(f"{'Trial':<8} {'Sharpe':<10} {'max_loss':<12} {'exposure':<12} {'PnL':<12} {'MaxDD':<10}")
                print("-" * 80)

                sorted_trials = sorted(trials, key=lambda t: t.objective_value, reverse=True)
                for t in sorted_trials[:10]:
                    params = t.params
                    max_loss = params.get("max_loss_percent", "N/A")
                    exposure = params.get("max_total_exposure", "N/A")
                    print(f"#{t.trial_number:<7} {t.objective_value:<10.4f} {max_loss:<12} {exposure:<12} {t.total_return:<12.2f} {t.max_drawdown:<10.2%}")

        elif job and job.status.value == "failed":
            print(f"\n优化失败: {job.error_message}")

    finally:
        await optimizer.close()
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
