#!/usr/bin/env python3
"""
阶段 0: 3 年基准回测

串行执行，每次一个币种，按时间窗口分批跑（limit 最大 1000）。

用法:
    python scripts/phase0_3year_backtest.py BTC
    python scripts/phase0_3year_backtest.py ETH
    python scripts/phase0_3year_backtest.py SOL
"""

import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal

DB_PATH = "data/v3_dev.db"

# 锁定配置
ORDER_STRATEGY = {
    "id": "locked_dual_tp",
    "name": "Locked Dual TP",
    "tp_levels": 2,
    "tp_ratios": [0.6, 0.4],
    "tp_targets": [1.0, 2.5],
    "initial_stop_loss_rr": -1.0,
    "trailing_stop_enabled": True,
    "oco_enabled": True
}

STRATEGY_CONFIG = [{
    "name": "pinbar",
    "triggers": [{"type": "pinbar", "enabled": True}],
    "filters": [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": 0.005}},
        {"type": "mtf", "enabled": True, "params": {}},
    ]
}]

# 按年份划分
YEAR_CHUNKS = [
    {"name": "2023", "start": "2023-01-01", "end": "2023-12-31"},
    {"name": "2024", "start": "2024-01-01", "end": "2024-12-31"},
    {"name": "2025", "start": "2025-01-01", "end": "2025-04-01"},
]

# 每批 800 小时（约 33 天），留余量
BATCH_HOURS = 800


async def run_batch_backtest(symbol: str, start_ts: int, end_ts: int) -> dict:
    """运行单批次回测（指定精确时间范围）"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    request = BacktestRequest(
        symbol=symbol,
        timeframe="1h",
        limit=1000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=STRATEGY_CONFIG,
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
    )

    report = await backtester.run_backtest(request)
    await repo.close()

    return {
        "trades": report.total_trades,
        "pnl": float(report.total_pnl),
        "wins": int(report.total_trades * report.win_rate),
    }


async def run_year_backtest(symbol: str, year_name: str, start_date: str, end_date: str) -> dict:
    """运行单年份回测（分批请求，精确时间范围）"""
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

    all_trades = 0
    all_pnl = Decimal("0")
    all_wins = 0
    batch_count = 0

    current_ts = start_ts
    while current_ts < end_ts:
        batch_count += 1
        batch_end_ts = min(current_ts + BATCH_HOURS * 60 * 60 * 1000, end_ts)

        try:
            result = await run_batch_backtest(symbol, current_ts, batch_end_ts)
            all_trades += result["trades"]
            all_pnl += Decimal(str(result["pnl"]))
            all_wins += result["wins"]

            if result["trades"] > 0:
                print(f"    批次 {batch_count}: {result['trades']} 笔, PnL: {result['pnl']:.2f}")
            else:
                print(f"    批次 {batch_count}: 无交易")

        except Exception as e:
            print(f"    批次 {batch_count}: 错误 - {e}")

        current_ts = batch_end_ts

    return {
        "year": year_name,
        "trades": all_trades,
        "pnl": float(all_pnl),
        "wins": all_wins,
        "win_rate": all_wins / all_trades if all_trades > 0 else 0,
        "batches": batch_count,
    }


async def run_full_backtest(symbol: str) -> dict:
    """运行完整 3 年回测"""
    print(f"\n{'='*60}")
    print(f"开始回测: {symbol}")
    print(f"{'='*60}")

    results = []
    total_trades = 0
    total_pnl = Decimal("0")
    total_wins = 0

    for chunk in YEAR_CHUNKS:
        print(f"\n处理 {chunk['name']} ({chunk['start']} ~ {chunk['end']})...")
        try:
            year_result = await run_year_backtest(
                symbol, chunk["name"], chunk["start"], chunk["end"]
            )
            results.append(year_result)

            total_trades += year_result["trades"]
            total_pnl += Decimal(str(year_result["pnl"]))
            total_wins += year_result["wins"]

            print(f"  {chunk['name']} 汇总: {year_result['trades']} 笔, "
                  f"PnL: {year_result['pnl']:.2f}, "
                  f"胜率: {year_result['win_rate']:.1%}")

        except Exception as e:
            import traceback
            print(f"  ❌ {chunk['name']} 错误: {e}")
            traceback.print_exc()
            results.append({"year": chunk["name"], "error": str(e)})

    # 汇总
    summary = {
        "symbol": symbol,
        "total_trades": total_trades,
        "total_pnl": float(total_pnl),
        "avg_pnl": float(total_pnl / total_trades) if total_trades > 0 else 0,
        "win_rate": total_wins / total_trades if total_trades > 0 else 0,
        "by_year": results,
    }

    print(f"\n{'='*60}")
    print(f"汇总结果: {symbol}")
    print(f"{'='*60}")
    print(f"总交易数: {summary['total_trades']}")
    print(f"总 PnL: {summary['total_pnl']:.2f}")
    print(f"单笔 PnL: {summary['avg_pnl']:.2f}")
    print(f"总胜率: {summary['win_rate']:.1%}")

    return summary


async def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/phase0_3year_backtest.py <SYMBOL>")
        print("示例: python scripts/phase0_3year_backtest.py BTC")
        sys.exit(1)

    symbol_arg = sys.argv[1].upper()
    symbol_map = {
        "BTC": "BTC/USDT:USDT",
        "ETH": "ETH/USDT:USDT",
        "SOL": "SOL/USDT:USDT",
    }

    if symbol_arg not in symbol_map:
        print(f"错误: 不支持的币种 {symbol_arg}")
        print(f"支持的币种: {', '.join(symbol_map.keys())}")
        sys.exit(1)

    symbol = symbol_map[symbol_arg]

    print("=" * 60)
    print("阶段 0: 3 年基准回测")
    print("=" * 60)
    print(f"币种: {symbol}")
    print(f"周期: 1h")
    print(f"配置: Pinbar + EMA(0.5%) + MTF + 双TP")
    print(f"范围: 2023-01-01 ~ 2025-04-01")
    print("=" * 60)

    try:
        result = await run_full_backtest(symbol)

        # 保存结果
        output_file = f"docs/diagnostic-reports/phase0_{symbol_arg}_3year.json"
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存: {output_file}")

    except Exception as e:
        import traceback
        print(f"\n❌ 错误: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
