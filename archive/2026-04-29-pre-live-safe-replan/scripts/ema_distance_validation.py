#!/usr/bin/env python3
"""
EMA 距离过滤验证实验

对比两组回测：
1. 无距离过滤（min_distance_pct=0，默认）
2. 有距离过滤（min_distance_pct=0.005）

使用真实生产配置：pinbar + ema + atr + mtf
"""

import asyncio
import json
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, List

# 数据库路径
DB_PATH = "data/v3_dev.db"

# 回测参数
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
TIMEFRAME = "1h"
DAYS = 90

# 双 TP 配置
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


def build_strategy_config(min_distance_pct: float) -> List[Dict[str, Any]]:
    """
    构建策略配置

    FilterConfig 格式：
    {
        "type": "ema_trend",
        "enabled": True,
        "params": {"min_distance_pct": 0.005}  # 参数在 params 字典中
    }
    """
    return [{
        "name": "pinbar",
        "triggers": [{"type": "pinbar", "enabled": True}],
        "filters": [
            {
                "type": "ema_trend",
                "enabled": True,
                "params": {"min_distance_pct": min_distance_pct}
            },
            {"type": "atr", "enabled": True, "params": {}},
            {"type": "mtf", "enabled": True, "params": {}}
        ]
    }]


async def run_backtest(symbol: str, min_distance_pct: float) -> Dict[str, Any]:
    """运行单个回测"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy

    # 初始化数据仓库
    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    # 创建回测引擎
    backtester = Backtester(None, data_repository=repo)

    # 构建请求
    request = BacktestRequest(
        symbol=symbol,
        timeframe=TIMEFRAME,
        limit=1000,  # 90 days * 24h = 2160 bars, but limit max 1000
        strategies=build_strategy_config(min_distance_pct),
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
    )

    # 运行回测
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
    """主函数"""
    print("=" * 60)
    print("EMA 距离过滤验证实验")
    print("=" * 60)
    print()
    print(f"回测范围：")
    print(f"  币种：{', '.join(SYMBOLS)}")
    print(f"  周期：{TIMEFRAME}")
    print(f"  天数：~{DAYS} 天（limit=1000 bars）")
    print()
    print(f"策略配置：pinbar + ema_trend + atr + mtf")
    print(f"双 TP：TP1=1.0R (60%), TP2=2.5R (40%)")
    print()
    print("=" * 60)
    print()

    results = []

    # 两组实验
    experiments = [
        ("无距离过滤", 0.0),
        ("有距离过滤 (0.5%)", 0.005),
    ]

    for exp_name, min_dist in experiments:
        print(f"\n【{exp_name}】min_distance_pct = {min_dist}")
        print("-" * 60)

        exp_results = []

        for symbol in SYMBOLS:
            print(f"  {symbol}...", end=" ", flush=True)
            try:
                result = await run_backtest(symbol, min_dist)
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

        # 汇总
        total_trades = sum(r["trades"] for r in exp_results)
        total_pnl = sum(r["total_pnl"] for r in exp_results)
        avg_win_rate = sum(r["win_rate"] for r in exp_results) / len(exp_results) if exp_results else 0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0

        results.append({
            "name": exp_name,
            "min_distance_pct": min_dist,
            "total_trades": total_trades,
            "avg_win_rate": avg_win_rate,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "details": exp_results,
        })

        print(f"\n  汇总：{total_trades} trades, {avg_win_rate:.1%} win, {total_pnl:.2f} PnL, {avg_pnl:.2f} avg")

    # 输出对比表
    print("\n")
    print("=" * 60)
    print("对比结果")
    print("=" * 60)
    print()
    print(f"| 实验 | min_distance | 交易数 | 胜率 | 总PnL | 单笔PnL |")
    print(f"|------|-------------|--------|------|--------|----------|")
    for r in results:
        print(f"| {r['name']} | {r['min_distance_pct']} | {r['total_trades']} | {r['avg_win_rate']:.1%} | {r['total_pnl']:.2f} | {r['avg_pnl']:.2f} |")

    # 计算改善
    if len(results) == 2:
        baseline = results[0]
        filtered = results[1]
        signals_filtered = baseline["total_trades"] - filtered["total_trades"]
        pnl_diff = filtered["total_pnl"] - baseline["total_pnl"]

        print()
        if baseline["total_trades"] > 0:
            print(f"信号过滤数：{signals_filtered} ({signals_filtered / baseline['total_trades'] * 100:.1f}%)")
        else:
            print(f"信号过滤数：{signals_filtered}")
        print(f"PnL 改善：{pnl_diff:+.2f} USDT")

    # 保存结果
    output_file = f"docs/diagnostic-reports/DA-{datetime.now().strftime('%Y%m%d')}-003-ema-distance-validation.json"
    with open(output_file, "w") as f:
        # 转换 Decimal 为 float
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
