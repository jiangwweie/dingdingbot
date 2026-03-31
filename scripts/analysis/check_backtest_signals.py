#!/usr/bin/env python3
"""
检查回测信号
"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('/usr/local/monitorDog/data/signals-prod.db')
cursor = conn.cursor()

# 获取所有回测信号
cursor.execute("""
SELECT id, created_at, symbol, timeframe, direction, strategy_name, kline_timestamp, source
FROM signals
WHERE source = 'backtest'
ORDER BY id DESC
LIMIT 30
""")

print("=== 回测信号列表 ===")
for row in cursor.fetchall():
    signal_id, created_at, symbol, timeframe, direction, strategy, kline_ts, source = row
    if kline_ts:
        dt = datetime.fromtimestamp(kline_ts / 1000, tz=timezone.utc) + timedelta(hours=8)
        time_str = dt.strftime('%Y-%m-%d %H:%M')
    else:
        time_str = 'N/A'
    print(f"ID:{signal_id:4d} | {symbol:<20} | {timeframe:<4} | {direction:<5} | {time_str}")

conn.close()
