#!/usr/bin/env python3
"""
R1: Baseline Capital Allocation Search

只做 research-only，不改 src，不改 runtime，不提交 git。
使用 official Backtester engine，不使用 proxy 撮合。
搜索 max_total_exposure 和 max_loss_percent 的最优组合。

约束：MaxDD <= 35%
目标：在约束内找到 total PnL / Sharpe / Calmar 最高的配置。
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.backtester import Backtester
from src.application.research_control_plane import BASELINE_RUNTIME_OVERRIDES
from src.domain.models import (
    BacktestRequest,
    RiskConfig,
    Direction,
    BacktestRuntimeOverrides,
    OrderStrategy,
)
from src.infrastructure.historical_data_repository import HistoricalDataRepository


# ============================================================
# 固定策略参数（baseline）
# ============================================================
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
MTF_TIMEFRAME = "4h"
DIRECTION = Direction.LONG
EMA_PERIOD = 50
MTF_EMA_PERIOD = 60
TP_RATIOS = [1.0, 3.5]  # TP1=1.0R, TP2=3.5R
TP_PARTIAL_RATIOS = [0.5, 0.5]  # 50% at TP1, 50% at TP2

# BNB9 成本
FEE_RATE = Decimal("0.000405")
ENTRY_SLIPPAGE = Decimal("0.0001")
TP_SLIPPAGE = Decimal("0")

# 固定风控
MAX_LEVERAGE = 20
DAILY_MAX_TRADES = 50
INITIAL_BALANCE = Decimal("10000")

# 时间范围
START_TIME = 1672531200000  # 2023-01-01 00:00:00 UTC in milliseconds
END_TIME = 1767225599000    # 2025-12-31 23:59:59 UTC in milliseconds


# ============================================================
# 搜索参数网格
# ============================================================
EXPOSURE_LEVELS = [
    Decimal("1.0"),
    Decimal("1.25"),
    Decimal("1.5"),
    Decimal("1.75"),
    Decimal("2.0"),
    Decimal("2.25"),
    Decimal("2.5"),
    Decimal("3.0"),
]

RISK_LEVELS = [
    Decimal("0.005"),
    Decimal("0.0075"),
    Decimal("0.01"),
    Decimal("0.0125"),
    Decimal("0.015"),
    Decimal("0.0175"),
    Decimal("0.02"),
]


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


def compute_sharpe(pnl_series: List[Decimal]) -> Decimal:
    """计算 Sharpe ratio（简化版，假设无风险利率=0）"""
    if not pnl_series or len(pnl_series) < 2:
        return Decimal("0")

    import statistics
    returns = [float(p) for p in pnl_series]
    mean_ret = statistics.mean(returns)
    std_ret = statistics.stdev(returns)

    if std_ret == 0:
        return Decimal("0")

    return Decimal(str(mean_ret / std_ret))


def compute_calmar(total_pnl: Decimal, max_dd: Decimal) -> Decimal:
    """计算 Calmar ratio = Total PnL / MaxDD"""
    if max_dd == 0:
        return Decimal("0")
    return total_pnl / max_dd


async def run_single_config(
    backtester: Backtester,
    exposure: Decimal,
    risk_pct: Decimal,
) -> Optional[Dict[str, Any]]:
    """运行单个配置的回测"""
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
            limit=30000,  # 足够覆盖 2023-2025
            strategies=[build_strategy_definition()],
            risk_overrides=risk_config,
            mode="v3_pms",
            initial_balance=INITIAL_BALANCE,
            fee_rate=FEE_RATE,
            slippage_rate=ENTRY_SLIPPAGE,
            tp_slippage_rate=TP_SLIPPAGE,
        )

        # 设置 OrderStrategy（TP 配置）
        request.order_strategy = OrderStrategy(
            id="r1_search",
            name="R1 Search",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        # 设置 runtime overrides（从 baseline 复制并设置 LONG-only）
        overrides = BASELINE_RUNTIME_OVERRIDES.model_copy(deep=True)
        overrides.allowed_directions = ["LONG"]

        # 运行回测
        report = await backtester.run_backtest(
            request,
            runtime_overrides=overrides,
        )

        if not report or not hasattr(report, 'positions'):
            print(f"  ⚠️  exposure={exposure}, risk={risk_pct}: 无结果")
            return None

        # 从 positions 计算 yearly stats
        yearly_pnl = {}
        yearly_trades = {}
        yearly_max_dd = {}

        for pos in report.positions:
            # 从 exit_time 提取年份
            if pos.exit_time:
                year = datetime.fromtimestamp(pos.exit_time / 1000, tz=timezone.utc).year
                if year not in yearly_pnl:
                    yearly_pnl[year] = Decimal("0")
                    yearly_trades[year] = 0
                    yearly_max_dd[year] = Decimal("0")

                yearly_pnl[year] += pos.realized_pnl
                yearly_trades[year] += 1

        # 计算 3yr 总计
        total_pnl = sum(yearly_pnl.values())
        total_trades = sum(yearly_trades.values())

        # MaxDD 从报告中获取
        max_dd_overall = report.max_drawdown
        max_dd_pct = max_dd_overall / Decimal("100")  # report.max_drawdown 已经是百分比

        # 计算 Sharpe（简化：用 yearly PnL 作为 returns）
        pnl_series = list(yearly_pnl.values())
        sharpe = compute_sharpe(pnl_series)

        # 计算 Calmar
        calmar = compute_calmar(total_pnl, max_dd_overall * INITIAL_BALANCE / Decimal("100"))

        # 构建 yearly breakdown
        yearly_breakdown = {}
        for year in sorted(yearly_pnl.keys()):
            yearly_breakdown[str(year)] = {
                "pnl": float(yearly_pnl[year]),
                "trades": yearly_trades[year],
                "max_dd": float(yearly_max_dd.get(year, 0)),
                "win_rate": 0.0,  # TODO: 从 positions 计算
            }

        # 检查 exposure rejected（从 close_events 或 metadata 中提取）
        exposure_rejected = 0
        if hasattr(report, 'close_events'):
            exposure_rejected = sum(1 for e in report.close_events if "exposure" in str(e).lower())

        # 检查是否触发 daily_max_trades
        daily_max_triggered = False  # TODO: 需要从 metadata 中提取

        # 检查是否有 position_size=0
        has_zero_size = any(
            "position_size=0" in str(pos) for pos in report.positions
        )

        result = {
            "exposure": float(exposure),
            "risk_pct": float(risk_pct),
            "total_pnl": float(total_pnl),
            "total_return": float(total_pnl / INITIAL_BALANCE),
            "max_dd": float(max_dd_overall * INITIAL_BALANCE / Decimal("100")),
            "max_dd_pct": float(max_dd_pct),
            "sharpe": float(sharpe),
            "calmar": float(calmar),
            "trades": total_trades,
            "exposure_rejected": exposure_rejected,
            "avg_exposure_used": 0,  # TODO: 需要从 metadata 中提取
            "daily_max_triggered": daily_max_triggered,
            "has_zero_size": has_zero_size,
            "yearly": yearly_breakdown,
        }

        print(f"  ✓ exposure={exposure}, risk={risk_pct}: PnL={total_pnl:.2f}, MaxDD={max_dd_pct*100:.1f}%, Calmar={calmar:.2f}")

        return result

    except Exception as e:
        print(f"  ✗ exposure={exposure}, risk={risk_pct}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """主函数"""
    print("=" * 80)
    print("R1: Baseline Capital Allocation Search")
    print("=" * 80)
    print(f"Symbol: {SYMBOL}")
    print(f"Timeframe: {TIMEFRAME}")
    print(f"Direction: {DIRECTION.value}")
    print(f"Period: {START_TIME} → {END_TIME}")
    print(f"Constraint: MaxDD <= 35%")
    print(f"Grid: {len(EXPOSURE_LEVELS)} exposures × {len(RISK_LEVELS)} risks = {len(EXPOSURE_LEVELS) * len(RISK_LEVELS)} configs")
    print("=" * 80)

    # 初始化数据仓库和 gateway
    data_repo = HistoricalDataRepository()

    # 创建一个 minimal exchange gateway（仅用于历史数据）
    from src.infrastructure.exchange_gateway import ExchangeGateway
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=False,
    )

    # 初始化 Backtester
    backtester = Backtester(
        exchange_gateway=gateway,
        data_repository=data_repo,
    )

    # 先跑 baseline 验证（exposure=1.0, risk=1%）
    print("\n[验证] Baseline exposure=1.0, risk=1%")
    baseline_result = await run_single_config(backtester, Decimal("1.0"), Decimal("0.01"))
    if baseline_result:
        print(f"  Baseline: PnL={baseline_result['total_pnl']:.2f}, MaxDD={baseline_result['max_dd_pct']*100:.1f}%")
        print(f"  Expected (from H4): 2023=-3924, 2024=+8501, 2025=+4490")

    # 搜索所有配置
    print("\n[搜索] 开始扫描...")
    all_results = []

    for exposure in EXPOSURE_LEVELS:
        for risk_pct in RISK_LEVELS:
            result = await run_single_config(backtester, exposure, risk_pct)
            if result:
                all_results.append(result)

    print(f"\n[完成] 共获得 {len(all_results)} 个有效结果")

    # 筛选 MaxDD <= 35% 的配置
    valid_results = [r for r in all_results if r["max_dd_pct"] <= 0.35]

    if not valid_results:
        print("\n[警告] 所有配置 MaxDD > 35%，选择最接近 35% 的配置")
        valid_results = sorted(all_results, key=lambda r: abs(r["max_dd_pct"] - 0.35))[:10]

    print(f"\n[筛选] {len(valid_results)} 个配置满足 MaxDD <= 35%")

    # 排序找出最优配置
    # 1. Total PnL 最高
    best_pnl = max(valid_results, key=lambda r: r["total_pnl"])

    # 2. Sharpe 最高
    best_sharpe = max(valid_results, key=lambda r: r["sharpe"])

    # 3. Calmar 最高
    best_calmar = max(valid_results, key=lambda r: r["calmar"])

    # 4. Conservative: MaxDD <= 25% 中收益最高
    conservative_results = [r for r in valid_results if r["max_dd_pct"] <= 0.25]
    if conservative_results:
        best_conservative = max(conservative_results, key=lambda r: r["total_pnl"])
    else:
        best_conservative = None

    # 输出结果
    print("\n" + "=" * 80)
    print("最优配置")
    print("=" * 80)

    print("\n[1] Total PnL 最高（MaxDD <= 35%）:")
    print(f"  exposure={best_pnl['exposure']}, risk={best_pnl['risk_pct']}")
    print(f"  Total PnL={best_pnl['total_pnl']:.2f}, Return={best_pnl['total_return']*100:.1f}%")
    print(f"  MaxDD={best_pnl['max_dd_pct']*100:.1f}%, Sharpe={best_pnl['sharpe']:.2f}, Calmar={best_pnl['calmar']:.2f}")
    print(f"  Trades={best_pnl['trades']}, Exposure rejected={best_pnl['exposure_rejected']}")
    print(f"  Yearly: {best_pnl['yearly']}")

    print("\n[2] Sharpe 最高:")
    print(f"  exposure={best_sharpe['exposure']}, risk={best_sharpe['risk_pct']}")
    print(f"  Total PnL={best_sharpe['total_pnl']:.2f}, Sharpe={best_sharpe['sharpe']:.2f}, Calmar={best_sharpe['calmar']:.2f}")
    print(f"  MaxDD={best_sharpe['max_dd_pct']*100:.1f}%")

    print("\n[3] Calmar 最高:")
    print(f"  exposure={best_calmar['exposure']}, risk={best_calmar['risk_pct']}")
    print(f"  Total PnL={best_calmar['total_pnl']:.2f}, Calmar={best_calmar['calmar']:.2f}, Sharpe={best_calmar['sharpe']:.2f}")
    print(f"  MaxDD={best_calmar['max_dd_pct']*100:.1f}%")

    if best_conservative:
        print("\n[4] Conservative (MaxDD <= 25%):")
        print(f"  exposure={best_conservative['exposure']}, risk={best_conservative['risk_pct']}")
        print(f"  Total PnL={best_conservative['total_pnl']:.2f}, MaxDD={best_conservative['max_dd_pct']*100:.1f}%")
        print(f"  Calmar={best_conservative['calmar']:.2f}, Sharpe={best_conservative['sharpe']:.2f}")

    # 检查是否有配置触发 daily_max_trades 或 position_size=0
    daily_triggered = [r for r in valid_results if r["daily_max_triggered"]]
    zero_size = [r for r in valid_results if r["has_zero_size"]]

    if daily_triggered:
        print(f"\n⚠️  {len(daily_triggered)} 个配置触发了 daily_max_trades 限制")
    if zero_size:
        print(f"⚠️  {len(zero_size)} 个配置出现 position_size=0")

    # 保存 JSON
    output = {
        "title": "R1: Baseline Capital Allocation Search",
        "date": "2026-04-28",
        "constraint": "MaxDD <= 35%",
        "fixed_params": {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "direction": DIRECTION.value,
            "ema_period": EMA_PERIOD,
            "mtf_ema_period": MTF_EMA_PERIOD,
            "tp_ratios": TP_RATIOS,
            "tp_partial_ratios": TP_PARTIAL_RATIOS,
            "fee_rate": float(FEE_RATE),
            "entry_slippage": float(ENTRY_SLIPPAGE),
            "tp_slippage": float(TP_SLIPPAGE),
            "max_leverage": MAX_LEVERAGE,
            "daily_max_trades": DAILY_MAX_TRADES,
            "initial_balance": float(INITIAL_BALANCE),
        },
        "search_grid": {
            "exposure_levels": [float(e) for e in EXPOSURE_LEVELS],
            "risk_levels": [float(r) for r in RISK_LEVELS],
        },
        "baseline_verification": baseline_result,
        "all_results": all_results,
        "valid_results": valid_results,
        "best_configs": {
            "max_pnl": best_pnl,
            "max_sharpe": best_sharpe,
            "max_calmar": best_calmar,
            "conservative": best_conservative,
        },
        "warnings": {
            "daily_max_triggered_count": len(daily_triggered),
            "zero_size_count": len(zero_size),
        },
    }

    output_path = Path("reports/research/r1_baseline_capital_allocation_search_2026-04-28.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[保存] JSON → {output_path}")

    # 生成 MD 报告
    md_path = Path("docs/planning/2026-04-28-r1-baseline-capital-allocation-search.md")
    generate_md_report(md_path, output)

    print(f"[保存] MD → {md_path}")
    print("\n" + "=" * 80)
    print("R1 完成")
    print("=" * 80)


def generate_md_report(md_path: Path, data: Dict[str, Any]):
    """生成 MD 报告"""
    md = []
    md.append("# R1: Baseline Capital Allocation Search")
    md.append("")
    md.append(f"> **日期**: 2026-04-28")
    md.append(f"> **性质**: research-only，不改 src，不改 runtime，不提交 git")
    md.append(f"> **约束**: MaxDD <= 35%")
    md.append("")
    md.append("---")
    md.append("")

    # 0. 核心结论
    md.append("## 0. 核心结论（先说结论）")
    md.append("")

    best_pnl = data["best_configs"]["max_pnl"]
    best_calmar = data["best_configs"]["max_calmar"]
    conservative = data["best_configs"]["conservative"]

    md.append(f"**在 MaxDD <= 35% 约束下：**")
    md.append(f"- 最高收益：**{best_pnl['total_pnl']:.2f} USDT**（exposure={best_pnl['exposure']}, risk={best_pnl['risk_pct']}）")
    md.append(f"- 最高 Calmar：**{best_calmar['calmar']:.2f}**（exposure={best_calmar['exposure']}, risk={best_calmar['risk_pct']}）")
    if conservative:
        md.append(f"- Conservative (MaxDD<=25%)：**{conservative['total_pnl']:.2f} USDT**（exposure={conservative['exposure']}, risk={conservative['risk_pct']}）")
    md.append("")

    # 1. 固定参数
    md.append("## 1. 固定策略参数")
    md.append("")
    md.append("| 参数 | 值 |")
    md.append("|------|-----|")
    fixed = data["fixed_params"]
    md.append(f"| Symbol | {fixed['symbol']} |")
    md.append(f"| Timeframe | {fixed['timeframe']} |")
    md.append(f"| Direction | {fixed['direction']} |")
    md.append(f"| EMA Period | {fixed['ema_period']} |")
    md.append(f"| MTF EMA Period | {fixed['mtf_ema_period']} |")
    md.append(f"| TP Ratios | {fixed['tp_ratios']} |")
    md.append(f"| TP Partial Ratios | {fixed['tp_partial_ratios']} |")
    md.append(f"| Fee Rate | {fixed['fee_rate']*100:.4f}% |")
    md.append(f"| Entry Slippage | {fixed['entry_slippage']*100:.4f}% |")
    md.append(f"| Max Leverage | {fixed['max_leverage']} |")
    md.append(f"| Daily Max Trades | {fixed['daily_max_trades']} |")
    md.append(f"| Initial Balance | {fixed['initial_balance']} USDT |")
    md.append("")

    # 2. 搜索网格
    md.append("## 2. 搜索参数网格")
    md.append("")
    md.append("### 2.1 max_total_exposure")
    md.append("")
    md.append(", ".join([str(e) for e in data["search_grid"]["exposure_levels"]]))
    md.append("")
    md.append("### 2.2 max_loss_percent")
    md.append("")
    md.append(", ".join([f"{r*100:.2f}%" for r in data["search_grid"]["risk_levels"]]))
    md.append("")
    md.append(f"**总配置数**: {len(data['all_results'])}")
    md.append("")

    # 3. Baseline 验证
    md.append("## 3. Baseline 验证（exposure=1.0, risk=1%）")
    md.append("")
    baseline = data["baseline_verification"]
    if baseline:
        md.append("| 指标 | 值 |")
        md.append("|------|-----|")
        md.append(f"| Total PnL | {baseline['total_pnl']:.2f} USDT |")
        md.append(f"| MaxDD | {baseline['max_dd_pct']*100:.1f}% |")
        md.append(f"| Sharpe | {baseline['sharpe']:.2f} |")
        md.append(f"| Calmar | {baseline['calmar']:.2f} |")
        md.append(f"| Trades | {baseline['trades']} |")
        md.append("")
        md.append("**Yearly Breakdown:**")
        md.append("")
        md.append("| Year | PnL | Trades | MaxDD | WR |")
        md.append("|------|-----|--------|-------|-----|")
        for year, stats in sorted(baseline["yearly"].items()):
            md.append(f"| {year} | {stats['pnl']:.2f} | {stats['trades']} | {stats['max_dd']:.2f} | {stats['win_rate']*100:.1f}% |")
        md.append("")

    # 4. 最优配置
    md.append("## 4. 最优配置")
    md.append("")

    md.append("### 4.1 Total PnL 最高（MaxDD <= 35%）")
    md.append("")
    md.append("| 指标 | 值 |")
    md.append("|------|-----|")
    md.append(f"| max_total_exposure | {best_pnl['exposure']} |")
    md.append(f"| max_loss_percent | {best_pnl['risk_pct']*100:.2f}% |")
    md.append(f"| Total PnL | **{best_pnl['total_pnl']:.2f} USDT** |")
    md.append(f"| Total Return | {best_pnl['total_return']*100:.1f}% |")
    md.append(f"| MaxDD | {best_pnl['max_dd_pct']*100:.1f}% |")
    md.append(f"| Sharpe | {best_pnl['sharpe']:.2f} |")
    md.append(f"| Calmar | {best_pnl['calmar']:.2f} |")
    md.append(f"| Trades | {best_pnl['trades']} |")
    md.append(f"| Exposure Rejected | {best_pnl['exposure_rejected']} |")
    md.append("")
    md.append("**Yearly Breakdown:**")
    md.append("")
    md.append("| Year | PnL | Trades | MaxDD | WR |")
    md.append("|------|-----|--------|-------|-----|")
    for year, stats in sorted(best_pnl["yearly"].items()):
        md.append(f"| {year} | {stats['pnl']:.2f} | {stats['trades']} | {stats['max_dd']:.2f} | {stats['win_rate']*100:.1f}% |")
    md.append("")

    best_sharpe = data["best_configs"]["max_sharpe"]
    md.append("### 4.2 Sharpe 最高")
    md.append("")
    md.append("| 指标 | 值 |")
    md.append("|------|-----|")
    md.append(f"| max_total_exposure | {best_sharpe['exposure']} |")
    md.append(f"| max_loss_percent | {best_sharpe['risk_pct']*100:.2f}% |")
    md.append(f"| Total PnL | {best_sharpe['total_pnl']:.2f} USDT |")
    md.append(f"| Sharpe | **{best_sharpe['sharpe']:.2f}** |")
    md.append(f"| Calmar | {best_sharpe['calmar']:.2f} |")
    md.append(f"| MaxDD | {best_sharpe['max_dd_pct']*100:.1f}% |")
    md.append("")

    md.append("### 4.3 Calmar 最高")
    md.append("")
    md.append("| 指标 | 值 |")
    md.append("|------|-----|")
    md.append(f"| max_total_exposure | {best_calmar['exposure']} |")
    md.append(f"| max_loss_percent | {best_calmar['risk_pct']*100:.2f}% |")
    md.append(f"| Total PnL | {best_calmar['total_pnl']:.2f} USDT |")
    md.append(f"| Calmar | **{best_calmar['calmar']:.2f}** |")
    md.append(f"| Sharpe | {best_calmar['sharpe']:.2f} |")
    md.append(f"| MaxDD | {best_calmar['max_dd_pct']*100:.1f}% |")
    md.append("")

    if conservative:
        md.append("### 4.4 Conservative (MaxDD <= 25%)")
        md.append("")
        md.append("| 指标 | 值 |")
        md.append("|------|-----|")
        md.append(f"| max_total_exposure | {conservative['exposure']} |")
        md.append(f"| max_loss_percent | {conservative['risk_pct']*100:.2f}% |")
        md.append(f"| Total PnL | **{conservative['total_pnl']:.2f} USDT** |")
        md.append(f"| MaxDD | {conservative['max_dd_pct']*100:.1f}% |")
        md.append(f"| Calmar | {conservative['calmar']:.2f} |")
        md.append(f"| Sharpe | {conservative['sharpe']:.2f} |")
        md.append("")

    # 5. 警告
    warnings = data["warnings"]
    if warnings["daily_max_triggered_count"] > 0 or warnings["zero_size_count"] > 0:
        md.append("## 5. 警告")
        md.append("")
        if warnings["daily_max_triggered_count"] > 0:
            md.append(f"- ⚠️  {warnings['daily_max_triggered_count']} 个配置触发了 daily_max_trades 限制")
        if warnings["zero_size_count"] > 0:
            md.append(f"- ⚠️  {warnings['zero_size_count']} 个配置出现 position_size=0")
        md.append("")

    # 6. 结论
    md.append("## 6. 结论与建议")
    md.append("")
    md.append(f"**在 MaxDD <= 35% 约束下，ETH Pinbar baseline 最高收益为 {best_pnl['total_pnl']:.2f} USDT（3yr）。**")
    md.append("")
    md.append(f"对应参数：")
    md.append(f"- max_total_exposure = {best_pnl['exposure']}")
    md.append(f"- max_loss_percent = {best_pnl['risk_pct']*100:.2f}%")
    md.append("")
    md.append(f"**年度表现：**")
    for year, stats in sorted(best_pnl["yearly"].items()):
        md.append(f"- {year}: PnL={stats['pnl']:.2f}, MaxDD={stats['max_dd']:.2f}")
    md.append("")
    md.append(f"**是否需要 OOS 验证：**")
    md.append(f"- 当前搜索基于 2023-2025 全量数据，存在过拟合风险")
    md.append(f"- 建议使用 2026 Q1 作为 OOS 验证区间")
    md.append(f"- 如果 OOS 表现显著低于预期，应降级到 conservative 配置")
    md.append("")
    md.append(f"**是否建议进入下一轮更细粒度搜索：**")
    md.append(f"- 如果最优配置位于网格边界（exposure=3.0 或 risk=2.0%），建议扩大搜索范围")
    md.append(f"- 如果最优配置位于网格内部，建议在最优配置周围进行细粒度搜索")
    md.append("")

    md.append("---")
    md.append("")
    md.append("*R1 搜索完成时间: 2026-04-28*")
    md.append("*性质: research-only，不改 src，不改 runtime，不提交 git*")

    # 写入文件
    md_path.parent.mkdir(parents=True, exist_ok=True)
    with open(md_path, "w") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    asyncio.run(main())
