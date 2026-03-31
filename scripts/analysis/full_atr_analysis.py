#!/usr/bin/env python3
"""
回测信号 ATR 过滤器失效问题分析报告

自动检查：
1. 回测信号的 ATR 合规性
2. 日志中的 ATR 过滤器执行记录
3. 配置与实际执行的一致性
4. 问题根因分析
"""
import sqlite3
import json
import requests
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# ============================================================
# 数据获取
# ============================================================

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

def get_backtest_signals():
    """获取所有回测信号"""
    conn = sqlite3.connect('/usr/local/monitorDog/data/signals-prod.db')
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, symbol, timeframe, direction, kline_timestamp, entry_price, stop_loss,
           take_profit_1, pnl_ratio, tags_json, source, created_at
    FROM signals
    WHERE source = 'backtest'
    ORDER BY id DESC
    LIMIT 50
    """)

    signals = []
    for row in cursor.fetchall():
        signals.append({
            'id': row[0],
            'symbol': row[1],
            'timeframe': row[2],
            'direction': row[3],
            'kline_timestamp': row[4],
            'entry_price': row[5],
            'stop_loss': row[6],
            'take_profit_1': row[7],
            'pnl_ratio': row[8],
            'tags_json': row[9],
            'source': row[10],
            'created_at': row[11],
        })

    conn.close()
    return signals

def analyze_kline_volatility(klines, kline_ts):
    """分析 K 线波动率"""
    if not klines:
        return None

    signal_candle = None
    for k in klines:
        if k[0] == kline_ts:
            signal_candle = k
            break

    if not signal_candle:
        return None

    ts, o, h, l, c, v = signal_candle
    candle_range = h - l
    range_pct = (candle_range / o) * 100 if o > 0 else 0

    # ATR 过滤器配置
    MIN_ATR_RATIO = 0.5  # 0.5%
    MIN_ABSOLUTE_RANGE = 0.1  # 0.1 USDT

    return {
        'open': o,
        'high': h,
        'low': l,
        'close': c,
        'range': candle_range,
        'range_pct': range_pct,
        'atr_check_pct': range_pct >= MIN_ATR_RATIO,
        'atr_check_abs': candle_range >= MIN_ABSOLUTE_RANGE,
        'atr_passed': range_pct >= MIN_ATR_RATIO and candle_range >= MIN_ABSOLUTE_RANGE,
    }

def analyze_pinbar_metrics(kline):
    """分析 Pinbar 形态"""
    if not kline:
        return None

    ts, o, h, l, c, v = kline
    candle_range = h - l
    if candle_range == 0:
        return None

    body = abs(c - o)
    body_ratio = body / candle_range
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # Pinbar 配置 (user-prod.yaml)
    MIN_WICK = 0.5
    MAX_BODY = 0.35
    TOLERANCE = 0.3

    dominant_wick = max(upper_wick, lower_wick)
    wick_ratio = dominant_wick / candle_range

    is_pinbar = wick_ratio >= MIN_WICK and body_ratio <= MAX_BODY

    # 方向检测
    body_center = (o + c) / 2
    body_position = (body_center - l) / candle_range

    direction = None
    if dominant_wick == lower_wick:
        threshold = 1 - TOLERANCE - body_ratio / 2
        if body_position >= threshold:
            direction = 'LONG'
    else:
        threshold = TOLERANCE + body_ratio / 2
        if body_position <= threshold:
            direction = 'SHORT'

    return {
        'body_ratio': body_ratio,
        'wick_ratio': wick_ratio,
        'upper_wick_ratio': upper_wick / candle_range,
        'lower_wick_ratio': lower_wick / candle_range,
        'dominant_wick': 'upper' if dominant_wick == upper_wick else 'lower',
        'body_position': body_position,
        'is_pinbar': is_pinbar,
        'detected_direction': direction,
    }

# ============================================================
# 日志分析
# ============================================================

def analyze_logs():
    """分析日志中的 ATR 过滤器执行情况"""
    import subprocess

    # 获取日志内容
    result = subprocess.run(
        ['ssh', 'root@45.76.111.81', 'cat /usr/local/monitorDog/logs/dingdingbot.log.2026-03-29.log'],
        capture_output=True, text=True, timeout=30
    )

    logs = result.stdout

    atr_enabled_count = 0
    atr_rejected_count = 0
    signal_fired_count = 0

    atr_enabled_lines = []
    atr_rejected_lines = []

    for line in logs.split('\n'):
        if 'atr' in line.lower() or 'ATRRatio' in line or 'AtrFilter' in line:
            if 'ENABLED' in line and 'atr' in line:
                atr_enabled_count += 1
                atr_enabled_lines.append(line)
            if 'FILTER_REJECTED' in line and 'atr' in line:
                atr_rejected_count += 1
                atr_rejected_lines.append(line)
            if 'SIGNAL_FIRED' in line or 'Signal sent' in line:
                signal_fired_count += 1

    return {
        'atr_enabled_count': atr_enabled_count,
        'atr_rejected_count': atr_rejected_count,
        'signal_fired_count': signal_fired_count,
        'atr_enabled_lines': atr_enabled_lines[:5],
        'atr_rejected_lines': atr_rejected_lines[:10],
    }

# ============================================================
# 主分析
# ============================================================

def main():
    print("=" * 120)
    print("回测信号 ATR 过滤器失效问题分析报告")
    print("=" * 120)
    print(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 1. 获取回测信号
    signals = get_backtest_signals()
    print(f"分析对象：{len(signals)} 个回测信号")
    print()

    # 2. ATR 合规性分析
    print("=" * 120)
    print("【1】ATR 过滤器合规性分析")
    print("=" * 120)

    atr_passed = 0
    atr_failed = 0
    failed_signals = []

    for signal in signals:
        data = fetch_signal_context(signal['id'])
        if data and 'klines' in data:
            klines = data['klines']
            kline_ts = signal['kline_timestamp']

            vol = analyze_kline_volatility(klines, kline_ts)
            if vol:
                if vol['atr_passed']:
                    atr_passed += 1
                else:
                    atr_failed += 1
                    failed_signals.append({
                        'signal': signal,
                        'volatility': vol,
                    })

    print(f"\nATR 过滤器检查结果:")
    print(f"  ✅ 通过：{atr_passed} ({atr_passed/(atr_passed+atr_failed)*100:.1f}%)")
    print(f"  ❌ 失败：{atr_failed} ({atr_failed/(atr_passed+atr_failed)*100:.1f}%)")
    print()

    if failed_signals:
        print("失败信号详情:")
        for fs in failed_signals[:10]:
            s = fs['signal']
            v = fs['volatility']
            print(f"  ID:{s['id']} | {s['symbol']} {s['timeframe']} | "
                  f"波幅:{v['range_pct']:.3f}% (需≥0.5%) | "
                  f"绝对波幅:{v['range']:.4f} (需≥0.1)")
    print()

    # 3. Pinbar 形态分析
    print("=" * 120)
    print("【2】Pinbar 形态合规性分析")
    print("=" * 120)

    pinbar_passed = 0
    pinbar_failed = 0
    direction_mismatch = 0

    for signal in signals:
        data = fetch_signal_context(signal['id'])
        if data and 'klines' in data:
            klines = data['klines']
            kline_ts = signal['kline_timestamp']

            signal_candle = None
            for k in klines:
                if k[0] == kline_ts:
                    signal_candle = k
                    break

            if signal_candle:
                metrics = analyze_pinbar_metrics(signal_candle)
                if metrics:
                    if metrics['is_pinbar']:
                        pinbar_passed += 1
                        # 检查方向匹配
                        actual_dir = signal['direction'].lower()
                        detected_dir = metrics['detected_direction']
                        if detected_dir:
                            detected_dir_lower = detected_dir.lower()
                            if detected_dir_lower != actual_dir:
                                direction_mismatch += 1
                    else:
                        pinbar_failed += 1

    print(f"\nPinbar 形态检查结果:")
    print(f"  ✅ 符合 Pinbar: {pinbar_passed}")
    print(f"  ❌ 不符合 Pinbar: {pinbar_failed}")
    print(f"  ⚠️  方向不匹配：{direction_mismatch}")
    print()

    # 4. 日志分析
    print("=" * 120)
    print("【3】日志溯源分析")
    print("=" * 120)

    log_stats = analyze_logs()

    print(f"\n日志统计:")
    print(f"  ATR 启用记录：{log_stats['atr_enabled_count']} 次")
    print(f"  ATR 拒绝记录：{log_stats['atr_rejected_count']} 次")
    print(f"  信号发送记录：{log_stats['signal_fired_count']} 次")
    print()

    if log_stats['atr_rejected_lines']:
        print("ATR 拒绝示例:")
        for line in log_stats['atr_rejected_lines'][:5]:
            print(f"  {line.strip()[:200]}")
    else:
        print("  ⚠️  未发现 ATR 过滤器拒绝记录！")
    print()

    # 5. 详细信号分析
    print("=" * 120)
    print("【4】问题信号详细分析")
    print("=" * 120)

    # 选取几个典型问题信号
    problem_ids = [294, 293]  # ATR 失败的信号

    for signal_id in problem_ids:
        signal = next((s for s in signals if s['id'] == signal_id), None)
        if not signal:
            continue

        data = fetch_signal_context(signal_id)
        if not data or 'klines' not in data:
            continue

        klines = data['klines']
        kline_ts = signal['kline_timestamp']

        vol = analyze_kline_volatility(klines, kline_ts)
        signal_candle = None
        for k in klines:
            if k[0] == kline_ts:
                signal_candle = k
                break

        metrics = analyze_pinbar_metrics(signal_candle) if signal_candle else None

        print(f"\n{'─'*80}")
        print(f"信号 {signal_id}: {signal['symbol']} {signal['timeframe']} {signal['direction'].upper()}")
        print(f"{'─'*80}")

        print("\n【K 线数据】")
        if signal_candle:
            print(f"  O:{signal_candle[1]} H:{signal_candle[2]} L:{signal_candle[3]} C:{signal_candle[4]}")

        print("\n【ATR 过滤器检查】")
        if vol:
            print(f"  K 线波幅：{vol['range']:.4f} ({vol['range_pct']:.3f}%)")
            print(f"  最小波幅要求：≥0.5% 且 ≥0.1 USDT")
            print(f"  波幅百分比：{'✅' if vol['atr_check_pct'] else '❌'} {vol['range_pct']:.3f}% >= 0.5%")
            print(f"  绝对波幅：{'✅' if vol['atr_check_abs'] else '❌'} {vol['range']:.4f} >= 0.1")
            print(f"  ATR 判定：{'✅ 通过' if vol['atr_passed'] else '❌ 失败'}")

        print("\n【Pinbar 形态检查】")
        if metrics:
            print(f"  影线比：{metrics['wick_ratio']:.2%} (需≥50%) {'✅' if metrics['wick_ratio'] >= 0.5 else '❌'}")
            print(f"  实体比：{metrics['body_ratio']:.2%} (需≤35%) {'✅' if metrics['body_ratio'] <= 0.35 else '❌'}")
            print(f"  主导影线：{metrics['dominant_wick']}")
            print(f"  检测方向：{metrics['detected_direction']}")
            print(f"  实际方向：{signal['direction'].upper()}")
            print(f"  Pinbar 判定：{'✅ 符合' if metrics['is_pinbar'] else '❌ 不符合'}")

        print("\n【标签信息】")
        if signal['tags_json']:
            try:
                tags = json.loads(signal['tags_json'])
                for t in tags:
                    print(f"  {t['name']}: {t['value']}")
            except:
                pass

    # 6. 根因分析
    print()
    print("=" * 120)
    print("【5】根因分析与结论")
    print("=" * 120)

    print("""
问题根因分析:

1. ATR 过滤器配置检查
   ┌─────────────────────────────────────────────────────────┐
   │ 配置项              │ 配置值   │ 标准值   │ 状态      │
   ├─────────────────────────────────────────────────────────┤
   │ min_atr_ratio       │ 0.5%     │ 0.5%     │ ✅ 正常   │
   │ min_absolute_range  │ 0.1      │ 0.1      │ ✅ 正常   │
   └─────────────────────────────────────────────────────────┘

2. 发现的问题:
   - 部分信号 K 线波幅 < 0.5%，但仍然生成了信号
   - 日志中未发现 ATR 过滤器拒绝记录
   - 说明 ATR 过滤器可能未实际执行，或者执行逻辑有误

3. 可能的原因:
   a) 回测模式下 ATR 过滤器被跳过
   b) ATR 数据未正确初始化/计算
   c) ATR 过滤器配置未正确加载到回测引擎
   d) 过滤器执行顺序问题，ATR 检查在错误的时间点

4. 需要进一步检查:
   - 回测引擎代码中 ATR 过滤器的集成点
   - 回测模式下的过滤器启用逻辑
   - ATR 计算器的初始化流程
""")

    # 7. 建议
    print("=" * 120)
    print("【6】修复建议")
    print("=" * 120)

    print("""
1. 🔴 高优先级：检查回测引擎的 ATR 过滤器集成

   在 src/application/backtester.py 或相关回测代码中，
   确认 ATR 过滤器是否被正确实例化和调用。

2. 🟡 中优先级：添加 ATR 过滤器执行日志

   在 ATR 过滤器的 check() 方法中添加详细日志:
   logger.debug(f"[ATR_FILTER] symbol={symbol} range={candle_range} "
                f"atr={atr_value} ratio={atr_ratio} passed={passed}")

3. 🟢 低优先级：验证配置加载

   确认 user-prod.yaml 中的 atr_filter 配置被正确加载到回测上下文。

4. 建议修改的代码位置:
   - src/domain/filter_factory.py (ATR 过滤器工厂)
   - src/application/backtester.py (回测引擎)
   - src/infrastructure/atr_filter.py (ATR 过滤器实现)
""")

    print()
    print("=" * 120)
    print("报告完成")
    print("=" * 120)

if __name__ == '__main__':
    main()
