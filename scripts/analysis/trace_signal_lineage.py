#!/usr/bin/env python3
"""
Pinbar 信号溯源分析 - 重建检测链路日志

从数据库中读取信号，调用 API 获取上下文数据，重建当时的检测流程。
"""
import json
import subprocess
from datetime import datetime, timezone, timedelta
from decimal import Decimal

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
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def calculate_pinbar_metrics(kline):
    """计算 Pinbar 形态指标"""
    open_p = Decimal(str(kline[1]))
    high = Decimal(str(kline[2]))
    low = Decimal(str(kline[3]))
    close = Decimal(str(kline[4]))

    candle_range = high - low
    if candle_range == 0:
        return None

    body_size = abs(close - open_p)
    body_ratio = body_size / candle_range

    upper_wick = high - max(open_p, close)
    lower_wick = min(open_p, close) - low
    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range

    body_center = (open_p + close) / Decimal(2)
    body_position = (body_center - low) / candle_range

    return {
        'range': float(candle_range),
        'body': float(body_size),
        'body_ratio': float(body_ratio),
        'upper_wick': float(upper_wick),
        'upper_wick_ratio': float(upper_wick / candle_range),
        'lower_wick': float(lower_wick),
        'lower_wick_ratio': float(lower_wick / candle_range),
        'dominant_wick': 'upper' if dominant_wick == upper_wick else 'lower',
        'wick_ratio': float(wick_ratio),
        'body_position': float(body_position),
    }

def check_pinbar_config(metrics, config_source='core.yaml'):
    """检查是否符合 Pinbar 配置阈值"""
    # 配置文件阈值 (core.yaml)
    if config_source == 'core.yaml':
        min_wick = Decimal('0.5')
        max_body = Decimal('0.35')
        tolerance = Decimal('0.3')
    else:
        # 代码默认阈值
        min_wick = Decimal('0.6')
        max_body = Decimal('0.3')
        tolerance = Decimal('0.1')

    wick_pass = Decimal(str(metrics['wick_ratio'])) >= min_wick
    body_pass = Decimal(str(metrics['body_ratio'])) <= max_body

    # 方向检测
    direction = None
    if metrics['dominant_wick'] == 'lower':
        # 看涨：实体必须在顶部
        threshold = Decimal(1) - tolerance - Decimal(str(metrics['body_ratio'])) / 2
        if Decimal(str(metrics['body_position'])) >= threshold:
            direction = 'LONG'
    else:
        # 看跌：实体必须在底部
        threshold = tolerance + Decimal(str(metrics['body_ratio'])) / 2
        if Decimal(str(metrics['body_position'])) <= threshold:
            direction = 'SHORT'

    return {
        'wick_pass': wick_pass,
        'body_pass': body_pass,
        'pinbar_pass': wick_pass and body_pass,
        'detected_direction': direction,
        'config_source': config_source,
    }

def analyze_filter_chain(signal_data, kline_metrics):
    """分析过滤器链路"""
    tags = signal_data.get('tags_json', '[]')
    try:
        tags_data = json.loads(tags)
    except:
        tags_data = []

    filters = {}
    for tag in tags_data:
        name = tag.get('name', '')
        value = tag.get('value', '')

        if name == 'MTF':
            filters['mtf'] = {'passed': value == 'Confirmed', 'value': value}
        elif name == 'EMA':
            # Neutral 表示 EMA 过滤器未启用或不要求匹配
            filters['ema'] = {'passed': True, 'value': value}
        elif name == 'Atr Volatility':
            filters['atr'] = {'passed': value == 'Passed', 'value': value}

    return filters

def generate_trace_log(signal_id, data):
    """生成溯源日志"""
    signal = data.get('signal', {})
    klines = data.get('klines', [])

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
        return None

    # 计算 Pinbar 指标
    metrics = calculate_pinbar_metrics(signal_candle)

    # 检查配置
    check_yaml = check_pinbar_config(metrics, 'core.yaml')
    check_code = check_pinbar_config(metrics, 'code_default')

    # 过滤器分析
    filters = analyze_filter_chain(signal, metrics)

    # 生成溯源日志
    log_lines = []
    log_lines.append("=" * 80)
    log_lines.append(f"[TRACE] Signal ID: {signal_id}")
    log_lines.append(f"[TRACE] Symbol: {signal.get('symbol')} | Timeframe: {signal.get('timeframe')}")
    log_lines.append(f"[TRACE] Strategy: {signal.get('strategy_name')}")
    log_lines.append(f"[TRACE] Signal Time: {format_beijing_time(signal_ts)} (CST)")
    log_lines.append("")

    log_lines.append("-" * 80)
    log_lines.append("[STEP 1] K-line Input")
    log_lines.append(f"  O:{signal_candle[1]} H:{signal_candle[2]} L:{signal_candle[3]} C:{signal_candle[4]}")
    log_lines.append(f"  Range: {metrics['range']:.4f} | Body: {metrics['body']:.4f} ({metrics['body_ratio']:.2%})")
    log_lines.append(f"  Upper Wick: {metrics['upper_wick']:.4f} ({metrics['upper_wick_ratio']:.2%})")
    log_lines.append(f"  Lower Wick: {metrics['lower_wick']:.4f} ({metrics['lower_wick_ratio']:.2%})")
    log_lines.append(f"  Dominant Wick: {metrics['dominant_wick'].upper()} ({metrics['wick_ratio']:.2%})")
    log_lines.append(f"  Body Position: {metrics['body_position']:.4f} (0=bottom, 1=top)")
    log_lines.append("")

    log_lines.append("-" * 80)
    log_lines.append("[STEP 2] Pinbar Pattern Detection")
    log_lines.append(f"  Config Source: core.yaml")
    log_lines.append(f"    min_wick_ratio >= 50%: {'✅' if check_yaml['wick_pass'] else '❌'}")
    log_lines.append(f"    max_body_ratio <= 35%: {'✅' if check_yaml['body_pass'] else '❌'}")
    log_lines.append(f"    → Pattern Match: {'✅' if check_yaml['pinbar_pass'] else '❌'}")
    log_lines.append(f"    → Detected Direction: {check_yaml['detected_direction'] or 'None'}")
    log_lines.append("")
    log_lines.append(f"  Config Source: code_default (fallback)")
    log_lines.append(f"    min_wick_ratio >= 60%: {'✅' if check_code['wick_pass'] else '❌'}")
    log_lines.append(f"    max_body_ratio <= 30%: {'✅' if check_code['body_pass'] else '❌'}")
    log_lines.append(f"    → Pattern Match: {'✅' if check_code['pinbar_pass'] else '❌'}")
    log_lines.append(f"    → Detected Direction: {check_code['detected_direction'] or 'None'}")
    log_lines.append("")

    log_lines.append("-" * 80)
    log_lines.append("[STEP 3] Filter Chain")
    for fname, fdata in filters.items():
        status = '✅' if fdata['passed'] else '❌'
        log_lines.append(f"  {fname.upper()}: {status} ({fdata['value']})")
    log_lines.append("")

    log_lines.append("-" * 80)
    log_lines.append("[STEP 4] Final Result")
    actual_direction = signal.get('direction', 'UNKNOWN').upper()
    score = signal.get('score', 0)

    # 判断是否应该生成信号
    should_fire = check_yaml['pinbar_pass'] and check_yaml['detected_direction'] == actual_direction
    all_filters_pass = all(f['passed'] for f in filters.values())

    if should_fire and all_filters_pass:
        log_lines.append(f"  ✅ SIGNAL_FIRED | {actual_direction} | Score: {score:.4f}")
    else:
        log_lines.append(f"  ❌ SIGNAL_BLOCKED")
        if not check_yaml['pinbar_pass']:
            log_lines.append(f"     Reason: Pattern detection failed")
        elif check_yaml['detected_direction'] != actual_direction:
            log_lines.append(f"     Reason: Direction mismatch - detected {check_yaml['detected_direction']}, got {actual_direction}")
        if not all_filters_pass:
            log_lines.append(f"     Reason: Filter chain failed")

    log_lines.append("")
    log_lines.append("=" * 80)

    return '\n'.join(log_lines)

def main():
    signal_ids = ['291', '290', '289', '288', '287', '286']

    print("=" * 80)
    print("Pinbar 信号溯源分析报告")
    print("生成时间:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 80)
    print()

    for signal_id in signal_ids:
        data = run_api_call(signal_id)

        if 'error' in data or 'signal' not in data:
            print(f"\n[信号 {signal_id}] 无法获取数据")
            continue

        trace_log = generate_trace_log(signal_id, data)
        if trace_log:
            print(trace_log)

if __name__ == '__main__':
    main()
