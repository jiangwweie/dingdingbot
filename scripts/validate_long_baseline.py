#!/usr/bin/env python3
"""验证 LONG-only 基线在 2024/2025 年的表现"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.application.backtester import Backtester
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides


def date_to_timestamp(date_str: str) -> int:
    """将日期字符串转换为毫秒时间戳"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


async def run_window(start: str, end: str, label: str, gateway: ExchangeGateway):
    """运行单个时间窗口的回测"""
    print(f"\n{'='*60}")
    print(f"窗口: {label}")
    print(f"{'='*60}")
    
    # 固定条件
    overrides = BacktestRuntimeOverrides(
        direction_filter="LONG",
        cost_mode="stress",
        max_atr_ratio=Decimal("0.0059"),
        min_distance_pct=Decimal("0.0080"),
        ema_period=90,
        breakeven_enabled=False,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp1_ratio=Decimal("1.0"),
        tp2_ratio=Decimal("3.5"),
    )
    
    request = BacktestRequest(
        mode="v3_pms",  # 使用 v3_pms 模式
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=date_to_timestamp(start),
        end_time=date_to_timestamp(end),
        limit=10000,
        initial_balance=Decimal("10000.0"),
        strategies=[],
        runtime_overrides=overrides,
    )
    
    backtester = Backtester(exchange_gateway=gateway)
    result = await backtester.run_backtest(request)
    
    # 修正 win_rate（如果是小数形式，转换为百分比）
    win_rate = float(result.win_rate)
    if win_rate < 1.0:
        win_rate = win_rate * 100
    
    # 输出关键指标
    print(f"\n结果:")
    print(f"  total_pnl:     {result.total_pnl:.2f} USDT")
    print(f"  total_trades:  {result.total_trades}")
    print(f"  win_rate:      {win_rate:.1f}%")
    print(f"  max_drawdown:  {result.max_drawdown:.2f}%")
    print(f"  sharpe:        {result.sharpe_ratio:.2f}" if result.sharpe_ratio else "  sharpe:        N/A")
    
    return {
        "label": label,
        "total_pnl": float(result.total_pnl),
        "total_trades": result.total_trades,
        "win_rate": win_rate,
        "max_drawdown": float(result.max_drawdown),
        "sharpe": float(result.sharpe_ratio) if result.sharpe_ratio else 0.0,
    }


async def main():
    print("="*60)
    print("LONG-only 基线验证 (MTF 真源已修正)")
    print("="*60)
    print("\n固定条件:")
    print("  symbol:            ETH/USDT:USDT")
    print("  timeframe:         1h")
    print("  direction:         LONG-only")
    print("  cost_mode:         stress")
    print("  max_atr_ratio:     0.0059")
    print("  min_distance_pct:  0.0080")
    print("  ema_period:        90")
    print("  breakeven_enabled: False")
    print("  tp_ratios:         [0.5, 0.5]")
    print("  TP1:               1.0R")
    print("  TP2:               3.5R")
    
    # 初始化 ExchangeGateway
    print("\n初始化 ExchangeGateway...")
    gateway = ExchangeGateway(
        exchange_name="binance",
        api_key="",
        api_secret="",
        testnet=False,
    )
    await gateway.initialize()
    
    # 运行两个窗口
    results = []
    results.append(await run_window("2024-01-01", "2024-12-31", "2024年", gateway))
    results.append(await run_window("2025-01-01", "2025-12-31", "2025年", gateway))
    
    # 关闭 gateway
    await gateway.close()
    
    # 输出汇总表
    print("\n" + "="*60)
    print("两年结果汇总")
    print("="*60)
    print(f"{'年份':<10} {'总盈亏':<15} {'交易数':<10} {'胜率':<10} {'最大回撤':<12} {'夏普':<8}")
    print("-"*60)
    for r in results:
        print(f"{r['label']:<10} {r['total_pnl']:>13.2f}   {r['total_trades']:<8} {r['win_rate']:>7.1f}%   {r['max_drawdown']:>9.1f}%   {r['sharpe']:>6.2f}")
    
    # 判断是否都为正
    all_positive = all(r["total_pnl"] > 0 for r in results)
    
    print("\n" + "="*60)
    print("结论")
    print("="*60)
    print(f"1. 这套 LONG-only 基线在 2024/2025 是否都为正: {'✅ 是' if all_positive else '❌ 否'}")
    print(f"2. 是否可以把它当作新的临时基线: {'✅ 可以' if all_positive else '❌ 不行'}")
    
    if all_positive:
        # 分析哪个参数最值得微调
        print(f"3. 下一步更应该微调哪个单一参数:")
        print(f"   - max_atr_ratio (当前 0.0059): 影响入场质量")
        print(f"   - min_distance_pct (当前 0.0080): 影响止损距离")
        print(f"   - TP2 (当前 3.5R): 影响盈利空间")
        print(f"\n   建议: 优先微调 TP2 (3.5R → 4.0R 或 3.0R)")
        print(f"   理由: TP2 直接影响盈亏比，对总盈亏影响最大")
    
    print("\n" + "="*60)
    print("✅ LONG-only 基线验证完成")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
