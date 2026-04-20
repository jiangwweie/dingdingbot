#!/usr/bin/env python3
"""
P0 + P1 验证脚本

P0: 统计当前双 TP 策略的 TP1/TP2/SL 实际成交比例
P1: 试验单 TP 策略：TP=1.5R，100% 仓位，对比盈亏

用法:
    python3 scripts/validate_p0_p1.py
"""

import asyncio
import json
import sqlite3
import sys
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TIMEFRAME = "1h"
YEAR_CHUNKS = [
    {"name": "2023", "start": "2023-01-01", "end": "2024-01-01"},
    {"name": "2024", "start": "2024-01-01", "end": "2025-01-01"},
]

STRATEGY_CONFIG = [{
    "name": "pinbar",
    "triggers": [{"type": "pinbar", "enabled": True}],
    "filters": [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": 0.005}},
        {"type": "mtf", "enabled": True, "params": {}},
    ],
}]


async def run_backtest_with_config(
    order_strategy_dict: Dict,
    experiment_label: str,
) -> Dict[str, Any]:
    """运行回测并收集 close_events 统计"""
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy
    from src.application.config_manager import ConfigManager

    # 初始化 ConfigManager（确保 KV 配置可用）
    config_manager = ConfigManager(DB_PATH)
    await config_manager.initialize_from_db()
    config_entry_repo = ConfigEntryRepository(DB_PATH)
    await config_entry_repo.initialize()
    config_manager.set_config_entry_repository(config_entry_repo)
    ConfigManager.set_instance(config_manager)

    # 确保 TTP 关闭
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    updated_at = int(datetime.now().timestamp() * 1000)
    for key, val, typ in [
        ("backtest.tp_trailing_enabled", "false", "boolean"),
        ("backtest.trailing_exit_enabled", "false", "boolean"),
    ]:
        cursor.execute(
            "INSERT OR REPLACE INTO config_entries_v2 (config_key, config_value, value_type, version, updated_at, profile_name) VALUES (?,?,?,?,?,?)",
            (key, val, typ, "v1.0.0", updated_at, "default")
        )
    conn.commit()
    conn.close()

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()
    backtester = Backtester(None, data_repository=repo)

    all_close_events = []
    all_positions = []

    for symbol in SYMBOLS:
        print(f"\n  [{experiment_label}] 处理 {symbol}...")
        for chunk in YEAR_CHUNKS:
            start_ts = int(datetime.strptime(chunk["start"], "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(chunk["end"], "%Y-%m-%d").timestamp() * 1000)

            request = BacktestRequest(
                symbol=symbol,
                timeframe=TIMEFRAME,
                limit=30000,
                start_time=start_ts,
                end_time=end_ts,
                strategies=STRATEGY_CONFIG,
                order_strategy=OrderStrategy(**order_strategy_dict),
                mode="v3_pms",
            )

            report = await backtester.run_backtest(request)

            # 收集 close_events
            if hasattr(report, 'close_events') and report.close_events:
                all_close_events.extend(report.close_events)
            if hasattr(report, 'positions') and report.positions:
                all_positions.extend(report.positions)

            print(
                f"    {chunk['name']}: {report.total_trades} 笔, "
                f"PnL: {report.total_pnl:.2f}, "
                f"WinRate: {report.win_rate:.1%}"
            )

    await repo.close()

    # 统计 TP1/TP2/SL/Trailing Exit 分布
    exit_stats: Dict[str, int] = {}
    for event in all_close_events:
        reason = event.exit_reason or event.event_type
        exit_stats[reason] = exit_stats.get(reason, 0) + 1

    return {
        "exit_stats": exit_stats,
        "total_events": len(all_close_events),
    }


async def main():
    print("=" * 70)
    print("P0 + P1 验证")
    print("=" * 70)

    # ── 基线：双 TP (1.0R / 2.5R) ──
    print("\n>>> 基线：双 TP (TP1=1.0R 60%, TP2=2.5R 40%) <<<")
    baseline_strategy = {
        "id": "baseline_dual_tp",
        "name": "Baseline Dual TP",
        "tp_levels": 2,
        "tp_ratios": [0.6, 0.4],
        "tp_targets": [1.0, 2.5],
        "initial_stop_loss_rr": -1.0,
        "trailing_stop_enabled": True,
        "oco_enabled": True,
    }
    baseline_result = await run_backtest_with_config(baseline_strategy, "基线")

    # ── P1：单 TP=1.5R ──
    print("\n>>> P1：单 TP=1.5R 100% 仓位 <<<")
    single_tp_strategy = {
        "id": "single_tp_1_5r",
        "name": "Single TP 1.5R",
        "tp_levels": 1,
        "tp_ratios": [1.0],
        "tp_targets": [1.5],
        "initial_stop_loss_rr": -1.0,
        "trailing_stop_enabled": True,
        "oco_enabled": True,
    }
    single_tp_result = await run_backtest_with_config(single_tp_strategy, "P1")

    # ── 输出对比 ──
    print("\n" + "=" * 70)
    print("P0: 平仓原因分布对比")
    print("=" * 70)

    all_reasons = sorted(set(
        list(baseline_result["exit_stats"].keys()) + list(single_tp_result["exit_stats"].keys())
    ))

    print(f"\n{'原因':<20} {'基线 (双TP)':<20} {'P1 (单TP 1.5R)':<20} {'占比-基线':<12} {'占比-P1':<12}")
    print("-" * 84)

    b_total = baseline_result["total_events"]
    s_total = single_tp_result["total_events"]

    for reason in all_reasons:
        b_count = baseline_result["exit_stats"].get(reason, 0)
        s_count = single_tp_result["exit_stats"].get(reason, 0)
        b_pct = f"{b_count/b_total:.1%}" if b_total > 0 else "N/A"
        s_pct = f"{s_count/s_total:.1%}" if s_total > 0 else "N/A"
        print(f"{reason:<20} {b_count:<20} {s_count:<20} {b_pct:<12} {s_pct:<12}")

    print(f"\n{'总计':<20} {b_total:<20} {s_total:<20}")

    # 保存结果
    output = {
        "baseline": baseline_result,
        "p1_single_tp": single_tp_result,
        "timestamp": datetime.now().isoformat(),
    }
    output_file = "docs/diagnostic-reports/p0_p1_validation.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    class DecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return super().default(obj)

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, cls=DecimalEncoder)

    print(f"\n结果已保存: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
