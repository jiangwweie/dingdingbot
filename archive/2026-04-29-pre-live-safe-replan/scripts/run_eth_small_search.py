#!/usr/bin/env python3
"""
ETH 1h 双窗口小规模搜索 (2024 + 2025)

固定强先验（不搜索）：
- direction = LONG-only
- breakeven_enabled = False
- tp_ratios = [0.5, 0.5]
- tp_targets = [1.0, 3.5]
- mode = v3_pms
- cost_mode = stress

搜索参数（弱先验）：
- ema_period: [90, 150], step=10
- max_atr_ratio: [0.004, 0.008], step=0.001
- min_distance_pct: [0.005, 0.012], step=0.001

目标函数（混合）：
- score = pnl_2024 + pnl_2025 + 800*(sharpe_2024 + sharpe_2025)

硬约束（不满足即淘汰）：
- pnl_2024 > 0
- pnl_2025 > 0
- max_dd_2024 < 30%
- max_dd_2025 < 30%
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import optuna

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

# ============================================================
# 固定配置
# ============================================================

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

# 强先验（固定）
FIXED_PARAMS = {
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "breakeven_enabled": False,
}

# 时间窗口
W2024_START = 1704067200000  # 2024-01-01
W2024_END = 1735689599000    # 2024-12-31
W2025_START = 1735689600000  # 2025-01-01
W2025_END = 1767225599000    # 2025-12-31

# 搜索参数范围
EMA_PERIOD_RANGE = (90, 150, 10)      # [90, 100, 110, 120, 130, 140, 150]
MAX_ATR_RATIO_RANGE = (0.004, 0.008, 0.001)  # [0.004, 0.005, 0.006, 0.007, 0.008]
MIN_DISTANCE_PCT_RANGE = (0.005, 0.012, 0.001)  # [0.005, 0.006, ..., 0.012]

N_TRIALS = 50


def generate_step_values(low: float, high: float, step: float) -> List[float]:
    """生成步进值列表"""
    values = []
    v = low
    while v <= high + 1e-9:
        values.append(round(v, 6))
        v += step
    return values


async def run_backtest(
    backtester: Backtester,
    start: int,
    end: int,
    ema_period: int,
    max_atr_ratio: float,
    min_distance_pct: float,
) -> Dict[str, Any]:
    """执行单次回测"""
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

    overrides = BacktestRuntimeOverrides(
        tp_ratios=FIXED_PARAMS["tp_ratios"],
        tp_targets=FIXED_PARAMS["tp_targets"],
        breakeven_enabled=FIXED_PARAMS["breakeven_enabled"],
        max_atr_ratio=Decimal(str(max_atr_ratio)),
        min_distance_pct=Decimal(str(min_distance_pct)),
        ema_period=ema_period,
        allowed_directions=["LONG"],
    )

    result = await backtester.run_backtest(request, runtime_overrides=overrides)

    pnl = float(result.total_pnl)
    trades = result.total_trades
    wr = float(result.win_rate) / 100 if result.win_rate else 0.0
    dd = float(result.max_drawdown) if result.max_drawdown else 0.0
    sharpe = float(result.sharpe_ratio) if result.sharpe_ratio else 0.0

    return {
        "pnl": pnl,
        "trades": trades,
        "win_rate": wr,
        "max_dd": dd,
        "sharpe": sharpe,
    }


async def objective(
    backtester: Backtester,
    trial: optuna.Trial,
) -> float:
    """目标函数：混合 PnL + Sharpe"""
    # 采样参数
    ema_period = trial.suggest_int("ema_period", 90, 150, step=10)
    max_atr_ratio = trial.suggest_float("max_atr_ratio", 0.004, 0.008, step=0.001)
    min_distance_pct = trial.suggest_float("min_distance_pct", 0.005, 0.012, step=0.001)

    # 运行双窗口回测
    r2024 = await run_backtest(
        backtester, W2024_START, W2024_END,
        ema_period, max_atr_ratio, min_distance_pct
    )
    r2025 = await run_backtest(
        backtester, W2025_START, W2025_END,
        ema_period, max_atr_ratio, min_distance_pct
    )

    # 存储结果用于后续分析
    trial.set_user_attr("pnl_2024", r2024["pnl"])
    trial.set_user_attr("pnl_2025", r2025["pnl"])
    trial.set_user_attr("sharpe_2024", r2024["sharpe"])
    trial.set_user_attr("sharpe_2025", r2025["sharpe"])
    trial.set_user_attr("max_dd_2024", r2024["max_dd"])
    trial.set_user_attr("max_dd_2025", r2025["max_dd"])
    trial.set_user_attr("trades_2024", r2024["trades"])
    trial.set_user_attr("trades_2025", r2025["trades"])
    trial.set_user_attr("win_rate_2024", r2024["win_rate"])
    trial.set_user_attr("win_rate_2025", r2025["win_rate"])

    # 硬约束检查
    if r2024["pnl"] <= 0:
        return -1e9
    if r2025["pnl"] <= 0:
        return -1e9
    if r2024["max_dd"] >= 0.30:
        return -1e9
    if r2025["max_dd"] >= 0.30:
        return -1e9

    # 混合目标函数
    score = (
        r2024["pnl"] + r2025["pnl"]
        + 800 * (r2024["sharpe"] + r2025["sharpe"])
    )

    return score


async def main():
    print("=" * 70)
    print("ETH 1h 双窗口小规模搜索 (2024 + 2025)")
    print("=" * 70)

    print("\n固定强先验:")
    print(f"  direction:        LONG-only")
    print(f"  breakeven_enabled: {FIXED_PARAMS['breakeven_enabled']}")
    print(f"  tp_ratios:        {FIXED_PARAMS['tp_ratios']}")
    print(f"  tp_targets:       {FIXED_PARAMS['tp_targets']}")
    print(f"  mode:             v3_pms")
    print(f"  cost_mode:        stress")

    print("\n搜索参数（弱先验）:")
    print(f"  ema_period:       [90, 150], step=10")
    print(f"  max_atr_ratio:    [0.004, 0.008], step=0.001")
    print(f"  min_distance_pct: [0.005, 0.012], step=0.001")

    print(f"\n预算: {N_TRIALS} trials")
    print("\n目标函数: score = pnl_2024 + pnl_2025 + 800*(sharpe_2024 + sharpe_2025)")
    print("\n硬约束:")
    print("  pnl_2024 > 0")
    print("  pnl_2025 > 0")
    print("  max_dd_2024 < 30%")
    print("  max_dd_2025 < 30%")

    # 初始化
    print("\n" + "=" * 70)
    print("初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)
    print("  数据仓库: OK")
    print("  回测器: OK")

    # 创建 study
    study = optuna.create_study(direction="maximize")

    # 定义同步目标函数包装
    def sync_objective(trial):
        return asyncio.get_event_loop().run_until_complete(
            objective(bt, trial)
        )

    # 运行优化
    print("\n" + "=" * 70)
    print(f"开始搜索 ({N_TRIALS} trials)...")
    print("=" * 70)

    # 使用异步方式运行
    for i in range(N_TRIALS):
        trial = study.ask()
        try:
            value = await objective(bt, trial)
            study.tell(trial, value)
            print(f"  [{i+1:2d}/{N_TRIALS}] score={value:+.2f}  "
                  f"ema={trial.params['ema_period']:3d}  "
                  f"atr={trial.params['max_atr_ratio']:.3f}  "
                  f"dist={trial.params['min_distance_pct']:.3f}")
        except Exception as e:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            print(f"  [{i+1:2d}/{N_TRIALS}] FAILED: {e}")

    # 汇总结果
    print("\n" + "=" * 70)
    print("搜索完成")
    print("=" * 70)

    # 获取所有有效试验
    valid_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]

    # 过滤满足硬约束的试验
    feasible_trials = []
    for t in valid_trials:
        pnl_2024 = t.user_attrs.get("pnl_2024", -1e9)
        pnl_2025 = t.user_attrs.get("pnl_2025", -1e9)
        max_dd_2024 = t.user_attrs.get("max_dd_2024", 1.0)
        max_dd_2025 = t.user_attrs.get("max_dd_2025", 1.0)

        if pnl_2024 > 0 and pnl_2025 > 0 and max_dd_2024 < 0.30 and max_dd_2025 < 0.30:
            feasible_trials.append(t)

    print(f"\n有效试验: {len(valid_trials)}/{N_TRIALS}")
    print(f"可行试验（满足硬约束）: {len(feasible_trials)}/{len(valid_trials)}")

    if not feasible_trials:
        print("\n无可行解！所有试验均违反硬约束。")
        print("建议：放宽搜索空间或调整硬约束。")
        await repo.close()
        return

    # 排序
    feasible_trials.sort(key=lambda t: t.value, reverse=True)

    # Best params
    best = feasible_trials[0]
    print("\n" + "=" * 70)
    print("Best Params")
    print("=" * 70)
    print(f"  ema_period:       {best.params['ema_period']}")
    print(f"  max_atr_ratio:    {best.params['max_atr_ratio']:.4f}")
    print(f"  min_distance_pct: {best.params['min_distance_pct']:.4f}")
    print(f"  score:            {best.value:+.2f}")
    print(f"\n  2024:")
    print(f"    pnl:     {best.user_attrs['pnl_2024']:+.2f}")
    print(f"    sharpe:  {best.user_attrs['sharpe_2024']:.4f}")
    print(f"    max_dd:  {best.user_attrs['max_dd_2024']:.2%}")
    print(f"    trades:  {best.user_attrs['trades_2024']}")
    print(f"  2025:")
    print(f"    pnl:     {best.user_attrs['pnl_2025']:+.2f}")
    print(f"    sharpe:  {best.user_attrs['sharpe_2025']:.4f}")
    print(f"    max_dd:  {best.user_attrs['max_dd_2025']:.2%}")
    print(f"    trades:  {best.user_attrs['trades_2025']}")

    # Top 10
    print("\n" + "=" * 70)
    print("Top 10 参数组合")
    print("=" * 70)
    print(f"{'rank':<5} {'ema':>5} {'atr':>7} {'dist':>7} {'pnl24':>10} {'pnl25':>10} {'sh24':>8} {'sh25':>8} {'dd24':>7} {'dd25':>7} {'tr24':>5} {'tr25':>5}")
    print("-" * 100)

    for i, t in enumerate(feasible_trials[:10], 1):
        p = t.params
        a = t.user_attrs
        print(f"{i:<5} {p['ema_period']:>5} {p['max_atr_ratio']:>7.3f} {p['min_distance_pct']:>7.3f} "
              f"{a['pnl_2024']:>+10.2f} {a['pnl_2025']:>+10.2f} "
              f"{a['sharpe_2024']:>8.4f} {a['sharpe_2025']:>8.4f} "
              f"{a['max_dd_2024']:>7.2%} {a['max_dd_2025']:>7.2%} "
              f"{a['trades_2024']:>5} {a['trades_2025']:>5}")

    # 参数敏感性分析
    print("\n" + "=" * 70)
    print("参数敏感性分析")
    print("=" * 70)

    top10 = feasible_trials[:10]

    # ema_period 分布
    ema_vals = [t.params['ema_period'] for t in top10]
    ema_min, ema_max = min(ema_vals), max(ema_vals)
    ema_counts = {}
    for v in ema_vals:
        ema_counts[v] = ema_counts.get(v, 0) + 1
    print(f"\nema_period 分布 (Top 10):")
    for v in sorted(ema_counts.keys()):
        bar = "*" * ema_counts[v]
        print(f"  {v:>3}: {bar} ({ema_counts[v]})")
    if ema_max <= 110:
        print("  => 偏向低值区 [90-110]，建议继续向下探索")
    elif ema_min >= 130:
        print("  => 偏向高值区 [130-150]，建议继续向上探索")
    else:
        print("  => 分布较散，当前基线 111 落在稳定区")

    # max_atr_ratio 分布
    atr_vals = [t.params['max_atr_ratio'] for t in top10]
    atr_min, atr_max = min(atr_vals), max(atr_vals)
    atr_counts = {}
    for v in atr_vals:
        key = round(v, 3)
        atr_counts[key] = atr_counts.get(key, 0) + 1
    print(f"\nmax_atr_ratio 分布 (Top 10):")
    for v in sorted(atr_counts.keys()):
        bar = "*" * atr_counts[v]
        print(f"  {v:.3f}: {bar} ({atr_counts[v]})")
    if atr_max <= 0.005:
        print("  => 偏向低值区 [0.004-0.005]，建议继续向下探索")
    elif atr_min >= 0.007:
        print("  => 偏向高值区 [0.007-0.008]，建议继续向上探索")
    else:
        print("  => 分布较散，当前基线 0.0059 落在稳定区")

    # min_distance_pct 分布
    dist_vals = [t.params['min_distance_pct'] for t in top10]
    dist_min, dist_max = min(dist_vals), max(dist_vals)
    dist_counts = {}
    for v in dist_vals:
        key = round(v, 3)
        dist_counts[key] = dist_counts.get(key, 0) + 1
    print(f"\nmin_distance_pct 分布 (Top 10):")
    for v in sorted(dist_counts.keys()):
        bar = "*" * dist_counts[v]
        print(f"  {v:.3f}: {bar} ({dist_counts[v]})")
    if dist_max <= 0.006:
        print("  => 偏向低值区 [0.005-0.006]，建议继续向下探索")
    elif dist_min >= 0.010:
        print("  => 偏向高值区 [0.010-0.012]，建议继续向上探索")
    else:
        print("  => 分布较散，当前基线 0.008 落在稳定区")

    # 当前基线是否落在稳定区
    print("\n" + "=" * 70)
    print("当前基线检查")
    print("=" * 70)
    baseline_ema = 111
    baseline_atr = 0.0059
    baseline_dist = 0.008

    ema_in_range = ema_min <= baseline_ema <= ema_max
    atr_in_range = atr_min <= baseline_atr <= atr_max
    dist_in_range = dist_min <= baseline_dist <= dist_max

    print(f"\n当前基线: ema={baseline_ema}, atr={baseline_atr:.4f}, dist={baseline_dist:.4f}")
    print(f"  ema_period:       {'在稳定区' if ema_in_range else '不在稳定区'} [{ema_min}, {ema_max}]")
    print(f"  max_atr_ratio:    {'在稳定区' if atr_in_range else '不在稳定区'} [{atr_min:.4f}, {atr_max:.4f}]")
    print(f"  min_distance_pct: {'在稳定区' if dist_in_range else '不在稳定区'} [{dist_min:.4f}, {dist_max:.4f}]")

    if ema_in_range and atr_in_range and dist_in_range:
        print("\n结论: 当前基线落在 Top 10 稳定区，可作为后续搜索起点。")
    else:
        print("\n结论: 当前基线不在 Top 10 稳定区，建议调整基线参数。")

    await repo.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
