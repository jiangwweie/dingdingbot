#!/usr/bin/env python3
"""检查问题信号的标签数据"""
import sqlite3
import json

conn = sqlite3.connect('/usr/local/monitorDog/data/signals-prod.db')
cursor = conn.cursor()

# 获取信号 293 和 294 的详细记录
cursor.execute("""
SELECT id, symbol, timeframe, direction, kline_timestamp, tags_json
FROM signals
WHERE id IN (293, 294)
""")

for row in cursor.fetchall():
    signal_id, symbol, timeframe, direction, kline_ts, tags = row
    print(f"\n=== 信号 {signal_id} ===")
    print(f"符号：{symbol} {timeframe} {direction}")

    # 检查 tags
    if tags:
        try:
            tags_data = json.loads(tags)
            print(f"标签：{tags_data}")

            # 检查是否有 ATR 相关标签
            has_atr = any(t.get('name', '').lower().find('atr') >= 0 for t in tags_data)
            print(f"有 ATR 标签：{has_atr}")
        except Exception as e:
            print(f"标签解析失败：{e}")
    else:
        print("无标签数据")

conn.close()
