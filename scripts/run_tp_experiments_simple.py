#!/usr/bin/env python3
"""
TP 参数实验脚本 - 简化版（仅对比实验 A vs B）

实验 A: TP=1.5R（当前基准）
实验 B: TP=1.2R（提高触发率）

回测范围: BTC/ETH/SOL × 1h = 3 次回测
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

sys.path.insert(0, '.')

# 回测配置
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TIMEFRAMES = ["1h"]

# TP 实验配置
TP_EXPERIMENTS = {
    "A": {
        "name": "基准 (TP=1.5R)",
        "tp_levels": 1,
        "tp_ratios": ["1.0"],
        "tp_targets": ["1.5"],
    },
    "B": {
        "name": "提高触发率 (TP=1.2R)",
        "tp_levels": 1,
        "tp_ratios": ["1.0"],
        "tp_targets": ["1.2"],
    },
}


@dataclass
class ExperimentResult:
    """实验结果"""
    experiment: str
    symbol: str
    timeframe: str
    total_trades: int
    winning_trades: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    tp1_count: int
    sl_count: int


async def run_single_backtest(
    symbol: str,
    timeframe: str,
    tp_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """运行单次回测"""
    from src.application.backtester import Backtester
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.backtest_repository import BacktestReportRepository
    from src.infrastructure.order_repository import OrderRepository
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.domain.models import BacktestRequest

    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=True,
    )
    await gateway.initialize()

    data_repo = HistoricalDataRepository()
    await data_repo.initialize()

    backtest_repo = BacktestReportRepository()
    await backtest_repo.initialize()

    order_repo = OrderRepository()
    await order_repo.initialize()

    try:
        backtester = Backtester(gateway, data_repository=data_repo)

        request = BacktestRequest(
            symbol=symbol,
            timeframe=timeframe,
            mode="v3_pms",
            limit=1000,  # 获取更多 K 线
            initial_balance="10000",
            slippage_rate="0.001",
            fee_rate="0.0004",
            order_strategy={
                "id": f"tp_exp_{exp_id}_{symbol.replace('/', '_')}_{timeframe}",
                "name": tp_config["name"],
                "tp_levels": tp_config["tp_levels"],
                "tp_ratios": tp_config["tp_ratios"],
                "tp_targets": tp_config["tp_targets"],
                "trailing_stop_enabled": True,
                "oco_enabled": True,
            },
        )

        report = await backtester.run_backtest(
            request,
            account_snapshot=None,
            repository=None,
            backtest_repository=backtest_repo,
            order_repository=order_repo,
        )

        return report.model_dump()

    except Exception as e:
        print(f"  ❌ 回测失败: {e}")
        return None
    finally:
        await gateway.close()
        await data_repo.close()
        await backtest_repo.close()
        await order_repo.close()


def extract_metrics(report: Dict[str, Any], experiment: str, symbol: str, timeframe: str) -> Optional[ExperimentResult]:
    """从回测报告中提取关键指标"""
    if not report:
        return None

    total_trades = report.get("total_trades", 0)
    if total_trades == 0:
        return None

    winning_trades = report.get("winning_trades", 0)
    win_rate = report.get("win_rate", "0")
    total_pnl = float(report.get("total_pnl", "0"))

    # 统计出场类型
    tp1_count = 0
    sl_count = 0

    close_events = report.get("close_events", [])
    for event in close_events:
        event_type = event.get("event_type", "")
        if event_type == "TP1":
            tp1_count += 1
        elif event_type == "SL":
            sl_count += 1

    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

    return ExperimentResult(
        experiment=experiment,
        symbol=symbol,
        timeframe=timeframe,
        total_trades=total_trades,
        winning_trades=winning_trades,
        win_rate=float(win_rate) if isinstance(win_rate, str) else win_rate,
        total_pnl=total_pnl,
        avg_pnl=avg_pnl,
        tp1_count=tp1_count,
        sl_count=sl_count,
    )


async def run_all_experiments() -> List[ExperimentResult]:
    """运行所有实验"""
    results = []

    total_runs = len(TP_EXPERIMENTS) * len(SYMBOLS) * len(TIMEFRAMES)
    current_run = 0

    print(f"\n{'='*60}")
    print(f"TP 参数实验 - 共 {total_runs} 次回测")
    print(f"{'='*60}")

    for exp_id, exp_config in TP_EXPERIMENTS.items():
        print(f"\n[实验 {exp_id}] {exp_config['name']}")

        for symbol in SYMBOLS:
            for timeframe in TIMEFRAMES:
                current_run += 1
                print(f"  [{current_run}/{total_runs}] {symbol} {timeframe}...", end=" ", flush=True)

                report = await run_single_backtest(symbol, timeframe, exp_config)

                if report:
                    result = extract_metrics(report, exp_id, symbol, timeframe)
                    if result:
                        results.append(result)
                        print(f"✅ {result.total_trades} trades, {result.win_rate:.1%} win, {result.total_pnl:.2f} PnL")
                    else:
                        print("⚠️ 无交易")
                else:
                    print("❌ 失败")

    return results


def analyze_results(results: List[ExperimentResult]) -> Dict[str, Any]:
    """分析实验结果"""
    by_experiment = defaultdict(list)
    for r in results:
        by_experiment[r.experiment].append(r)

    summary = {}
    for exp_id, exp_results in by_experiment.items():
        total_trades = sum(r.total_trades for r in exp_results)
        total_wins = sum(r.winning_trades for r in exp_results)
        total_pnl = sum(r.total_pnl for r in exp_results)
        total_tp1 = sum(r.tp1_count for r in exp_results)
        total_sl = sum(r.sl_count for r in exp_results)

        avg_win_rate = total_wins / total_trades if total_trades > 0 else 0
        avg_pnl_per_trade = total_pnl / total_trades if total_trades > 0 else 0

        summary[exp_id] = {
            "name": TP_EXPERIMENTS[exp_id]["name"],
            "total_trades": total_trades,
            "total_wins": total_wins,
            "win_rate": avg_win_rate,
            "total_pnl": total_pnl,
            "avg_pnl_per_trade": avg_pnl_per_trade,
            "tp1_count": total_tp1,
            "sl_count": total_sl,
            "tp_trigger_rate": total_tp1 / total_trades if total_trades > 0 else 0,
        }

    return summary


def print_summary(summary: Dict[str, Any]):
    """打印汇总结果"""
    print("\n" + "=" * 80)
    print("实验结果汇总")
    print("=" * 80)

    print(f"\n{'实验':<8} {'名称':<30} {'交易数':>8} {'胜率':>8} {'总PnL':>12} {'单笔PnL':>10} {'TP触发率':>10}")
    print("-" * 80)

    for exp_id in ["A", "B"]:
        if exp_id in summary:
            s = summary[exp_id]
            print(f"{exp_id:<8} {s['name']:<30} {s['total_trades']:>8} "
                  f"{s['win_rate']:>7.1%} {s['total_pnl']:>12.2f} "
                  f"{s['avg_pnl_per_trade']:>10.2f} {s['tp_trigger_rate']:>9.1%}")

    print("\n" + "-" * 80)
    print("出场类型统计:")
    print(f"{'实验':<8} {'TP1':>8} {'SL':>8}")
    print("-" * 40)
    for exp_id in ["A", "B"]:
        if exp_id in summary:
            s = summary[exp_id]
            print(f"{exp_id:<8} {s['tp1_count']:>8} {s['sl_count']:>8}")

    # 对比分析
    print("\n" + "=" * 80)
    print("对比分析")
    print("=" * 80)

    if "A" in summary and "B" in summary:
        a = summary["A"]
        b = summary["B"]

        pnl_diff = b["total_pnl"] - a["total_pnl"]
        winrate_diff = b["win_rate"] - a["win_rate"]
        tp_rate_diff = b["tp_trigger_rate"] - a["tp_trigger_rate"]

        print(f"\n实验 B vs A:")
        print(f"  总 PnL: {b['total_pnl']:.2f} vs {a['total_pnl']:.2f} = {pnl_diff:+.2f}")
        print(f"  胜率: {b['win_rate']:.1%} vs {a['win_rate']:.1%} = {winrate_diff:+.1%}")
        print(f"  TP 触发率: {b['tp_trigger_rate']:.1%} vs {a['tp_trigger_rate']:.1%} = {tp_rate_diff:+.1%}")

        if pnl_diff > 0:
            print(f"\n✅ 结论: TP=1.2R 优于 TP=1.5R，建议降低 TP 目标")
        else:
            print(f"\n⚠️ 结论: TP=1.5R 优于 TP=1.2R，当前配置更优")


async def main():
    """主函数"""
    print("=" * 60)
    print("TP 参数实验脚本（简化版）")
    print("=" * 60)
    print(f"\n实验配置:")
    for exp_id, exp_config in TP_EXPERIMENTS.items():
        print(f"  {exp_id}: {exp_config['name']}")
        print(f"      tp_targets={exp_config['tp_targets']}")

    print(f"\n回测范围:")
    print(f"  币种: {', '.join(SYMBOLS)}")
    print(f"  周期: {', '.join(TIMEFRAMES)}")

    results = await run_all_experiments()

    if not results:
        print("\n⚠️ 无有效结果")
        return

    summary = analyze_results(results)
    print_summary(summary)


if __name__ == "__main__":
    asyncio.run(main())
