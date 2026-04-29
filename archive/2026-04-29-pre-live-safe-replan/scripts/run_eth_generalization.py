#!/usr/bin/env python3
"""
ETH/USDT 1h 长训练集参数泛化验证

任务 1: 数据完整性检查 ✅
任务 2-6: Optuna 优化 + OOS 验证 + Forward Check

训练集: 2021-01-01 ~ 2024-12-31 (4年)
OOS: 2025-01-01 ~ 2025-12-31
Forward: 2026-01-01 ~ 2026-03-31
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


# ============================================================
# 配置
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
DB_PATH = "data/v3_dev.db"

# 时间范围
TRAIN_START = 1609459200000  # 2021-01-01 00:00:00 UTC
TRAIN_END = 1735689599000    # 2024-12-31 23:59:59 UTC
OOS_START = 1735689600000    # 2025-01-01 00:00:00 UTC
OOS_END = 1767225599000      # 2025-12-31 23:59:59 UTC
FWD_START = 1767225600000    # 2026-01-01 00:00:00 UTC
FWD_END = 1775087999000      # 2026-03-31 23:59:59 UTC

# 固定参数
INITIAL_BALANCE = Decimal("10000")
N_TRIALS = 40
OBJECTIVE = OptimizationObjective.SHARPE

# Stress 成本口径
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

# 固定订单策略
TP_RATIOS = [Decimal("0.6"), Decimal("0.4")]
TP_TARGETS = [Decimal("1.0"), Decimal("2.5")]
BREAKEVEN_ENABLED = False

# 参数空间
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


def fmt_ts(ts_ms):
    return datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M UTC")


async def run_backtest(backtester, start, end, params, label=""):
    """运行单次回测并返回结果"""
    from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=start,
        end_time=end,
        mode="v3_pms",
        initial_balance=INITIAL_BALANCE,
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
    )

    runtime_overrides = BacktestRuntimeOverrides(
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        breakeven_enabled=BREAKEVEN_ENABLED,
        max_atr_ratio=Decimal(str(params.get("max_atr_ratio"))),
        min_distance_pct=Decimal(str(params.get("min_distance_pct"))),
        ema_period=params.get("ema_period"),
    )

    result = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)
    return result


async def main():
    print("=" * 70)
    print("ETH/USDT 1h 长训练集参数泛化验证")
    print("=" * 70)

    print(f"\n训练集: {fmt_ts(TRAIN_START)} ~ {fmt_ts(TRAIN_END)}")
    print(f"OOS验证: {fmt_ts(OOS_START)} ~ {fmt_ts(OOS_END)}")
    print(f"Forward: {fmt_ts(FWD_START)} ~ {fmt_ts(FWD_END)}")
    print(f"Trials: {N_TRIALS}")
    print(f"目标: {OBJECTIVE.value}")
    print(f"成本: stress (slippage={SLIPPAGE_RATE}, fee={FEE_RATE})")

    # 初始化
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    backtester = Backtester(exchange_gateway=None, data_repository=data_repo)
    optimizer = StrategyOptimizer(exchange_gateway=None, backtester=backtester)
    await optimizer.initialize()

    try:
        # ========== 任务 3: Optuna 优化 ==========
        print("\n" + "=" * 70)
        print("任务 3: 在 2021-2024 训练集上运行 Optuna")
        print("=" * 70)

        request = OptimizationRequest(
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

        print("\n启动优化...")
        job = await optimizer.start_optimization(request)
        print(f"Job ID: {job.job_id}")
        print(f"Total trials: {job.total_trials}")

        # 轮询等待完成
        last_trial = 0
        while True:
            await asyncio.sleep(3)
            current_job = optimizer.get_job(job.job_id)
            if current_job is None:
                print("任务丢失!")
                break
            if current_job.current_trial != last_trial:
                print(f"  进度: {current_job.current_trial}/{current_job.total_trials}")
                last_trial = current_job.current_trial
            if current_job.status.value in ["completed", "failed", "stopped"]:
                print(f"  任务结束: {current_job.status.value}")
                if current_job.error_message:
                    print(f"  错误: {current_job.error_message}")
                break

        # 获取结果
        results = await optimizer.get_trial_results(job.job_id, limit=100)
        if not results:
            print("无试验结果!")
            return

        # 按目标值排序
        sorted_results = sorted(results, key=lambda x: x.objective_value, reverse=True)
        valid_results = [r for r in sorted_results if r.total_trades > 0]

        print(f"\n有效试验: {len(valid_results)}/{len(results)}")

        # 打印 Top 5
        print("\n" + "-" * 70)
        print("Top 5 试验 (训练集 2021-2024):")
        print("-" * 70)
        for i, r in enumerate(valid_results[:5], 1):
            print(f"\n[{i}] Trial #{r.trial_number}")
            print(f"    sharpe: {r.objective_value:.4f}")
            print(f"    max_atr_ratio: {r.params.get('max_atr_ratio', 0):.4f}")
            print(f"    min_distance_pct: {r.params.get('min_distance_pct', 0):.4f}")
            print(f"    ema_period: {r.params.get('ema_period', 0)}")
            print(f"    return: {r.total_return:.2%}")
            print(f"    max_dd: {r.max_drawdown:.2%}")
            print(f"    win_rate: {r.win_rate:.2%}")
            print(f"    trades: {r.total_trades}")

        # 稳定区间分析
        print("\n" + "=" * 70)
        print("参数稳定区间分析 (Top 30%):")
        print("=" * 70)

        top_n = max(3, len(valid_results) // 3)
        top_results = valid_results[:top_n]

        atr_vals = [r.params.get('max_atr_ratio', 0) for r in top_results]
        dist_vals = [r.params.get('min_distance_pct', 0) for r in top_results]
        ema_vals = [r.params.get('ema_period', 0) for r in top_results]

        print(f"\nmax_atr_ratio: {min(atr_vals):.4f} ~ {max(atr_vals):.4f} (range: {max(atr_vals)-min(atr_vals):.4f})")
        print(f"min_distance_pct: {min(dist_vals):.4f} ~ {max(dist_vals):.4f} (range: {max(dist_vals)-min(dist_vals):.4f})")
        print(f"ema_period: {min(ema_vals)} ~ {max(ema_vals)} (range: {max(ema_vals)-min(ema_vals)})")

        # ========== 任务 4: 2025 OOS 验证 ==========
        print("\n" + "=" * 70)
        print("任务 4: 2025 OOS 验证")
        print("=" * 70)

        # 选 Top 3 + 中间参数组
        test_params = []
        if len(valid_results) >= 1:
            test_params.append(("Best", valid_results[0].params))
        if len(valid_results) >= 3:
            test_params.append(("Mid1", valid_results[1].params))
        if len(valid_results) >= 5:
            test_params.append(("Mid2", valid_results[4].params))
        # 添加区间中心参数
        center_params = {
            "max_atr_ratio": (min(atr_vals) + max(atr_vals)) / 2,
            "min_distance_pct": (min(dist_vals) + max(dist_vals)) / 2,
            "ema_period": int((min(ema_vals) + max(ema_vals)) / 2),
        }
        test_params.append(("Center", center_params))

        print(f"\n测试 {len(test_params)} 组参数:")
        for name, p in test_params:
            print(f"  {name}: atr={p.get('max_atr_ratio',0):.4f} dist={p.get('min_distance_pct',0):.4f} ema={p.get('ema_period',0)}")

        oos_results = []
        for name, params in test_params:
            print(f"\n--- OOS: {name} ---")
            result = await run_backtest(backtester, OOS_START, OOS_END, params, f"OOS_{name}")

            trades = result.total_trades
            pnl = float(result.total_pnl)
            win_rate = float(result.win_rate) / 100  # PMSBacktestReport win_rate 是百分比
            max_dd = float(result.max_drawdown) / 100
            sharpe = float(result.sharpe_ratio) if result.sharpe_ratio else 0.0

            print(f"  trades: {trades}, pnl: {pnl}, win_rate: {win_rate:.2%}, max_dd: {max_dd:.2%}, sharpe: {sharpe:.4f}")

            oos_results.append({
                "name": name,
                "params": params,
                "trades": trades,
                "pnl": pnl,
                "win_rate": win_rate,
                "max_dd": max_dd,
                "sharpe": sharpe,
            })

        # ========== 任务 5: 2026 Q1 Forward Check ==========
        print("\n" + "=" * 70)
        print("任务 5: 2026 Q1 Forward Check")
        print("=" * 70)

        fwd_results = []
        for name, params in test_params:
            print(f"\n--- Forward: {name} ---")
            result = await run_backtest(backtester, FWD_START, FWD_END, params, f"FWD_{name}")

            trades = result.total_trades
            pnl = float(result.total_pnl)
            win_rate = float(result.win_rate) / 100  # PMSBacktestReport win_rate 是百分比
            max_dd = float(result.max_drawdown) / 100
            sharpe = float(result.sharpe_ratio) if result.sharpe_ratio else 0.0

            print(f"  trades: {trades}, pnl: {pnl}, win_rate: {win_rate:.2%}, max_dd: {max_dd:.2%}, sharpe: {sharpe:.4f}")

            fwd_results.append({
                "name": name,
                "trades": trades,
                "pnl": pnl,
                "win_rate": win_rate,
                "max_dd": max_dd,
                "sharpe": sharpe,
            })

        # ========== 任务 6: 最终判断 ==========
        print("\n" + "=" * 70)
        print("任务 6: 最终判断")
        print("=" * 70)

        # 训练集表现
        best_train = valid_results[0] if valid_results else None
        print(f"\n1. 长训练集 vs 单年训练:")
        if best_train:
            print(f"   训练集最优 sharpe: {best_train.objective_value:.4f}")
            print(f"   参数: atr={best_train.params.get('max_atr_ratio',0):.4f}, dist={best_train.params.get('min_distance_pct',0):.4f}, ema={best_train.params.get('ema_period',0)}")

        # OOS 表现
        print(f"\n2. 2025 OOS 是否改善:")
        if oos_results:
            best_oos = max(oos_results, key=lambda x: x.get('sharpe', 0))
            worst_oos = min(oos_results, key=lambda x: x.get('sharpe', 0))
            print(f"   最好: {best_oos['name']} sharpe={best_oos['sharpe']:.4f} trades={best_oos['trades']}")
            print(f"   最差: {worst_oos['name']} sharpe={worst_oos['sharpe']:.4f} trades={worst_oos['trades']}")

            profitable_oos = [r for r in oos_results if r['pnl'] > 0]
            print(f"   正收益参数组: {len(profitable_oos)}/{len(oos_results)}")

        # Forward check
        print(f"\n3. 2026 Q1 Forward Check:")
        if fwd_results:
            profitable_fwd = [r for r in fwd_results if r['pnl'] > 0]
            print(f"   正收益参数组: {len(profitable_fwd)}/{len(fwd_results)}")
            for r in fwd_results:
                print(f"   {r['name']}: sharpe={r['sharpe']:.4f} trades={r['trades']}")

        # 泛化稳定区间
        print(f"\n4. 可泛化参数区间:")
        oos_stable = [r for r in oos_results if r['sharpe'] > 0]
        if len(oos_stable) >= 2:
            stable_atr = [r['params'].get('max_atr_ratio', 0) for r in oos_stable if r.get('params')]
            stable_dist = [r['params'].get('min_distance_pct', 0) for r in oos_stable if r.get('params')]
            stable_ema = [r['params'].get('ema_period', 0) for r in oos_stable if r.get('params')]
            if stable_atr and stable_dist and stable_ema:
                print(f"   OOS 正收益参数范围:")
                print(f"     max_atr_ratio: {min(stable_atr):.4f} ~ {max(stable_atr):.4f}")
                print(f"     min_distance_pct: {min(stable_dist):.4f} ~ {max(stable_dist):.4f}")
                print(f"     ema_period: {min(stable_ema)} ~ {max(stable_ema)}")
        else:
            print("   未形成稳定泛化区间")

        # 建议
        print(f"\n5. 下一步建议:")
        oos_profitable = len([r for r in oos_results if r['pnl'] > 0])
        if oos_profitable >= len(oos_results) * 0.5:
            print("   ✓ 建议进入 expected 口径验证")
        elif oos_profitable >= len(oos_results) * 0.3:
            print("   △ 建议继续扩大多年份 Optuna (50+ trials)")
        else:
            print("   ✗ 建议回到策略逻辑调整")

    finally:
        await optimizer.close()
        await data_repo.close()
        print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())
