#!/usr/bin/env python3
"""
ATR 过滤器影响验证

对比两组回测：
1. 不含 ATR（pinbar + ema + mtf）
2. 含 ATR（pinbar + ema + atr + mtf）

使用 DynamicStrategyRunner 路径
"""

import asyncio
import json
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, List

DB_PATH = "data/v3_dev.db"
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
TIMEFRAME = "1h"

ORDER_STRATEGY = {
    "id": "dual_tp_experiment",
    "name": "Dual TP Experiment",
    "tp_levels": 2,
    "tp_ratios": [0.6, 0.4],
    "tp_targets": [1.0, 2.5],
    "initial_stop_loss_rr": -1.0,
    "trailing_stop_enabled": True,
    "oco_enabled": True
}


def build_strategy_config(include_atr: bool, min_distance_pct: float = 0.005) -> List[Dict[str, Any]]:
    """构建策略配置"""
    filters = [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": min_distance_pct}},
        {"type": "mtf", "enabled": True, "params": {}},
    ]
    if include_atr:
        filters.append({"type": "atr", "enabled": True, "params": {}})

    return [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": filters
    }]


async def run_backtest(symbol: str, include_atr: bool) -> Dict[str, Any]:
    """运行单个回测"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    request = BacktestRequest(
        symbol=symbol,
        timeframe=TIMEFRAME,
        limit=1000,
        strategies=build_strategy_config(include_atr),
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
    )

    report = await backtester.run_backtest(request)
    await repo.close()

    return {
        "symbol": symbol,
        "trades": report.total_trades,
        "win_rate": report.win_rate,
        "total_pnl": float(report.total_pnl),
        "avg_pnl": float(report.total_pnl / report.total_trades) if report.total_trades > 0 else 0,
    }


async def main():
    print("=" * 60)
    print("ATR 过滤器影响验证")
    print("=" * 60)
    print()
    print(f"币种：{', '.join(SYMBOLS)}")
    print(f"周期：{TIMEFRAME}")
    print(f"双 TP：TP1=1.0R (60%), TP2=2.5R (40%)")
    print(f"EMA 距离：0.5%")
    print()
    print("=" * 60)

    results = []

    experiments = [
        ("不含 ATR", False),
        ("含 ATR", True),
    ]

    for exp_name, include_atr in experiments:
        print(f"\n【{exp_name}】")
        print("-" * 60)

        exp_results = []

        for symbol in SYMBOLS:
            print(f"  {symbol}...", end=" ", flush=True)
            try:
                result = await run_backtest(symbol, include_atr)
                exp_results.append(result)
                print(f"✅ {result['trades']} trades, {result['win_rate']:.1%} win, {result['total_pnl']:.2f} PnL")
            except Exception as e:
                import traceback
                print(f"❌ Error: {e}")
                traceback.print_exc()
                exp_results.append({
                    "symbol": symbol,
                    "trades": 0,
                    "win_rate": 0,
                    "total_pnl": 0,
                    "avg_pnl": 0,
                })

        total_trades = sum(r["trades"] for r in exp_results)
        total_pnl = sum(r["total_pnl"] for r in exp_results)
        avg_win_rate = sum(r["win_rate"] for r in exp_results) / len(exp_results) if exp_results else 0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

        results.append({
            "name": exp_name,
            "include_atr": include_atr,
            "total_trades": total_trades,
            "avg_win_rate": avg_win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "details": exp_results,
        })

        print(f"\n  汇总：{total_trades} trades, {avg_win_rate:.1%} win, {total_pnl:.2f} PnL, {avg_pnl:.2f} avg")

    print("\n")
    print("=" * 60)
    print("对比结果")
    print("=" * 60)
    print()
    print(f"| 实验 | 交易数 | 胜率 | 总PnL | 单笔PnL |")
    print(f"|------|--------|------|--------|----------|")
    for r in results:
        print(f"| {r['name']} | {r['total_trades']} | {r['avg_win_rate']:.1%} | {r['total_pnl']:.2f} | {r['avg_pnl']:.2f} |")

    if len(results) == 2:
        baseline = results[0]
        with_atr = results[1]
        signals_filtered = baseline["total_trades"] - with_atr["total_trades"]
        pnl_diff = with_atr["total_pnl"] - baseline["total_pnl"]

        print()
        print(f"ATR 过滤信号数：{signals_filtered}")
        print(f"PnL 差异：{pnl_diff:+.2f} USDT")

        if signals_filtered > 0:
            pnl_per_filtered = pnl_diff / signals_filtered
            print(f"每个被过滤信号的 PnL 影响：{pnl_per_filtered:+.2f} USDT")

    output_file = f"docs/diagnostic-reports/DA-{datetime.now().strftime('%Y%m%d')}-004-atr-filter-impact.json"
    with open(output_file, "w") as f:
        def convert_decimals(obj):
            if isinstance(obj, dict):
                return {k: convert_decimals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_decimals(v) for v in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            else:
                return obj
        json.dump(convert_decimals(results), f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存到：{output_file}")


if __name__ == "__main__":
    asyncio.run(main())
