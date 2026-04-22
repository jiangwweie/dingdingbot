#!/usr/bin/env python3
"""
诊断黄金回测中被跳过信号的原因 - 使用本地数据库
"""
import asyncio
import aiosqlite
from decimal import Decimal
from datetime import datetime, timezone

DB_PATH = "data/v3_dev.db"


async def diagnose():
    """诊断被跳过的信号"""

    print("=" * 80)
    print("黄金回测跳过信号诊断")
    print("=" * 80)

    async with aiosqlite.connect(DB_PATH) as db:
        # 查询黄金 1h 数据
        cursor = await db.execute("""
            SELECT timestamp, open, high, low, close, volume
            FROM klines
            WHERE symbol = 'XAU/USDT:USDT' AND timeframe = '1h'
            ORDER BY timestamp ASC
        """)
        rows = await cursor.fetchall()

        print(f"\n获取到 {len(rows)} 根 K 线")

        # 计算每根 K 线的止损距离
        initial_balance = Decimal("10000")
        max_loss_percent = Decimal("0.01")  # 1%
        risk_amount = initial_balance * max_loss_percent  # 100 USDT

        # Pinbar 检测参数
        min_wick_ratio = Decimal("0.6")
        max_body_ratio = Decimal("0.3")

        # 统计
        pinbar_count = 0
        long_pinbars = []
        skipped = []

        for row in rows:
            timestamp, open_p, high, low, close, volume = row
            open_p = Decimal(open_p)
            high = Decimal(high)
            low = Decimal(low)
            close = Decimal(close)

            # 简化的 Pinbar 检测（只检测看涨 Pinbar）
            body = abs(close - open_p)
            total_range = high - low

            if total_range > Decimal("0"):
                # 看涨 Pinbar: 长下影线，实体在顶部
                lower_wick = min(open_p, close) - low
                upper_wick = high - max(open_p, close)

                # 检测看涨 Pinbar（下影线长，实体小）
                if lower_wick >= total_range * min_wick_ratio and body <= total_range * max_body_ratio:
                    pinbar_count += 1

                    # LONG 信号：止损在 low
                    stop_loss = low
                    entry_price = close
                    stop_distance = entry_price - stop_loss
                    stop_distance_pct = stop_distance / entry_price * 100

                    # 计算仓位
                    position_size = risk_amount / stop_distance

                    signal_info = {
                        "timestamp": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
                        "entry": float(entry_price),
                        "stop_loss": float(stop_loss),
                        "stop_distance": float(stop_distance),
                        "stop_distance_pct": float(stop_distance_pct),
                        "position_size": float(position_size),
                        "high": float(high),
                        "low": float(low),
                        "body_pct": float(body / total_range * 100) if total_range > 0 else 0,
                        "lower_wick_pct": float(lower_wick / total_range * 100) if total_range > 0 else 0,
                    }

                    long_pinbars.append(signal_info)

                    if position_size <= 0:
                        skipped.append(signal_info)

        print(f"\n检测到看涨 Pinbar: {pinbar_count}")

        if long_pinbars:
            print(f"\n所有 LONG Pinbar 信号统计:")
            avg_stop_pct = sum(s["stop_distance_pct"] for s in long_pinbars) / len(long_pinbars)
            avg_position = sum(s["position_size"] for s in long_pinbars) / len(long_pinbars)
            print(f"  平均止损距离: {avg_stop_pct:.2f}%")
            print(f"  平均仓位大小: {avg_position:.4f}")

        if skipped:
            print(f"\n被跳过信号数: {len(skipped)}")
            print("\n被跳过信号详情:")
            print("-" * 80)
            for s in skipped:
                print(f"  时间: {s['timestamp']}")
                print(f"  入场价: {s['entry']:.2f}")
                print(f"  止损价: {s['stop_loss']:.2f}")
                print(f"  止损距离: {s['stop_distance']:.2f} ({s['stop_distance_pct']:.2f}%)")
                print(f"  仓位大小: {s['position_size']:.6f}")
                print(f"  K线范围: high={s['high']:.2f}, low={s['low']:.2f}")
                print(f"  实体占比: {s['body_pct']:.1f}%, 下影线占比: {s['lower_wick_pct']:.1f}%")
                print("-" * 40)

        # 分析根因
        print("\n" + "=" * 80)
        print("根因分析")
        print("=" * 80)

        if skipped:
            # 对比跳过和正常信号
            valid = [s for s in long_pinbars if s["position_size"] > 0]
            if valid:
                avg_valid_stop = sum(s["stop_distance_pct"] for s in valid) / len(valid)
                avg_skip_stop = sum(s["stop_distance_pct"] for s in skipped) / len(skipped)
                print(f"\n正常信号平均止损距离: {avg_valid_stop:.2f}%")
                print(f"跳过信号平均止损距离: {avg_skip_stop:.2f}%")
                print(f"差异: {avg_skip_stop - avg_valid_stop:.2f}%")

            print(f"\n仓位计算公式: position_size = risk_amount / stop_distance")
            print(f"  risk_amount = {initial_balance} × {max_loss_percent} = {float(risk_amount):.2f} USDT")
            print(f"\n当 stop_distance 过大时:")
            print(f"  例: 止损距离 = {skipped[0]['stop_distance']:.2f} USDT")
            print(f"  position_size = {float(risk_amount):.2f} / {skipped[0]['stop_distance']:.2f} = {skipped[0]['position_size']:.4f}")

            print(f"\n根因: 黄金价格波动大，Pinbar K 线的止损距离过大")
            print(f"  黄金价格 ~3000 USDT，单根 K 线波动可达 50-100 USDT")
            print(f"  ETH 价格 ~2000-4000 USDT，单根 K 线波动通常 10-30 USDT")
            print(f"  黄金止损距离百分比远大于 ETH，导致仓位计算结果极小")

            # 计算需要多少 max_loss_percent 才能产生有效仓位
            min_position = Decimal("0.01")  # 最小有效仓位
            for s in skipped:
                required_risk = min_position * Decimal(str(s["stop_distance"]))
                required_pct = required_risk / initial_balance * 100
                print(f"\n要产生 {min_position} 仓位，需要 max_loss_percent = {float(required_pct):.2f}%")


if __name__ == "__main__":
    asyncio.run(diagnose())