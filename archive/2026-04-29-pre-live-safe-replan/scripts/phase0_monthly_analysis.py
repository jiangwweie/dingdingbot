#!/usr/bin/env python3
"""
阶段 0: 按币种和月份分析盈亏

输出每个币种的月度交易统计。
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from collections import defaultdict

DB_PATH = "data/v3_dev.db"

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

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]


async def run_backtest_with_positions(symbol: str):
    """运行回测并返回仓位详情"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    request = BacktestRequest(
        symbol=symbol,
        timeframe="1h",
        limit=30000,
        strategies=STRATEGY_CONFIG,
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
    )

    report = await backtester.run_backtest(request)
    await repo.close()

    return report


async def main():
    print("=" * 80)
    print("阶段 0: 按币种和月份分析盈亏")
    print("=" * 80)

    all_results = {}

    for symbol in SYMBOLS:
        print(f"\n处理 {symbol}...")
        report = await run_backtest_with_positions(symbol)

        # 按月份分组
        monthly_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": Decimal("0")})

        for pos in report.positions:
            if pos.exit_time:
                # 从毫秒时间戳提取年月
                dt = datetime.fromtimestamp(pos.exit_time / 1000)
                month_key = dt.strftime("%Y-%m")

                monthly_stats[month_key]["trades"] += 1
                monthly_stats[month_key]["pnl"] += pos.realized_pnl
                if pos.realized_pnl > 0:
                    monthly_stats[month_key]["wins"] += 1

        # 转换为可序列化格式
        monthly_list = []
        for month_key in sorted(monthly_stats.keys()):
            stats = monthly_stats[month_key]
            trades = stats["trades"]
            wins = stats["wins"]
            pnl = float(stats["pnl"])
            win_rate = wins / trades if trades > 0 else 0

            monthly_list.append({
                "month": month_key,
                "trades": trades,
                "wins": wins,
                "pnl": pnl,
                "win_rate": win_rate,
            })

        all_results[symbol] = {
            "total_trades": report.total_trades,
            "total_pnl": float(report.total_pnl),
            "win_rate": float(report.win_rate),
            "monthly": monthly_list,
        }

        print(f"  总计: {report.total_trades} 笔, {report.win_rate:.1%} 胜率, {report.total_pnl:.2f} PnL")

    # 输出汇总表
    print("\n" + "=" * 80)
    print("月度盈亏统计")
    print("=" * 80)

    # 收集所有月份
    all_months = set()
    for symbol, data in all_results.items():
        for m in data["monthly"]:
            all_months.add(m["month"])

    all_months = sorted(all_months)

    # 打印表头
    symbols_short = ["BTC", "ETH", "SOL"]
    header = f"{'月份':<10}" + "".join([f"{s:>15}" for s in symbols_short]) + f"{'合计':>15}"
    print(header)
    print("-" * 70)

    # 按月打印
    total_by_symbol = {s: 0 for s in symbols_short}
    for month in all_months:
        row = f"{month:<10}"
        month_total = 0
        for i, symbol in enumerate(SYMBOLS):
            symbol_short = symbols_short[i]
            month_data = next((m for m in all_results[symbol]["monthly"] if m["month"] == month), None)
            if month_data:
                pnl = month_data["pnl"]
                trades = month_data["trades"]
                win_rate = month_data["win_rate"]
                row += f"{pnl:>10.2f} ({trades:>2})"
                month_total += pnl
                total_by_symbol[symbol_short] += pnl
            else:
                row += f"{'--':>15}"
        row += f"{month_total:>15.2f}"
        print(row)

    # 打印合计
    print("-" * 70)
    total_row = f"{'合计':<10}"
    grand_total = 0
    for symbol_short in symbols_short:
        total_row += f"{total_by_symbol[symbol_short]:>15.2f}"
        grand_total += total_by_symbol[symbol_short]
    total_row += f"{grand_total:>15.2f}"
    print(total_row)

    # 保存详细数据
    output_file = "docs/diagnostic-reports/phase0_monthly_analysis.json"
    with open(output_file, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n详细数据已保存: {output_file}")

    # 按年份汇总
    print("\n" + "=" * 80)
    print("年度盈亏统计")
    print("=" * 80)

    yearly_by_symbol = defaultdict(lambda: defaultdict(lambda: {"trades": 0, "pnl": 0, "wins": 0}))

    for symbol, data in all_results.items():
        for m in data["monthly"]:
            year = m["month"][:4]
            yearly_by_symbol[symbol][year]["trades"] += m["trades"]
            yearly_by_symbol[symbol][year]["pnl"] += m["pnl"]
            yearly_by_symbol[symbol][year]["wins"] += m["wins"]

    # 打印年度表
    years = ["2023", "2024", "2025"]
    header = f"{'年份':<10}" + "".join([f"{s:>15}" for s in symbols_short]) + f"{'合计':>15}"
    print(header)
    print("-" * 70)

    for year in years:
        row = f"{year:<10}"
        year_total = 0
        for i, symbol in enumerate(SYMBOLS):
            year_data = yearly_by_symbol[symbol].get(year, {"trades": 0, "pnl": 0, "wins": 0})
            pnl = year_data["pnl"]
            trades = year_data["trades"]
            row += f"{pnl:>10.2f} ({trades:>3})"
            year_total += pnl
        row += f"{year_total:>15.2f}"
        print(row)

    print("-" * 70)
    total_row = f"{'合计':<10}"
    grand_total = 0
    for i, symbol in enumerate(SYMBOLS):
        symbol_total = sum(yearly_by_symbol[symbol][y]["pnl"] for y in years)
        total_row += f"{symbol_total:>15.2f}"
        grand_total += symbol_total
    total_row += f"{grand_total:>15.2f}"
    print(total_row)


if __name__ == "__main__":
    asyncio.run(main())
