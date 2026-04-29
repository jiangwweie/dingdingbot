#!/usr/bin/env python3
"""ATR/Price 分布诊断 — 看每个币种的真实 ATR/price 百分位分布"""

import sqlite3
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = "data/v3_dev.db"
TIMEFRAME = "1h"
SYMBOLS = ["ETH/USDT:USDT", "BTC/USDT:USDT", "SOL/USDT:USDT"]
ATR_PERIOD = 14


def calc_atr_series(rows, period=14):
    """计算 ATR 序列，返回 (timestamp, close, atr, atr_pct) 列表"""
    results = []
    tr_buf = []  # True Range 缓冲区
    prev_close = None
    atr = None

    for ts, high, low, close in rows:
        h = float(high)
        l = float(low)
        c = float(close)

        if prev_close is not None:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        else:
            tr = h - l

        tr_buf.append(tr)

        if len(tr_buf) < period:
            prev_close = c
            continue

        if atr is None:
            # 首个 ATR = 简单平均
            atr = sum(tr_buf[-period:]) / period
        else:
            # Wilder 平滑
            atr = (atr * (period - 1) + tr) / period

        atr_pct = atr / c if c > 0 else 0
        results.append((ts, c, atr, atr_pct))
        prev_close = c

    return results


def percentile(data, p):
    """计算百分位"""
    if not data:
        return 0
    s = sorted(data)
    idx = int(len(s) * p / 100)
    idx = min(idx, len(s) - 1)
    return s[idx]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for symbol in SYMBOLS:
        print(f"\n{'='*60}")
        print(f"  {symbol} — ATR({ATR_PERIOD}) / Price 分布")
        print(f"{'='*60}")

        cur.execute("""
            SELECT timestamp, high, low, close
            FROM klines
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp
        """, (symbol, TIMEFRAME))

        rows = cur.fetchall()
        print(f"  总 K 线数: {len(rows)}")

        atr_data = calc_atr_series(rows, ATR_PERIOD)
        print(f"  ATR 就绪数: {len(atr_data)}")

        if not atr_data:
            print("  ⚠️ 无数据")
            continue

        atr_pcts = [d[3] for d in atr_data]

        # 百分位分布
        pcts = [5, 10, 25, 50, 75, 90, 95]
        print(f"\n  ATR/Price 百分位分布:")
        print(f"  {'百分位':<10} {'ATR/Price':<15} {'含义'}")
        print(f"  {'-'*45}")
        for p in pcts:
            val = percentile(atr_pcts, p)
            print(f"  P{p:<8} {val:<15.4f} {val*100:.2f}% 的时间 ATR/Price 低于此值")

        mean_val = sum(atr_pcts) / len(atr_pcts)
        print(f"\n  均值: {mean_val:.4f} ({mean_val*100:.2f}%)")

        # 分桶统计：看各阈值会过滤掉多少数据
        print(f"\n  阈值过滤效果 (ATR/Price > X → 拒绝):")
        print(f"  {'阈值':<15} {'被过滤比例':<15} {'剩余信号数 (估算)'}")
        print(f"  {'-'*50}")
        for threshold in [0.005, 0.008, 0.01, 0.012, 0.015, 0.02, 0.025, 0.03]:
            filtered = sum(1 for x in atr_pcts if x > threshold)
            pct = filtered / len(atr_pcts) * 100
            remaining = len(atr_pcts) - filtered
            print(f"  {threshold*100:.1f}%{' ':<11} {pct:>6.1f}%{' ':<8} {remaining:>8}")

        # 与 SL=1% 的关系
        print(f"\n  关键洞察 (SL=1%):")
        above_1pct = sum(1 for x in atr_pcts if x > 0.01)
        above_1_5pct = sum(1 for x in atr_pcts if x > 0.015)
        print(f"  ATR/Price > 1.0%: {above_1pct}/{len(atr_pcts)} = {above_1pct/len(atr_pcts)*100:.1f}% (噪声 > SL，SL 无效)")
        print(f"  ATR/Price > 1.5%: {above_1_5pct}/{len(atr_pcts)} = {above_1_5pct/len(atr_pcts)*100:.1f}%")

    conn.close()


if __name__ == "__main__":
    main()
