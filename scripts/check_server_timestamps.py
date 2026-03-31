#!/usr/bin/env python3
"""
检查服务器上信号数据库中的 kline_timestamp 值
"""
import sqlite3
from datetime import datetime, timezone, timedelta
import sys

DB_PATH = "/root/monitor/data/signals.db"

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, kline_timestamp, symbol, timeframe FROM signals ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()

    print("=== 服务器数据库中的信号 ===")
    for row in rows:
        signal_id, kline_ts, symbol, timeframe = row
        if kline_ts is None:
            print(f"ID: {signal_id} | kline_timestamp: NULL")
            continue

        utc_dt = datetime.fromtimestamp(kline_ts / 1000, tz=timezone.utc)
        beijing_dt = utc_dt + timedelta(hours=8)
        tokyo_dt = utc_dt + timedelta(hours=9)

        fmt = "%Y-%m-%d %H:%M:%S"
        print(f"ID: {signal_id} | {symbol} | {timeframe}")
        print(f"  kline_timestamp: {kline_ts}")
        print(f"  UTC: {utc_dt.strftime(fmt)}")
        print(f"  Beijing (UTC+8): {beijing_dt.strftime(fmt)}")
        print(f"  Tokyo (UTC+9): {tokyo_dt.strftime(fmt)}")
        print()

    conn.close()
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
