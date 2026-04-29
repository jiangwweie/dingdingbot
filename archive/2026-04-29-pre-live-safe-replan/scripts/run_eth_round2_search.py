#!/usr/bin/env python3
"""
ETH 1h 二轮确认性小搜索

目标：验证上一轮结论是否稳定复现，给出可冻结的新基线参数。

固定不变（强先验）：
- direction = LONG-only
- breakeven_enabled = False
- tp_ratios = [0.5, 0.5]
- tp_targets = [1.0, 3.5]
- mode = v3_pms
- cost_mode = stress

二轮搜索空间（更窄）：
- ema_period: [110, 120, 130]
- max_atr_ratio: [0.005, 0.006, 0.007, 0.008]
- min_distance_pct: [0.007, 0.008]
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import optuna

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides

# 固定配置
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
W2024_START = 1704067200000
W2024_END = 1735689599000
W2025_START = 1735689600000
W2025_END = 1767225599000

# 二轮搜索空间（更窄）
EMA_PERIOD_CHOICES = [110, 120, 130]
MAX_ATR_RATIO_CHOICES = [0.005, 0.006, 0.007, 0.008]
MIN_DISTANCE_PCT_CHOICES = [0.007, 0.008]

N_TRIALS = 30

# 上一轮 best params
PREV_BEST = {
    "ema_period": 120,
    "max_atr_ratio": 0.007,
    "min_distance_pct": 0.008,
}


async def run_backtest(
    backtester: Backtester,
    start: int,
    end: int,
    ema_period: int,
    max_atr_ratio: float,
    min_distance_pct: float,
) -> Dict[str, Any]:
    request = BacktestRequest(
        symbol=SYMBOL, timeframe=TIMEFRAME,
        start_time=start, end_time=end,
        mode="v3_pms", initial_balance=INITIAL_BALANCE,
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

    return {
        "pnl": float(result.total_pnl),
        "trades": result.total_trades,
        "win_rate": float(result.win_rate) / 100 if result.win_rate else 0.0,
        "max_dd": float(result.max_drawdown) if result.max_drawdown else 0.0,
        "sharpe": float(result.sharpe_ratio) if result.sharpe_ratio else 0.0,
    }


async def objective(backtester: Backtester, trial: optuna.Trial) -> float:
    ema_period = trial.suggest_categorical("ema_period", EMA_PERIOD_CHOICES)
    max_atr_ratio = trial.suggest_categorical("max_atr_ratio", MAX_ATR_RATIO_CHOICES)
    min_distance_pct = trial.suggest_categorical("min_distance_pct", MIN_DISTANCE_PCT_CHOICES)

    r2024 = await run_backtest(backtester, W2024_START, W2024_END, ema_period, max_atr_ratio, min_distance_pct)
    r2025 = await run_backtest(backtester, W2025_START, W2025_END, ema_period, max_atr_ratio, min_distance_pct)

    trial.set_user_attr("pnl_2024", r2024["pnl"])
    trial.set_user_attr("pnl_2025", r2025["pnl"])
    trial.set_user_attr("sharpe_2024", r2024["sharpe"])
    trial.set_user_attr("sharpe_2025", r2025["sharpe"])
    trial.set_user_attr("max_dd_2024", r2024["max_dd"])
    trial.set_user_attr("max_dd_2025", r2025["max_dd"])
    trial.set_user_attr("trades_2024", r2024["trades"])
    trial.set_user_attr("trades_2025", r2025["trades"])

    # 硬约束
    if r2024["pnl"] <= 0 or r2025["pnl"] <= 0:
        return -1e9
    if r2024["max_dd"] >= 0.30 or r2025["max_dd"] >= 0.30:
        return -1e9

    score = r2024["pnl"] + r2025["pnl"] + 800 * (r2024["sharpe"] + r2025["sharpe"])
    return score


async def main():
    print("=" * 70)
    print("ETH 1h 二轮确认性小搜索")
    print("=" * 70)

    print("\n固定强先验:")
    print(f"  direction:         LONG-only")
    print(f"  breakeven_enabled: {FIXED_PARAMS['breakeven_enabled']}")
    print(f"  tp_ratios:         {FIXED_PARAMS['tp_ratios']}")
    print(f"  tp_targets:        {FIXED_PARAMS['tp_targets']}")
    print(f"  mode:              v3_pms")
    print(f"  cost_mode:         stress")

    print("\n二轮搜索空间（更窄）:")
    print(f"  ema_period:        {EMA_PERIOD_CHOICES}")
    print(f"  max_atr_ratio:     {MAX_ATR_RATIO_CHOICES}")
    print(f"  min_distance_pct:  {MIN_DISTANCE_PCT_CHOICES}")

    print(f"\n预算: {N_TRIALS} trials")
    print(f"\n上一轮 best params: ema={PREV_BEST['ema_period']}, atr={PREV_BEST['max_atr_ratio']}, dist={PREV_BEST['min_distance_pct']}")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    study = optuna.create_study(direction="maximize")

    print("\n" + "=" * 70)
    print(f"开始搜索 ({N_TRIALS} trials)...")
    print("=" * 70)

    for i in range(N_TRIALS):
        trial = study.ask()
        try:
            value = await objective(bt, trial)
            study.tell(trial, value)
            feasible = "✓" if value > -1e8 else "✗"
            print(f"  [{i+1:2d}/{N_TRIALS}] {feasible} score={value:+.2f}  "
                  f"ema={trial.params['ema_period']:3d}  "
                  f"atr={trial.params['max_atr_ratio']:.3f}  "
                  f"dist={trial.params['min_distance_pct']:.3f}")
        except Exception as e:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            print(f"  [{i+1:2d}/{N_TRIALS}] FAILED: {e}")

    print("\n" + "=" * 70)
    print("搜索完成")
    print("=" * 70)

    valid_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
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
        print("\n无可行解！")
        await repo.close()
        return

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
    print(f"{'rank':<5} {'ema':>5} {'atr':>7} {'dist':>7} {'pnl24':>10} {'pnl25':>10} {'sh24':>8} {'sh25':>8} {'dd24':>8} {'dd25':>8}")
    print("-" * 90)

    for i, t in enumerate(feasible_trials[:10], 1):
        p = t.params
        a = t.user_attrs
        print(f"{i:<5} {p['ema_period']:>5} {p['max_atr_ratio']:>7.3f} {p['min_distance_pct']:>7.3f} "
              f"{a['pnl_2024']:>+10.2f} {a['pnl_2025']:>+10.2f} "
              f"{a['sharpe_2024']:>8.4f} {a['sharpe_2025']:>8.4f} "
              f"{a['max_dd_2024']:>8.2%} {a['max_dd_2025']:>8.2%}")

    # 一致性判断
    print("\n" + "=" * 70)
    print("与上一轮一致性判断")
    print("=" * 70)

    top10 = feasible_trials[:10]

    # ema_period 分布
    ema_counts = {}
    for t in top10:
        v = t.params['ema_period']
        ema_counts[v] = ema_counts.get(v, 0) + 1

    print(f"\nema_period 分布 (Top 10):")
    for v in sorted(ema_counts.keys()):
        bar = "*" * ema_counts[v]
        print(f"  {v:>3}: {bar} ({ema_counts[v]})")

    ema_match = best.params['ema_period'] == PREV_BEST['ema_period']
    print(f"  上一轮 best: {PREV_BEST['ema_period']}, 本轮 best: {best.params['ema_period']}")
    print(f"  => {'一致 ✓' if ema_match else '不一致 ✗'}")

    # max_atr_ratio 分布
    atr_counts = {}
    for t in top10:
        v = t.params['max_atr_ratio']
        atr_counts[v] = atr_counts.get(v, 0) + 1

    print(f"\nmax_atr_ratio 分布 (Top 10):")
    for v in sorted(atr_counts.keys()):
        bar = "*" * atr_counts[v]
        print(f"  {v:.3f}: {bar} ({atr_counts[v]})")

    # 检查是否仍不敏感（不同 atr 值但相同 pnl/sharpe）
    atr_sensitivity_check = {}
    for t in top10:
        key = (t.params['ema_period'], t.params['min_distance_pct'])
        if key not in atr_sensitivity_check:
            atr_sensitivity_check[key] = []
        atr_sensitivity_check[key].append({
            'atr': t.params['max_atr_ratio'],
            'pnl_2024': t.user_attrs['pnl_2024'],
            'pnl_2025': t.user_attrs['pnl_2025'],
        })

    atr_insensitive = False
    for key, values in atr_sensitivity_check.items():
        if len(values) > 1:
            pnl24_set = set(round(v['pnl_2024'], 2) for v in values)
            pnl25_set = set(round(v['pnl_2025'], 2) for v in values)
            if len(pnl24_set) == 1 and len(pnl25_set) == 1:
                atr_insensitive = True
                break

    print(f"  => {'仍不敏感（不同 atr 值产生相同 pnl）' if atr_insensitive else '存在敏感性'}")

    # min_distance_pct 分布
    dist_counts = {}
    for t in top10:
        v = t.params['min_distance_pct']
        dist_counts[v] = dist_counts.get(v, 0) + 1

    print(f"\nmin_distance_pct 分布 (Top 10):")
    for v in sorted(dist_counts.keys()):
        bar = "*" * dist_counts[v]
        print(f"  {v:.3f}: {bar} ({dist_counts[v]})")

    dist_match = best.params['min_distance_pct'] == PREV_BEST['min_distance_pct']
    print(f"  上一轮 best: {PREV_BEST['min_distance_pct']}, 本轮 best: {best.params['min_distance_pct']}")
    print(f"  => {'一致 ✓' if dist_match else '不一致 ✗'}")

    # 冻结基线建议
    print("\n" + "=" * 70)
    print("冻结基线建议")
    print("=" * 70)

    # 统计 Top 10 的参数范围
    ema_vals = [t.params['ema_period'] for t in top10]
    atr_vals = [t.params['max_atr_ratio'] for t in top10]
    dist_vals = [t.params['min_distance_pct'] for t in top10]

    print(f"\n推荐冻结值:")
    print(f"  ema_period:       {best.params['ema_period']}")
    print(f"  max_atr_ratio:    {best.params['max_atr_ratio']:.4f}")
    print(f"  min_distance_pct: {best.params['min_distance_pct']:.4f}")

    print(f"\n可接受浮动区间:")
    print(f"  ema_period:       [{min(ema_vals)}, {max(ema_vals)}]")
    print(f"  max_atr_ratio:    [{min(atr_vals):.4f}, {max(atr_vals):.4f}]")
    print(f"  min_distance_pct: [{min(dist_vals):.4f}, {max(dist_vals):.4f}]")

    # 敏感性结论
    print(f"\n参数敏感性结论:")
    if len(set(ema_vals)) == 1:
        print(f"  ema_period: 高度收敛于 {ema_vals[0]}")
    else:
        print(f"  ema_period: 存在波动，但集中在 {min(ema_vals)}-{max(ema_vals)}")

    if atr_insensitive:
        print(f"  max_atr_ratio: 不敏感，可固定为任意值（推荐 0.006）")
    else:
        print(f"  max_atr_ratio: 存在敏感性，建议固定为 {best.params['max_atr_ratio']:.4f}")

    if len(set(dist_vals)) == 1:
        print(f"  min_distance_pct: 高度收敛于 {dist_vals[0]}")
    else:
        print(f"  min_distance_pct: 存在波动，但集中在 {min(dist_vals):.4f}-{max(dist_vals):.4f}")

    # 最终建议
    print(f"\n最终冻结基线:")
    frozen_ema = best.params['ema_period']
    frozen_atr = 0.006 if atr_insensitive else best.params['max_atr_ratio']
    frozen_dist = best.params['min_distance_pct']

    print(f"  ema_period:       {frozen_ema}")
    print(f"  max_atr_ratio:    {frozen_atr:.4f}")
    print(f"  min_distance_pct: {frozen_dist:.4f}")
    print(f"  tp_ratios:        [0.5, 0.5]")
    print(f"  tp_targets:       [1.0, 3.5]")
    print(f"  breakeven_enabled: False")
    print(f"  direction:        LONG-only")

    await repo.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
