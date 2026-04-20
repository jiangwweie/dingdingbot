#!/usr/bin/env python3
"""
Trailing Exit 回测验证脚本 (ADR-2026-04-20)

对比实验：
- 实验 A: trailing_exit_enabled=False（当前方案，无追踪退出）
- 实验 B: trailing_exit_enabled=True（追踪退出机制）

使用 BTC/ETH/SOL 三种币，1h 周期，2 年数据（2023-01-01 ~ 2025-01-01）

用法:
    python scripts/validate_trailing_exit.py

输出:
    - 总体指标对比表（总交易数、胜率、总 PnL、单笔 PnL）
    - 分币种对比表
    - 追踪退出事件统计（激活次数、退出次数）
    - 决策门判断（PnL 提升 > 10% -> 有效）
"""

import asyncio
import json
import sqlite3
import sys
import os
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Any, Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 数据库路径
DB_PATH = "data/v3_dev.db"

# 回测范围
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]
TIMEFRAME = "1h"

# 按年份划分（2022 年数据缺失，仅跑 2023-2025）
YEAR_CHUNKS = [
    # {"name": "2022", "start": "2022-01-01", "end": "2023-01-01"},  # 数据缺失
    {"name": "2023", "start": "2023-01-01", "end": "2024-01-01"},
    {"name": "2024", "start": "2024-01-01", "end": "2025-01-01"},
]

# 锁定配置（Pinbar + EMA + MTF + 双 TP）
ORDER_STRATEGY = {
    "id": "trailing_exit_validation",
    "name": "Trailing Exit Validation Dual TP",
    "tp_levels": 2,
    "tp_ratios": [0.6, 0.4],
    "tp_targets": [1.0, 2.5],
    "initial_stop_loss_rr": -1.0,
    "trailing_stop_enabled": True,
    "oco_enabled": True,
}

STRATEGY_CONFIG = [{
    "name": "pinbar",
    "triggers": [{"type": "pinbar", "enabled": True}],
    "filters": [
        {"type": "ema_trend", "enabled": True, "params": {"min_distance_pct": 0.005}},
        {"type": "mtf", "enabled": True, "params": {}},
    ],
}]

# Trailing Exit 参数（ADR-2026-04-20 推荐）
TRAILING_EXIT_PARAMS = {
    "trailing_exit_enabled": True,
    "trailing_exit_percent": "0.015",             # 1.5% 回撤容忍
    "trailing_exit_activation_rr": "0.3",         # 0.3R 激活
    "trailing_exit_slippage_rate": "0.001",        # 0.1% 滑点
}


async def set_trailing_exit_config(enabled: bool) -> None:
    """
    设置 Trailing Exit 配置到数据库

    通过 config_entries_v2 表设置 KV 配置，使用 backtest. 前缀。
    同时确保 TTP 配置关闭，避免两个追踪机制互相干扰。

    Args:
        enabled: 是否启用 Trailing Exit
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    profile_name = "default"
    version = "v1.0.0"
    updated_at = int(datetime.now().timestamp() * 1000)

    # Trailing Exit 配置项（使用 backtest. 前缀）
    configs = [
        ("backtest.trailing_exit_enabled", "true" if enabled else "false", "boolean"),
        ("backtest.trailing_exit_percent", TRAILING_EXIT_PARAMS["trailing_exit_percent"], "decimal"),
        ("backtest.trailing_exit_activation_rr", TRAILING_EXIT_PARAMS["trailing_exit_activation_rr"], "decimal"),
        ("backtest.trailing_exit_slippage_rate", TRAILING_EXIT_PARAMS["trailing_exit_slippage_rate"], "decimal"),
        # 确保 TTP 关闭，避免双重追踪干扰
        ("backtest.tp_trailing_enabled", "false", "boolean"),
    ]

    for config_key, config_value, value_type in configs:
        cursor.execute("""
            INSERT OR REPLACE INTO config_entries_v2
            (config_key, config_value, value_type, version, updated_at, profile_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (config_key, config_value, value_type, version, updated_at, profile_name))

    conn.commit()
    conn.close()
    print(f"已设置 Trailing Exit 配置: enabled={enabled}")


async def run_backtest(
    symbol: str,
    start_ts: int,
    end_ts: int,
) -> Dict[str, Any]:
    """
    运行单次回测

    Args:
        symbol: 币种
        start_ts: 开始时间戳（毫秒）
        end_ts: 结束时间戳（毫秒）

    Returns:
        回测结果字典
    """
    from src.infrastructure.historical_data_repository import HistoricalDataRepository
    from src.infrastructure.config_entry_repository import ConfigEntryRepository
    from src.application.backtester import Backtester
    from src.domain.models import BacktestRequest, OrderStrategy
    from src.application.config_manager import ConfigManager

    # Initialize ConfigManager to read KV configs
    config_manager = ConfigManager(DB_PATH)
    await config_manager.initialize_from_db()

    # 注入 ConfigEntryRepository，否则 get_backtest_configs() 抛 RuntimeError
    config_entry_repo = ConfigEntryRepository(DB_PATH)
    await config_entry_repo.initialize()
    config_manager.set_config_entry_repository(config_entry_repo)

    ConfigManager.set_instance(config_manager)

    repo = HistoricalDataRepository(DB_PATH)
    await repo.initialize()

    backtester = Backtester(None, data_repository=repo)

    request = BacktestRequest(
        symbol=symbol,
        timeframe=TIMEFRAME,
        limit=30000,
        start_time=start_ts,
        end_time=end_ts,
        strategies=STRATEGY_CONFIG,
        order_strategy=OrderStrategy(**ORDER_STRATEGY),
        mode="v3_pms",
    )

    report = await backtester.run_backtest(request)
    await repo.close()

    # 统计追踪退出事件
    trailing_exit_count = 0
    trailing_activated_count = 0
    if hasattr(report, 'close_events') and report.close_events:
        for event in report.close_events:
            if event.event_category == 'trailing_exit':
                trailing_exit_count += 1
            elif event.event_category == 'trailing_activated':
                trailing_activated_count += 1

    return {
        "symbol": symbol,
        "total_trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "total_pnl": float(report.total_pnl),
        "avg_pnl": float(report.total_pnl / report.total_trades) if report.total_trades > 0 else 0,
        "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0,
        "max_drawdown": float(report.max_drawdown) if report.max_drawdown else 0,
        "trailing_exit_count": trailing_exit_count,
        "trailing_activated_count": trailing_activated_count,
    }


async def run_experiment(
    trailing_exit_enabled: bool,
) -> Dict[str, Any]:
    """
    运行完整实验

    Args:
        trailing_exit_enabled: 是否启用 Trailing Exit

    Returns:
        实验结果
    """
    # 设置 Trailing Exit 配置
    await set_trailing_exit_config(trailing_exit_enabled)

    results = {
        "trailing_exit_enabled": trailing_exit_enabled,
        "symbols": {},
        "total_trades": 0,
        "total_pnl": Decimal("0"),
        "total_wins": 0,
        "by_period": [],
        "trailing_exit_count": 0,
        "trailing_activated_count": 0,
    }

    for symbol in SYMBOLS:
        print(f"\n处理 {symbol}...")
        symbol_trades = 0
        symbol_pnl = Decimal("0")
        symbol_wins = 0
        symbol_trailing_exit = 0
        symbol_trailing_activated = 0

        for chunk in YEAR_CHUNKS:
            start_ts = int(datetime.strptime(chunk["start"], "%Y-%m-%d").timestamp() * 1000)
            end_ts = int(datetime.strptime(chunk["end"], "%Y-%m-%d").timestamp() * 1000)

            try:
                result = await run_backtest(symbol, start_ts, end_ts)
                symbol_trades += result["total_trades"]
                symbol_pnl += Decimal(str(result["total_pnl"]))
                symbol_wins += int(result["total_trades"] * result["win_rate"])
                symbol_trailing_exit += result.get("trailing_exit_count", 0)
                symbol_trailing_activated += result.get("trailing_activated_count", 0)

                if result["total_trades"] > 0:
                    print(
                        f"  {chunk['name']}: {result['total_trades']} 笔, "
                        f"PnL: {result['total_pnl']:.2f}, "
                        f"Trailing退出: {result.get('trailing_exit_count', 0)}, "
                        f"Trailing激活: {result.get('trailing_activated_count', 0)}"
                    )

            except Exception as e:
                import traceback
                print(f"  {chunk['name']}: 错误 - {e}")
                traceback.print_exc()

        results["symbols"][symbol] = {
            "trades": symbol_trades,
            "pnl": float(symbol_pnl),
            "win_rate": symbol_wins / symbol_trades if symbol_trades > 0 else 0,
            "trailing_exit_count": symbol_trailing_exit,
            "trailing_activated_count": symbol_trailing_activated,
        }
        results["total_trades"] += symbol_trades
        results["total_pnl"] += symbol_pnl
        results["total_wins"] += symbol_wins
        results["trailing_exit_count"] += symbol_trailing_exit
        results["trailing_activated_count"] += symbol_trailing_activated

    results["overall_win_rate"] = (
        results["total_wins"] / results["total_trades"]
        if results["total_trades"] > 0 else 0
    )
    results["overall_pnl"] = float(results["total_pnl"])
    results["avg_pnl_per_trade"] = float(
        results["total_pnl"] / results["total_trades"]
        if results["total_trades"] > 0 else 0
    )

    return results


def print_comparison(experiment_a: Dict, experiment_b: Dict) -> None:
    """打印对比结果"""
    print("\n" + "=" * 80)
    print("Trailing Exit 回测验证对比结果 (ADR-2026-04-20)")
    print("=" * 80)

    # ── 总体指标对比 ──
    print("\n[总体指标对比]")
    print("-" * 80)
    print(f"{'指标':<25} {'实验 A (Exit off)':<25} {'实验 B (Exit on)':<25} {'差异':<15}")
    print("-" * 80)

    metrics = [
        ("总交易数", "total_trades", ""),
        ("总胜率", "overall_win_rate", "%"),
        ("总 PnL (USDT)", "overall_pnl", ""),
        ("单笔 PnL (USDT)", "avg_pnl_per_trade", ""),
    ]

    for name, key, unit in metrics:
        val_a = experiment_a.get(key, 0)
        val_b = experiment_b.get(key, 0)

        if "rate" in key or "win_rate" in key:
            val_a_str = f"{val_a:.1%}"
            val_b_str = f"{val_b:.1%}"
            diff = val_b - val_a
            diff_str = f"{diff:+.1%}"
        else:
            val_a_str = f"{val_a:.2f}"
            val_b_str = f"{val_b:.2f}"
            diff = val_b - val_a
            diff_str = f"{diff:+.2f}"

        print(f"{name:<25} {val_a_str:<25} {val_b_str:<25} {diff_str:<15}")

    # ── 分币种对比 ──
    print("\n[分币种对比]")
    print("-" * 80)
    print(
        f"{'币种':<15} {'A 交易数':<10} {'B 交易数':<10} "
        f"{'A 胜率':<10} {'B 胜率':<10} "
        f"{'A PnL':<15} {'B PnL':<15} {'PnL 差异':<15}"
    )
    print("-" * 80)

    for symbol in SYMBOLS:
        sym_a = experiment_a["symbols"].get(symbol, {})
        sym_b = experiment_b["symbols"].get(symbol, {})

        trades_a = sym_a.get("trades", 0)
        trades_b = sym_b.get("trades", 0)
        wr_a = sym_a.get("win_rate", 0)
        wr_b = sym_b.get("win_rate", 0)
        pnl_a = sym_a.get("pnl", 0)
        pnl_b = sym_b.get("pnl", 0)
        diff = pnl_b - pnl_a

        print(
            f"{symbol:<15} {trades_a:<10} {trades_b:<10} "
            f"{wr_a:<10.1%} {wr_b:<10.1%} "
            f"{pnl_a:<15.2f} {pnl_b:<15.2f} {diff:+.2f}"
        )

    # ── 追踪退出事件统计 ──
    print("\n[追踪退出事件统计]")
    print("-" * 80)
    print(f"{'币种':<15} {'A 激活数':<15} {'B 激活数':<15} {'A 退出数':<15} {'B 退出数':<15}")
    print("-" * 80)

    for symbol in SYMBOLS:
        sym_a = experiment_a["symbols"].get(symbol, {})
        sym_b = experiment_b["symbols"].get(symbol, {})

        act_a = sym_a.get("trailing_activated_count", 0)
        act_b = sym_b.get("trailing_activated_count", 0)
        exit_a = sym_a.get("trailing_exit_count", 0)
        exit_b = sym_b.get("trailing_exit_count", 0)

        print(f"{symbol:<15} {act_a:<15} {act_b:<15} {exit_a:<15} {exit_b:<15}")

    # ── 决策门判断 ──
    print("\n[决策门判断]")
    print("-" * 80)

    # 计算提升比例
    if experiment_a["overall_pnl"] != 0:
        pnl_change = (
            (experiment_b["overall_pnl"] - experiment_a["overall_pnl"])
            / abs(experiment_a["overall_pnl"])
            * 100
        )
    else:
        pnl_change = 0

    if experiment_b["overall_pnl"] > experiment_a["overall_pnl"]:
        if pnl_change > 10:
            verdict = "有效 (PnL 提升 > 10%)"
        else:
            verdict = f"轻微有效 (PnL 提升 {pnl_change:.1f}%, 未达 10% 门限)"
        print(f"Trailing Exit {verdict}")
    elif experiment_b["overall_pnl"] < experiment_a["overall_pnl"]:
        print(f"Trailing Exit 无效：总 PnL 下降 {-pnl_change:.1f}%")
    else:
        print("Trailing Exit 无明显影响：总 PnL 相同")

    print(f"  - 实验 A (Exit off): {experiment_a['overall_pnl']:.2f} USDT")
    print(f"  - 实验 B (Exit on):  {experiment_b['overall_pnl']:.2f} USDT")

    # 追踪退出事件验证
    if experiment_b["trailing_activated_count"] > 0:
        print(
            f"\n追踪退出功能验证：成功 "
            f"(激活 {experiment_b['trailing_activated_count']} 次, "
            f"退出 {experiment_b['trailing_exit_count']} 次)"
        )
        # 激活但未退出的比例
        if experiment_b["trailing_activated_count"] > 0:
            exit_rate = (
                experiment_b["trailing_exit_count"]
                / experiment_b["trailing_activated_count"]
                * 100
            )
            print(f"激活->退出转化率: {exit_rate:.1f}%")
    else:
        print("\n追踪退出功能验证：未触发激活（可能参数不匹配或行情未满足条件）")

    print("=" * 80)


async def main():
    """主函数"""
    print("=" * 80)
    print("Trailing Exit 回测验证 (ADR-2026-04-20)")
    print("=" * 80)
    print(f"币种: {', '.join(SYMBOLS)}")
    print(f"周期: {TIMEFRAME}")
    print(f"范围: 2023-01-01 ~ 2025-01-01")
    print(f"Trailing Exit 参数:")
    print(f"  - trailing_exit_percent: {TRAILING_EXIT_PARAMS['trailing_exit_percent']} (回撤容忍度)")
    print(f"  - trailing_exit_activation_rr: {TRAILING_EXIT_PARAMS['trailing_exit_activation_rr']} (激活阈值)")
    print(f"  - trailing_exit_slippage_rate: {TRAILING_EXIT_PARAMS['trailing_exit_slippage_rate']} (滑点率)")
    print("=" * 80)

    # 运行实验 A: Trailing Exit off
    print("\n\n>>> 开始实验 A: Trailing Exit off <<<")
    experiment_a = await run_experiment(trailing_exit_enabled=False)

    # 运行实验 B: Trailing Exit on
    print("\n\n>>> 开始实验 B: Trailing Exit on <<<")
    experiment_b = await run_experiment(trailing_exit_enabled=True)

    # 打印对比结果
    print_comparison(experiment_a, experiment_b)

    # 保存结果
    output = {
        "experiment_a": experiment_a,
        "experiment_b": experiment_b,
        "trailing_exit_params": TRAILING_EXIT_PARAMS,
        "timestamp": datetime.now().isoformat(),
        "symbols": SYMBOLS,
        "timeframe": TIMEFRAME,
        "range": "2023-01-01 ~ 2025-01-01",
    }

    output_file = "docs/diagnostic-reports/trailing_exit_validation_backtest.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    class DecimalEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return super().default(obj)

    with open(output_file, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, cls=DecimalEncoder)

    print(f"\n结果已保存: {output_file}")

    # 恢复默认配置（关闭 Trailing Exit）
    await set_trailing_exit_config(False)


if __name__ == "__main__":
    asyncio.run(main())
