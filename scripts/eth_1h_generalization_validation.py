#!/usr/bin/env python3
"""
ETH/USDT:USDT 1h 策略参数泛化验证

核心目标：
验证长训练集（2021-2024）是否比单年训练（2024）更能产生可泛化参数

框架：
1. 训练集：2021-01-01 ~ 2024-12-31
2. OOS 验证：2025-01-01 ~ 2025-12-31
3. Forward Check：2026-01-01 ~ 2026-03-31

任务列表：
- 任务 2: 构建训练/验证框架
- 任务 3: 训练集 Optuna 优化
- 任务 4: 2025 OOS 验证
- 任务 5: 2026 Q1 forward check
- 任务 6: 输出最终判断

用法:
    PYTHONPATH=. python scripts/eth_1h_generalization_validation.py
"""
import asyncio
import sys
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    OptimizationRequest,
    OptimizationObjective,
    ParameterSpace,
    ParameterDefinition,
    ParameterType,
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.application.strategy_optimizer import StrategyOptimizer


# ============================================================
# 实验配置（任务 2 框架）
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MODE = "v3_pms"

# 时间范围
TRAIN_START = int(datetime(2021, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
TRAIN_END = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
OOS_START = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
OOS_END = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
FORWARD_START = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
FORWARD_END = int(datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

# 固定参数
BREAKEVEN_ENABLED = False
TP_RATIOS = [Decimal("0.6"), Decimal("0.4")]
TP_TARGETS = [Decimal("1.0"), Decimal("2.5")]

# Stress 口径成本参数
SLIPPAGE_RATE = Decimal("0.001")      # 0.1%
TP_SLIPPAGE_RATE = Decimal("0.0005")  # 0.05%
FEE_RATE = Decimal("0.0004")          # 0.04%

# 优化配置
OBJECTIVE = OptimizationObjective.SHARPE
N_TRIALS = 40  # 30~50 范围内
INITIAL_BALANCE = Decimal("10000")

DB_PATH = "data/v3_dev.db"

# 参数空间（任务 3 搜索范围）
PARAMETER_SPACE = ParameterSpace(parameters=[
    ParameterDefinition(
        name="max_atr_ratio",
        type=ParameterType.FLOAT,
        low_float=0.005,
        high_float=0.015,
    ),
    ParameterDefinition(
        name="min_distance_pct",
        type=ParameterType.FLOAT,
        low_float=0.003,
        high_float=0.008,
    ),
    ParameterDefinition(
        name="ema_period",
        type=ParameterType.INT,
        low=100,
        high=250,
    ),
])


def format_timestamp(ts_ms: int) -> str:
    """格式化时间戳"""
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S UTC")


def print_section(title: str):
    """打印分隔符"""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


async def run_single_backtest(
    backtester: Backtester,
    start_time: int,
    end_time: int,
    max_atr_ratio: Decimal,
    min_distance_pct: Decimal,
    ema_period: int,
    label: str = "Backtest",
) -> Dict[str, Any]:
    """
    运行单次回测

    Returns:
        回测结果字典
    """
    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=start_time,
        end_time=end_time,
        limit=10000,
        mode=MODE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
        initial_balance=INITIAL_BALANCE,
    )

    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=max_atr_ratio,
        min_distance_pct=min_distance_pct,
        ema_period=ema_period,
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        breakeven_enabled=BREAKEVEN_ENABLED,
    )

    request.order_strategy = OrderStrategy(
        id="generalization_test",
        name="Generalization Test Strategy",
        tp_levels=2,
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    return {
        "label": label,
        "total_pnl": float(report.total_pnl),
        "total_trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "max_drawdown": float(report.max_drawdown) * 100,
        "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "total_return": float(report.total_return) * 100,
        "winning_trades": report.winning_trades,
        "losing_trades": report.losing_trades,
        "total_fees": float(report.total_fees_paid),
    }


async def main():
    """主函数"""
    print_section("ETH/USDT:USDT 1h 策略参数泛化验证")

    # 打印实验配置
    print("\n实验配置:")
    print(f"  交易对: {SYMBOL}")
    print(f"  周期: {TIMEFRAME}")
    print(f"  模式: {MODE}")
    print(f"\n时间范围:")
    print(f"  训练集: {format_timestamp(TRAIN_START)} ~ {format_timestamp(TRAIN_END)}")
    print(f"  OOS:    {format_timestamp(OOS_START)} ~ {format_timestamp(OOS_END)}")
    print(f"  Forward:{format_timestamp(FORWARD_START)} ~ {format_timestamp(FORWARD_END)}")

    print("\n固定参数:")
    print(f"  breakeven_enabled: {BREAKEVEN_ENABLED}")
    print(f"  tp_ratios: {TP_RATIOS}")
    print(f"  tp_targets: {TP_TARGETS}")

    print("\nStress 口径成本:")
    print(f"  slippage_rate: {SLIPPAGE_RATE}")
    print(f"  tp_slippage_rate: {TP_SLIPPAGE_RATE}")
    print(f"  fee_rate: {FEE_RATE}")

    print("\n搜索参数:")
    for param in PARAMETER_SPACE.parameters:
        if param.type == ParameterType.FLOAT:
            print(f"  {param.name}: [{param.low_float}, {param.high_float}]")
        else:
            print(f"  {param.name}: [{param.low}, {param.high}]")
    print(f"  trials: {N_TRIALS}")

    # 初始化组件
    print_section("初始化组件")

    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()
    print(f"  数据仓库: {DB_PATH}")

    backtester = Backtester(
        exchange_gateway=None,
        data_repository=data_repo,
    )
    print("  Backtester 初始化完成")

    optimizer = StrategyOptimizer(
        exchange_gateway=None,
        backtester=backtester,
    )
    await optimizer.initialize()
    print("  StrategyOptimizer 初始化完成")

    # ======================== 任务 3: 训练集 Optuna 优化 ========================
    print_section("任务 3: 训练集 Optuna 优化 (2021-2024)")

    train_request = OptimizationRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=TRAIN_START,
        end_time=TRAIN_END,
        objective=OBJECTIVE,
        n_trials=N_TRIALS,
        parameter_space=PARAMETER_SPACE,
        initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
        fixed_params={
            "tp_ratios": TP_RATIOS,
            "tp_targets": TP_TARGETS,
            "breakeven_enabled": BREAKEVEN_ENABLED,
            "tp_slippage_rate": TP_SLIPPAGE_RATE,
        },
    )

    print("\n启动优化任务...")
    job = await optimizer.start_optimization(train_request)
    print(f"  job_id: {job.job_id}")

    # 轮询进度
    last_trial = 0
    while True:
        await asyncio.sleep(3)
        current_job = optimizer.get_job(job.job_id)
        if current_job is None:
            print("  任务丢失!")
            break

        if current_job.current_trial != last_trial:
            print(f"  进度: {current_job.current_trial}/{current_job.total_trials}")
            last_trial = current_job.current_trial

        if current_job.status.value in ["completed", "failed", "stopped"]:
            print(f"\n  任务结束: {current_job.status.value}")
            if current_job.error_message:
                print(f"  错误: {current_job.error_message}")
            break

    # 获取优化结果
    results = await optimizer.get_trial_results(job.job_id, limit=100)

    if not results:
        print("\n无有效试验结果，终止验证")
        await optimizer.close()
        await data_repo.close()
        return

    # 筛选有效结果
    valid_results = [r for r in results if r.total_trades > 0]
    print(f"\n有效试验: {len(valid_results)}/{len(results)}")

    if not valid_results:
        print("无有效交易，终止验证")
        await optimizer.close()
        await data_repo.close()
        return

    # 按 Sharpe 排序
    sorted_results = sorted(valid_results, key=lambda x: x.objective_value, reverse=True)

    # 打印 Top 5
    print("\nTop 5 参数 (训练集):")
    print("-" * 70)
    for i, r in enumerate(sorted_results[:5], 1):
        print(f"  [{i}] Trial #{r.trial_number}")
        print(f"      sharpe: {r.objective_value:.4f}")
        print(f"      max_atr_ratio: {r.params.get('max_atr_ratio', 'N/A'):.4f}")
        print(f"      min_distance_pct: {r.params.get('min_distance_pct', 'N/A'):.4f}")
        print(f"      ema_period: {r.params.get('ema_period', 'N/A')}")
        print(f"      return: {r.total_return:.2%}")
        print(f"      max_dd: {r.max_drawdown:.2%}")
        print(f"      trades: {r.total_trades}")

    # 选择最佳参数 + 2组备选参数
    best = sorted_results[0]
    best_params = {
        "max_atr_ratio": Decimal(str(best.params.get("max_atr_ratio", 0.01))),
        "min_distance_pct": Decimal(str(best.params.get("min_distance_pct", 0.005))),
        "ema_period": int(best.params.get("ema_period", 200)),
    }

    # 备选参数（选择第 2、3 名或参数有显著差异的）
    alt_params_list = []
    for r in sorted_results[1:4]:
        alt_params_list.append({
            "max_atr_ratio": Decimal(str(r.params.get("max_atr_ratio", 0.01))),
            "min_distance_pct": Decimal(str(r.params.get("min_distance_pct", 0.005))),
            "ema_period": int(r.params.get("ema_period", 200)),
        })

    # ======================== 任务 4: 2025 OOS 验证 ========================
    print_section("任务 4: 2025 OOS 验证")

    print("\n使用最佳参数验证 2025 全年:")
    print(f"  max_atr_ratio: {best_params['max_atr_ratio']}")
    print(f"  min_distance_pct: {best_params['min_distance_pct']}")
    print(f"  ema_period: {best_params['ema_period']}")

    # 最佳参数 OOS
    best_oos_result = await run_single_backtest(
        backtester=backtester,
        start_time=OOS_START,
        end_time=OOS_END,
        max_atr_ratio=best_params["max_atr_ratio"],
        min_distance_pct=best_params["min_distance_pct"],
        ema_period=best_params["ema_period"],
        label="OOS 2025 (Best)",
    )

    print("\n2025 OOS 结果 (最佳参数):")
    print(f"  total_pnl: {best_oos_result['total_pnl']:.2f} USDT")
    print(f"  total_return: {best_oos_result['total_return']:.2f}%")
    print(f"  total_trades: {best_oos_result['total_trades']}")
    print(f"  win_rate: {best_oos_result['win_rate']:.2f}%")
    print(f"  max_drawdown: {best_oos_result['max_drawdown']:.2f}%")
    print(f"  sharpe_ratio: {best_oos_result['sharpe_ratio']:.4f}")

    # 备选参数 OOS
    alt_oos_results = []
    for i, alt_params in enumerate(alt_params_list[:2], 1):
        print(f"\n备选参数 {i} OOS:")
        print(f"  max_atr_ratio: {alt_params['max_atr_ratio']}")
        print(f"  min_distance_pct: {alt_params['min_distance_pct']}")
        print(f"  ema_period: {alt_params['ema_period']}")

        result = await run_single_backtest(
            backtester=backtester,
            start_time=OOS_START,
            end_time=OOS_END,
            max_atr_ratio=alt_params["max_atr_ratio"],
            min_distance_pct=alt_params["min_distance_pct"],
            ema_period=alt_params["ema_period"],
            label=f"OOS 2025 (Alt {i})",
        )
        alt_oos_results.append((alt_params, result))

        print(f"  total_pnl: {result['total_pnl']:.2f} USDT")
        print(f"  total_return: {result['total_return']:.2f}%")
        print(f"  total_trades: {result['total_trades']}")
        print(f"  win_rate: {result['win_rate']:.2f}%")
        print(f"  max_drawdown: {result['max_drawdown']:.2f}%")

    # ======================== 任务 5: 2026 Q1 Forward Check ========================
    print_section("任务 5: 2026 Q1 Forward Check")

    print("\n使用相同参数验证 2026 Q1 (仅作 forward observation):")

    # 最佳参数 Forward
    best_forward_result = await run_single_backtest(
        backtester=backtester,
        start_time=FORWARD_START,
        end_time=FORWARD_END,
        max_atr_ratio=best_params["max_atr_ratio"],
        min_distance_pct=best_params["min_distance_pct"],
        ema_period=best_params["ema_period"],
        label="Forward 2026 Q1 (Best)",
    )

    print("\n2026 Q1 Forward 结果 (最佳参数):")
    print(f"  total_pnl: {best_forward_result['total_pnl']:.2f} USDT")
    print(f"  total_return: {best_forward_result['total_return']:.2f}%")
    print(f"  total_trades: {best_forward_result['total_trades']}")
    print(f"  win_rate: {best_forward_result['win_rate']:.2f}%")
    print(f"  max_drawdown: {best_forward_result['max_drawdown']:.2f}%")
    print(f"  sharpe_ratio: {best_forward_result['sharpe_ratio']:.4f}")

    # 备选参数 Forward
    alt_forward_results = []
    for i, (alt_params, _) in enumerate(alt_oos_results, 1):
        result = await run_single_backtest(
            backtester=backtester,
            start_time=FORWARD_START,
            end_time=FORWARD_END,
            max_atr_ratio=alt_params["max_atr_ratio"],
            min_distance_pct=alt_params["min_distance_pct"],
            ema_period=alt_params["ema_period"],
            label=f"Forward 2026 Q1 (Alt {i})",
        )
        alt_forward_results.append((alt_params, result))

        print(f"\n备选参数 {i} Forward:")
        print(f"  total_pnl: {result['total_pnl']:.2f} USDT")
        print(f"  total_return: {result['total_return']:.2f}%")
        print(f"  total_trades: {result['total_trades']}")

    # ======================== 任务 6: 输出最终判断 ========================
    print_section("任务 6: 最终判断")

    # 汇总表格
    print("\n汇总表格:")
    print("-" * 70)
    print(f"{'参数组':<15} {'训练集Return':<12} {'OOS Return':<12} {'Forward Return':<12}")
    print("-" * 70)

    # 训练集最佳参数的结果
    train_return = best.total_return * 100
    print(f"{'Best':<15} {train_return:>10.2f}% {best_oos_result['total_return']:>10.2f}% {best_forward_result['total_return']:>10.2f}%")

    for i, ((alt_params, oos_r), (_, fwd_r)) in enumerate(zip(alt_oos_results, alt_forward_results), 1):
        print(f"{'Alt ' + str(i):<15} {'--':>10} {oos_r['total_return']:>10.2f}% {fwd_r['total_return']:>10.2f}%")

    # 判断逻辑
    print("\n" + "-" * 70)
    print("判断分析:")
    print("-" * 70)

    # 1. 长训练集 vs 单年训练
    print("\n1. 长训练集（2021-2024）是否比单年 2024 训练更稳？")
    # 2024 单年训练的历史结果（来自之前诊断）
    single_year_oos_failed = True  # 2024 单年训练在 2025 OOS 失败
    long_train_oos_positive = best_oos_result['total_return'] > 0

    if long_train_oos_positive:
        print("  结论: 长训练集 OOS 表现改善")
        print(f"    - 2025 OOS Return: {best_oos_result['total_return']:.2f}%")
        print("    - 相比单年训练（OOS 失败），长训练集表现更好")
    else:
        print("  结论: 长训练集 OOS 仍不理想")
        print(f"    - 2025 OOS Return: {best_oos_result['total_return']:.2f}%")

    # 2. 2025 OOS 是否改善
    print("\n2. 2025 OOS 是否改善？")
    if long_train_oos_positive:
        print("  结论: 改善，OOS 为正收益")
    else:
        print("  结论: 未改善，OOS 仍为负")

    # 3. 2026 Q1 forward check 方向是否一致
    print("\n3. 2026 Q1 forward check 是否支持同方向判断？")
    forward_same_direction = (
        (best_oos_result['total_return'] > 0 and best_forward_result['total_return'] > 0) or
        (best_oos_result['total_return'] < 0 and best_forward_result['total_return'] < 0)
    )
    if forward_same_direction:
        print("  结论: Forward 和 OOS 方向一致")
    else:
        print("  结论: Forward 和 OOS 方向不一致，需谨慎解读")

    # 4. 是否存在可泛化参数区间
    print("\n4. 是否存在可泛化参数区间？")

    # 检查备选参数是否也在 OOS 表现良好
    alt_positive_count = sum(1 for _, r in alt_oos_results if r['total_return'] > 0)

    if long_train_oos_positive and alt_positive_count >= 1:
        print("  结论: 存在稳定区间")
        print(f"    - 最佳参数 OOS 正收益")
        print(f"    - 备选参数中 {alt_positive_count}/{len(alt_oos_results)} 也为正收益")

        # 分析参数范围
        all_positive_params = [best_params]
        for (p, r) in alt_oos_results:
            if r['total_return'] > 0:
                all_positive_params.append(p)

        if len(all_positive_params) >= 2:
            atr_vals = [p['max_atr_ratio'] for p in all_positive_params]
            dist_vals = [p['min_distance_pct'] for p in all_positive_params]
            ema_vals = [p['ema_period'] for p in all_positive_params]

            print(f"\n    稳定参数区间:")
            print(f"      max_atr_ratio: {min(atr_vals):.4f} ~ {max(atr_vals):.4f}")
            print(f"      min_distance_pct: {min(dist_vals):.4f} ~ {max(dist_vals):.4f}")
            print(f"      ema_period: {min(ema_vals)} ~ {max(ema_vals)}")
    else:
        print("  结论: 未发现稳定泛化区间")

    # 5. 下一步建议
    print("\n5. 下一步建议:")
    print("-" * 70)

    if long_train_oos_positive and alt_positive_count >= 1:
        print("  建议 A: 进入 expected 口径验证")
        print("    - 当前 stress 口径已验证通过")
        print("    - 下一步可使用 expected 口径（更低滑点）验证上限潜力")

        print("\n  建议 B: 继续扩大多年份验证")
        print("    - 当前仅验证 2025 OOS")
        print("    - 可扩展到 2023 OOS 进行多年份交叉验证")
    else:
        print("  建议: 回到策略逻辑调整")
        print("    - 长训练集未能解决泛化问题")
        print("    - 需要检查策略逻辑是否存在结构性问题")
        print("    - 或考虑放宽 ATR/Distance 过滤条件")

    # 保存结果到 JSON
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "train_range": f"{format_timestamp(TRAIN_START)} ~ {format_timestamp(TRAIN_END)}",
            "oos_range": f"{format_timestamp(OOS_START)} ~ {format_timestamp(OOS_END)}",
            "forward_range": f"{format_timestamp(FORWARD_START)} ~ {format_timestamp(FORWARD_END)}",
            "n_trials": N_TRIALS,
        },
        "best_params": {
            "max_atr_ratio": float(best_params["max_atr_ratio"]),
            "min_distance_pct": float(best_params["min_distance_pct"]),
            "ema_period": best_params["ema_period"],
        },
        "training_result": {
            "sharpe": best.objective_value,
            "return": best.total_return,
            "max_drawdown": best.max_drawdown,
            "total_trades": best.total_trades,
        },
        "oos_result": best_oos_result,
        "forward_result": best_forward_result,
        "alt_oos_results": [
            {
                "params": {k: float(v) if isinstance(v, Decimal) else v for k, v in p.items()},
                "result": r
            }
            for p, r in alt_oos_results
        ],
        "conclusions": {
            "long_train_better": long_train_oos_positive,
            "oos_improved": long_train_oos_positive,
            "forward_consistent": forward_same_direction,
            "stable_range_found": long_train_oos_positive and alt_positive_count >= 1,
        },
    }

    output_path = Path(__file__).parent.parent / "docs" / "diagnostic-reports" / "eth_1h_generalization_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n结果已保存至: {output_path}")

    # 清理
    print_section("清理资源")
    await optimizer.close()
    await data_repo.close()
    print("  资源已释放")

    print_section("脚本执行完成")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n脚本被中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
