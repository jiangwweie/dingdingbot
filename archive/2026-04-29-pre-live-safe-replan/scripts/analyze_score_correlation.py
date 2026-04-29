#!/usr/bin/env python3
"""
评分公式验证脚本 - 从回测数据库提取信号评分与盈亏结果，分析相关性

任务 1.1: 从数据库提取原始数据
任务 1.2: 精细分组分析（0.05 间隔，20 档）
任务 1.3: 拆解评分成分（wick_ratio, body_ratio, atr_ratio）
任务 1.4: 模拟新评分公式 v2，验证相关性
"""

import sqlite3
import json
import statistics
from decimal import Decimal
from collections import defaultdict
from typing import List, Dict, Any, Tuple

DB_PATH = "data/v3_dev.db"


def extract_raw_data() -> List[Dict[str, Any]]:
    """
    任务 1.1: 从数据库提取原始数据
    返回: [{report_id, symbol, timeframe, signal_idx, final_score, components, pnl, is_win}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    results = []

    # 获取所有有交易的报告
    cursor.execute("""
        SELECT id, symbol, timeframe, total_trades, winning_trades, positions_summary
        FROM backtest_reports
        WHERE total_trades > 0
    """)
    reports = cursor.fetchall()

    for report_id, symbol, timeframe, total_trades, winning_trades, positions_json in reports:
        # 获取归因数据
        cursor.execute("""
            SELECT signal_attributions
            FROM backtest_attributions
            WHERE report_id = ?
        """, (report_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            continue

        signal_attributions = json.loads(row[0])

        # 解析 positions_summary 获取每个仓位的 PnL
        positions = json.loads(positions_json) if positions_json else []

        # 建立 signal_id -> position 映射
        signal_to_position = {}
        for pos in positions:
            signal_id = pos.get('signal_id')
            if signal_id:
                signal_to_position[signal_id] = pos

        # 获取出场事件统计
        cursor.execute("""
            SELECT position_id, event_type, close_pnl
            FROM position_close_events
            WHERE report_id = ?
        """, (report_id,))
        close_events = cursor.fetchall()

        # 建立 position_id -> 出场结果 映射
        position_outcomes = {}
        for pos_id, event_type, close_pnl in close_events:
            if pos_id not in position_outcomes:
                position_outcomes[pos_id] = {'events': [], 'pnl': Decimal('0')}
            position_outcomes[pos_id]['events'].append(event_type)
            if close_pnl:
                position_outcomes[pos_id]['pnl'] += Decimal(close_pnl)

        # 合并信号评分与仓位 PnL
        for idx, attr in enumerate(signal_attributions):
            final_score = attr.get('final_score', 0)
            components = attr.get('components', [])

            # 尝试通过索引匹配仓位
            pnl = Decimal('0')
            is_win = False
            exit_type = None

            if idx < len(positions):
                pos = positions[idx]
                pos_id = pos.get('position_id', pos.get('id'))
                signal_id = pos.get('signal_id')

                # 优先使用出场事件数据
                if pos_id in position_outcomes:
                    outcome = position_outcomes[pos_id]
                    pnl = outcome['pnl']
                    is_win = pnl > 0
                    exit_type = outcome['events'][0] if outcome['events'] else None
                else:
                    # 回退到 position 的 realized_pnl
                    pnl = Decimal(pos.get('realized_pnl', '0'))
                    is_win = pnl > 0

            results.append({
                'report_id': report_id,
                'symbol': symbol,
                'timeframe': timeframe,
                'signal_idx': idx,
                'final_score': final_score,
                'components': components,
                'pnl': float(pnl),
                'is_win': is_win,
                'exit_type': exit_type,
            })

    conn.close()
    return results


def score_distribution_analysis(data: List[Dict[str, Any]], bucket_size: float = 0.05) -> Dict[str, Any]:
    """
    任务 1.2: 精细分组分析（0.05 间隔，20 档）
    """
    # 按分数分桶
    buckets = defaultdict(list)
    for item in data:
        score = item['final_score']
        bucket_idx = int(score / bucket_size)
        bucket_key = f"{bucket_idx * bucket_size:.2f}-{(bucket_idx + 1) * bucket_size:.2f}"
        buckets[bucket_key].append(item)

    # 计算每个桶的统计量
    analysis = []
    for bucket_key in sorted(buckets.keys()):
        items = buckets[bucket_key]
        wins = [i for i in items if i['is_win']]
        losses = [i for i in items if not i['is_win']]

        win_rate = len(wins) / len(items) if items else 0
        avg_pnl = statistics.mean([i['pnl'] for i in items]) if items else 0
        avg_score = statistics.mean([i['final_score'] for i in items]) if items else 0

        analysis.append({
            'bucket': bucket_key,
            'count': len(items),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'avg_pnl': avg_pnl,
            'avg_score': avg_score,
        })

    return {
        'buckets': analysis,
        'total_signals': len(data),
        'total_wins': sum(1 for i in data if i['is_win']),
        'overall_win_rate': sum(1 for i in data if i['is_win']) / len(data) if data else 0,
    }


def component_analysis(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    任务 1.3: 拆解评分成分（pattern, ema_trend, mtf, atr）
    """
    component_stats = defaultdict(lambda: {'scores': [], 'wins': [], 'losses': []})

    for item in data:
        for comp in item['components']:
            name = comp.get('name', 'unknown')
            score = comp.get('score', 0)
            component_stats[name]['scores'].append(score)
            if item['is_win']:
                component_stats[name]['wins'].append(score)
            else:
                component_stats[name]['losses'].append(score)

    analysis = {}
    for name, stats in component_stats.items():
        scores = stats['scores']
        wins = stats['wins']
        losses = stats['losses']

        analysis[name] = {
            'count': len(scores),
            'avg_score': statistics.mean(scores) if scores else 0,
            'std_score': statistics.stdev(scores) if len(scores) > 1 else 0,
            'avg_score_when_win': statistics.mean(wins) if wins else 0,
            'avg_score_when_loss': statistics.mean(losses) if losses else 0,
            'score_diff': (statistics.mean(wins) if wins else 0) - (statistics.mean(losses) if losses else 0),
        }

    return analysis


def calculate_score_v2(wick_ratio: float, body_ratio: float, body_position: float, atr_ratio: float = None) -> float:
    """
    任务 1.4: 新评分公式 v2（Opus 建议）

    关键改变：
    - 影线占比：从"越长越好"改为"0.7 附近最好"（钟形曲线）
    - 极端波幅：从"加分"改为"减分"（超过 1.5x ATR 开始打折）
    - 新增维度：实体位置（body_position）反映收盘力度
    """
    # 影线质量：bell curve centered at 0.7
    wick_score = 1.0 - abs(wick_ratio - 0.7) * 3
    wick_score = max(0, min(wick_score, 1.0))

    # 实体位置质量（body_position 0=bottom, 1=top）
    position_score = body_position

    # 波幅质量：0.5-1.5 ATR 是最佳区间
    if atr_ratio and atr_ratio > 0:
        if atr_ratio < 0.5:
            vol_score = atr_ratio / 0.5
        elif atr_ratio <= 1.5:
            vol_score = 1.0
        else:
            vol_score = 1.5 / atr_ratio
    else:
        vol_score = 0.5

    # 综合评分
    score = wick_score * 0.4 + position_score * 0.3 + vol_score * 0.3

    return min(score, 1.0)


def simulate_v2_score(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    任务 1.4: 模拟新评分公式 v2，验证相关性

    由于我们没有原始的 wick_ratio, body_ratio 等数据，
    这里用现有 component scores 来模拟
    """
    # 提取 pattern score 作为 wick_ratio 的代理
    # 注意：这是近似，因为 pattern score 已经是综合评分

    v1_scores = []
    v2_scores = []
    wins = []

    for item in data:
        v1_score = item['final_score']

        # 从 components 提取原始数据
        pattern_score = 0
        ema_score = 0
        mtf_score = 0
        atr_score = 0

        for comp in item['components']:
            name = comp.get('name', '')
            score = comp.get('score', 0)
            if name == 'pattern':
                pattern_score = score
            elif name == 'ema_trend':
                ema_score = score
            elif name == 'mtf':
                mtf_score = score
            elif name == 'atr_volatility':
                atr_score = score

        # 模拟 v2 评分
        # 假设 pattern_score ≈ wick_ratio（近似）
        # body_position 从 ema_score 推断（ema 强 = 收盘位置好）
        wick_ratio = pattern_score  # 近似
        body_ratio = 1 - pattern_score  # 近似
        body_position = ema_score  # 近似
        atr_ratio = atr_score * 2 if atr_score > 0 else 1.0

        v2_score = calculate_score_v2(wick_ratio, body_ratio, body_position, atr_ratio)

        v1_scores.append(v1_score)
        v2_scores.append(v2_score)
        wins.append(1 if item['is_win'] else 0)

    # 计算相关性
    def correlation(x, y):
        n = len(x)
        if n < 2:
            return 0
        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)
        std_x = statistics.stdev(x)
        std_y = statistics.stdev(y)
        if std_x == 0 or std_y == 0:
            return 0
        return sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / (n * std_x * std_y)

    v1_corr = correlation(v1_scores, wins)
    v2_corr = correlation(v2_scores, wins)

    # 分桶对比
    def bucket_analysis(scores, wins, bucket_size=0.1):
        buckets = defaultdict(lambda: {'wins': 0, 'total': 0})
        for score, win in zip(scores, wins):
            bucket_idx = int(score / bucket_size)
            bucket_key = f"{bucket_idx * bucket_size:.1f}-{(bucket_idx + 1) * bucket_size:.1f}"
            buckets[bucket_key]['total'] += 1
            if win:
                buckets[bucket_key]['wins'] += 1

        result = []
        for key in sorted(buckets.keys()):
            b = buckets[key]
            result.append({
                'bucket': key,
                'count': b['total'],
                'wins': b['wins'],
                'win_rate': b['wins'] / b['total'] if b['total'] > 0 else 0,
            })
        return result

    return {
        'v1_correlation': v1_corr,
        'v2_correlation': v2_corr,
        'v1_buckets': bucket_analysis(v1_scores, wins),
        'v2_buckets': bucket_analysis(v2_scores, wins),
        'improvement': v2_corr - v1_corr,
    }


def main():
    print("=" * 60)
    print("评分公式验证脚本")
    print("=" * 60)

    # 任务 1.1: 提取原始数据
    print("\n[任务 1.1] 从数据库提取原始数据...")
    data = extract_raw_data()
    print(f"  提取到 {len(data)} 条信号数据")

    if not data:
        print("  ⚠️ 无数据，退出")
        return

    # 任务 1.2: 精细分组分析
    print("\n[任务 1.2] 精细分组分析（0.05 间隔）...")
    dist_analysis = score_distribution_analysis(data, bucket_size=0.05)

    print(f"\n  总信号数: {dist_analysis['total_signals']}")
    print(f"  总胜数: {dist_analysis['total_wins']}")
    print(f"  整体胜率: {dist_analysis['overall_win_rate']:.2%}")

    print("\n  分数区间分布:")
    print(f"  {'区间':<12} {'数量':>6} {'胜数':>6} {'胜率':>8} {'平均PnL':>12}")
    print("  " + "-" * 50)
    for b in dist_analysis['buckets']:
        if b['count'] > 0:
            print(f"  {b['bucket']:<12} {b['count']:>6} {b['wins']:>6} {b['win_rate']:>7.1%} {b['avg_pnl']:>12.2f}")

    # 任务 1.3: 拆解评分成分
    print("\n[任务 1.3] 拆解评分成分...")
    comp_analysis = component_analysis(data)

    print("\n  各成分统计:")
    print(f"  {'成分':<15} {'数量':>6} {'平均分':>8} {'胜时分':>8} {'败时分':>8} {'差值':>8}")
    print("  " + "-" * 55)
    for name, stats in comp_analysis.items():
        print(f"  {name:<15} {stats['count']:>6} {stats['avg_score']:>8.3f} "
              f"{stats['avg_score_when_win']:>8.3f} {stats['avg_score_when_loss']:>8.3f} "
              f"{stats['score_diff']:>+8.3f}")

    # 任务 1.4: 模拟新评分公式
    print("\n[任务 1.4] 模拟新评分公式 v2...")
    v2_analysis = simulate_v2_score(data)

    print(f"\n  V1 评分与胜率相关性: {v2_analysis['v1_correlation']:+.4f}")
    print(f"  V2 评分与胜率相关性: {v2_analysis['v2_correlation']:+.4f}")
    print(f"  改善: {v2_analysis['improvement']:+.4f}")

    print("\n  V1 分桶胜率:")
    for b in v2_analysis['v1_buckets']:
        if b['count'] > 0:
            print(f"    {b['bucket']}: {b['win_rate']:.1%} ({b['count']} 信号)")

    print("\n  V2 分桶胜率:")
    for b in v2_analysis['v2_buckets']:
        if b['count'] > 0:
            print(f"    {b['bucket']}: {b['win_rate']:.1%} ({b['count']} 信号)")

    # 结论
    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)

    if v2_analysis['v1_correlation'] < 0:
        print("⚠️ V1 评分是反向指标（分数越高，胜率越低）")
    else:
        print("✅ V1 评分是正向指标")

    if v2_analysis['v2_correlation'] > v2_analysis['v1_correlation']:
        print(f"✅ V2 评分相关性改善 {v2_analysis['improvement']:+.4f}")
    else:
        print(f"⚠️ V2 评分相关性未改善")

    # 找出最优分数区间
    best_bucket = max(dist_analysis['buckets'], key=lambda b: b['win_rate'] if b['count'] >= 3 else 0)
    print(f"\n最优分数区间: {best_bucket['bucket']} (胜率 {best_bucket['win_rate']:.1%})")

    # 按周期分析
    print("\n" + "=" * 60)
    print("按周期分析")
    print("=" * 60)

    tf_data = defaultdict(list)
    for item in data:
        tf_data[item['timeframe']].append(item)

    for tf, items in sorted(tf_data.items()):
        wins = sum(1 for i in items if i['is_win'])
        win_rate = wins / len(items) if items else 0
        avg_score = statistics.mean([i['final_score'] for i in items]) if items else 0
        print(f"  {tf}: {len(items)} 信号, 胜率 {win_rate:.1%}, 平均分 {avg_score:.3f}")


if __name__ == "__main__":
    main()
