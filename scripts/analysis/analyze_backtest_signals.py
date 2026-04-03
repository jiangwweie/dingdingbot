#!/usr/bin/env python3
"""
回测信号业务逻辑合规性分析
"""
import sqlite3
from datetime import datetime, timedelta

def analyze_signals(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get all backtest signals with full details
    c.execute("""
    SELECT id, symbol, timeframe, direction, entry_price, stop_loss,
           created_at, source, tags_json, score, leverage, position_size, risk_info
    FROM signals
    WHERE source='backtest'
    ORDER BY id DESC
    """)

    signals = c.fetchall()
    print(f"=== 回测信号分析报告 ===\n")
    print(f"总信号数：{len(signals)}\n")

    # Calculate volatility for each signal
    print("信号详细分析:")
    print("-" * 120)

    issues_found = []

    for s in signals:
        id_, symbol, tf, direction, entry, sl, created, source, tags, score, lev, pos_size, risk = s
        entry = float(entry)
        sl = float(sl)

        # Calculate stop loss distance
        if direction == 'long':
            sl_distance_pct = abs(entry - sl) / entry * 100
        else:
            sl_distance_pct = abs(sl - entry) / entry * 100

        print(f"ID:{id_} | {symbol} | {tf} | {direction.upper():5} | 入场:{entry:.2f} | 止损:{sl:.2f} | 止损距离:{sl_distance_pct:.3f}% | 评分:{score:.2f} | 杠杆:{lev}x")

        # Check for logical issues
        issues = []

        # Issue 1: Stop loss too tight (< 0.1%)
        if sl_distance_pct < 0.1:
            issues.append(f"止损过近 ({sl_distance_pct:.3f}%)")

        # Issue 2: Direction vs SL logic
        if direction == 'long' and sl > entry:
            issues.append(f"多单止损高于入场 ({entry} vs {sl})")
        if direction == 'short' and sl < entry:
            issues.append(f"空单止损低于入场 ({entry} vs {sl})")

        if issues:
            issues_found.append({
                'id': id_,
                'symbol': symbol,
                'direction': direction,
                'entry': entry,
                'stop_loss': sl,
                'issues': issues
            })
            print(f"         [问题] {', '.join(issues)}")

    print("\n" + "=" * 120)
    print(f"发现问题的信号数：{len(issues_found)}")
    if issues_found:
        print("\n问题信号汇总:")
        for issue in issues_found:
            print(f"  - ID:{issue['id']} {issue['symbol']} {issue['direction']}: {', '.join(issue['issues'])}")

    conn.close()
    return issues_found

if __name__ == "__main__":
    analyze_signals("/usr/local/monitorDog/data/signals.db")
