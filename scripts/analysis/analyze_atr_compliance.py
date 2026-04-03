#!/usr/bin/env python3
"""
ATR 过滤器合规性深度分析
检查回测信号的波动率是否满足 ATR 过滤器要求
"""
import sqlite3
import json
from decimal import Decimal

def analyze_atr_compliance(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Get all backtest signals
    c.execute("""
    SELECT id, symbol, timeframe, direction, entry_price, stop_loss,
           created_at, tags_json, score, leverage, position_size, risk_info,
           pattern_score
    FROM signals
    WHERE source='backtest'
    ORDER BY id DESC
    """)

    signals = c.fetchall()

    print("=" * 130)
    print("ATR 过滤器合规性深度分析报告")
    print("=" * 130)
    print(f"\n分析信号总数：{len(signals)}\n")

    # ATR 过滤器配置
    MIN_ATR_RATIO = Decimal("0.005")  # 0.5%
    MIN_ABSOLUTE_RANGE = Decimal("0.1")

    print(f"ATR 过滤器配置:")
    print(f"  - min_atr_ratio: {MIN_ATR_RATIO} (0.5%)")
    print(f"  - min_absolute_range: {MIN_ABSOLUTE_RANGE}")
    print()

    compliance_issues = []

    print("信号详细分析:")
    print("-" * 130)

    for s in signals:
        id_, symbol, tf, direction, entry, sl, created, tags_json, score, lev, pos_size, risk, pattern_score = s

        entry = Decimal(str(entry))
        sl = Decimal(str(sl))

        # Parse tags
        try:
            tags = json.loads(tags_json) if tags_json else []
        except:
            tags = []

        # Calculate candle range (approximate from entry and stop loss)
        # For long: candle_range ≈ entry - low (where stop_loss is set)
        # For short: candle_range ≈ high - entry

        # We need to estimate the actual candle range from the signal data
        # Stop loss distance can give us an estimate of volatility

        if direction == 'long':
            # For long signals, stop loss is below entry
            sl_distance = entry - sl
            # Estimate candle range (假设止损设置在 K 线低点附近)
            estimated_candle_range = sl_distance * Decimal(str(2))  # 粗略估计
        else:
            # For short signals, stop loss is above entry
            sl_distance = sl - entry
            estimated_candle_range = sl_distance * Decimal(str(2))

        # Calculate volatility ratio
        if entry > 0:
            volatility_pct = (estimated_candle_range / entry) * 100
        else:
            volatility_pct = Decimal("0")

        # Check ATR compliance
        issues = []

        # Check 1: Absolute range threshold
        if estimated_candle_range < MIN_ABSOLUTE_RANGE:
            issues.append(f"绝对波动率不足 ({estimated_candle_range:.4f} < {MIN_ABSOLUTE_RANGE})")

        # Check 2: ATR ratio (simulated)
        # If candle_range < ATR * 0.005, it fails
        # We estimate ATR ≈ candle_range / actual_ratio
        # If actual ratio < 0.005, it should have been filtered

        # For this analysis, we check if the stop loss distance is reasonable
        sl_distance_pct = (abs(entry - sl) / entry) * 100

        # Warning if SL distance is too tight (might indicate ATR filter issue)
        if sl_distance_pct < Decimal("0.3"):
            issues.append(f"止损距离过近 ({sl_distance_pct:.3f}%) - 可能 ATR 过滤失效")

        tags_str = ", ".join([t.get('name', '') + ':' + t.get('value', '') for t in tags])

        print(f"ID:{id_} | {symbol} | {tf} | {direction.upper():5} | 入场:{float(entry):.2f} | SL 距离:{float(sl_distance_pct):.3f}% | 评分:{pattern_score:.2f} | 标签:{tags_str[:40]}")

        if issues:
            compliance_issues.append({
                'id': id_,
                'symbol': symbol,
                'direction': direction,
                'entry': float(entry),
                'sl_distance_pct': float(sl_distance_pct),
                'issues': issues
            })
            for issue in issues:
                print(f"         [警告] {issue}")

    print("\n" + "=" * 130)
    print(f"潜在问题信号数：{len(compliance_issues)}")

    if compliance_issues:
        print("\n问题信号汇总:")
        for issue in compliance_issues:
            print(f"  - ID:{issue['id']} {issue['symbol']} {issue['direction']}: {', '.join(issue['issues'])}")

    # Summary statistics
    print("\n" + "=" * 130)
    print("统计摘要:")

    long_signals = [s for s in signals if s[3] == 'long']
    short_signals = [s for s in signals if s[3] == 'short']

    print(f"  - 多单信号：{len(long_signals)}")
    print(f"  - 空单信号：{len(short_signals)}")

    # Score distribution
    scores = [float(s[8]) for s in signals]
    if scores:
        avg_score = sum(scores) / len(scores)
        min_score = min(scores)
        max_score = max(scores)
        print(f"  - 平均评分：{avg_score:.2f}")
        print(f"  - 最低评分：{min_score:.2f}")
        print(f"  - 最高评分：{max_score:.2f}")

    conn.close()
    return compliance_issues

if __name__ == "__main__":
    analyze_atr_compliance("/usr/local/monitorDog/data/signals.db")
