#!/usr/bin/env python3
"""
R2 Capital Allocation Search - 修复版（参数注入审计 + 全量搜索）

修复内容：
1. 风险参数注入入口：使用 request.risk_overrides (RiskConfig)，而非 BacktestRuntimeOverrides
2. runtime_overrides 只保留策略/订单/成本参数
3. 增加"参数生效证据"输出
4. 全量运行 168 组（2023/2024/2025 各 56 组）

历史 bug 修复回顾：
- cb06ea0: PMS 回测 account_snapshot.positions=[] → exposure limit 失效（已修复）
- 96f0328: risk_calculator exposure constraint 三层独立约束重构（已修复）
- 44e9694: Backtester 消费 request.risk_overrides（已修复）
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.backtester import Backtester, BacktestRequest, BacktestRuntimeOverrides
from src.domain.models import RiskConfig
from src.application.config_manager import ConfigManager
from src.infrastructure.exchange_gateway import ExchangeGateway


# BNB9 成本配置
BNB9_FEE_RATE = Decimal("0.000405")  # 0.0405%
BNB9_SLIPPAGE = Decimal("0.0001")    # 0.01%

# 搜索网格
EXPOSURE_LEVELS = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
RISK_LEVELS = [0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175, 0.02]  # 0.5% - 2.0%

# 时间范围（时间戳，毫秒）
YEAR_RANGES = {
    "2023": (
        int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
        int(datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    ),
    "2024": (
        int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
        int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    ),
    "2025": (
        int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
        int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
    ),
}


async def run_single_config(
    symbol: str,
    timeframe: str,
    start_time: int,
    end_time: int,
    exposure: float,
    risk: float,
    config_manager,
    gateway,
) -> Dict[str, Any]:
    """运行单个配置的回测（修复版）"""

    # ✅ 修复：使用 RiskConfig 传递风险参数
    risk_overrides = RiskConfig(
        max_loss_percent=Decimal(str(risk)),
        max_total_exposure=Decimal(str(exposure)),
        max_leverage=20,
        daily_max_trades=50,
    )

    # ✅ runtime_overrides 显式锁定 baseline 策略参数
    runtime_overrides = BacktestRuntimeOverrides(
        # 策略参数（baseline 锁定）
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        mtf_ema_period=60,
        max_atr_ratio=None,  # ATR 移除

        # 订单参数（baseline 锁定）
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        breakeven_enabled=False,

        # 诊断参数
        allowed_directions=["LONG"],

        # 成本参数
        fee_rate=BNB9_FEE_RATE,
        slippage_rate=BNB9_SLIPPAGE,
        tp_slippage_rate=Decimal("0"),
    )

    # ✅ 创建 BacktestRequest（风险参数通过 risk_overrides 传递）
    request = BacktestRequest(
        symbol=symbol,
        timeframe=timeframe,
        start_time=start_time,
        end_time=end_time,
        mode="v3_pms",
        risk_overrides=risk_overrides,
    )

    # 创建 Backtester
    backtester = Backtester(
        exchange_gateway=gateway,
        config_manager=config_manager,
    )

    # 运行回测
    report = await backtester.run_backtest(
        request=request,
        runtime_overrides=runtime_overrides,
    )

    # ✅ 提取关键指标 + 参数生效证据
    return {
        # 参数证据
        "risk_overrides_max_loss_percent": float(risk_overrides.max_loss_percent),
        "risk_overrides_max_total_exposure": float(risk_overrides.max_total_exposure),
        "risk_overrides_max_leverage": risk_overrides.max_leverage,
        "mode": request.mode,
        "allowed_directions": runtime_overrides.allowed_directions,

        # 回测结果
        "exposure": exposure,
        "risk": risk,
        "pnl": float(report.total_pnl),
        "max_dd": float(report.max_drawdown),
        "trades": report.total_trades,
        "win_rate": float(report.win_rate),
        "profit_factor": float(report.profit_factor) if hasattr(report, "profit_factor") else 0.0,
        "debug_curve_max_dd": float(report.debug_curve_max_dd) if hasattr(report, "debug_curve_max_dd") else float(report.max_drawdown),
    }


async def run_yearly_search(config_manager, gateway) -> Dict[str, List[Dict]]:
    """运行年度独立搜索"""

    results = {"2023": [], "2024": [], "2025": []}

    # 固定参数（复用 R0）
    symbol = "ETH/USDT:USDT"
    timeframe = "1h"

    total_configs = len(EXPOSURE_LEVELS) * len(RISK_LEVELS)
    current = 0

    for year, (start_time, end_time) in YEAR_RANGES.items():
        print(f"\n{'='*60}")
        print(f"搜索 {year} 年最优配置...")
        print(f"时间范围: {start_time} ~ {end_time} (时间戳)")
        print(f"{'='*60}")

        for exposure in EXPOSURE_LEVELS:
            for risk in RISK_LEVELS:
                current += 1
                print(f"\n[{current}/{total_configs * 3}] {year} | exposure={exposure}, risk={risk*100:.2f}%")

                try:
                    result = await run_single_config(
                        symbol=symbol,
                        timeframe=timeframe,
                        start_time=start_time,
                        end_time=end_time,
                        exposure=exposure,
                        risk=risk,
                        config_manager=config_manager,
                        gateway=gateway,
                    )

                    results[year].append(result)
                    print(f"  PnL: {result['pnl']:.2f}, MaxDD: {result['max_dd']:.2%}, Trades: {result['trades']}")

                except Exception as e:
                    print(f"  ❌ 错误: {e}")
                    results[year].append({
                        "exposure": exposure,
                        "risk": risk,
                        "error": str(e),
                    })

    return results


def find_yearly_optimal(results: Dict[str, List[Dict]], max_dd_threshold: float = 0.50) -> Dict:
    """找到每年最优配置（MaxDD <= 50%）"""

    yearly_optimal = {}

    for year, configs in results.items():
        print(f"\n{'='*60}")
        print(f"{year} 年最优配置筛选...")
        print(f"{'='*60}")

        # 过滤可行配置（MaxDD <= 50%）
        feasible = [
            c for c in configs
            if "error" not in c and c["debug_curve_max_dd"] <= max_dd_threshold
        ]

        print(f"总配置数: {len(configs)}")
        print(f"可行配置: {len(feasible)} (MaxDD <= {max_dd_threshold*100:.0f}%)")

        if not feasible:
            print(f"⚠️ {year} 年没有可行配置！")
            yearly_optimal[year] = None
            continue

        # 按 PnL 排序
        feasible.sort(key=lambda x: x["pnl"], reverse=True)

        # 最优配置
        optimal = feasible[0]
        yearly_optimal[year] = optimal

        print(f"\n最优配置:")
        print(f"  exposure: {optimal['exposure']}")
        print(f"  risk: {optimal['risk']*100:.2f}%")
        print(f"  PnL: {optimal['pnl']:.2f} USDT")
        print(f"  MaxDD: {optimal['debug_curve_max_dd']:.2%}")
        print(f"  Trades: {optimal['trades']}")

        # Top 3 配置
        print(f"\nTop 3 配置:")
        for i, c in enumerate(feasible[:3], 1):
            print(f"  {i}. exposure={c['exposure']}, risk={c['risk']*100:.2f}%, "
                  f"PnL={c['pnl']:.2f}, MaxDD={c['debug_curve_max_dd']:.2%}")

    return yearly_optimal


def validate_exposure_effectiveness(results: Dict[str, List[Dict]]) -> Dict:
    """验证 exposure 参数是否生效"""

    validation = {}

    for year, configs in results.items():
        print(f"\n{'='*60}")
        print(f"{year} 年 Exposure 参数验证...")
        print(f"{'='*60}")

        # 对比 exposure=1.0 vs exposure=3.0（相同 risk）
        for risk in RISK_LEVELS:
            config_1_0 = next(
                (c for c in configs if c["exposure"] == 1.0 and c["risk"] == risk and "error" not in c),
                None
            )
            config_3_0 = next(
                (c for c in configs if c["exposure"] == 3.0 and c["risk"] == risk and "error" not in c),
                None
            )

            if config_1_0 and config_3_0:
                pnl_diff = config_3_0["pnl"] - config_1_0["pnl"]
                pnl_diff_pct = (pnl_diff / abs(config_1_0["pnl"]) * 100) if config_1_0["pnl"] != 0 else 0

                print(f"  risk={risk*100:.2f}%: "
                      f"exposure=1.0 PnL={config_1_0['pnl']:.2f}, "
                      f"exposure=3.0 PnL={config_3_0['pnl']:.2f}, "
                      f"差异={pnl_diff:.2f} ({pnl_diff_pct:+.1f}%)")

                key = f"{year}_risk_{risk*100:.2f}"
                validation[key] = {
                    "year": year,
                    "risk": risk,
                    "exposure_1_0_pnl": config_1_0["pnl"],
                    "exposure_3_0_pnl": config_3_0["pnl"],
                    "pnl_diff": pnl_diff,
                    "pnl_diff_pct": pnl_diff_pct,
                }

    return validation


async def load_all_configs() -> ConfigManager:
    """加载所有配置"""
    config_manager = ConfigManager()
    await config_manager.initialize_from_db()
    return config_manager


async def create_mock_gateway() -> ExchangeGateway:
    """创建 mock exchange gateway（用于回测）"""
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=True,
    )
    # 不需要初始化，因为只用于回测
    return gateway


async def main():
    """主函数"""

    print("="*60)
    print("R2 Capital Allocation Search")
    print("使用修复后的 risk_calculator.py（三层独立约束）")
    print("每年独立核算，BNB9 成本配置")
    print("="*60)

    # 加载配置
    print("\n加载配置...")
    config_manager = await load_all_configs()

    # 创建 mock gateway
    print("\n创建 mock gateway...")
    gateway = await create_mock_gateway()

    # 运行搜索
    print("\n开始搜索...")
    results = await run_yearly_search(config_manager, gateway)

    # 找到每年最优配置
    print("\n筛选最优配置...")
    yearly_optimal = find_yearly_optimal(results)

    # 验证 exposure 参数
    print("\n验证 exposure 参数...")
    validation = validate_exposure_effectiveness(results)

    # 保存结果
    output = {
        "search_date": datetime.now().isoformat(),
        "search_type": "R2_yearly_independent",
        "cost_config": "BNB9",
        "fee_rate": float(BNB9_FEE_RATE),
        "slippage": float(BNB9_SLIPPAGE),
        "exposure_levels": EXPOSURE_LEVELS,
        "risk_levels": [r * 100 for r in RISK_LEVELS],  # 转为百分比
        "yearly_results": results,
        "yearly_optimal": yearly_optimal,
        "exposure_validation": validation,
    }

    output_file = Path("reports/research/r2_capital_allocation_search_2026-04-29.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 搜索完成！结果已保存到: {output_file}")

    # 打印年度最优配置汇总
    print("\n" + "="*60)
    print("年度最优配置汇总")
    print("="*60)

    for year in ["2023", "2024", "2025"]:
        if yearly_optimal[year]:
            opt = yearly_optimal[year]
            print(f"\n{year} 年:")
            print(f"  exposure: {opt['exposure']}")
            print(f"  risk: {opt['risk']*100:.2f}%")
            print(f"  PnL: {opt['pnl']:.2f} USDT")
            print(f"  MaxDD: {opt['debug_curve_max_dd']:.2%}")
            print(f"  Trades: {opt['trades']}")
        else:
            print(f"\n{year} 年: 无可行配置")


if __name__ == "__main__":
    asyncio.run(main())
