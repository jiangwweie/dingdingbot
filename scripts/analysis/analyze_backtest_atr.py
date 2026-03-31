#!/usr/bin/env python3
"""
分析回测信号的 ATR 和波动情况
"""
import sqlite3
import json
import requests
from datetime import datetime, timezone, timedelta

def fetch_signal_context(signal_id):
    """获取信号上下文"""
    url = f"http://45.76.111.81/api/signals/{signal_id}/context"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return None

conn = sqlite3.connect('/usr/local/monitorDog/data/signals-prod.db')
cursor = conn.cursor()

# 获取回测信号
cursor.execute("""
SELECT id, symbol, timeframe, direction, kline_timestamp, entry_price, stop_loss,
       take_profit_1, pnl_ratio, tags_json
FROM signals
WHERE source = 'backtest'
ORDER BY id DESC
LIMIT 15
""")

signals = cursor.fetchall()
conn.close()

print("=" * 100)
print("回测信号 ATR 和波动分析")
print("=" * 100)

for row in signals:
    signal_id, symbol, timeframe, direction, kline_ts, entry, sl, tp1, pnl, tags = row

    print(f"\n{'='*100}")
    print(f"【信号 {signal_id}】{symbol} {timeframe} {direction.upper()}")
    print(f"  入场价：{entry} | 止损：{sl} | 盈亏比：{pnl}")

    # 解析 tags_json
    if tags:
        try:
            tags_data = json.loads(tags)
            tag_str = " | ".join([f"{t['name']}: {t['value']}" for t in tags_data])
            print(f"  标签：{tag_str}")
        except:
            print(f"  标签：解析失败")

    # 获取 K 线数据
    if kline_ts:
        dt = datetime.fromtimestamp(kline_ts / 1000, tz=timezone.utc) + timedelta(hours=8)
        print(f"  K 线时间：{dt.strftime('%Y-%m-%d %H:%M')} CST")

        # 计算 K 线波幅
        data = fetch_signal_context(signal_id)
        if data and 'klines' in data:
            klines = data['klines']
            signal_candle = None
            for k in klines:
                if k[0] == kline_ts:
                    signal_candle = k
                    break

            if signal_candle:
                ts, o, h, l, c, v = signal_candle
                candle_range = h - l
                range_pct = (candle_range / o) * 100 if o > 0 else 0

                print(f"  信号 K 线：O:{o} H:{h} L:{l} C:{c}")
                print(f"  K 线波幅：{candle_range:.4f} ({range_pct:.3f}%)")

                # ATR 过滤器检查
                # min_atr_ratio: 0.5, min_absolute_range: 0.1
                atr_check = range_pct >= 0.5 if candle_range >= 0.1 else False
                print(f"  ATR 检查：波幅{range_pct:.3f}% vs 0.5% = {'✅ 通过' if range_pct >= 0.5 else '❌ 失败'}")
            else:
                print(f"  信号 K 线：未找到")
        else:
            print(f"  K 线数据：无法获取")

print("\n" + "=" * 100)
