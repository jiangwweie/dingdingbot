#!/usr/bin/env python3
"""
R1 Capital Allocation Audit - MaxDD 重新计算与验证

审计目标：
1. 验证 R1 报告中的 MaxDD 是否正确
2. 重新计算 mark-to-market equity curve 的 MaxDD
3. 检查 2023 年亏损 -5751 USDT 时，MaxDD 是否合理
4. 验证 Calmar ratio 是否失真
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    BacktestRequest,
    RiskConfig,
    BacktestRuntimeOverrides,
    OrderStrategy,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository


# ============================================================
# 固定参数（与 R1 一致）
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MTF_TIMEFRAME = "4h"
EMA_PERIOD = 50
MTF_EMA_PERIOD = 60
TP_RATIOS = [1.0, 3.5]
TP_PARTIAL_RATIOS = [0.5, 0.5]

# BNB9 成本
FEE_RATE = Decimal("0.000405")
ENTRY_SLIPPAGE = Decimal("0.0001")
TP_SLIPPAGE = Decimal("0")

# 固定风控
MAX_LEVERAGE = 20
DAILY_MAX_TRADES = 50
INITIAL_BALANCE = Decimal("10000")

# 时间范围
START_TIME = 1672531200000  # 2023-01-01 00:00:00 UTC
END_TIME = 1767225599000    # 2025-12-31 23:59:59 UTC


# ============================================================
# 辅助函数
# ============================================================
def build_strategy_definition() -> Dict[str, Any]:
    """构建 baseline Pinbar 策略定义（LONG-only）"""
    return {
        "name": "pinbar_baseline",
        "trigger": {
            "type": "pinbar",
            "params": {
                "min_wick_ratio": 0.6,
                "max_body_ratio": 0.3,
                "body_position_tolerance": 0.1,
            }
        },
        "filters": [
            {
                "type": "ema_trend",
                "params": {
                    "period": EMA_PERIOD,
                    "direction": "bullish",
                }
            },
            {
                "type": "mtf",
                "params": {
                    "timeframe": MTF_TIMEFRAME,
                    "ema_period": MTF_EMA_PERIOD,
                    "direction": "bullish",
                }
            },
        ],
        "apply_to": [f"{SYMBOL}:{TIMEFRAME}"],
    }


def compute_equity_curve(
    positions: List[Any],
    initial_balance: Decimal,
    start_time: int,
    end_time: int,
) -> List[Dict[str, Any]]:
    """
    计算 mark-to-market equity curve

    Args:
        positions: PositionSummary 列表
        initial_balance: 初始资金
        start_time: 开始时间戳
        end_time: 结束时间戳

    Returns:
        [{timestamp, equity, cash, unrealized_pnl}, ...]
    """
    # 按时间排序所有事件
    events = []

    # 添加初始资金
    events.append({
        "timestamp": start_time,
        "type": "init",
        "equity": float(initial_balance),
    })

    # 添加所有仓位事件
    for pos in positions:
        # 入场事件
        if pos.entry_time:
            events.append({
                "timestamp": pos.entry_time,
                "type": "entry",
                "position_id": pos.position_id,
            })

        # 出场事件
        if pos.exit_time:
            events.append({
                "timestamp": pos.exit_time,
                "type": "exit",
                "position_id": pos.position_id,
                "realized_pnl": float(pos.realized_pnl),
            })

    # 按时间排序
    events.sort(key=lambda x: x["timestamp"])

    # 计算 equity curve
    equity_curve = []
    cash = float(initial_balance)
    open_positions = {}  # position_id -> entry_time
    total_realized_pnl = 0.0

    for event in events:
        if event["type"] == "init":
            equity = cash

        elif event["type"] == "entry":
            open_positions[event["position_id"]] = event["timestamp"]
            # 入场时，cash 不变（假设全仓交易）
            equity = cash

        elif event["type"] == "exit":
            # 出场时，cash 增加（或减少）
            cash += event["realized_pnl"]
            total_realized_pnl += event["realized_pnl"]
            if event["position_id"] in open_positions:
                del open_positions[event["position_id"]]
            equity = cash

        equity_curve.append({
            "timestamp": event["timestamp"],
            "equity": equity,
            "cash": cash,
            "open_positions": len(open_positions),
            "total_realized_pnl": total_realized_pnl,
        })

    return equity_curve


def compute_max_drawdown(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算最大回撤

    Returns:
        {
            "max_dd_usdt": float,
            "max_dd_pct": float,
            "peak_equity": float,
            "trough_equity": float,
            "peak_time": int,
            "trough_time": int,
        }
    """
    if not equity_curve:
        return {
            "max_dd_usdt": 0.0,
            "max_dd_pct": 0.0,
            "peak_equity": 0.0,
            "trough_equity": 0.0,
            "peak_time": 0,
            "trough_time": 0,
        }

    peak_equity = equity_curve[0]["equity"]
    peak_time = equity_curve[0]["timestamp"]
    max_dd_usdt = 0.0
    max_dd_pct = 0.0
    trough_equity = peak_equity
    trough_time = peak_time

    for point in equity_curve:
        equity = point["equity"]

        # 更新峰值
        if equity > peak_equity:
            peak_equity = equity
            peak_time = point["timestamp"]

        # 计算当前回撤
        dd_usdt = peak_equity - equity
        dd_pct = (dd_usdt / peak_equity * 100) if peak_equity > 0 else 0.0

        # 更新最大回撤
        if dd_usdt > max_dd_usdt:
            max_dd_usdt = dd_usdt
            max_dd_pct = dd_pct
            trough_equity = equity
            trough_time = point["timestamp"]

    return {
        "max_dd_usdt": max_dd_usdt,
        "max_dd_pct": max_dd_pct,
        "peak_equity": peak_equity,
        "trough_equity": trough_equity,
        "peak_time": peak_time,
        "trough_time": trough_time,
    }


async def audit_single_config(
    backtester: Backtester,
    exposure: Decimal,
    risk_pct: Decimal,
) -> Dict[str, Any]:
    """审计单个配置"""
    try:
        # 构建 RiskConfig
        risk_config = RiskConfig(
            max_loss_percent=risk_pct,
            max_leverage=MAX_LEVERAGE,
            max_total_exposure=exposure,
            daily_max_trades=DAILY_MAX_TRADES,
        )

        # 构建 BacktestRequest
        request = BacktestRequest(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start_time=START_TIME,
            end_time=END_TIME,
            limit=30000,
            strategies=[build_strategy_definition()],
            risk_overrides=risk_config,
            mode="v3_pms",
            initial_balance=INITIAL_BALANCE,
            fee_rate=FEE_RATE,
            slippage_rate=ENTRY_SLIPPAGE,
            tp_slippage_rate=TP_SLIPPAGE,
        )

        # 设置 OrderStrategy
        request.order_strategy = OrderStrategy(
            id="r1_audit",
            name="R1 Audit",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        # 设置 runtime overrides
        overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
        overrides.allowed_directions = ["LONG"]

        # 运行回测
        report = await backtester.run_backtest(
            request,
            runtime_overrides=overrides,
        )

        if not report or not hasattr(report, 'positions'):
            return None

        # 计算 equity curve
        equity_curve = compute_equity_curve(
            report.positions,
            INITIAL_BALANCE,
            START_TIME,
            END_TIME,
        )

        # 计算正确的 MaxDD
        max_dd_info = compute_max_drawdown(equity_curve)

        # 提取原始报告的 MaxDD
        original_max_dd_pct = float(report.max_drawdown)

        # 计算 yearly breakdown
        yearly_pnl = {}
        yearly_positions = {}

        for pos in report.positions:
            if pos.exit_time:
                year = datetime.fromtimestamp(pos.exit_time / 1000, tz=timezone.utc).year
                if year not in yearly_pnl:
                    yearly_pnl[year] = Decimal("0")
                    yearly_positions[year] = []
                yearly_pnl[year] += pos.realized_pnl
                yearly_positions[year].append(pos)

        # 计算每年的 MaxDD
        yearly_max_dd = {}
        for year, year_positions in yearly_positions.items():
            year_start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
            year_end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

            year_equity_curve = compute_equity_curve(
                year_positions,
                INITIAL_BALANCE,
                year_start,
                year_end,
            )
            year_max_dd = compute_max_drawdown(year_equity_curve)
            yearly_max_dd[year] = year_max_dd

        return {
            "exposure": float(exposure),
            "risk_pct": float(risk_pct),
            "original_max_dd_pct": original_max_dd_pct,
            "recalculated_max_dd_usdt": max_dd_info["max_dd_usdt"],
            "recalculated_max_dd_pct": max_dd_info["max_dd_pct"],
            "peak_equity": max_dd_info["peak_equity"],
            "trough_equity": max_dd_info["trough_equity"],
            "total_pnl": float(sum(yearly_pnl.values())),
            "trades": len(report.positions),
            "yearly_pnl": {str(k): float(v) for k, v in yearly_pnl.items()},
            "yearly_max_dd": {str(k): v for k, v in yearly_max_dd.items()},
            "equity_curve_length": len(equity_curve),
        }

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    print("=" * 80)
    print("R1 Capital Allocation Audit")
    print("=" * 80)

    # 读取 R1 原始结果
    r1_json_path = Path("reports/research/r1_baseline_capital_allocation_search_2026-04-28.json")
    with open(r1_json_path) as f:
        r1_data = json.load(f)

    print(f"\n[R1 原始报告]")
    print(f"  最优配置: exposure={r1_data['best_configs']['max_pnl']['exposure']}, risk={r1_data['best_configs']['max_pnl']['risk_pct']}")
    print(f"  原始 MaxDD: {r1_data['best_configs']['max_pnl']['max_dd_pct']*100:.2f}%")
    print(f"  原始 PnL: {r1_data['best_configs']['max_pnl']['total_pnl']:.2f} USDT")

    # 初始化 Backtester
    data_repo = HistoricalDataRepository()
    from src.infrastructure.exchange_gateway import ExchangeGateway
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=False,
    )
    backtester = Backtester(
        exchange_gateway=gateway,
        data_repository=data_repo,
    )

    # 审计关键配置
    configs_to_audit = [
        (Decimal("1.0"), Decimal("0.01")),  # baseline
        (Decimal("1.0"), Decimal("0.02")),  # R1 最优
        (Decimal("1.0"), Decimal("0.005")), # 保守
    ]

    print(f"\n[审计关键配置]")
    audit_results = []

    for exposure, risk_pct in configs_to_audit:
        print(f"\n  审计: exposure={exposure}, risk={risk_pct}")
        result = await audit_single_config(backtester, exposure, risk_pct)
        if result:
            audit_results.append(result)
            print(f"    原始 MaxDD: {result['original_max_dd_pct']:.2f}%")
            print(f"    重算 MaxDD: {result['recalculated_max_dd_pct']:.2f}% ({result['recalculated_max_dd_usdt']:.2f} USDT)")
            print(f"    差异: {result['recalculated_max_dd_pct'] - result['original_max_dd_pct']:.2f}%")
            print(f"    总 PnL: {result['total_pnl']:.2f} USDT")
            print(f"    年度 PnL: {result['yearly_pnl']}")

    # 分析结果
    print("\n" + "=" * 80)
    print("审计结论")
    print("=" * 80)

    for result in audit_results:
        print(f"\n[exposure={result['exposure']}, risk={result['risk_pct']}]")
        print(f"  原始 MaxDD: {result['original_max_dd_pct']:.2f}%")
        print(f"  重算 MaxDD: {result['recalculated_max_dd_pct']:.2f}%")
        print(f"  差异: {result['recalculated_max_dd_pct'] - result['original_max_dd_pct']:.2f}%")

        if abs(result['recalculated_max_dd_pct'] - result['original_max_dd_pct']) > 5.0:
            print(f"  ⚠️  MaxDD 差异过大！原始报告可能错误。")
        else:
            print(f"  ✅ MaxDD 基本一致。")

    # 保存审计结果
    output = {
        "title": "R1 Capital Allocation Audit",
        "date": "2026-04-29",
        "r1_original": {
            "best_config": r1_data['best_configs']['max_pnl'],
        },
        "audit_results": audit_results,
        "conclusion": {
            "max_dd_correct": all(
                abs(r['recalculated_max_dd_pct'] - r['original_max_dd_pct']) < 5.0
                for r in audit_results
            ),
        },
    }

    output_path = Path("reports/research/r1_capital_allocation_audit_2026-04-29.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[保存] {output_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
