#!/usr/bin/env python3
"""
验证 K 线图渲染逻辑
"""
import json
import subprocess
from datetime import datetime, timezone, timedelta

# 1. 获取 API 数据
result = subprocess.run(
    ['curl', '-s', 'http://45.76.111.81/api/signals/291/context'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

if 'error' in data:
    print(f"API Error: {data['error']}")
    exit(1)

signal = data.get('signal', {})
klines = data.get('klines', [])

print("=" * 60)
print("K 线图渲染验证报告")
print("=" * 60)

# 2. 信号信息
print("\n【1】信号信息")
print("-" * 40)
print(f"信号 ID: {signal.get('id')}")
print(f"币种：{signal.get('symbol')}")
print(f"周期：{signal.get('timeframe')}")
print(f"方向：{signal.get('direction')}")
print(f"kline_timestamp: {signal.get('kline_timestamp')}")

signal_ts = signal.get('kline_timestamp')
if signal_ts:
    dt = datetime.fromtimestamp(signal_ts/1000, tz=timezone.utc) + timedelta(hours=8)
    print(f"信号时间 (北京时间): {dt.strftime('%Y-%m-%d %H:%M:%S')} CST")

# 3. K 线数据信息
print("\n【2】K 线数据")
print("-" * 40)
print(f"K 线数量：{len(klines)}")

if klines:
    first_ts = klines[0][0]
    last_ts = klines[-1][0]
    first_dt = datetime.fromtimestamp(first_ts/1000, tz=timezone.utc) + timedelta(hours=8)
    last_dt = datetime.fromtimestamp(last_ts/1000, tz=timezone.utc) + timedelta(hours=8)
    print(f"第一根 K 线：{first_dt.strftime('%m-%d %H:%M')} CST (TS: {first_ts})")
    print(f"最后一根 K 线：{last_dt.strftime('%m-%d %H:%M')} CST (TS: {last_ts})")

# 4. 信号 K 线匹配
print("\n【3】信号 K 线匹配")
print("-" * 40)

signal_ts_sec = signal_ts // 1000 if signal_ts else None
found_index = None
found_candle = None

for i, k in enumerate(klines):
    k_ts_sec = k[0] // 1000
    if k_ts_sec == signal_ts_sec:
        found_index = i
        found_candle = k
        break

if found_candle:
    k_dt = datetime.fromtimestamp(found_candle[0]/1000, tz=timezone.utc) + timedelta(hours=8)
    print(f"✓ 匹配成功")
    print(f"  索引位置：{found_index}")
    print(f"  K 线时间：{k_dt.strftime('%m-%d %H:%M')} CST")
    print(f"  O: {found_candle[1]}, H: {found_candle[2]}, L: {found_candle[3]}, C: {found_candle[4]}")
else:
    print("✗ 匹配失败 - 信号 K 线不在数据范围内")

# 5. 前端渲染逻辑验证
print("\n【4】前端渲染逻辑验证")
print("-" * 40)

# 模拟前端代码逻辑
def simulate_frontend_logic(klines, signal_ts):
    """模拟前端的 K 线数据处理和信号匹配"""
    # 步骤 1: 转换 K 线数据 (毫秒转秒)
    kline_data = [(k[0] // 1000, k[1], k[2], k[3], k[4]) for k in klines]

    # 步骤 2: 转换信号时间戳
    signal_timestamp = signal_ts // 1000 if signal_ts else None

    # 步骤 3: 查找信号 K 线
    signal_candle = None
    for k in kline_data:
        if k[0] == signal_timestamp:
            signal_candle = k
            break

    return signal_candle is not None

if simulate_frontend_logic(klines, signal_ts):
    print("✓ 前端可以找到信号 K 线")
else:
    print("✗ 前端无法找到信号 K 线")

# 6. 标记渲染配置
print("\n【5】标记渲染配置")
print("-" * 40)
direction = signal.get('direction', '')
if direction == 'long':
    print(f"方向：LONG (多)")
    print(f"  标记位置：belowBar (K 线下方)")
    print(f"  标记形状：arrowUp (向上箭头)")
    print(f"  标记颜色：#34C759 (绿色)")
    print(f"  标记文本：多 (入场)")
elif direction == 'short':
    print(f"方向：SHORT (空)")
    print(f"  标记位置：aboveBar (K 线上方)")
    print(f"  标记形状：arrowDown (向下箭头)")
    print(f"  标记颜色：#FF3B30 (红色)")
    print(f"  标记文本：空 (入场)")

# 7. 止盈止损线
print("\n【6】止盈止损线")
print("-" * 40)
print(f"入场价：{signal.get('entry_price')}")
print(f"止损价：{signal.get('stop_loss')}")

tp_levels = signal.get('take_profit_levels', [])
if tp_levels:
    print(f"止盈级别：{len(tp_levels)}")
    for tp in tp_levels:
        print(f"  {tp.get('tp_id')}: {tp.get('price_level')} ({float(tp.get('position_ratio', 0))*100:.0f}%)")
else:
    print("止盈级别：无")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
