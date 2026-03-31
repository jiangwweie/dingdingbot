#!/usr/bin/env python3
"""
检查服务器数据库中的信号
"""
import sqlite3
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('/root/monitor/data/signals.db')
cursor = conn.cursor()

cursor.execute("""
SELECT id, created_at, symbol, timeframe, direction, strategy_name, kline_timestamp
FROM signals
ORDER BY id DESC
LIMIT 20
""")

for row in cursor.fetchall():
    signal_id, created_at, symbol, timeframe, direction, strategy, kline_ts = row

    # 转换时间
    if kline_ts:
        dt = datetime.fromtimestamp(kline_ts / 1000, tz=timezone.utc) + timedelta(hours=8)
        time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        time_str = 'N/A'

    print(f"ID:{signal_id:4d} | {symbol:<20} | {timeframe:<4} | {direction:<5} | {strategy:<20} | {time_str}")

conn.close()
