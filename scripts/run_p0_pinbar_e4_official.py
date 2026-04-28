#!/usr/bin/env python3
"""
P0: Pinbar(E4 donchian_distance) Official Backtester Validation

验证在 official backtester dynamic strategy path 下，donchian_distance filter 是否能稳定改善 Pinbar baseline。

实验设计：
- E0: Pinbar baseline (EMA50 + MTF EMA60) via dynamic strategy path
- E1: Pinbar + donchian_distance (EMA50 + MTF EMA60 + donchian_distance) via dynamic strategy path

严格约束：
- 不修改 src/ 核心代码
- 不修改 sim1_eth_runtime / runtime profile
- 使用 Backtester official dynamic strategy path (BacktestRequest.strategies)
- 不使用 legacy IsolatedStrategyRunner
- 不使用 proxy 撮合
"""
import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    StrategyDefinition,
    BacktestRequest,
    RiskConfig,
    OrderStrategy,
    AccountSnapshot,
    PMSBacktestReport,
    BacktestRuntimeOverrides,
)
from src.domain.logic_tree import FilterConfig, FilterLeaf, LogicNode, TriggerConfig, TriggerLeaf
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.historical_data_repository import HistoricalDataRepository

# ─── 常量 ───────────────────────────────────────────────────────────────

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MTF_TIMEFRAME = "4h"

# BNB9 口径 (修正)
BNB9_SLIPPAGE = Decimal("0.0001")  # 0.01% entry slippage
BNB9_TP_SLIPPAGE = Decimal("0")  # 0% TP slippage
BNB9_FEE = Decimal("0.000405")  # 0.0405% fee

INITIAL_BALANCE = Decimal("10000")

# Risk config (research profile)
RESEARCH_RISK = RiskConfig(
    max_loss_percent=Decimal("0.01"),  # 1%
    max_leverage=20,
    max_total_exposure=Decimal("2.0"),  # Research profile (not sim1 1.0)
    max_position_percent=Decimal("0.2"),
    daily_max_loss=Decimal("0.05"),
    daily_max_trades=50,
    min_balance=Decimal("100"),
)

# Order strategy (baseline TP/SL - frozen baseline)
ORDER_STRATEGY = OrderStrategy(
    id="p0_pinbar_e4",
    name="P0 Pinbar E4",
    tp_levels=2,
    tp_ratios=[Decimal("0.5"), Decimal("0.5")],  # 50% TP1, 50% TP2
    tp_targets=[Decimal("1.0"), Decimal("3.5")],  # TP1 at 1R, TP2 at 3.5R
    initial_stop_loss_rr=Decimal("-1.0"),
    trailing_stop_enabled=False,
    oco_enabled=True,
)

# E4 threshold from M1c
E4_THRESHOLD = "-0.016809"

REPORT_DIR = PROJECT_ROOT / "reports" / "research"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ─── 策略构造 ────────────────────────────────────────────────────────────

def create_pinbar_baseline_strategy() -> StrategyDefinition:
    """创建 Pinbar baseline 策略（E0: 无 donchian_distance）"""
    # Trigger: Pinbar
    pinbar_trigger = TriggerLeaf(
        id="pinbar_trigger",
        config=TriggerConfig(
            type="pinbar",
            enabled=True,
            params={
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1"
            }
        )
    )

    # Filters: EMA50 + MTF EMA60
    ema_filter = FilterLeaf(
        id="ema_filter",
        config=FilterConfig(
            type="ema_trend",
            enabled=True,
            params={"period": 50}
        )
    )

    mtf_filter = FilterLeaf(
        id="mtf_filter",
        config=FilterConfig(
            type="mtf",
            enabled=True,
            params={}
        )
    )

    # Logic tree: trigger AND filters
    logic_tree = LogicNode(
        gate="AND",
        children=[
            pinbar_trigger,
            LogicNode(gate="AND", children=[ema_filter, mtf_filter])
        ]
    )

    return StrategyDefinition(
        id="pinbar_baseline_e0",
        name="Pinbar Baseline (E0)",
        logic_tree=logic_tree,
        apply_to=["ETH/USDT:USDT:1h"]
    )


def create_pinbar_e4_strategy() -> StrategyDefinition:
    """创建 Pinbar + E4 donchian_distance 策略（E1）"""
    # Trigger: Pinbar
    pinbar_trigger = TriggerLeaf(
        id="pinbar_trigger",
        config=TriggerConfig(
            type="pinbar",
            enabled=True,
            params={
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1"
            }
        )
    )

    # Filters: EMA50 + MTF EMA60 + donchian_distance
    ema_filter = FilterLeaf(
        id="ema_filter",
        config=FilterConfig(
            type="ema_trend",
            enabled=True,
            params={"period": 50}
        )
    )

    mtf_filter = FilterLeaf(
        id="mtf_filter",
        config=FilterConfig(
            type="mtf",
            enabled=True,
            params={}
        )
    )

    donchian_filter = FilterLeaf(
        id="donchian_filter",
        config=FilterConfig(
            type="donchian_distance",
            enabled=True,
            params={
                "lookback": 20,
                "max_distance_to_high_pct": E4_THRESHOLD
            }
        )
    )

    # Logic tree: trigger AND filters
    logic_tree = LogicNode(
        gate="AND",
        children=[
            pinbar_trigger,
            LogicNode(gate="AND", children=[ema_filter, mtf_filter, donchian_filter])
        ]
    )

    return StrategyDefinition(
        id="pinbar_e4_e1",
        name="Pinbar + E4 Donchian Distance (E1)",
        logic_tree=logic_tree,
        apply_to=["ETH/USDT:USDT:1h"]
    )


# ─── 回测执行 ────────────────────────────────────────────────────────────

async def run_backtest(
    strategy: StrategyDefinition,
    label: str,
    start_date: str,
    end_date: str,
    gateway: ExchangeGateway,
    data_repo: HistoricalDataRepository
) -> Dict[str, Any]:
    """运行回测并返回结果"""
    print(f"\n{'='*80}")
    print(f"Running backtest: {label}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Strategy: {strategy.id}")
    print(f"{'='*80}\n")

    # 创建 Backtester
    backtester = Backtester(
        exchange_gateway=gateway,
        data_repository=data_repo
    )

    # Convert dates to timestamps (milliseconds)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1) - timedelta(seconds=1)
    start_ts = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)

    # 创建 BacktestRequest (dynamic strategy path)
    # Convert StrategyDefinition to dict for BacktestRequest
    # CRITICAL: Exclude legacy fields to prevent deserialization failure
    strategy_dict = strategy.model_dump(
        mode="json",
        exclude={
            "trigger",
            "triggers",
            "filters",
            "trigger_logic",
            "filter_logic",
        },
    )

    # 本地反序列化自检
    try:
        StrategyDefinition(**strategy_dict)
        print(f"✓ Strategy deserialization self-check passed")
    except Exception as e:
        print(f"✗ Strategy deserialization self-check FAILED: {e}")
        print(f"  strategy_dict keys: {list(strategy_dict.keys())}")
        raise

    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=start_ts,
        end_time=end_ts,
        initial_balance=INITIAL_BALANCE,
        strategies=[strategy_dict],  # Dynamic strategy path (as dict)
        risk_overrides=RESEARCH_RISK,
        order_strategy=ORDER_STRATEGY,  # CRITICAL: Order strategy for TP/SL
        mode="v3_pms",  # Use v3_pms for position-level backtesting with full PnL/MaxDD
        slippage_rate=BNB9_SLIPPAGE,
        tp_slippage_rate=BNB9_TP_SLIPPAGE,
        fee_rate=BNB9_FEE,
    )

    # 支持度检查：确认 v3_pms + dynamic strategy path
    assert request.mode == "v3_pms", f"mode must be v3_pms, got {request.mode}"
    assert request.strategies is not None and len(request.strategies) > 0, "strategies must be non-empty"
    assert request.order_strategy is not None, "order_strategy must be provided"
    print(f"✓ v3_pms dynamic strategy path confirmed: mode={request.mode}, strategies={len(request.strategies)}, order_strategy={request.order_strategy.id}")

    # CRITICAL: Set LONG-only via runtime_overrides
    overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
    overrides.allowed_directions = ["LONG"]
    print(f"✓ Runtime overrides: allowed_directions={overrides.allowed_directions}")

    # 运行回测
    report = await backtester.run_backtest(
        request,
        runtime_overrides=overrides,
    )

    # 提取关键指标
    if isinstance(report, PMSBacktestReport):
        total_pnl = float(report.total_pnl)
        total_trades = len(report.positions) if report.positions else 0
        max_dd = float(report.max_drawdown) if hasattr(report, 'max_drawdown') else 0.0

        # 计算胜率
        wins = sum(1 for p in report.positions if p.realized_pnl > 0) if report.positions else 0
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        # 计算 profit factor
        total_wins = sum(float(p.realized_pnl) for p in report.positions if p.realized_pnl > 0) if report.positions else 0.0
        total_losses = abs(sum(float(p.realized_pnl) for p in report.positions if p.realized_pnl <= 0)) if report.positions else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0

        # 平均盈亏
        avg_win = total_wins / wins if wins > 0 else 0.0
        avg_loss = total_losses / (total_trades - wins) if (total_trades - wins) > 0 else 0.0

        summary = {
            "label": label,
            "strategy_id": strategy.id,
            "start_date": start_date,
            "end_date": end_date,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_dd": max_dd,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "wins": wins,
            "losses": total_trades - wins,
            # CRITICAL: Preserve attribution/filter evidence from PMS report
            "signal_attributions": report.signal_attributions or [],
            "aggregate_attribution": report.aggregate_attribution or {},
            "analysis_dimensions": report.analysis_dimensions or {},
            "debug_max_drawdown_detail": report.debug_max_drawdown_detail,
            "debug_equity_curve_len": len(report.debug_equity_curve or []),
        }
    else:
        # Legacy report format
        summary = {
            "label": label,
            "strategy_id": strategy.id,
            "start_date": start_date,
            "end_date": end_date,
            "total_pnl": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_dd": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "wins": 0,
            "losses": 0,
        }

    # 打印摘要
    print(f"\n{label} Summary:")
    print(f"  Total PnL: {summary['total_pnl']:,.2f}")
    print(f"  Total Trades: {summary['total_trades']}")
    print(f"  Win Rate: {summary['win_rate']:.2%}")
    print(f"  Profit Factor: {summary['profit_factor']:.2f}")
    print(f"  Max DD: {summary['max_dd']:,.2f}")
    print(f"  Avg Win: {summary['avg_win']:,.2f}")
    print(f"  Avg Loss: {summary['avg_loss']:,.2f}")

    return summary


async def run_yearly_backtests(
    strategy: StrategyDefinition,
    label: str,
    gateway: ExchangeGateway,
    data_repo: HistoricalDataRepository
) -> Dict[str, Any]:
    """运行分年回测"""
    yearly_results = {}

    for year in [2023, 2024, 2025]:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        result = await run_backtest(
            strategy=strategy,
            label=f"{label} ({year})",
            start_date=start_date,
            end_date=end_date,
            gateway=gateway,
            data_repo=data_repo
        )

        yearly_results[str(year)] = result

    # 运行总区间
    total_result = await run_backtest(
        strategy=strategy,
        label=f"{label} (2023-2025)",
        start_date="2023-01-01",
        end_date="2025-12-31",
        gateway=gateway,
        data_repo=data_repo
    )

    return {
        "yearly": yearly_results,
        "total": total_result
    }


# ─── 对比分析 ────────────────────────────────────────────────────────────

def compare_results(e0_results: Dict, e1_results: Dict) -> Dict[str, Any]:
    """对比 E0 和 E1 结果"""
    e0_total = e0_results["total"]
    e1_total = e1_results["total"]

    comparison = {
        "total_pnl_diff": e1_total["total_pnl"] - e0_total["total_pnl"],
        "total_pnl_pct": (e1_total["total_pnl"] - e0_total["total_pnl"]) / abs(e0_total["total_pnl"]) * 100 if e0_total["total_pnl"] != 0 else 0,
        "trades_diff": e1_total["total_trades"] - e0_total["total_trades"],
        "trades_pct": (e1_total["total_trades"] - e0_total["total_trades"]) / e0_total["total_trades"] * 100 if e0_total["total_trades"] != 0 else 0,
        "max_dd_diff": e1_total["max_dd"] - e0_total["max_dd"],
        "win_rate_diff": e1_total["win_rate"] - e0_total["win_rate"],
        "profit_factor_diff": e1_total["profit_factor"] - e0_total["profit_factor"],
    }

    # 分年对比
    yearly_comparison = {}
    for year in ["2023", "2024", "2025"]:
        if year in e0_results["yearly"] and year in e1_results["yearly"]:
            e0_year = e0_results["yearly"][year]
            e1_year = e1_results["yearly"][year]
            yearly_comparison[year] = {
                "pnl_diff": e1_year["total_pnl"] - e0_year["total_pnl"],
                "pnl_pct": (e1_year["total_pnl"] - e0_year["total_pnl"]) / abs(e0_year["total_pnl"]) * 100 if e0_year["total_pnl"] != 0 else 0,
                "trades_diff": e1_year["total_trades"] - e0_year["total_trades"],
                "max_dd_diff": e1_year["max_dd"] - e0_year["max_dd"],
                "win_rate_diff": e1_year["win_rate"] - e0_year["win_rate"],
            }

    comparison["yearly"] = yearly_comparison

    return comparison


def evaluate_pass_criteria(e0_results: Dict, e1_results: Dict, comparison: Dict) -> Dict[str, Any]:
    """评估 PASS 标准"""
    criteria = {}

    # 1. 2023 loss reduction >= 20%
    if "2023" in comparison["yearly"]:
        y2023 = comparison["yearly"]["2023"]
        e0_2023_pnl = e0_results["yearly"]["2023"]["total_pnl"]
        e1_2023_pnl = e1_results["yearly"]["2023"]["total_pnl"]

        # 如果 E0 2023 是亏损（负 PnL），计算亏损减少比例
        if e0_2023_pnl < 0:
            loss_reduction = (e1_2023_pnl - e0_2023_pnl) / abs(e0_2023_pnl) * 100
            criteria["2023_loss_reduction"] = {
                "value": loss_reduction,
                "pass": loss_reduction >= 20,
                "description": f"2023 loss reduction: {loss_reduction:.1f}% (>= 20% required)"
            }
        else:
            criteria["2023_loss_reduction"] = {
                "value": 0,
                "pass": True,
                "description": "2023 baseline is profitable, no loss to reduce"
            }

    # 2. MaxDD 降低
    criteria["max_dd_reduction"] = {
        "value": comparison["max_dd_diff"],
        "pass": comparison["max_dd_diff"] < 0,
        "description": f"MaxDD reduction: {comparison['max_dd_diff']:,.2f} (< 0 required)"
    }

    # 3. 3yr PnL 不显著恶化
    pnl_change_pct = comparison["total_pnl_pct"]
    criteria["total_pnl"] = {
        "value": comparison["total_pnl_diff"],
        "pass": pnl_change_pct > -10,  # 允许最多 10% 恶化
        "description": f"3yr PnL change: {comparison['total_pnl_diff']:,.2f} ({pnl_change_pct:.1f}%)"
    }

    # 综合判定
    all_pass = all(c["pass"] for c in criteria.values())
    criteria["overall"] = {
        "pass": all_pass,
        "description": "PASS" if all_pass else "FAIL"
    }

    return criteria


# ─── 主函数 ──────────────────────────────────────────────────────────────

async def main():
    """主函数"""
    print("\n" + "="*80)
    print("P0: Pinbar(E4 donchian_distance) Official Backtester Validation")
    print("="*80)
    print(f"\nE4 Threshold: {E4_THRESHOLD}")
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"MTF: {MTF_TIMEFRAME}")
    print(f"Direction: LONG-only")
    print(f"\nCost Model (BNB9):")
    print(f"  Entry Slippage: {BNB9_SLIPPAGE} (0.01%)")
    print(f"  TP Slippage: {BNB9_TP_SLIPPAGE} (0%)")
    print(f"  Fee: {BNB9_FEE} (0.0405%)")
    print(f"\nRisk Config:")
    print(f"  Max Loss: {RESEARCH_RISK.max_loss_percent} (1%)")
    print(f"  Max Exposure: {RESEARCH_RISK.max_total_exposure} (2.0x)")
    print(f"\nTP/SL:")
    print(f"  TP1: {ORDER_STRATEGY.tp_targets[0]}R ({ORDER_STRATEGY.tp_ratios[0]*100}%)")
    print(f"  TP2: {ORDER_STRATEGY.tp_targets[1]}R ({ORDER_STRATEGY.tp_ratios[1]*100}%)")

    # 初始化 gateway 和 data repo
    print("\nInitializing ExchangeGateway and HistoricalDataRepository...")
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",  # Public data only
        api_secret="",
        testnet=False
    )
    await gateway.initialize()

    data_repo = HistoricalDataRepository()

    # 创建策略
    e0_strategy = create_pinbar_baseline_strategy()
    e1_strategy = create_pinbar_e4_strategy()

    print(f"\nE0 Strategy: {e0_strategy.id}")
    print(f"  Filters: EMA50 + MTF EMA60")
    print(f"\nE1 Strategy: {e1_strategy.id}")
    print(f"  Filters: EMA50 + MTF EMA60 + donchian_distance")

    # 支持度检查：确认 E1 包含 donchian_distance filter
    e1_dict = e1_strategy.model_dump()
    has_donchian = False
    if "logic_tree" in e1_dict:
        # 递归检查 logic_tree 中是否有 donchian_distance filter
        def check_donchian_in_tree(node):
            if isinstance(node, dict):
                if node.get("type") == "filter" and "config" in node:
                    config = node["config"]
                    if config.get("type") == "donchian_distance":
                        return True
                if "children" in node:
                    for child in node["children"]:
                        if check_donchian_in_tree(child):
                            return True
            return False

        has_donchian = check_donchian_in_tree(e1_dict["logic_tree"])

    assert has_donchian, "E1 strategy must contain donchian_distance filter"
    print(f"✓ E1 strategy contains donchian_distance filter")

    # ========================================
    # Phase 1: 2023 Smoke Test
    # ========================================
    print("\n" + "="*80)
    print("Phase 1: 2023 Smoke Test")
    print("="*80)
    print("\nRunning E0 (2023 smoke)...")

    e0_2023 = await run_backtest(
        strategy=e0_strategy,
        label="E0 (2023 smoke)",
        start_date="2023-01-01",
        end_date="2023-12-31",
        gateway=gateway,
        data_repo=data_repo
    )

    print("\nRunning E1 (2023 smoke)...")
    e1_2023 = await run_backtest(
        strategy=e1_strategy,
        label="E1 (2023 smoke)",
        start_date="2023-01-01",
        end_date="2023-12-31",
        gateway=gateway,
        data_repo=data_repo
    )

    # Smoke test 验证
    print("\n" + "="*80)
    print("2023 Smoke Test Validation")
    print("="*80)

    smoke_pass = True

    # 1. 确认 E0 和 E1 都有 trades
    if e0_2023["total_trades"] == 0:
        print(f"✗ E0 has 0 trades - smoke test FAILED")
        smoke_pass = False
    else:
        print(f"✓ E0 has {e0_2023['total_trades']} trades")

    if e1_2023["total_trades"] == 0:
        print(f"✗ E1 has 0 trades - smoke test FAILED")
        smoke_pass = False
    else:
        print(f"✓ E1 has {e1_2023['total_trades']} trades")

    # 2. 确认 E1 trades <= E0 trades (donchian_distance should filter some)
    if e1_2023["total_trades"] > e0_2023["total_trades"]:
        print(f"✗ E1 trades ({e1_2023['total_trades']}) > E0 trades ({e0_2023['total_trades']}) - impossible")
        smoke_pass = False
    elif e1_2023["total_trades"] == e0_2023["total_trades"]:
        print(f"⚠ E1 trades == E0 trades ({e0_2023['total_trades']}) - donchian_distance may not be filtering")
        # 不直接失败，继续检查 filter evidence
    else:
        filtered = e0_2023["total_trades"] - e1_2023["total_trades"]
        print(f"✓ E1 filtered {filtered} trades (E0: {e0_2023['total_trades']}, E1: {e1_2023['total_trades']})")

    # 3. 检查 donchian_distance rejection evidence
    # PMSBacktestReport 包含 signal_attributions / analysis_dimensions
    donchian_evidence_found = False

    # 检查 signal_attributions
    signal_attrs = e1_2023.get("signal_attributions", [])
    if signal_attrs:
        print(f"✓ E1 has signal_attributions ({len(signal_attrs)} entries)")
        # 检查是否有 donchian_distance 相关的 attribution
        for attr in signal_attrs:
            if isinstance(attr, dict):
                attr_str = str(attr)
                if "donchian_distance" in attr_str or "too_close_to_donchian" in attr_str:
                    print(f"  ✓ Found donchian_distance evidence in signal_attributions")
                    donchian_evidence_found = True
                    break

    # 检查 analysis_dimensions
    analysis_dims = e1_2023.get("analysis_dimensions", {})
    if analysis_dims and isinstance(analysis_dims, dict):
        print(f"✓ E1 has analysis_dimensions")
        analysis_str = str(analysis_dims)
        if "donchian_distance" in analysis_str or "too_close_to_donchian" in analysis_str:
            print(f"  ✓ Found donchian_distance evidence in analysis_dimensions")
            donchian_evidence_found = True

    # 检查 aggregate_attribution
    agg_attr = e1_2023.get("aggregate_attribution", {})
    if agg_attr and isinstance(agg_attr, dict):
        print(f"✓ E1 has aggregate_attribution")
        agg_str = str(agg_attr)
        if "donchian_distance" in agg_str or "too_close_to_donchian" in agg_str:
            print(f"  ✓ Found donchian_distance evidence in aggregate_attribution")
            donchian_evidence_found = True

    # 如果没有找到直接证据，输出所有可用字段供调试
    if not donchian_evidence_found:
        print(f"\n⚠ E1 does NOT have explicit donchian_distance rejection evidence")
        print(f"  Available fields: {list(e1_2023.keys())}")
        print(f"  signal_attributions count: {len(signal_attrs)}")
        print(f"  analysis_dimensions keys: {list(analysis_dims.keys()) if analysis_dims else 'None'}")
        print(f"  aggregate_attribution keys: {list(agg_attr.keys()) if agg_attr else 'None'}")

        # CRITICAL: 必须找到证据，不允许"trades 少了就谨慎继续"
        print(f"\n✗ Cannot prove donchian_distance is working - smoke test FAILED")
        smoke_pass = False

    if donchian_evidence_found:
        print(f"\n✓ E1 has donchian_distance rejection evidence - filter is working")

    if not smoke_pass:
        print("\n❌ 2023 SMOKE TEST FAILED - Stopping execution")
        print("Please check:")
        print("  1. Is mode='v3_pms' being used?")
        print("  2. Are strategies being passed correctly?")
        print("  3. Is order_strategy provided?")
        print("  4. Is donchian_distance filter enabled?")
        print("  5. Are signal_attributions/analysis_dimensions available in PMSBacktestReport?")
        await gateway.close()
        return None

    print("\n✅ 2023 SMOKE TEST PASSED - Proceeding to full backtest")

    # ========================================
    # Phase 2: Full 2023-2025 Backtest
    # ========================================
    print("\n" + "="*80)
    print("Phase 2: Full 2023-2025 Backtest")
    print("="*80)

    # 运行 E0 baseline
    print("\nRunning E0: Pinbar Baseline (2023-2025)...")
    e0_results = await run_yearly_backtests(e0_strategy, "E0", gateway, data_repo)

    # 运行 E1 with donchian_distance
    print("\nRunning E1: Pinbar + E4 Donchian Distance (2023-2025)...")
    e1_results = await run_yearly_backtests(e1_strategy, "E1", gateway, data_repo)

    # 对比结果
    comparison = compare_results(e0_results, e1_results)

    # 评估 PASS 标准
    criteria = evaluate_pass_criteria(e0_results, e1_results, comparison)

    # 打印对比
    print("\n" + "="*80)
    print("Comparison: E1 vs E0")
    print("="*80)
    print(f"\nTotal PnL: {comparison['total_pnl_diff']:,.2f} ({comparison['total_pnl_pct']:.1f}%)")
    print(f"Total Trades: {comparison['trades_diff']} ({comparison['trades_pct']:.1f}%)")
    print(f"MaxDD: {comparison['max_dd_diff']:,.2f}")
    print(f"Win Rate: {comparison['win_rate_diff']:.2%}")
    print(f"Profit Factor: {comparison['profit_factor_diff']:.2f}")

    print("\nYearly Comparison:")
    for year, stats in comparison["yearly"].items():
        print(f"  {year}: PnL={stats['pnl_diff']:,.2f} ({stats['pnl_pct']:.1f}%), Trades={stats['trades_diff']}, MaxDD={stats['max_dd_diff']:,.2f}")

    print("\n" + "="*80)
    print("PASS Criteria Evaluation")
    print("="*80)
    for key, criterion in criteria.items():
        if key != "overall":
            status = "✓" if criterion["pass"] else "✗"
            print(f"{status} {criterion['description']}")

    print(f"\nOverall: {criteria['overall']['description']}")

    # 保存结果
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "e4_threshold": E4_THRESHOLD,
        "e0_results": e0_results,
        "e1_results": e1_results,
        "comparison": comparison,
        "criteria": criteria,
    }

    output_path = REPORT_DIR / f"p0_pinbar_e4_official_validation_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    # 关闭 gateway
    await gateway.close()

    return output


if __name__ == "__main__":
    asyncio.run(main())
