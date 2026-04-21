#!/usr/bin/env python3
"""
ETH/USDT:USDT 1h 样本外验证 (Out-of-Sample Validation)

验证 Optuna 最优参数在 2025 年数据上的泛化能力。

测试参数组：
1. 最优参数: max_atr_ratio=0.0082, min_distance_pct=0.0055, ema_period=151
2. 邻近参数 A: max_atr_ratio=0.0085, min_distance_pct=0.0054, ema_period=152
3. 邻近参数 B: max_atr_ratio=0.0090, min_distance_pct=0.0054, ema_period=151
4. 邻近参数 C: max_atr_ratio=0.0088, min_distance_pct=0.0058, ema_period=155
"""
import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    RiskConfig,
    OrderStrategy,
)
from src.application.backtester import Backtester
from src.infrastructure.historical_data_repository import HistoricalDataRepository


# ============================================================
# 配置参数
# ============================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"

# 2025 年样本外时间范围
START_TIME = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_TIME = int(datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)

# stress 口径成本参数
SLIPPAGE_RATE = Decimal("0.001")
TP_SLIPPAGE_RATE = Decimal("0.0005")
FEE_RATE = Decimal("0.0004")
INITIAL_BALANCE = Decimal("10000")

# 固定参数
TP_RATIOS = [Decimal("0.6"), Decimal("0.4")]
TP_TARGETS = [Decimal("1.0"), Decimal("2.5")]
BREAKEVEN_ENABLED = False

# 测试参数组
PARAMETER_SETS = [
    {
        "name": "最优参数",
        "max_atr_ratio": Decimal("0.0082"),
        "min_distance_pct": Decimal("0.0055"),
        "ema_period": 151,
    },
    {
        "name": "邻近参数 A",
        "max_atr_ratio": Decimal("0.0085"),
        "min_distance_pct": Decimal("0.0054"),
        "ema_period": 152,
    },
    {
        "name": "邻近参数 B",
        "max_atr_ratio": Decimal("0.0090"),
        "min_distance_pct": Decimal("0.0054"),
        "ema_period": 151,
    },
    {
        "name": "邻近参数 C",
        "max_atr_ratio": Decimal("0.0088"),
        "min_distance_pct": Decimal("0.0058"),
        "ema_period": 155,
    },
]

DB_PATH = "data/v3_dev.db"


async def run_single_backtest(
    backtester: Backtester,
    params: dict,
) -> dict:
    """运行单次回测并返回关键指标"""

    # 构建请求
    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_TIME,
        end_time=END_TIME,
        limit=9000,
        mode="v3_pms",
        slippage_rate=SLIPPAGE_RATE,
        tp_slippage_rate=TP_SLIPPAGE_RATE,
        fee_rate=FEE_RATE,
        initial_balance=INITIAL_BALANCE,
    )

    # 运行时参数覆盖
    runtime_overrides = BacktestRuntimeOverrides(
        max_atr_ratio=params["max_atr_ratio"],
        min_distance_pct=params["min_distance_pct"],
        ema_period=params["ema_period"],
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        breakeven_enabled=BREAKEVEN_ENABLED,
    )

    # 订单策略
    request.order_strategy = OrderStrategy(
        id="oos_validation",
        name="OOS Validation Strategy",
        tp_levels=2,
        tp_ratios=TP_RATIOS,
        tp_targets=TP_TARGETS,
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    # 风险配置
    request.risk_overrides = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
    )

    # 运行回测
    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    # 提取关键指标
    return {
        "name": params["name"],
        "max_atr_ratio": float(params["max_atr_ratio"]),
        "min_distance_pct": float(params["min_distance_pct"]),
        "ema_period": params["ema_period"],
        "total_pnl": float(report.total_pnl),
        "total_trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,  # 转为百分比
        "max_drawdown": float(report.max_drawdown) * 100,  # 转为百分比
        "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "total_return": float(report.total_return) * 100,  # 转为百分比
    }


async def main():
    """主函数"""
    print("=" * 80)
    print("ETH/USDT:USDT 1h 样本外验证 (2025)")
    print("=" * 80)

    print(f"\n配置:")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  时间范围: 2025-01-01 ~ 2025-12-31")
    print(f"  成本口径: stress (slippage={SLIPPAGE_RATE}, tp_slippage={TP_SLIPPAGE_RATE}, fee={FEE_RATE})")
    print(f"  初始资金: {INITIAL_BALANCE} USDT")

    print(f"\n固定参数:")
    print(f"  TP ratios: {TP_RATIOS}")
    print(f"  TP targets: {TP_TARGETS}")
    print(f"  Breakeven: {BREAKEVEN_ENABLED}")

    print(f"\n测试参数组 ({len(PARAMETER_SETS)} 组):")
    for i, params in enumerate(PARAMETER_SETS, 1):
        print(f"  [{i}] {params['name']}:")
        print(f"      max_atr_ratio={float(params['max_atr_ratio']):.4f}, "
              f"min_distance_pct={float(params['min_distance_pct']):.4f}, "
              f"ema_period={params['ema_period']}")

    # 初始化组件
    print("\n初始化组件...")
    data_repo = HistoricalDataRepository(DB_PATH)
    await data_repo.initialize()

    backtester = Backtester(
        exchange_gateway=None,
        data_repository=data_repo,
    )

    # 运行所有参数组
    results = []
    for i, params in enumerate(PARAMETER_SETS, 1):
        print(f"\n[{i}/{len(PARAMETER_SETS)}] 测试 {params['name']}...")
        result = await run_single_backtest(backtester, params)
        results.append(result)

        print(f"  完成: PnL={result['total_pnl']:.2f} USDT, "
              f"Trades={result['total_trades']}, "
              f"WinRate={result['win_rate']:.2f}%, "
              f"Sharpe={result['sharpe_ratio']:.4f}")

    # 输出结果对比表
    print("\n" + "=" * 80)
    print("样本外验证结果对比 (2025)")
    print("=" * 80)

    # 表头
    print(f"\n{'参数组':<15} {'PnL (USDT)':<12} {'Trades':<8} {'WinRate':<10} "
          f"{'MaxDD':<10} {'Sharpe':<10} {'Return':<10}")
    print("-" * 80)

    # 数据行
    for r in results:
        print(f"{r['name']:<15} {r['total_pnl']:>10.2f}   {r['total_trades']:>6}   "
              f"{r['win_rate']:>7.2f}%  {r['max_drawdown']:>7.2f}%  "
              f"{r['sharpe_ratio']:>8.4f}  {r['total_return']:>7.2f}%")

    # 参数详情
    print("\n" + "=" * 80)
    print("参数详情")
    print("=" * 80)
    print(f"\n{'参数组':<15} {'max_atr':<10} {'min_dist':<10} {'ema':<8}")
    print("-" * 50)
    for r in results:
        print(f"{r['name']:<15} {r['max_atr_ratio']:>8.4f}  {r['min_distance_pct']:>8.4f}  "
              f"{r['ema_period']:>6}")

    # 泛化能力分析
    print("\n" + "=" * 80)
    print("泛化能力分析")
    print("=" * 80)

    # 统计正收益数量
    positive_pnl = [r for r in results if r['total_pnl'] > 0]
    print(f"\n1. 正收益参数组: {len(positive_pnl)}/{len(results)}")

    # 最优参数表现
    best_result = results[0]  # 第一组是最优参数
    print(f"\n2. 最优参数在 2025 表现:")
    print(f"   - 总收益: {best_result['total_pnl']:.2f} USDT ({best_result['total_return']:.2f}%)")
    print(f"   - 夏普比率: {best_result['sharpe_ratio']:.4f}")
    print(f"   - 交易次数: {best_result['total_trades']}")
    print(f"   - 胜率: {best_result['win_rate']:.2f}%")
    print(f"   - 最大回撤: {best_result['max_drawdown']:.2f}%")

    if best_result['total_pnl'] > 0:
        print("   ✅ 仍为正收益，具备泛化能力")
    else:
        print("   ❌ 负收益，泛化能力存疑")

    # 邻近参数表现
    print(f"\n3. 邻近参数表现:")
    neighbor_results = results[1:]
    neighbor_positive = [r for r in neighbor_results if r['total_pnl'] > 0]

    if len(neighbor_positive) == len(neighbor_results):
        print("   ✅ 所有邻近参数均为正收益，稳定区间成立")
    elif len(neighbor_positive) >= len(neighbor_results) * 0.5:
        print(f"   ⚠️  {len(neighbor_positive)}/{len(neighbor_results)} 邻近参数为正收益，部分稳定")
    else:
        print(f"   ❌ 仅 {len(neighbor_positive)}/{len(neighbor_results)} 邻近参数为正收益，稳定性不足")

    # 平均性能
    avg_sharpe = sum(r['sharpe_ratio'] for r in results) / len(results)
    avg_return = sum(r['total_return'] for r in results) / len(results)
    print(f"\n4. 整体平均性能:")
    print(f"   - 平均夏普比率: {avg_sharpe:.4f}")
    print(f"   - 平均收益率: {avg_return:.2f}%")

    # 结论与建议
    print("\n" + "=" * 80)
    print("结论与建议")
    print("=" * 80)

    if best_result['total_pnl'] > 0 and len(neighbor_positive) >= len(neighbor_results) * 0.75:
        print("\n✅ 泛化验证通过")
        print("   - 最优参数在 2025 仍为正收益")
        print("   - 邻近参数整体表现良好")
        print("   - 2024 Optuna 结果具备泛化能力")
        print("\n建议下一步:")
        print("   → 进入 expected 口径验证 (realistic / bnb9)")
        print("   → 准备测试盘验收指标")
    elif best_result['total_pnl'] > 0:
        print("\n⚠️  泛化验证部分通过")
        print("   - 最优参数在 2025 为正收益")
        print("   - 但邻近参数稳定性不足")
        print("\n建议下一步:")
        print("   → 谨慎进入 expected 口径验证")
        print("   → 考虑缩小参数范围重新优化")
    else:
        print("\n❌ 泛化验证未通过")
        print("   - 最优参数在 2025 表现不佳")
        print("   - 2024 Optuna 结果可能过拟合")
        print("\n建议下一步:")
        print("   → 回到参数搜索，扩大数据范围")
        print("   → 或调整策略逻辑")

    # 清理资源
    print("\n清理资源...")
    await data_repo.close()
    print("   资源已释放")

    print("\n脚本执行完成")


if __name__ == "__main__":
    asyncio.run(main())
