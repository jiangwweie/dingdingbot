#!/usr/bin/env python3
"""
TP 参数实验脚本 - 对比不同 TP 目标的回测效果

任务 2.1: 实现参数优化脚本
任务 2.2-2.5: TP 实验 A/B/C/D

实验设计:
- A（基准）: TP=1.5R, tp_levels=1, tp_ratios=[1.0]
- B: TP=1.2R, tp_levels=1, tp_ratios=[1.0]
- C: TP=1.0R, tp_levels=1, tp_ratios=[1.0]
- D: TP=1.0R + 2.5R, tp_levels=2, tp_ratios=[0.6, 0.4]

回测范围: BTC/ETH/SOL/BNB × 1h/4h = 8 次回测
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

# 回测配置 - 仅 1h 周期（根据 Task A 要求）
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
TIMEFRAMES = ["1h"]  # 仅 1h

# 时间范围：使用本地完整历史数据（不指定 start_time/end_time，让 backtester 自动获取）
# 默认会获取所有可用数据

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
    "C": {
        "name": "激进 (TP=1.0R)",
        "tp_levels": 1,
        "tp_ratios": ["1.0"],
        "tp_targets": ["1.0"],
    },
    "D": {
        "name": "部分止盈 (TP1=1.0R, TP2=2.5R)",
        "tp_levels": 2,
        "tp_ratios": ["0.6", "0.4"],
        "tp_targets": ["1.0", "2.5"],
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
    max_drawdown: float
    sharpe_ratio: Optional[float]
    tp1_count: int
    tp2_count: int
    sl_count: int


async def run_single_backtest(
    symbol: str,
    timeframe: str,
    tp_config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    运行单次回测

    由于我们没有直接调用 API 的能力，这里直接调用 Backtester
    """
    from src.application.backtester import Backtester
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.backtest_repository import BacktestReportRepository
    from src.infrastructure.order_repository import OrderRepository
    from src.infrastructure.exchange_gateway import ExchangeGateway

    # 创建 Mock Gateway（不初始化，回测使用本地数据）
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=True,
    )
    # 注意：不调用 await gateway.initialize()，因为回测使用本地数据

    # 初始化 repositories
    data_repo = HistoricalDataRepository()
    await data_repo.initialize()

    backtest_repo = BacktestReportRepository()
    await backtest_repo.initialize()

    order_repo = OrderRepository()
    await order_repo.initialize()

    try:
        backtester = Backtester(gateway, data_repository=data_repo)

        # 构建请求（不指定时间范围，使用所有本地数据）
        # 生成唯一的 strategy_id（包含实验ID、币种、周期）
        exp_id = f"{tp_config['tp_levels']}_{tp_config['tp_targets'][0]}"
        safe_symbol = symbol.replace('/', '_').replace(':', '_')
        strategy_id = f"tp_exp_{exp_id}_{safe_symbol}_{timeframe}"

        request = {
            "symbol": symbol,
            "timeframe": timeframe,
            "mode": "v3_pms",
            "limit": 1000,  # 获取更多 K 线
            "initial_balance": "10000",
            "slippage_rate": "0.001",
            "fee_rate": "0.0004",
            "order_strategy": {
                "id": strategy_id,
                "name": tp_config["name"],
                "tp_levels": tp_config["tp_levels"],
                "tp_ratios": tp_config["tp_ratios"],
                "tp_targets": tp_config["tp_targets"],
                "trailing_stop_enabled": True,
                "oco_enabled": True,
            },
        }

        # 导入 BacktestRequest
        from src.domain.models import BacktestRequest
        backtest_request = BacktestRequest(**request)

        # 运行回测（不保存到数据库，避免 UNIQUE 约束冲突）
        report = await backtester.run_backtest(
            backtest_request,
            account_snapshot=None,
            repository=None,
            backtest_repository=None,  # 不保存到数据库
            order_repository=order_repo,
        )

        return report.model_dump()

    except Exception as e:
        print(f"  ❌ 回测失败: {e}")
        return None
    finally:
        # gateway 未初始化，无需关闭
        await data_repo.close()
        await backtest_repo.close()
        await order_repo.close()


def extract_metrics(report: Dict[str, Any], experiment: str, symbol: str, timeframe: str) -> Optional[ExperimentResult]:
    """从回测报告中提取关键指标"""
    if not report:
        return None

    positions = report.get("positions", [])
    if not positions:
        return None

    total_trades = report.get("total_trades", 0)
    winning_trades = report.get("winning_trades", 0)
    win_rate = report.get("win_rate", "0")

    total_pnl = float(report.get("total_pnl", "0"))
    max_drawdown = float(report.get("max_drawdown", "0"))
    sharpe_ratio = report.get("sharpe_ratio")

    # 统计出场类型
    tp1_count = 0
    tp2_count = 0
    sl_count = 0

    for pos in positions:
        exit_reason = pos.get("exit_reason", "")
        if exit_reason == "TP1":
            tp1_count += 1
        elif exit_reason == "TP2":
            tp2_count += 1
        elif exit_reason == "SL":
            sl_count += 1

    # 也检查 close_events
    close_events = report.get("close_events", [])
    for event in close_events:
        event_type = event.get("event_type", "")
        if event_type == "TP1":
            tp1_count += 1
        elif event_type == "TP2":
            tp2_count += 1
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
        max_drawdown=max_drawdown,
        sharpe_ratio=float(sharpe_ratio) if sharpe_ratio else None,
        tp1_count=tp1_count,
        tp2_count=tp2_count,
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
                        print(f"✅ {result.total_trades} trades, {result.win_rate:.1%} win rate, {result.total_pnl:.2f} PnL")
                    else:
                        print("⚠️ 无交易")
                else:
                    print("❌ 失败")

    return results


def analyze_results(results: List[ExperimentResult]) -> Dict[str, Any]:
    """分析实验结果"""
    # 按实验分组
    by_experiment = defaultdict(list)
    for r in results:
        by_experiment[r.experiment].append(r)

    # 计算每个实验的汇总指标
    summary = {}
    for exp_id, exp_results in by_experiment.items():
        total_trades = sum(r.total_trades for r in exp_results)
        total_wins = sum(r.winning_trades for r in exp_results)
        total_pnl = sum(r.total_pnl for r in exp_results)
        total_tp1 = sum(r.tp1_count for r in exp_results)
        total_tp2 = sum(r.tp2_count for r in exp_results)
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
            "tp2_count": total_tp2,
            "sl_count": total_sl,
            "tp_trigger_rate": (total_tp1 + total_tp2) / total_trades if total_trades > 0 else 0,
        }

    return summary


def print_summary(summary: Dict[str, Any]):
    """打印汇总结果"""
    print("\n" + "=" * 80)
    print("实验结果汇总")
    print("=" * 80)

    print(f"\n{'实验':<8} {'名称':<30} {'交易数':>8} {'胜率':>8} {'总PnL':>12} {'单笔PnL':>10} {'TP触发率':>10}")
    print("-" * 80)

    for exp_id in ["A", "B", "C", "D"]:
        if exp_id in summary:
            s = summary[exp_id]
            print(f"{exp_id:<8} {s['name']:<30} {s['total_trades']:>8} "
                  f"{s['win_rate']:>7.1%} {s['total_pnl']:>12.2f} "
                  f"{s['avg_pnl_per_trade']:>10.2f} {s['tp_trigger_rate']:>9.1%}")

    print("\n" + "-" * 80)
    print("出场类型统计:")
    print(f"{'实验':<8} {'TP1':>8} {'TP2':>8} {'SL':>8}")
    print("-" * 40)
    for exp_id in ["A", "B", "C", "D"]:
        if exp_id in summary:
            s = summary[exp_id]
            print(f"{exp_id:<8} {s['tp1_count']:>8} {s['tp2_count']:>8} {s['sl_count']:>8}")

    # 找出最优配置
    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)

    best_by_pnl = max(summary.items(), key=lambda x: x[1]["total_pnl"])
    best_by_winrate = max(summary.items(), key=lambda x: x[1]["win_rate"])
    best_by_ev = max(summary.items(), key=lambda x: x[1]["avg_pnl_per_trade"])

    print(f"\n最高总收益: 实验 {best_by_pnl[0]} ({best_by_pnl[1]['name']}) = {best_by_pnl[1]['total_pnl']:.2f}")
    print(f"最高胜率: 实验 {best_by_winrate[0]} ({best_by_winrate[1]['name']}) = {best_by_winrate[1]['win_rate']:.1%}")
    print(f"最高单笔期望: 实验 {best_by_ev[0]} ({best_by_ev[1]['name']}) = {best_by_ev[1]['avg_pnl_per_trade']:.2f}")


def save_results(results: List[ExperimentResult], summary: Dict[str, Any]):
    """保存结果到文件"""
    import os

    # 创建输出目录
    os.makedirs("docs/diagnostic-reports", exist_ok=True)

    # 保存详细结果
    results_json = [
        {
            "experiment": r.experiment,
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "total_trades": r.total_trades,
            "winning_trades": r.winning_trades,
            "win_rate": float(r.win_rate),
            "total_pnl": float(r.total_pnl),
            "avg_pnl": float(r.avg_pnl),
            "max_drawdown": float(r.max_drawdown),
            "sharpe_ratio": float(r.sharpe_ratio) if r.sharpe_ratio else None,
            "tp1_count": r.tp1_count,
            "tp2_count": r.tp2_count,
            "sl_count": r.sl_count,
        }
        for r in results
    ]

    # 转换 summary 中的 Decimal
    summary_json = {}
    for exp_id, s in summary.items():
        summary_json[exp_id] = {
            "name": s["name"],
            "total_trades": s["total_trades"],
            "total_wins": s["total_wins"],
            "win_rate": float(s["win_rate"]),
            "total_pnl": float(s["total_pnl"]),
            "avg_pnl_per_trade": float(s["avg_pnl_per_trade"]),
            "tp1_count": s["tp1_count"],
            "tp2_count": s["tp2_count"],
            "sl_count": s["sl_count"],
            "tp_trigger_rate": float(s["tp_trigger_rate"]),
        }

    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiments": TP_EXPERIMENTS,
        "summary": summary_json,
        "details": results_json,
    }

    with open("docs/diagnostic-reports/DA-20260419-002-tp-experiment-results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n结果已保存到: docs/diagnostic-reports/DA-20260419-002-tp-experiment-results.json")


async def main():
    """主函数"""
    print("=" * 60)
    print("TP 参数实验脚本")
    print("=" * 60)
    print(f"\n实验配置:")
    for exp_id, exp_config in TP_EXPERIMENTS.items():
        print(f"  {exp_id}: {exp_config['name']}")
        print(f"      tp_levels={exp_config['tp_levels']}, tp_targets={exp_config['tp_targets']}")

    print(f"\n回测范围:")
    print(f"  币种: {', '.join(SYMBOLS)}")
    print(f"  周期: {', '.join(TIMEFRAMES)}")
    print(f"  时间: 最近 3 年")

    # 运行实验
    results = await run_all_experiments()

    if not results:
        print("\n⚠️ 无有效结果")
        return

    # 分析结果
    summary = analyze_results(results)

    # 打印汇总
    print_summary(summary)

    # 保存结果
    save_results(results, summary)


if __name__ == "__main__":
    asyncio.run(main())
