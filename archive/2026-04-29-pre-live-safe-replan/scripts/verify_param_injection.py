#!/usr/bin/env python3
"""
ETH 1h 参数注入验证脚本

目标：验证不同参数组是否真的被正确注入并生效

测试参数组：
1. 最优参数: max_atr_ratio=0.0082, min_distance_pct=0.0055, ema_period=151
2. 邻近参数 A: max_atr_ratio=0.0085, min_distance_pct=0.0054, ema_period=152
3. 邻近参数 B: max_atr_ratio=0.0090, min_distance_pct=0.0054, ema_period=151
4. 邻近参数 C: max_atr_ratio=0.0088, min_distance_pct=0.0058, ema_period=155

验证方法：
1. 打印 resolved_params 确认参数被正确解析
2. 打印 ATR 过滤器的 max_atr_ratio 确认参数被正确注入
3. 打印 EMA 过滤器的 min_distance_pct 确认参数被正确注入
4. 运行回测并输出详细统计
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
from src.application.backtester import Backtester, resolve_backtest_params
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


async def run_single_backtest_with_diagnostics(
    backtester: Backtester,
    params: dict,
    index: int,
) -> dict:
    """运行单次回测并输出诊断信息"""

    print(f"\n{'='*80}")
    print(f"[{index}] 测试 {params['name']}")
    print(f"{'='*80}")

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
        id="param_validation",
        name="Parameter Validation Strategy",
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

    # 【步骤 1】验证参数解析
    print(f"\n【步骤 1】参数解析验证")
    print(f"  输入参数:")
    print(f"    max_atr_ratio = {params['max_atr_ratio']}")
    print(f"    min_distance_pct = {params['min_distance_pct']}")
    print(f"    ema_period = {params['ema_period']}")

    resolved_params = resolve_backtest_params(runtime_overrides, request)
    print(f"\n  resolved_params:")
    print(f"    max_atr_ratio = {resolved_params.max_atr_ratio}")
    print(f"    min_distance_pct = {resolved_params.min_distance_pct}")
    print(f"    ema_period = {resolved_params.ema_period}")

    # 验证是否一致
    if (resolved_params.max_atr_ratio == params["max_atr_ratio"] and
        resolved_params.min_distance_pct == params["min_distance_pct"] and
        resolved_params.ema_period == params["ema_period"]):
        print(f"  ✅ 参数解析正确")
    else:
        print(f"  ❌ 参数解析错误！")

    # 运行回测
    print(f"\n【步骤 2】运行回测...")
    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    # 提取关键指标
    result = {
        "name": params["name"],
        "max_atr_ratio": float(params["max_atr_ratio"]),
        "min_distance_pct": float(params["min_distance_pct"]),
        "ema_period": params["ema_period"],
        "total_pnl": float(report.total_pnl),
        "total_trades": report.total_trades,
        "win_rate": float(report.win_rate) * 100,
        "max_drawdown": float(report.max_drawdown) * 100,
        "sharpe_ratio": float(report.sharpe_ratio) if report.sharpe_ratio else 0.0,
        "total_return": float(report.total_return) * 100,
    }

    print(f"\n【步骤 3】回测结果:")
    print(f"  Total PnL: {result['total_pnl']:.2f} USDT")
    print(f"  Total Trades: {result['total_trades']}")
    print(f"  Win Rate: {result['win_rate']:.2f}%")
    print(f"  Max Drawdown: {result['max_drawdown']:.2f}%")
    print(f"  Sharpe Ratio: {result['sharpe_ratio']:.4f}")
    print(f"  Total Return: {result['total_return']:.2f}%")

    return result


async def main():
    """主函数"""
    print("=" * 80)
    print("ETH 1h 参数注入验证")
    print("=" * 80)

    print(f"\n配置:")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  时间范围: 2025-01-01 ~ 2025-12-31")
    print(f"  成本口径: stress")

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
        result = await run_single_backtest_with_diagnostics(backtester, params, i)
        results.append(result)

    # 输出对比表
    print("\n" + "=" * 80)
    print("参数注入验证结果对比")
    print("=" * 80)

    # 表头
    print(f"\n{'参数组':<15} {'PnL':<12} {'Trades':<8} {'WinRate':<10} "
          f"{'Sharpe':<10} {'Return':<10}")
    print("-" * 80)

    # 数据行
    for r in results:
        print(f"{r['name']:<15} {r['total_pnl']:>10.2f}   {r['total_trades']:>6}   "
              f"{r['win_rate']:>7.2f}%  {r['sharpe_ratio']:>8.4f}  {r['total_return']:>7.2f}%")

    # 参数对比
    print("\n" + "=" * 80)
    print("参数对比")
    print("=" * 80)
    print(f"\n{'参数组':<15} {'max_atr':<10} {'min_dist':<10} {'ema':<8}")
    print("-" * 50)
    for r in results:
        print(f"{r['name']:<15} {r['max_atr_ratio']:>8.4f}  {r['min_distance_pct']:>8.4f}  "
              f"{r['ema_period']:>6}")

    # 结果一致性分析
    print("\n" + "=" * 80)
    print("结果一致性分析")
    print("=" * 80)

    # 检查是否有完全相同的结果
    unique_results = {}
    for r in results:
        key = (r['total_pnl'], r['total_trades'], r['win_rate'])
        if key not in unique_results:
            unique_results[key] = []
        unique_results[key].append(r['name'])

    print(f"\n唯一结果组数: {len(unique_results)}")
    for i, (key, names) in enumerate(unique_results.items(), 1):
        pnl, trades, winrate = key
        print(f"\n组 {i}: PnL={pnl:.2f}, Trades={trades}, WinRate={winrate:.2f}%")
        print(f"  参数组: {', '.join(names)}")

    if len(unique_results) == 1:
        print("\n❌ 所有参数组结果完全相同！")
        print("   可能原因:")
        print("   1. 参数注入未生效")
        print("   2. 参数变化范围太小，未影响交易决策")
        print("   3. 策略逻辑对这些参数不敏感")
    elif len(unique_results) < len(results):
        print("\n⚠️  部分参数组结果相同")
        print("   需要进一步分析参数敏感性")
    else:
        print("\n✅ 所有参数组结果不同")
        print("   参数注入已生效")

    # 清理资源
    print("\n清理资源...")
    await data_repo.close()
    print("   资源已释放")

    print("\n脚本执行完成")


if __name__ == "__main__":
    asyncio.run(main())
