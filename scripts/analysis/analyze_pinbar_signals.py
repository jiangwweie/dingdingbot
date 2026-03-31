#!/usr/bin/env python3
"""
分析服务器信号是否符合 Pinbar 形态
"""
import json
import subprocess
from datetime import datetime, timezone, timedelta

def run_api_call(signal_id):
    """调用 API 获取信号上下文"""
    result = subprocess.run(
        ['curl', '-s', f'http://45.76.111.81/api/signals/{signal_id}/context'],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def format_beijing_time(timestamp_ms):
    """转换时间戳为北京时间"""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc) + timedelta(hours=8)
    return dt.strftime('%Y-%m-%d %H:%M')

def analyze_pinbar(kline, direction):
    """
    分析单根 K 线是否符合 Pinbar 形态

    Pinbar 定义:
    - 看涨：长下影线，实体在顶部
    - 看跌：长上影线，实体在底部

    参数 (默认):
    - min_wick_ratio: 0.6 (影线占比下限)
    - max_body_ratio: 0.3 (实体占比上限)
    - body_position_tolerance: 0.1 (实体位置容差)
    """
    open_p = kline[1]
    high = kline[2]
    low = kline[3]
    close = kline[4]

    # 计算 K 线各部分
    range_size = high - low
    if range_size == 0:
        return None, "K 线范围为 0"

    body = abs(close - open_p)
    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low

    body_ratio = body / range_size
    upper_wick_ratio = upper_wick / range_size
    lower_wick_ratio = lower_wick / range_size

    is_bullish_pinbar = lower_wick_ratio >= 0.6 and body_ratio <= 0.3 and open_p > (low + range_size * 0.7)
    is_bearish_pinbar = upper_wick_ratio >= 0.6 and body_ratio <= 0.3 and open_p < (low + range_size * 0.3)

    details = {
        'range': float(range_size),
        'body': float(body),
        'body_ratio': body_ratio,
        'upper_wick': float(upper_wick),
        'upper_wick_ratio': upper_wick_ratio,
        'lower_wick': float(lower_wick),
        'lower_wick_ratio': lower_wick_ratio,
    }

    if direction == 'long':
        if is_bullish_pinbar:
            return True, "符合看涨 Pinbar: 长下影线，实体在顶部"
        else:
            return False, f"不符合看涨 Pinbar - 下影线比:{lower_wick_ratio:.2%} (需>=60%), 实体比:{body_ratio:.2%} (需<=30%)"
    else:
        if is_bearish_pinbar:
            return True, "符合看跌 Pinbar: 长上影线，实体在底部"
        else:
            return False, f"不符合看跌 Pinbar - 上影线比:{upper_wick_ratio:.2%} (需>=60%), 实体比:{body_ratio:.2%} (需<=30%)"

    return details

def main():
    # 分析信号 ID 列表
    signal_ids = ['291', '290', '289', '288', '287', '286', '285', '284', '283', '282']

    print("=" * 100)
    print("Pinbar 信号分析报告")
    print("=" * 100)

    for signal_id in signal_ids:
        data = run_api_call(signal_id)

        if 'error' in data or 'signal' not in data:
            print(f"\n【信号 {signal_id}】无法获取数据")
            continue

        signal = data.get('signal', {})
        klines = data.get('klines', [])

        if not klines:
            print(f"\n【信号 {signal_id}】无 K 线数据")
            continue

        # 信号信息
        print(f"\n{'='*100}")
        print(f"【信号 {signal_id}】{signal.get('symbol')} | {signal.get('timeframe')} | {signal.get('direction').upper()}")
        print(f"策略：{signal.get('strategy_name')} | 评分：{signal.get('score', 0):.2%}")
        print(f"信号时间：{format_beijing_time(signal.get('kline_timestamp'))} (CST)")
        print(f"入场价：{signal.get('entry_price')} | 止损价：{signal.get('stop_loss')}")

        # Tags
        tags = signal.get('tags_json', '[]')
        if tags:
            try:
                tags_data = json.loads(tags)
                tag_str = " | ".join([f"{t['name']}: {t['value']}" for t in tags_data])
                print(f"标签：{tag_str}")
            except:
                pass

        # 找到信号 K 线
        signal_ts = signal.get('kline_timestamp')
        signal_candle = None
        signal_index = -1

        for i, k in enumerate(klines):
            if k[0] == signal_ts:
                signal_candle = k
                signal_index = i
                break

        if not signal_candle:
            print("❌ 信号 K 线不在数据范围内")
            continue

        print(f"\n【信号 K 线】(索引:{signal_index})")
        print(f"  时间：{format_beijing_time(signal_candle[0])}")
        print(f"  O:{signal_candle[1]} H:{signal_candle[2]} L:{signal_candle[3]} C:{signal_candle[4]}")

        # Pinbar 分析
        is_pinbar, reason = analyze_pinbar(signal_candle, signal.get('direction'))

        if is_pinbar:
            print(f"  ✅ {reason}")
        else:
            print(f"  ❌ {reason}")

        # 显示前后 K 线
        print(f"\n【K 线序列】(前后各 5 根)")
        start = max(0, signal_index - 5)
        end = min(len(klines), signal_index + 6)

        for i in range(start, end):
            k = klines[i]
            marker = ">>> " if i == signal_index else "    "

            # 计算这根 K 线的 Pinbar 特征
            range_size = k[2] - k[3]
            if range_size > 0:
                body = abs(k[4] - k[1])
                body_ratio = body / range_size
                upper_wick = (k[2] - max(k[1], k[4])) / range_size
                lower_wick = (min(k[1], k[4]) - k[3]) / range_size

                # 判断是否也是 Pinbar
                bullish = lower_wick >= 0.6 and body_ratio <= 0.3
                bearish = upper_wick >= 0.6 and body_ratio <= 0.3

                if bullish:
                    pinbar_type = "[看涨 Pinbar]"
                elif bearish:
                    pinbar_type = "[看跌 Pinbar]"
                else:
                    pinbar_type = ""
            else:
                pinbar_type = ""

            time_str = format_beijing_time(k[0]).split(' ')[1]
            direction = "🟢" if k[4] > k[1] else "🔴" if k[4] < k[1] else "⚪"

            print(f"{marker}{time_str} | O:{k[1]:.2f} H:{k[2]:.2f} L:{k[3]:.2f} C:{k[4]:.2f} {direction} {pinbar_type}")

        # 过滤流程分析
        print(f"\n【过滤流程分析】")
        tags = signal.get('tags_json', '[]')
        try:
            tags_data = json.loads(tags)
            for tag in tags_data:
                name = tag.get('name', '')
                value = tag.get('value', '')

                if name == 'MTF':
                    status = "✅" if value == 'Confirmed' else "❌"
                    print(f"  {status} MTF 多周期确认：{value}")
                elif name == 'EMA':
                    print(f"  ⚪ EMA 趋势过滤：{value}")
                elif name == 'Atr Volatility':
                    status = "✅" if value == 'Passed' else "❌"
                    print(f"  {status} ATR 波动率过滤：{value}")
        except:
            print("  无标签数据")

        print()

if __name__ == '__main__':
    main()
