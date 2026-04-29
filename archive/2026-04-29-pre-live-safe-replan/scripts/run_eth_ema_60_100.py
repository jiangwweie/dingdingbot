#!/usr/bin/env python3
"""
ETH 1h EMA 60-100 探索搜索

目标：验证 ema_period 在 60-100 区间是否有更优解。

固定不变：
- direction = LONG-only
- breakeven_enabled = False
- tp_ratios = [0.5, 0.5]
- tp_targets = [1.0, 3.5]
- mode = v3_pms
- cost_mode = stress
- max_atr_ratio = 0.006
- min_distance_pct = 0.007

搜索参数：
- ema_period: [60, 70, 80, 90, 100]
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

DB_PATH = "data/v3_dev.db"
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
INITIAL_BALANCE = Decimal("10000")
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")

FIXED_PARAMS = {
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "breakeven_enabled": False,
    "max_atr_ratio": Decimal("0.006"),
    "min_distance_pct": Decimal("0.007"),
}

W2024_START = 1704067200000
W2024_END = 1735689599000
W2025_START = 1735689600000
W2025_END = 1767225599000

EMA_PERIOD_CHOICES = [60, 70, 80, 90, 100]
N_TRIALS = 15  # 5个值，每个跑3次确认


async def run_backtest(backtester, start, end, ema_period):
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
        max_atr_ratio=FIXED_PARAMS["max_atr_ratio"],
        min_distance_pct=FIXED_PARAMS["min_distance_pct"],
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


async def objective(backtester, trial):
    ema_period = trial.suggest_categorical("ema_period", EMA_PERIOD_CHOICES)

    r2024 = await run_backtest(backtester, W2024_START, W2024_END, ema_period)
    r2025 = await run_backtest(backtester, W2025_START, W2025_END, ema_period)

    trial.set_user_attr("pnl_2024", r2024["pnl"])
    trial.set_user_attr("pnl_2025", r2025["pnl"])
    trial.set_user_attr("sharpe_2024", r2024["sharpe"])
    trial.set_user_attr("sharpe_2025", r2025["sharpe"])
    trial.set_user_attr("max_dd_2024", r2024["max_dd"])
    trial.set_user_attr("max_dd_2025", r2025["max_dd"])
    trial.set_user_attr("trades_2024", r2024["trades"])
    trial.set_user_attr("trades_2025", r2025["trades"])

    if r2024["pnl"] <= 0 or r2025["pnl"] <= 0:
        return -1e9
    if r2024["max_dd"] >= 0.30 or r2025["max_dd"] >= 0.30:
        return -1e9

    score = r2024["pnl"] + r2025["pnl"] + 800 * (r2024["sharpe"] + r2025["sharpe"])
    return score


async def main():
    print("=" * 70)
    print("ETH 1h EMA 60-100 探索搜索")
    print("=" * 70)

    print("\n固定参数:")
    print(f"  max_atr_ratio:    {FIXED_PARAMS['max_atr_ratio']}")
    print(f"  min_distance_pct: {FIXED_PARAMS['min_distance_pct']}")
    print(f"  tp_ratios:        {FIXED_PARAMS['tp_ratios']}")
    print(f"  tp_targets:       {FIXED_PARAMS['tp_targets']}")
    print(f"  breakeven_enabled: {FIXED_PARAMS['breakeven_enabled']}")
    print(f"  direction:        LONG-only")

    print(f"\n搜索参数:")
    print(f"  ema_period:       {EMA_PERIOD_CHOICES}")

    print(f"\n预算: {N_TRIALS} trials")

    print("\n初始化...")
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    bt = Backtester(exchange_gateway=None, data_repository=repo)

    study = optuna.create_study(direction="maximize")

    print("\n" + "=" * 70)
    print(f"开始搜索...")
    print("=" * 70)

    for i in range(N_TRIALS):
        trial = study.ask()
        try:
            value = await objective(bt, trial)
            study.tell(trial, value)
            feasible = "✓" if value > -1e8 else "✗"
            a = trial.user_attrs
            print(f"  [{i+1:2d}/{N_TRIALS}] {feasible} ema={trial.params['ema_period']:3d}  "
                  f"pnl24={a['pnl_2024']:+8.2f}  pnl25={a['pnl_2025']:+8.2f}  "
                  f"sh24={a['sharpe_2024']:.4f}  sh25={a['sharpe_2025']:.4f}")
        except Exception as e:
            study.tell(trial, state=optuna.trial.TrialState.FAIL)
            print(f"  [{i+1:2d}/{N_TRIALS}] FAILED: {e}")

    print("\n" + "=" * 70)
    print("结果汇总")
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

    feasible_trials.sort(key=lambda t: t.value, reverse=True)

    # 按 ema_period 去重，保留最佳
    seen_ema = set()
    unique_trials = []
    for t in feasible_trials:
        ema = t.params['ema_period']
        if ema not in seen_ema:
            seen_ema.add(ema)
            unique_trials.append(t)

    print(f"\n{'ema':>5} {'pnl24':>10} {'pnl25':>10} {'sh24':>8} {'sh25':>8} {'dd24':>8} {'dd25':>8} {'tr24':>5} {'tr25':>5}")
    print("-" * 80)

    for t in unique_trials:
        p = t.params
        a = t.user_attrs
        print(f"{p['ema_period']:>5} {a['pnl_2024']:>+10.2f} {a['pnl_2025']:>+10.2f} "
              f"{a['sharpe_2024']:>8.4f} {a['sharpe_2025']:>8.4f} "
              f"{a['max_dd_2024']:>8.2%} {a['max_dd_2025']:>8.2%} "
              f"{a['trades_2024']:>5} {a['trades_2025']:>5}")

    # 与 ema=120 对比
    print("\n" + "=" * 70)
    print("与 ema=120 对比")
    print("=" * 70)

    best_60_100 = unique_trials[0] if unique_trials else None
    if best_60_100:
        print(f"\n60-100 区间最优: ema={best_60_100.params['ema_period']}, score={best_60_100.value:+.2f}")
        print(f"120 区间最优:     ema=120, score=+3854.23 (上一轮)")

        if best_60_100.value > 3854.23:
            print(f"\n结论: ema={best_60_100.params['ema_period']} 优于 ema=120，建议调整冻结基线")
        else:
            print(f"\n结论: ema=120 仍为最优，冻结基线不变")
    else:
        print("\n无可行解")

    await repo.close()
    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
