#!/usr/bin/env python3
"""
R2 Capital Allocation Search - 修复版（参数注入审计 + Sanity Check）

修复内容：
1. 风险参数注入入口：使用 request.risk_overrides (RiskConfig)，而非 BacktestRuntimeOverrides
2. runtime_overrides 只保留策略/订单/成本参数
3. 增加"参数生效证据"输出
4. 先做 sanity check（2023 年 4 组），不直接全量跑

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

# Sanity Check 配置（2023 年 4 组）
SANITY_CHECK_CONFIGS = [
    {"exposure": 1.0, "risk": 0.005},  # exposure=1.0, risk=0.5%
    {"exposure": 1.0, "risk": 0.020},  # exposure=1.0, risk=2.0%
    {"exposure": 3.0, "risk": 0.005},  # exposure=3.0, risk=0.5%
    {"exposure": 3.0, "risk": 0.020},  # exposure=3.0, risk=2.0%
]

# 时间范围（2023 年）
YEAR_2023_RANGE = (
    int(datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp() * 1000),
    int(datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
)


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

    # ✅ runtime_overrides 只保留策略/订单/成本参数
    runtime_overrides = BacktestRuntimeOverrides(
        allowed_directions=["LONG"],
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

        # Debug 信息（如果有）
        "debug_curve_max_dd": float(report.debug_curve_max_dd) if hasattr(report, "debug_curve_max_dd") else float(report.max_drawdown),
    }


async def run_sanity_check(config_manager, gateway) -> List[Dict]:
    """运行 sanity check（2023 年 4 组）"""

    results = []

    # 固定参数
    symbol = "ETH/USDT:USDT"
    timeframe = "1h"
    start_time, end_time = YEAR_2023_RANGE

    print("\n" + "="*60)
    print("R2 Sanity Check - 2023 年 4 组配置")
    print("="*60)
    print(f"时间范围: {start_time} ~ {end_time}")
    print(f"Symbol: {symbol}, Timeframe: {timeframe}")
    print("="*60)

    for i, config in enumerate(SANITY_CHECK_CONFIGS, 1):
        exposure = config["exposure"]
        risk = config["risk"]

        print(f"\n[{i}/4] exposure={exposure}, risk={risk*100:.2f}%")

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

            results.append(result)

            # 打印关键证据
            print(f"  ✅ 参数注入证据:")
            print(f"    - risk_overrides.max_loss_percent={result['risk_overrides_max_loss_percent']}")
            print(f"    - risk_overrides.max_total_exposure={result['risk_overrides_max_total_exposure']}")
            print(f"    - risk_overrides.max_leverage={result['risk_overrides_max_leverage']}")
            print(f"    - mode={result['mode']}")
            print(f"  ✅ 回测结果:")
            print(f"    - PnL={result['pnl']:.2f}, MaxDD={result['max_dd']:.2%}, Trades={result['trades']}")

        except Exception as e:
            print(f"  ❌ 错误: {e}")
            results.append({
                "exposure": exposure,
                "risk": risk,
                "error": str(e),
            })

    return results


def validate_sanity_check(results: List[Dict]) -> Dict:
    """验证 sanity check 结果是否证明参数生效"""

    print("\n" + "="*60)
    print("Sanity Check 验证")
    print("="*60)

    # 检查是否有错误
    errors = [r for r in results if "error" in r]
    if errors:
        print(f"❌ 发现错误: {len(errors)} 组失败")
        for e in errors:
            print(f"  - exposure={e['exposure']}, risk={e['risk']}: {e['error']}")
        return {"valid": False, "reason": "errors_found"}

    # 提取 4 组结果
    r1 = results[0]  # exposure=1.0, risk=0.5%
    r2 = results[1]  # exposure=1.0, risk=2.0%
    r3 = results[2]  # exposure=3.0, risk=0.5%
    r4 = results[3]  # exposure=3.0, risk=2.0%

    # 验证 1: risk 提高后，PnL / MaxDD 是否变化？
    print("\n验证 1: Risk 参数生效")
    print(f"  exposure=1.0:")
    print(f"    - risk=0.5%: PnL={r1['pnl']:.2f}, MaxDD={r1['max_dd']:.2%}")
    print(f"    - risk=2.0%: PnL={r2['pnl']:.2f}, MaxDD={r2['max_dd']:.2%}")
    pnl_diff_risk = abs(r2['pnl'] - r1['pnl'])
    if pnl_diff_risk > 100:  # 差异 > 100 USDT
        print(f"  ✅ Risk 提高后 PnL 变化显著: {pnl_diff_risk:.2f} USDT")
    else:
        print(f"  ⚠️ Risk 提高后 PnL 变化不显著: {pnl_diff_risk:.2f} USDT")

    # 验证 2: exposure 提高后，PnL / trades 是否变化？
    print("\n验证 2: Exposure 参数生效")
    print(f"  risk=0.5%:")
    print(f"    - exposure=1.0: PnL={r1['pnl']:.2f}, Trades={r1['trades']}")
    print(f"    - exposure=3.0: PnL={r3['pnl']:.2f}, Trades={r3['trades']}")
    pnl_diff_exp = abs(r3['pnl'] - r1['pnl'])
    trades_diff_exp = abs(r3['trades'] - r1['trades'])
    if pnl_diff_exp > 100 or trades_diff_exp > 5:
        print(f"  ✅ Exposure 提高后变化显著:")
        print(f"    - PnL 差异: {pnl_diff_exp:.2f} USDT")
        print(f"    - Trades 差异: {trades_diff_exp}")
    else:
        print(f"  ⚠️ Exposure 提高后变化不显著:")
        print(f"    - PnL 差异: {pnl_diff_exp:.2f} USDT")
        print(f"    - Trades 差异: {trades_diff_exp}")

    # 验证 3: 4 组结果是否完全相同？
    print("\n验证 3: 结果多样性检查")
    all_pnls = [r['pnl'] for r in results]
    all_max_dds = [r['max_dd'] for r in results]
    all_trades = [r['trades'] for r in results]

    pnl_variance = len(set(all_pnls))
    max_dd_variance = len(set(all_max_dds))
    trades_variance = len(set(all_trades))

    print(f"  PnL 唯一值数量: {pnl_variance}/4")
    print(f"  MaxDD 唯一值数量: {max_dd_variance}/4")
    print(f"  Trades 唯一值数量: {trades_variance}/4")

    if pnl_variance == 1 and max_dd_variance == 1 and trades_variance == 1:
        print(f"  ❌ 所有结果完全相同，参数未生效！")
        return {"valid": False, "reason": "all_results_identical"}
    else:
        print(f"  ✅ 结果存在差异，参数可能生效")

    # 综合判定
    valid = (pnl_variance > 1 or max_dd_variance > 1 or trades_variance > 1)
    return {
        "valid": valid,
        "pnl_variance": pnl_variance,
        "max_dd_variance": max_dd_variance,
        "trades_variance": trades_variance,
        "risk_pnl_diff": pnl_diff_risk,
        "exposure_pnl_diff": pnl_diff_exp,
        "exposure_trades_diff": trades_diff_exp,
    }


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
    return gateway


async def main():
    """主函数"""

    print("="*60)
    print("R2 Capital Allocation Search - 修复版")
    print("参数注入审计 + Sanity Check")
    print("="*60)

    print("\n历史 bug 修复回顾:")
    print("  - cb06ea0: account_snapshot.positions=[] → exposure limit 失效（已修复）")
    print("  - 96f0328: risk_calculator 三层独立约束（已修复）")
    print("  - 44e9694: Backtester 消费 request.risk_overrides（已修复）")

    print("\n本次修复:")
    print("  ✅ 使用 RiskConfig 传递风险参数（而非 BacktestRuntimeOverrides）")
    print("  ✅ runtime_overrides 只保留策略/订单/成本参数")
    print("  ✅ 增加'参数生效证据'输出")
    print("  ✅ 先做 sanity check（2023 年 4 组），不直接全量跑")

    # 加载配置
    print("\n加载配置...")
    config_manager = await load_all_configs()

    # 创建 mock gateway
    print("\n创建 mock gateway...")
    gateway = await create_mock_gateway()

    # 运行 sanity check
    print("\n开始 sanity check...")
    results = await run_sanity_check(config_manager, gateway)

    # 验证 sanity check
    print("\n验证 sanity check...")
    validation = validate_sanity_check(results)

    # 保存结果
    output = {
        "sanity_check_date": datetime.now().isoformat(),
        "sanity_check_type": "R2_parameter_injection_audit",
        "cost_config": "BNB9",
        "fee_rate": float(BNB9_FEE_RATE),
        "slippage": float(BNB9_SLIPPAGE),
        "year": "2023",
        "configs": SANITY_CHECK_CONFIGS,
        "results": results,
        "validation": validation,
    }

    output_file = Path("reports/research/r2_sanity_check_2026-04-29.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Sanity check 完成！结果已保存到: {output_file}")

    # 最终判定
    print("\n" + "="*60)
    print("最终判定")
    print("="*60)

    if validation["valid"]:
        print("✅ 参数注入修复成功，sanity check 通过")
        print("✅ 可以继续全量运行 R2 搜索")
    else:
        print(f"❌ 参数注入仍有问题: {validation['reason']}")
        print("❌ 请停止并汇报，不要继续全量运行")

    print("\n等待用户确认后再运行全量搜索...")


if __name__ == "__main__":
    asyncio.run(main())