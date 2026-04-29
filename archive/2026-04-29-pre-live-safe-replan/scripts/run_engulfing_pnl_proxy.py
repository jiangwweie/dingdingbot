#!/usr/bin/env python3
"""
H5b: Engulfing PnL Proxy
验证 Engulfing + EMA50 + MTF EMA60 在完整成本和简化撮合下是否存在可交易 alpha

约束：
- research-only
- 不改 src 核心代码
- 不改 runtime profile
- 不进入 sim runtime
- 不新增 ATR
- 不做参数搜索

实验组：
E0：Pinbar baseline，对照
E1：Engulfing LONG-only，TP=[1.0, 3.5]，S1 stop
E2：Engulfing SHORT-only，TP=[1.0, 3.5]，S1 stop
E3：Engulfing LONG+SHORT shadow，TP=[1.0, 3.5]，S1 stop
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import (
    BacktestRequest,
    OrderStrategy,
    BacktestRuntimeOverrides,
    RiskConfig,
)

DB_PATH = "data/v3_dev.db"

# BNB9 成本口径
COST_CONFIG = {
    "slippage_rate": Decimal("0.0001"),
    "tp_slippage_rate": Decimal("0"),
    "fee_rate": Decimal("0.000405"),
    "initial_balance": Decimal("10000"),
}

# TP 配置：对齐 ETH baseline，TP1@1R (50%), TP2@3.5R (50%)
ORDER_STRATEGY = {
    "id": "dual_tp_h5b",
    "name": "Dual TP (H5b)",
    "tp_levels": 2,
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "initial_stop_loss_rr": Decimal("-1.0"),
    "trailing_stop_enabled": False,
    "oco_enabled": True,
}

# Research baseline 风险口径
RESEARCH_RISK_CONFIG = {
    "max_loss_percent": Decimal("0.01"),
    "max_leverage": 20,
    "max_total_exposure": Decimal("2.0"),
    "daily_max_trades": 50,
}


class EngulfingPnLProxy:
    """Engulfing PnL Proxy 分析器"""

    def __init__(self):
        self.repo = None
        self.backtester = None

    async def setup(self):
        self.repo = HistoricalDataRepository(DB_PATH)
        await self.repo.initialize()
        self.backtester = Backtester(None, data_repository=self.repo)

    async def teardown(self):
        if self.repo:
            await self.repo.close()

    def build_pinbar_strategy(self) -> List[Dict]:
        """构建 Pinbar baseline 策略配置"""
        return [{
            "name": "pinbar",
            "triggers": [{"type": "pinbar", "enabled": True}],
            "filters": [
                {"type": "ema_trend", "enabled": True, "params": {"period": 50}},
                {"type": "mtf", "enabled": True, "params": {"ema_period": 60}},
            ]
        }]

    def build_engulfing_strategy(self, allowed_directions: List[str]) -> List[Dict]:
        """构建 Engulfing 策略配置"""
        return [{
            "name": f"engulfing_{'_'.join(allowed_directions).lower()}",
            "triggers": [{"type": "engulfing", "enabled": True, "params": {"max_wick_ratio": 0.6}}],
            "filters": [
                {"type": "ema_trend", "enabled": True, "params": {"period": 50}},
                {"type": "mtf", "enabled": True, "params": {"ema_period": 60}},
            ]
        }]

    async def run_single_backtest(
        self,
        year: int,
        strategy_config: List[Dict],
        experiment_name: str,
        allowed_directions: List[str],
    ) -> Dict:
        """运行单次回测"""
        start_ts = int(datetime(year, 1, 1).timestamp() * 1000)
        end_ts = int(datetime(year, 12, 31, 23, 59, 59).timestamp() * 1000)

        request = BacktestRequest(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            limit=10000,
            start_time=start_ts,
            end_time=end_ts,
            strategies=strategy_config,
            risk_overrides=RiskConfig(
                max_loss_percent=RESEARCH_RISK_CONFIG["max_loss_percent"],
                max_leverage=RESEARCH_RISK_CONFIG["max_leverage"],
                max_total_exposure=RESEARCH_RISK_CONFIG["max_total_exposure"],
                daily_max_trades=RESEARCH_RISK_CONFIG["daily_max_trades"],
            ),
            order_strategy=OrderStrategy(**ORDER_STRATEGY),
            mode="v3_pms",
            **COST_CONFIG,
        )

        runtime_overrides = BacktestRuntimeOverrides(
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            breakeven_enabled=False,
            allowed_directions=allowed_directions,
        )

        report = await self.backtester.run_backtest(
            request,
            runtime_overrides=runtime_overrides,
        )

        # 提取详细统计
        stats = {
            "year": year,
            "experiment": experiment_name,
            "total_pnl": float(report.total_pnl),
            "total_trades": report.total_trades,
            "winning_trades": report.winning_trades,
            "losing_trades": report.losing_trades,
            "win_rate": float(report.win_rate * 100),
            "max_drawdown": float(report.max_drawdown * 100),
            "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
            "initial_balance": float(report.initial_balance),
            "final_balance": float(report.final_balance),
            "total_return": float(report.total_return * 100),
            "total_fees": float(report.total_fees_paid),
            "total_slippage": float(report.total_slippage_cost),
            # TP/SL breakdown
            "tp1_count": 0,
            "tp2_count": 0,
            "sl_count": 0,
            "tp1_pct": 0.0,
            "tp2_pct": 0.0,
            "sl_pct": 0.0,
            # Signal vs Trade
            "signal_fired_count": 0,
            "exposure_rejected_count": 0,
            # Holding time
            "avg_holding_hours": 0.0,
            # LONG/SHORT breakdown
            "long_trades": 0,
            "short_trades": 0,
            "long_pnl": 0.0,
            "short_pnl": 0.0,
        }

        # 从报告中提取更详细的统计（如果可用）
        if hasattr(report, 'trade_breakdown') and report.trade_breakdown:
            breakdown = report.trade_breakdown
            stats["tp1_count"] = breakdown.get("tp1_count", 0)
            stats["tp2_count"] = breakdown.get("tp2_count", 0)
            stats["sl_count"] = breakdown.get("sl_count", 0)
            stats["tp1_pct"] = 100 * stats["tp1_count"] / report.total_trades if report.total_trades > 0 else 0
            stats["tp2_pct"] = 100 * stats["tp2_count"] / report.total_trades if report.total_trades > 0 else 0
            stats["sl_pct"] = 100 * stats["sl_count"] / report.total_trades if report.total_trades > 0 else 0

        if hasattr(report, 'signal_stats') and report.signal_stats:
            stats["signal_fired_count"] = report.signal_stats.get("fired", 0)
            stats["exposure_rejected_count"] = report.signal_stats.get("exposure_rejected", 0)

        if hasattr(report, 'holding_time_stats') and report.holding_time_stats:
            stats["avg_holding_hours"] = report.holding_time_stats.get("avg_hours", 0.0)

        if hasattr(report, 'direction_breakdown') and report.direction_breakdown:
            stats["long_trades"] = report.direction_breakdown.get("long_count", 0)
            stats["short_trades"] = report.direction_breakdown.get("short_count", 0)
            stats["long_pnl"] = report.direction_breakdown.get("long_pnl", 0.0)
            stats["short_pnl"] = report.direction_breakdown.get("short_pnl", 0.0)

        return stats

    async def run_experiment(
        self,
        experiment_name: str,
        strategy_config: List[Dict],
        allowed_directions: List[str],
        years: List[int] = [2023, 2024, 2025],
    ) -> Dict[int, Dict]:
        """运行实验（多年）"""
        print(f"\n{'='*70}")
        print(f"实验: {experiment_name}")
        print(f"{'='*70}")

        yearly_stats = {}

        for year in years:
            print(f"\n--- {year} ---")
            stats = await self.run_single_backtest(
                year,
                strategy_config,
                experiment_name,
                allowed_directions,
            )
            yearly_stats[year] = stats

            print(f"PnL: {stats['total_pnl']:.2f} USDT")
            print(f"Trades: {stats['total_trades']}, WR: {stats['win_rate']:.2f}%")
            print(f"Sharpe: {stats['sharpe_ratio']:.4f}, MaxDD: {stats['max_drawdown']:.2f}%")
            if stats['tp1_count'] > 0 or stats['tp2_count'] > 0 or stats['sl_count'] > 0:
                print(f"TP1: {stats['tp1_pct']:.1f}%, TP2: {stats['tp2_pct']:.1f}%, SL: {stats['sl_pct']:.1f}%")
            if stats['long_trades'] > 0 or stats['short_trades'] > 0:
                print(f"LONG: {stats['long_trades']} ({stats['long_pnl']:.2f}), SHORT: {stats['short_trades']} ({stats['short_pnl']:.2f})")
            if stats['avg_holding_hours'] > 0:
                print(f"Avg Hold: {stats['avg_holding_hours']:.1f}h")

        return yearly_stats

    def print_summary(self, all_results: Dict[str, Dict[int, Dict]]):
        """打印汇总报告"""
        print("\n" + "="*70)
        print("H5b Engulfing PnL Proxy 汇总")
        print("="*70)

        for exp_name, yearly_stats in all_results.items():
            print(f"\n{'-'*70}")
            print(f"实验: {exp_name}")
            print(f"{'-'*70}")

            # 年度统计
            total_pnl = 0.0
            total_trades = 0
            total_winning = 0

            for year, stats in sorted(yearly_stats.items()):
                total_pnl += stats["total_pnl"]
                total_trades += stats["total_trades"]
                total_winning += stats["winning_trades"]

                print(f"{year}: PnL={stats['total_pnl']:8.2f}, "
                      f"Trades={stats['total_trades']:3d}, "
                      f"WR={stats['win_rate']:5.1f}%, "
                      f"Sharpe={stats['sharpe_ratio']:6.4f}, "
                      f"MaxDD={stats['max_drawdown']:5.2f}%")

            # 总计
            avg_wr = 100 * total_winning / total_trades if total_trades > 0 else 0

            print(f"\n3yr 总计: PnL={total_pnl:.2f}, Trades={total_trades}, WR={avg_wr:.1f}%")

            # 决策判定
            print(f"\n决策判定:")
            if total_pnl < -1000:
                print(f"❌ 3yr PnL 明显为负 ({total_pnl:.2f} < -1000)，关闭 Engulfing 主线")
            elif abs(total_pnl) < 500:
                print(f"⚠️  3yr PnL 接近 0 ({total_pnl:.2f})，需检查年度分布")
                # 检查 2023 是否有改善
                pnl_2023 = yearly_stats.get(2023, {}).get("total_pnl", 0)
                pnl_2024 = yearly_stats.get(2024, {}).get("total_pnl", 0)
                pnl_2025 = yearly_stats.get(2025, {}).get("total_pnl", 0)

                if pnl_2023 > pnl_2024 and pnl_2023 > pnl_2025:
                    print(f"   2023 有明显改善 (PnL={pnl_2023:.2f})，保留为组合候选，不进 runtime")
            elif total_pnl > 1000:
                print(f"✅ 3yr PnL 为正 ({total_pnl:.2f} > 1000)，有研究价值")

                # 检查 LONG vs SHORT
                long_pnl = sum(stats.get("long_pnl", 0) for stats in yearly_stats.values())
                short_pnl = sum(stats.get("short_pnl", 0) for stats in yearly_stats.values())

                if "LONG-only" in exp_name and long_pnl > 0:
                    print(f"   LONG-only 为正 ({long_pnl:.2f})，可进入组合研究")
                elif "SHORT-only" in exp_name and short_pnl > 0:
                    print(f"   SHORT-only 为正 ({short_pnl:.2f})，可进入 SHORT shadow 研究")

                # 检查 MaxDD
                max_dd = max(stats["max_drawdown"] for stats in yearly_stats.values())
                if max_dd > 30:
                    print(f"   ⚠️  MaxDD 较高 ({max_dd:.2f}%)，需风险口径复核，不进 runtime")
            else:
                print(f"⚠️  3yr PnL 中等 ({total_pnl:.2f})，需进一步分析")


async def main():
    proxy = EngulfingPnLProxy()
    try:
        await proxy.setup()
        results = {}

        # E0: Pinbar baseline
        print("\n" + "="*70)
        print("E0: Pinbar Baseline (对照组)")
        print("="*70)
        results["E0: Pinbar baseline"] = await proxy.run_experiment(
            "E0: Pinbar + EMA50 + MTF",
            proxy.build_pinbar_strategy(),
            ["LONG"],
        )

        # E1: Engulfing LONG-only
        results["E1: Engulfing LONG-only"] = await proxy.run_experiment(
            "E1: Engulfing + EMA50 + MTF + LONG-only",
            proxy.build_engulfing_strategy(["LONG"]),
            ["LONG"],
        )

        # E2: Engulfing SHORT-only
        results["E2: Engulfing SHORT-only"] = await proxy.run_experiment(
            "E2: Engulfing + EMA50 + MTF + SHORT-only",
            proxy.build_engulfing_strategy(["SHORT"]),
            ["SHORT"],
        )

        # E3: Engulfing LONG+SHORT
        results["E3: Engulfing LONG+SHORT"] = await proxy.run_experiment(
            "E3: Engulfing + EMA50 + MTF + LONG/SHORT",
            proxy.build_engulfing_strategy(["LONG", "SHORT"]),
            ["LONG", "SHORT"],
        )

        proxy.print_summary(results)

    finally:
        await proxy.teardown()


if __name__ == "__main__":
    asyncio.run(main())
