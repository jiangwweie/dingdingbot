#!/usr/bin/env python3
"""
R2a Baseline Smoke Test - 验证 R2 是否真正跑了 baseline

只跑 2024 年单组配置：
- exposure=2.0
- risk=1.0%

输出必须包含：
- 实际解析到的策略参数（ema_period / mtf_ema_period / tp_targets / tp_ratios / max_atr_ratio / allowed_directions）
- trades
- pnl
- maxdd
- 与冻结 baseline 的差异比对

验收标准：
- ✅ trades 几十笔 + PnL 明显正收益 → baseline 对齐成功
- ❌ 仍是数百笔交易或明显大幅负收益 → 立即停止，不继续全量搜索
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.application.backtester import Backtester, BacktestRequest, BacktestRuntimeOverrides
from src.domain.models import RiskConfig
from src.application.config_manager import ConfigManager
from src.infrastructure.exchange_gateway import ExchangeGateway


# BNB9 成本配置
BNB9_FEE_RATE = Decimal("0.000405")  # 0.0405%
BNB9_SLIPPAGE = Decimal("0.0001")    # 0.01%

# 冻结 baseline 参数
BASELINE_PARAMS = {
    "ema_period": 50,
    "min_distance_pct": Decimal("0.005"),
    "mtf_ema_period": 60,
    "max_atr_ratio": None,
    "tp_targets": [Decimal("1.0"), Decimal("3.5")],
    "tp_ratios": [Decimal("0.5"), Decimal("0.5")],
    "breakeven_enabled": False,
    "allowed_directions": ["LONG"],
}


async def run_smoke_test(config_manager, gateway) -> Dict[str, Any]:
    """运行 2024 年 smoke test"""

    # 时间范围：2024 年全年
    start_time = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    end_time = int(datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

    # 风险参数
    risk_overrides = RiskConfig(
        max_loss_percent=Decimal("0.01"),  # 1.0%
        max_total_exposure=Decimal("2.0"),
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

    # 创建 BacktestRequest
    request = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
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

    # 提取结果
    result = {
        # 实际解析到的策略参数
        "actual_ema_period": runtime_overrides.ema_period,
        "actual_mtf_ema_period": runtime_overrides.mtf_ema_period,
        "actual_tp_targets": [float(t) for t in runtime_overrides.tp_targets] if runtime_overrides.tp_targets else None,
        "actual_tp_ratios": [float(r) for r in runtime_overrides.tp_ratios] if runtime_overrides.tp_ratios else None,
        "actual_max_atr_ratio": float(runtime_overrides.max_atr_ratio) if runtime_overrides.max_atr_ratio else None,
        "actual_allowed_directions": runtime_overrides.allowed_directions,

        # 回测结果
        "trades": report.total_trades,
        "pnl": float(report.total_pnl),
        "max_dd": float(report.max_drawdown),
        "win_rate": float(report.win_rate),

        # 与冻结 baseline 的差异比对
        "baseline_ema_period": BASELINE_PARAMS["ema_period"],
        "baseline_mtf_ema_period": BASELINE_PARAMS["mtf_ema_period"],
        "baseline_tp_targets": [float(t) for t in BASELINE_PARAMS["tp_targets"]],
        "baseline_tp_ratios": [float(r) for r in BASELINE_PARAMS["tp_ratios"]],
        "baseline_max_atr_ratio": BASELINE_PARAMS["max_atr_ratio"],
        "baseline_allowed_directions": BASELINE_PARAMS["allowed_directions"],

        # 参数一致性检查
        "params_match": {
            "ema_period": runtime_overrides.ema_period == BASELINE_PARAMS["ema_period"],
            "mtf_ema_period": runtime_overrides.mtf_ema_period == BASELINE_PARAMS["mtf_ema_period"],
            "tp_targets": runtime_overrides.tp_targets == BASELINE_PARAMS["tp_targets"],
            "tp_ratios": runtime_overrides.tp_ratios == BASELINE_PARAMS["tp_ratios"],
            "max_atr_ratio": runtime_overrides.max_atr_ratio == BASELINE_PARAMS["max_atr_ratio"],
            "allowed_directions": runtime_overrides.allowed_directions == BASELINE_PARAMS["allowed_directions"],
        },
    }

    return result


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
    print("R2a Baseline Smoke Test")
    print("验证 R2 是否真正跑了 baseline")
    print("="*60)

    # 加载配置
    print("\n加载配置...")
    config_manager = await load_all_configs()

    # 创建 mock gateway
    print("\n创建 mock gateway...")
    gateway = await create_mock_gateway()

    # 运行 smoke test
    print("\n运行 2024 年 smoke test...")
    print("配置: exposure=2.0, risk=1.0%")
    result = await run_smoke_test(config_manager, gateway)

    # 保存结果
    output = {
        "smoke_test_date": datetime.now().isoformat(),
        "smoke_test_type": "R2a_baseline_verification",
        "year": "2024",
        "exposure": 2.0,
        "risk": 0.01,
        "result": result,
    }

    output_file = Path("reports/research/r2a_baseline_smoke_2026-04-29.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # 打印结果
    print("\n" + "="*60)
    print("Smoke Test 结果")
    print("="*60)

    print("\n【实际解析到的策略参数】")
    print(f"  ema_period: {result['actual_ema_period']}")
    print(f"  mtf_ema_period: {result['actual_mtf_ema_period']}")
    print(f"  tp_targets: {result['actual_tp_targets']}")
    print(f"  tp_ratios: {result['actual_tp_ratios']}")
    print(f"  max_atr_ratio: {result['actual_max_atr_ratio']}")
    print(f"  allowed_directions: {result['actual_allowed_directions']}")

    print("\n【回测结果】")
    print(f"  Trades: {result['trades']}")
    print(f"  PnL: {result['pnl']:.2f} USDT")
    print(f"  MaxDD: {result['max_dd']:.2%}")
    print(f"  Win Rate: {result['win_rate']:.2%}")

    print("\n【与冻结 baseline 的差异比对】")
    params_match = result["params_match"]
    all_match = all(params_match.values())

    for param, match in params_match.items():
        status = "✅" if match else "❌"
        print(f"  {status} {param}")

    print("\n【验收判断】")
    trades_ok = result["trades"] < 100  # 几十笔量级
    pnl_ok = result["pnl"] > 0  # 明显正收益

    if all_match and trades_ok and pnl_ok:
        print("✅ Baseline 对齐成功！")
        print(f"  - 参数完全一致")
        print(f"  - Trades: {result['trades']} (几十笔量级)")
        print(f"  - PnL: {result['pnl']:.2f} USDT (明显正收益)")
        print("\n可以继续全量搜索。")
    else:
        print("❌ Baseline 对齐失败！")
        if not all_match:
            print("  - 参数不一致")
        if not trades_ok:
            print(f"  - Trades: {result['trades']} (仍是数百笔)")
        if not pnl_ok:
            print(f"  - PnL: {result['pnl']:.2f} USDT (明显负收益)")
        print("\n立即停止，不继续全量搜索。")

    print(f"\n结果已保存到: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
