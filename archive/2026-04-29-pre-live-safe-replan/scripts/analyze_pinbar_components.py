#!/usr/bin/env python3
"""
Pinbar 成分与胜率相关性分析

Task C: 验证"高 wick_ratio = 陷阱形态"假设

步骤:
1. 从 backtest_reports.positions_summary 提取 entry_time
2. 用 entry_time + symbol 关联 klines 表
3. 计算 wick_ratio, body_ratio, body_position
4. 分析与胜率的相关性
"""

import sqlite3
import json
from decimal import Decimal
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import math


@dataclass
class SignalFeatures:
    """信号特征"""
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_time: int
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    exit_reason: str
    # K 线特征
    wick_ratio: Optional[float] = None
    body_ratio: Optional[float] = None
    body_position: Optional[float] = None
    atr_ratio: Optional[float] = None


def load_positions_from_reports(db_path: str) -> List[Dict[str, Any]]:
    """从 backtest_reports 加载 positions_summary"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, symbol, timeframe, positions_summary, total_trades
        FROM backtest_reports
        WHERE total_trades > 0
    """)

    all_positions = []
    for row in cursor.fetchall():
        report_id, symbol, timeframe, positions_json, _ = row
        if positions_json:
            positions = json.loads(positions_json)
            for pos in positions:
                pos['report_symbol'] = symbol
                pos['report_timeframe'] = timeframe
                all_positions.append(pos)

    conn.close()
    return all_positions


def get_kline_for_signal(db_path: str, symbol: str, timeframe: str, entry_time: int) -> Optional[Dict]:
    """获取信号触发时的 K 线数据"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 查找 entry_time 对应的 K 线（允许 ±1 根 K 线的容差）
    timeframe_ms = {
        '15m': 15 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
    }

    tolerance = timeframe_ms.get(timeframe, 60 * 60 * 1000) * 2

    cursor.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM klines
        WHERE symbol = ?
        AND timeframe = ?
        AND ABS(timestamp - ?) <= ?
        ORDER BY ABS(timestamp - ?)
        LIMIT 1
    """, (symbol, timeframe, entry_time, tolerance, entry_time))

    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            'timestamp': row[0],
            'open': Decimal(str(row[1])),
            'high': Decimal(str(row[2])),
            'low': Decimal(str(row[3])),
            'close': Decimal(str(row[4])),
            'volume': Decimal(str(row[5])),
        }
    return None


def calculate_features(kline: Dict) -> Tuple[float, float, float]:
    """计算 K 线特征"""
    o, h, l, c = kline['open'], kline['high'], kline['low'], kline['close']

    candle_range = h - l
    if candle_range == 0:
        return None, None, None

    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    # wick_ratio: 最大影线占比
    wick_ratio = float(max(upper_wick, lower_wick) / candle_range)

    # body_ratio: 实体占比
    body_ratio = float(body / candle_range)

    # body_position: 实体位置 (0=底部, 1=顶部)
    body_center = (max(o, c) + min(o, c)) / 2
    body_position = float((body_center - l) / candle_range)

    return wick_ratio, body_ratio, body_position


def analyze_correlation(features: List[SignalFeatures]) -> Dict[str, Any]:
    """分析特征与胜率的相关性"""

    # 提取有效数据
    wick_data = [(f.wick_ratio, 1 if f.realized_pnl > 0 else 0)
                 for f in features if f.wick_ratio is not None]
    body_data = [(f.body_ratio, 1 if f.realized_pnl > 0 else 0)
                 for f in features if f.body_ratio is not None]
    position_data = [(f.body_position, 1 if f.realized_pnl > 0 else 0)
                     for f in features if f.body_position is not None]

    def pearson_correlation(data: List[Tuple[float, int]]) -> float:
        """计算皮尔逊相关系数"""
        if len(data) < 10:
            return 0.0

        x = [d[0] for d in data]
        y = [d[1] for d in data]

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(a * b for a, b in zip(x, y))
        sum_x2 = sum(a * a for a in x)
        sum_y2 = sum(a * a for a in y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    # 分桶统计
    def bucket_analysis(data: List[Tuple[float, int]], buckets: List[Tuple[float, float]]) -> List[Dict]:
        results = []
        for low, high in buckets:
            bucket_data = [d for d in data if low <= d[0] < high]
            if bucket_data:
                wins = sum(d[1] for d in bucket_data)
                total = len(bucket_data)
                avg_pnl = 0  # 需要额外数据
                results.append({
                    'range': f"{low:.2f}-{high:.2f}",
                    'count': total,
                    'wins': wins,
                    'win_rate': wins / total if total > 0 else 0,
                })
        return results

    # wick_ratio 分桶
    wick_buckets = [(0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 1.00)]
    wick_bucket_results = bucket_analysis(wick_data, wick_buckets)

    # body_ratio 分桶
    body_buckets = [(0.0, 0.15), (0.15, 0.25), (0.25, 0.35), (0.35, 0.50), (0.50, 1.00)]
    body_bucket_results = bucket_analysis(body_data, body_buckets)

    # body_position 分桶
    position_buckets = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0)]
    position_bucket_results = bucket_analysis(position_data, position_buckets)

    return {
        'wick_ratio': {
            'correlation': pearson_correlation(wick_data),
            'buckets': wick_bucket_results,
            'sample_count': len(wick_data),
        },
        'body_ratio': {
            'correlation': pearson_correlation(body_data),
            'buckets': body_bucket_results,
            'sample_count': len(body_data),
        },
        'body_position': {
            'correlation': pearson_correlation(position_data),
            'buckets': position_bucket_results,
            'sample_count': len(position_data),
        },
    }


def main():
    db_path = 'data/v3_dev.db'

    print("=" * 60)
    print("Pinbar 成分与胜率相关性分析")
    print("=" * 60)

    # 1. 加载仓位数据
    print("\n[Step 1] 加载仓位数据...")
    positions = load_positions_from_reports(db_path)
    print(f"  共加载 {len(positions)} 个仓位")

    # 2. 关联 K 线数据并计算特征
    print("\n[Step 2] 关联 K 线数据并计算特征...")
    features = []
    matched = 0

    for pos in positions:
        signal = SignalFeatures(
            signal_id=pos.get('signal_id', ''),
            symbol=pos.get('report_symbol', ''),
            timeframe=pos.get('report_timeframe', ''),
            direction=pos.get('direction', ''),
            entry_time=pos.get('entry_time', 0),
            entry_price=Decimal(str(pos.get('entry_price', '0') or '0')),
            exit_price=Decimal(str(pos.get('exit_price', '0') or '0')),
            realized_pnl=Decimal(str(pos.get('realized_pnl', '0') or '0')),
            exit_reason=pos.get('exit_reason', ''),
        )

        # 获取 K 线数据
        kline = get_kline_for_signal(
            db_path,
            signal.symbol,
            signal.timeframe,
            signal.entry_time
        )

        if kline:
            wick, body, position = calculate_features(kline)
            signal.wick_ratio = wick
            signal.body_ratio = body
            signal.body_position = position
            matched += 1

        features.append(signal)

    print(f"  成功匹配 K 线: {matched} / {len(positions)}")

    # 3. 分析相关性
    print("\n[Step 3] 分析特征与胜率的相关性...")
    analysis = analyze_correlation(features)

    # 4. 输出结果
    print("\n" + "=" * 80)
    print("分析结果")
    print("=" * 80)

    # wick_ratio 分析
    print("\n## wick_ratio 与胜率")
    print(f"皮尔逊相关系数: {analysis['wick_ratio']['correlation']:.4f}")
    print(f"样本数: {analysis['wick_ratio']['sample_count']}")
    print("\n| 分桶 | 信号数 | 胜数 | 胜率 |")
    print("|------|--------|------|------|")
    for b in analysis['wick_ratio']['buckets']:
        print(f"| {b['range']} | {b['count']} | {b['wins']} | {b['win_rate']:.1%} |")

    # body_ratio 分析
    print("\n## body_ratio 与胜率")
    print(f"皮尔逊相关系数: {analysis['body_ratio']['correlation']:.4f}")
    print(f"样本数: {analysis['body_ratio']['sample_count']}")
    print("\n| 分桶 | 信号数 | 胜数 | 胜率 |")
    print("|------|--------|------|------|")
    for b in analysis['body_ratio']['buckets']:
        print(f"| {b['range']} | {b['count']} | {b['wins']} | {b['win_rate']:.1%} |")

    # body_position 分析
    print("\n## body_position 与胜率")
    print(f"皮尔逊相关系数: {analysis['body_position']['correlation']:.4f}")
    print(f"样本数: {analysis['body_position']['sample_count']}")
    print("\n| 分桶 | 信号数 | 胜数 | 胜率 |")
    print("|------|--------|------|------|")
    for b in analysis['body_position']['buckets']:
        print(f"| {b['range']} | {b['count']} | {b['wins']} | {b['win_rate']:.1%} |")

    # 结论
    print("\n" + "=" * 80)
    print("结论")
    print("=" * 80)

    wick_corr = analysis['wick_ratio']['correlation']
    body_corr = analysis['body_ratio']['correlation']
    pos_corr = analysis['body_position']['correlation']

    print(f"\n1. wick_ratio 与胜率相关性: {wick_corr:+.4f}")
    if wick_corr > 0.1:
        print("   → 正相关：影线占比越高，胜率越高")
    elif wick_corr < -0.1:
        print("   → 负相关：影线占比越高，胜率越低（支持'高分=陷阱'假设）")
    else:
        print("   → 相关性极弱，无显著预测力")

    print(f"\n2. body_ratio 与胜率相关性: {body_corr:+.4f}")
    print(f"\n3. body_position 与胜率相关性: {pos_corr:+.4f}")

    # 甜蜜区间分析
    print("\n## 甜蜜区间分析")
    wick_buckets = analysis['wick_ratio']['buckets']
    if wick_buckets:
        best_bucket = max(wick_buckets, key=lambda x: x['win_rate'])
        print(f"wick_ratio 最佳区间: {best_bucket['range']} (胜率 {best_bucket['win_rate']:.1%})")

    # 保存结果
    import os
    os.makedirs('docs/diagnostic-reports', exist_ok=True)

    with open('docs/diagnostic-reports/DA-20260419-003-pinbar-component-analysis.md', 'w') as f:
        f.write("# Pinbar 成分与胜率相关性分析\n\n")
        f.write(f"> 生成时间: 2026-04-19\n")
        f.write(f"> 样本数: {len(features)} (K线匹配: {matched})\n\n")
        f.write("---\n\n")
        f.write("## 执行摘要\n\n")
        f.write(f"| 成分 | 相关系数 | 说明 |\n")
        f.write(f"|------|----------|------|\n")
        f.write(f"| wick_ratio | {wick_corr:+.4f} | {'负相关' if wick_corr < -0.1 else '正相关' if wick_corr > 0.1 else '无显著相关'} |\n")
        f.write(f"| body_ratio | {body_corr:+.4f} | {'负相关' if body_corr < -0.1 else '正相关' if body_corr > 0.1 else '无显著相关'} |\n")
        f.write(f"| body_position | {pos_corr:+.4f} | {'负相关' if pos_corr < -0.1 else '正相关' if pos_corr > 0.1 else '无显著相关'} |\n\n")
        f.write("## wick_ratio 分桶统计\n\n")
        f.write("| 分桶 | 信号数 | 胜数 | 胜率 |\n")
        f.write("|------|--------|------|------|\n")
        for b in analysis['wick_ratio']['buckets']:
            f.write(f"| {b['range']} | {b['count']} | {b['wins']} | {b['win_rate']:.1%} |\n")
        f.write("\n## 结论\n\n")
        if wick_corr < -0.1:
            f.write("**'高分=陷阱'假设成立**: wick_ratio 与胜率负相关，影线占比越高胜率越低。\n")
        elif wick_corr > 0.1:
            f.write("**'高分=陷阱'假设不成立**: wick_ratio 与胜率正相关，影线占比越高胜率越高。\n")
        else:
            f.write("**'高分=陷阱'假设不成立**: wick_ratio 与胜率无显著相关性。\n")

    print("\n结果已保存到: docs/diagnostic-reports/DA-20260419-003-pinbar-component-analysis.md")


if __name__ == "__main__":
    main()
