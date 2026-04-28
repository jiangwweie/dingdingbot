#!/usr/bin/env python3
"""
R1b Capital Allocation Audit V2 - 严格二次审计

审计目标：
1. 不接受 R1 原报告，不接受 R1 audit 结论
2. 完整审计 56 组配置
3. 对账三种 equity curve：
   - report.debug_equity_curve (Backtester 输出)
   - realized_equity_curve (只在平仓时更新)
   - mark_to_market_equity_curve (每根 K 线计入浮盈浮亏，本轮暂不实现)
4. 明确区分 realized vs mark-to-market
5. 输出可行解表（MaxDD <= 35%）

约束：
- 不修改 src 核心代码
- 不修改 runtime profile
- 不修改 sim1_eth_runtime
- 不扩大参数搜索
- 只允许新增/修改 research audit 脚本
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


def compute_realized_equity_curve(
    positions: List[Any],
    initial_balance: Decimal,
    start_time: int,
    end_time: int,
) -> List[Dict[str, Any]]:
    """
    计算 realized equity curve（只在平仓时更新权益）

    注意：这不是 mark-to-market equity curve！
    - 不追踪持仓期间的浮盈浮亏
    - 只在平仓时更新 cash
    - 适用于评估"已实现盈亏"的风险

    Args:
        positions: PositionSummary 列表
        initial_balance: 初始资金
        start_time: 开始时间戳
        end_time: 结束时间戳

    Returns:
        [{timestamp, equity, cash, realized_pnl}, ...]
    """
    # 按时间排序所有事件
    events = []

    # 添加初始资金
    events.append({
        "timestamp": start_time,
        "type": "init",
        "equity": float(initial_balance),
    })

    # 添加所有仓位平仓事件
    for pos in positions:
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
    total_realized_pnl = 0.0

    for event in events:
        if event["type"] == "init":
            equity = cash

        elif event["type"] == "exit":
            # 出场时，cash 增加（或减少）
            cash += event["realized_pnl"]
            total_realized_pnl += event["realized_pnl"]
            equity = cash

        equity_curve.append({
            "timestamp": event["timestamp"],
            "equity": equity,
            "cash": cash,
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
            id="r1b_audit",
            name="R1b Audit",
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

        # ========================================
        # A. 对账 report 自带 MaxDD
        # ========================================

        # 1. report.max_drawdown
        report_max_dd = float(report.max_drawdown)

        # 2. report.debug_max_drawdown_detail
        debug_detail = report.debug_max_drawdown_detail or {}

        # 3. 用 report.debug_equity_curve 重新计算的 MaxDD
        debug_curve_maxdd = 0.0
        debug_curve_detail = {}
        if report.debug_equity_curve:
            debug_curve_dd = compute_max_drawdown(report.debug_equity_curve)
            debug_curve_maxdd = debug_curve_dd["max_dd_pct"]
            debug_curve_detail = debug_curve_dd

        # 4. 用 positions realized curve 重新计算的 MaxDD
        realized_curve = compute_realized_equity_curve(
            report.positions,
            INITIAL_BALANCE,
            START_TIME,
            END_TIME,
        )
        realized_curve_dd = compute_max_drawdown(realized_curve)
        realized_curve_maxdd = realized_curve_dd["max_dd_pct"]

        # ========================================
        # B. 年度统计
        # ========================================
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

        # 计算每年的 MaxDD（基于 realized curve）
        yearly_max_dd = {}
        for year, year_positions in yearly_positions.items():
            year_start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
            year_end = int(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

            year_equity_curve = compute_realized_equity_curve(
                year_positions,
                INITIAL_BALANCE,
                year_start,
                year_end,
            )
            year_max_dd = compute_max_drawdown(year_equity_curve)
            yearly_max_dd[year] = year_max_dd

        # ========================================
        # C. 可行性判定
        # ========================================
        feasible_by_debug = debug_curve_maxdd <= 35.0
        feasible_by_realized = realized_curve_maxdd <= 35.0

        return {
            "exposure": float(exposure),
            "risk_pct": float(risk_pct),
            "total_pnl": float(report.total_pnl),
            "trades": len(report.positions),
            # 三种 MaxDD 对账
            "report_max_dd": report_max_dd,
            "debug_detail_max_dd": debug_detail.get("drawdown", 0.0),
            "debug_curve_max_dd": debug_curve_maxdd,
            "realized_curve_max_dd": realized_curve_maxdd,
            # 详细信息
            "debug_curve_detail": debug_curve_detail,
            "realized_curve_detail": realized_curve_dd,
            "debug_detail": debug_detail,
            # 年度统计
            "yearly_pnl": {str(k): float(v) for k, v in yearly_pnl.items()},
            "yearly_max_dd": {str(k): v for k, v in yearly_max_dd.items()},
            # 可行性
            "feasible_by_debug_curve": feasible_by_debug,
            "feasible_by_realized_curve": feasible_by_realized,
        }

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    print("=" * 80)
    print("R1b Capital Allocation Audit V2 - 严格二次审计")
    print("=" * 80)

    # 读取 R1 原始结果
    r1_json_path = Path("reports/research/r1_baseline_capital_allocation_search_2026-04-28.json")
    with open(r1_json_path) as f:
        r1_data = json.load(f)

    print(f"\n[R1 原始报告]")
    print(f"  最优配置: exposure={r1_data['best_configs']['max_pnl']['exposure']}, risk={r1_data['best_configs']['max_pnl']['risk_pct']}")

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

    # 重新生成搜索网格（与 R1 一致）
    exposure_levels = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
    risk_levels = [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02]

    all_configs = []
    for exposure in exposure_levels:
        for risk_pct in risk_levels:
            all_configs.append((Decimal(str(exposure)), Decimal(str(risk_pct))))

    print(f"\n[审计所有配置] 共 {len(all_configs)} 组")
    audit_results = []

    for i, (exposure, risk_pct) in enumerate(all_configs, 1):
        print(f"\n  [{i}/{len(all_configs)}] 审计: exposure={exposure}, risk={risk_pct}")
        result = await audit_single_config(backtester, exposure, risk_pct)
        if result:
            audit_results.append(result)
            print(f"    report.max_dd: {result['report_max_dd']:.2f}%")
            print(f"    debug_curve_max_dd: {result['debug_curve_max_dd']:.2f}%")
            print(f"    realized_curve_max_dd: {result['realized_curve_max_dd']:.2f}%")
            print(f"    total_pnl: {result['total_pnl']:.2f} USDT")
            print(f"    feasible_by_debug: {result['feasible_by_debug_curve']}")
            print(f"    feasible_by_realized: {result['feasible_by_realized_curve']}")

    # ========================================
    # 分析结果
    # ========================================
    print("\n" + "=" * 80)
    print("审计结论")
    print("=" * 80)

    # D. 输出可行解表
    feasible_by_debug = [r for r in audit_results if r["feasible_by_debug_curve"]]
    feasible_by_realized = [r for r in audit_results if r["feasible_by_realized_curve"]]

    print(f"\n[可行解统计]")
    print(f"  基于 debug_curve (MaxDD <= 35%): {len(feasible_by_debug)} 组")
    print(f"  基于 realized_curve (MaxDD <= 35%): {len(feasible_by_realized)} 组")

    if feasible_by_debug:
        print(f"\n[基于 debug_curve 的可行配置]")
        for r in sorted(feasible_by_debug, key=lambda x: x["total_pnl"], reverse=True)[:5]:
            print(f"  exposure={r['exposure']}, risk={r['risk_pct']}")
            print(f"    PnL: {r['total_pnl']:.2f} USDT")
            print(f"    MaxDD: {r['debug_curve_max_dd']:.2f}%")
            print(f"    Trades: {r['trades']}")

    if feasible_by_realized:
        print(f"\n[基于 realized_curve 的可行配置]")
        for r in sorted(feasible_by_realized, key=lambda x: x["total_pnl"], reverse=True)[:5]:
            print(f"  exposure={r['exposure']}, risk={r['risk_pct']}")
            print(f"    PnL: {r['total_pnl']:.2f} USDT")
            print(f"    MaxDD: {r['realized_curve_max_dd']:.2f}%")
            print(f"    Trades: {r['trades']}")

    # E. 重点核验 risk=0.5%
    print(f"\n[重点核验 risk=0.5%]")
    risk_05_configs = [r for r in audit_results if abs(r["risk_pct"] - 0.005) < 0.0001]
    for r in risk_05_configs:
        print(f"\n  exposure={r['exposure']}, risk=0.5%")
        print(f"    report.max_dd: {r['report_max_dd']:.2f}%")
        print(f"    debug_curve_max_dd: {r['debug_curve_max_dd']:.2f}%")
        print(f"    realized_curve_max_dd: {r['realized_curve_max_dd']:.2f}%")
        print(f"    total_pnl: {r['total_pnl']:.2f} USDT")

        if r["debug_curve_max_dd"] > 35.0:
            detail = r["debug_curve_detail"]
            print(f"    ⚠️  MaxDD > 35%")
            print(f"      Peak: {detail['peak_equity']:.2f} USDT @ {datetime.fromtimestamp(detail['peak_time']/1000, tz=timezone.utc)}")
            print(f"      Trough: {detail['trough_equity']:.2f} USDT @ {datetime.fromtimestamp(detail['trough_time']/1000, tz=timezone.utc)}")
            print(f"      MaxDD: {detail['max_dd_usdt']:.2f} USDT ({detail['max_dd_pct']:.2f}%)")

    # 保存审计结果
    output = {
        "title": "R1b Capital Allocation Audit V2",
        "date": "2026-04-29",
        "audit_type": "strict_reaudit",
        "total_configs": len(all_configs),
        "audit_results": audit_results,
        "feasible_summary": {
            "by_debug_curve": len(feasible_by_debug),
            "by_realized_curve": len(feasible_by_realized),
        },
        "conclusion": {
            "has_feasible_config": len(feasible_by_debug) > 0 or len(feasible_by_realized) > 0,
            "note": "本审计基于 realized equity curve，未计算真实 mark-to-market curve",
        },
    }

    output_path = Path("reports/research/r1b_capital_allocation_audit_v2_2026-04-29.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[保存] {output_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
