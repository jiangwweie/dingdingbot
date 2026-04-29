#!/usr/bin/env python3
"""对账脚本：max_drawdown vs 最大单笔亏损"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.application.backtester import Backtester
from src.domain.models import BacktestRequest, BacktestRuntimeOverrides


async def main():
    print("=" * 80)
    print("max_drawdown vs 最大单笔亏损对账")
    print("=" * 80)

    repo = HistoricalDataRepository("data/v3_dev.db")
    await repo.initialize()

    bt = Backtester(exchange_gateway=None, data_repository=repo)

    req = BacktestRequest(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        start_time=1704067200000,  # 2024-01-01
        end_time=1735689599000,    # 2024-12-31
        mode="v3_pms",
        initial_balance=Decimal("10000"),
        slippage_rate=Decimal("0.001"),
        tp_slippage_rate=Decimal("0.0005"),
        fee_rate=Decimal("0.0004"),
    )

    ov = BacktestRuntimeOverrides(
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        max_atr_ratio=Decimal("0.0059"),
        min_distance_pct=Decimal("0.0080"),
        ema_period=111,
        allowed_directions=["LONG"],
    )

    try:
        result = await bt.run_backtest(req, runtime_overrides=ov)

        print("\n【1. 暴露的数据】")
        print("-" * 80)
        print("✅ equity_curve 原始数据（前 5 条 + 后 5 条）")
        if result.debug_equity_curve:
            curve = result.debug_equity_curve
            print(f"  总长度: {len(curve)}")
            for i, item in enumerate(curve[:5]):
                print(f"  [{i}] ts={item['timestamp']}, equity={item['equity']:.2f}")
            print("  ...")
            for i, item in enumerate(curve[-5:], len(curve)-5):
                print(f"  [{i}] ts={item['timestamp']}, equity={item['equity']:.2f}")

        print("\n✅ max_drawdown 峰谷明细")
        if result.debug_max_drawdown_detail:
            detail = result.debug_max_drawdown_detail
            print(f"  Peak:     {detail['peak']:.2f} USDT (ts={detail['peak_ts']})")
            print(f"  Trough:   {detail['trough']:.2f} USDT (ts={detail['trough_ts']})")
            print(f"  Drawdown: {detail['drawdown']*100:.2f}%")

        print("\n✅ close_events（最大亏损单）")
        if result.close_events:
            pnls = [(float(e.close_pnl), e) for e in result.close_events]
            pnls.sort(key=lambda x: x[0])
            max_loss_pnl, max_loss_event = pnls[0]

            print(f"  最大单笔亏损: {max_loss_pnl:.2f} USDT")
            print(f"  平仓时间戳:   {max_loss_event.close_time}")
            print(f"  平仓原因:     {max_loss_event.exit_reason}")
            print(f"  Position ID:  {max_loss_event.position_id}")

        print("\n【2. max_drawdown 峰谷明细】")
        print("-" * 80)
        if result.debug_max_drawdown_detail:
            detail = result.debug_max_drawdown_detail
            peak = detail['peak']
            trough = detail['trough']
            dd = detail['drawdown']

            print(f"Peak equity:   {peak:.2f} USDT")
            print(f"Peak timestamp: {detail['peak_ts']}")
            print(f"Trough equity: {trough:.2f} USDT")
            print(f"Trough timestamp: {detail['trough_ts']}")
            print(f"Drawdown:      {dd*100:.2f}%")
            print(f"验证: ({peak:.2f} - {trough:.2f}) / {peak:.2f} = {((peak - trough) / peak)*100:.2f}%")

        print("\n【3. 最大亏损单前后曲线明细】")
        print("-" * 80)
        if result.debug_equity_curve and result.close_events:
            # 找到最大亏损单
            pnls = [(float(e.close_pnl), e) for e in result.close_events]
            pnls.sort(key=lambda x: x[0])
            max_loss_pnl, max_loss_event = pnls[0]
            loss_ts = max_loss_event.close_time

            # 在 equity_curve 中定位
            curve = result.debug_equity_curve
            idx = -1
            for i, item in enumerate(curve):
                if item['timestamp'] == loss_ts:
                    idx = i
                    break

            if idx >= 0:
                print(f"最大亏损单平仓时间: {loss_ts}")
                print(f"在 equity_curve 中的索引: {idx}")
                print()

                # 输出前后 3 根
                start = max(0, idx - 3)
                end = min(len(curve), idx + 4)

                for i in range(start, end):
                    item = curve[i]
                    marker = " <-- 平仓当根" if i == idx else ""
                    print(f"  [{i}] ts={item['timestamp']}, equity={item['equity']:.2f}{marker}")

                # 计算平仓前后的 equity 变化
                if idx > 0:
                    equity_before = curve[idx - 1]['equity']
                    equity_at = curve[idx]['equity']
                    equity_after = curve[idx + 1]['equity'] if idx + 1 < len(curve) else equity_at

                    print()
                    print(f"平仓前一根 equity: {equity_before:.2f} USDT")
                    print(f"平仓当根 equity:   {equity_at:.2f} USDT")
                    print(f"平仓后一根 equity: {equity_after:.2f} USDT")
                    print(f"平仓前后差异:      {equity_at - equity_before:.2f} USDT")
                    print(f"实际 close_pnl:    {max_loss_pnl:.2f} USDT")

        print("\n【4. 结论】")
        print("=" * 80)

        if result.debug_max_drawdown_detail and result.debug_equity_curve and result.close_events:
            detail = result.debug_max_drawdown_detail
            peak = detail['peak']
            trough = detail['trough']

            # 找最大亏损单
            pnls = [(float(e.close_pnl), e) for e in result.close_events]
            pnls.sort(key=lambda x: x[0])
            max_loss_pnl, max_loss_event = pnls[0]
            loss_ts = max_loss_event.close_time

            # 定位
            curve = result.debug_equity_curve
            idx = -1
            for i, item in enumerate(curve):
                if item['timestamp'] == loss_ts:
                    idx = i
                    break

            if idx >= 0:
                equity_at_loss = curve[idx]['equity']

                # 判断
                print(f"最大单笔亏损: {max_loss_pnl:.2f} USDT")
                print(f"平仓时 equity: {equity_at_loss:.2f} USDT")
                print(f"Peak equity:   {peak:.2f} USDT")
                print(f"Trough equity: {trough:.2f} USDT")
                print()

                # 检查这笔亏损是否在 peak 和 trough 之间
                if equity_at_loss < peak and equity_at_loss > trough:
                    print("✅ 这笔亏损发生在 peak 和 trough 之间")
                    print(f"   但 trough ({trough:.2f}) > equity_at_loss ({equity_at_loss:.2f})")
                    print(f"   说明 trough 不是由这笔亏损形成的！")
                    print()
                    print("🔍 问题：为什么 trough 比最大亏损单的 equity 还高？")
                    print("   可能原因：")
                    print("   1. 这笔亏损后，equity 又继续下跌到更低点")
                    print("   2. 或者这笔亏损前，equity 已经在更低点")
                    print("   3. 或者 equity_curve 记录时机有问题")
                elif equity_at_loss == trough:
                    print("✅ 这笔亏损形成了 trough")
                    print(f"   但 drawdown = {detail['drawdown']*100:.2f}%")
                    print(f"   单笔亏损占比 = {abs(max_loss_pnl)/peak*100:.2f}%")
                    if abs(detail['drawdown']) < abs(max_loss_pnl)/peak:
                        print("   ❌ drawdown 小于单笔亏损占比，矛盾！")
                else:
                    print("⚠️  这笔亏损既不是 peak 也不是 trough")

    finally:
        await repo.close()

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
