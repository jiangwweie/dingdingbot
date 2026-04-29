#!/usr/bin/env python3
"""
PMS回测深度诊断 - 利用signal_attempts表分析信号质量

用法：
    python3 scripts/analyze_backtest_signals.py --latest
    python3 scripts/analyze_backtest_signals.py --report-id <ID>

功能：
    1. 关联回测报告和信号尝试记录
    2. 分析被过滤的信号 vs 实际成交的信号
    3. 找出"成交后亏损"的信号特征
"""
import argparse
import asyncio
import json
import sys
from decimal import Decimal
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, '/Users/jiangwei/Documents/final')

import aiosqlite
from src.infrastructure.backtest_repository import BacktestReportRepository


class SignalAwareDiagnoser:
    """利用signal_attempts进行深度诊断"""

    def __init__(self, backtest_repo: BacktestReportRepository, db_path: str = "data/v3_dev.db"):
        self.backtest_repo = backtest_repo
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """初始化数据库连接"""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

    async def close(self):
        """关闭数据库连接"""
        if self._db:
            await self._db.close()

    async def analyze_report_with_signals(self, report_id: str) -> Dict[str, Any]:
        """
        深度分析报告，关联signal_attempts数据
        """
        # 1. 获取回测报告
        report = await self.backtest_repo.get_report(report_id)
        if not report:
            return {"error": f"报告不存在: {report_id}"}

        # 2. 获取关联的signal_attempts（通过时间范围）
        signal_attempts = await self._fetch_signal_attempts(
            report.backtest_start,
            report.backtest_end,
            report.strategy_id
        )

        # 3. 深度分析
        analysis = {
            "report_summary": {
                "strategy": report.strategy_name,
                "symbol": report.strategy_id,  # 这里可能需要调整
                "period": f"{self._ts_to_str(report.backtest_start)} ~ {self._ts_to_str(report.backtest_end)}",
                "total_return": f"{report.total_return*100:.2f}%",
                "win_rate": f"{report.win_rate*100:.1f}%",
                "total_trades": report.total_trades,
            },
            "signal_funnel": self._analyze_signal_funnel(signal_attempts),
            "fired_signals_analysis": self._analyze_fired_signals(signal_attempts, report.positions),
            "filtered_signals_analysis": self._analyze_filtered_signals(signal_attempts),
            "position_signal_correlation": self._correlate_positions_signals(report.positions, signal_attempts),
            "insights": [],
        }

        # 4. 生成洞察
        analysis["insights"] = self._generate_insights(analysis)

        return analysis

    async def _fetch_signal_attempts(self, start_ts: int, end_ts: int, strategy_hint: str = None) -> List[Dict]:
        """
        获取时间范围内的signal_attempts记录

        通过kline_timestamp关联，因为回测信号的时间戳与K线对齐
        """
        cursor = await self._db.execute("""
            SELECT * FROM signal_attempts
            WHERE kline_timestamp BETWEEN ? AND ?
            ORDER BY kline_timestamp ASC
        """, (start_ts, end_ts))

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    def _analyze_signal_funnel(self, attempts: List[Dict]) -> Dict:
        """分析信号漏斗：多少信号生成 → 多少被过滤 → 多少成交"""
        total = len(attempts)
        if total == 0:
            return {"error": "未找到signal_attempts记录"}

        fired = [a for a in attempts if a.get('final_result') == 'SIGNAL_FIRED']
        filtered = [a for a in attempts if a.get('final_result') == 'FILTERED']
        no_pattern = [a for a in attempts if a.get('final_result') == 'NO_PATTERN']

        # 过滤原因统计
        filter_reasons = defaultdict(int)
        for a in filtered:
            reason = a.get('filter_reason') or a.get('filter_stage') or 'UNKNOWN'
            filter_reasons[reason] += 1

        return {
            "total_attempts": total,
            "fired_count": len(fired),
            "filtered_count": len(filtered),
            "no_pattern_count": len(no_pattern),
            "fired_rate": f"{len(fired)/total*100:.1f}%",
            "filtered_rate": f"{len(filtered)/total*100:.1f}%",
            "filter_reasons": dict(filter_reasons),
        }

    def _analyze_fired_signals(self, attempts: List[Dict], positions: List[Any]) -> Dict:
        """分析成交信号的特征"""
        fired = [a for a in attempts if a.get('final_result') == 'SIGNAL_FIRED']
        if not fired:
            return {"error": "没有成交的信号记录"}

        # 形态评分分布
        scores = [a.get('pattern_score', 0) or 0 for a in fired]
        avg_score = sum(scores) / len(scores) if scores else 0

        score_distribution = {
            "high (>=0.8)": sum(1 for s in scores if s >= 0.8),
            "medium (0.6-0.8)": sum(1 for s in scores if 0.6 <= s < 0.8),
            "low (<0.6)": sum(1 for s in scores if s < 0.6),
        }

        # 方向分布
        directions = defaultdict(int)
        for a in fired:
            directions[a.get('direction', 'UNKNOWN')] += 1

        # 策略分布
        strategies = defaultdict(int)
        for a in fired:
            strategies[a.get('strategy_name', 'unknown')] += 1

        return {
            "count": len(fired),
            "avg_pattern_score": f"{avg_score:.2f}",
            "score_distribution": score_distribution,
            "direction_distribution": dict(directions),
            "strategy_distribution": dict(strategies),
        }

    def _analyze_filtered_signals(self, attempts: List[Dict]) -> Dict:
        """分析被过滤信号的特征 - 关键！"""
        filtered = [a for a in attempts if a.get('final_result') == 'FILTERED']
        if not filtered:
            return {"message": "没有被过滤的信号"}

        # 按过滤阶段分组
        by_stage = defaultdict(lambda: {"count": 0, "avg_score": [], "reasons": defaultdict(int)})

        for a in filtered:
            stage = a.get('filter_stage') or 'UNKNOWN'
            by_stage[stage]["count"] += 1
            if a.get('pattern_score'):
                by_stage[stage]["avg_score"].append(a['pattern_score'])

            reason = a.get('filter_reason') or 'unknown'
            by_stage[stage]["reasons"][reason] += 1

        # 计算平均评分
        result = {}
        for stage, data in by_stage.items():
            scores = data["avg_score"]
            result[stage] = {
                "count": data["count"],
                "avg_score": f"{sum(scores)/len(scores):.2f}" if scores else "N/A",
                "top_reasons": dict(sorted(data["reasons"].items(), key=lambda x: -x[1])[:3]),
            }

        return result

    def _correlate_positions_signals(self, positions: List[Any], attempts: List[Dict]) -> Dict:
        """
        关联positions和signals - 关键诊断！

        检查：成交的信号中，哪些最终盈利，哪些亏损，特征是什么
        """
        if not positions:
            return {"error": "没有持仓记录"}

        # 构建attempts的时间索引
        attempt_by_time = {}
        for a in attempts:
            ts = a.get('kline_timestamp')
            if ts:
                attempt_by_time[ts] = a

        # 分析每笔position对应的signal
        winning_signals = []
        losing_signals = []

        for pos in positions:
            # 通过entry_time匹配signal_attempt
            entry_time = pos.entry_time
            attempt = attempt_by_time.get(entry_time)

            if not attempt:
                continue

            signal_info = {
                "position_id": pos.position_id,
                "pnl": float(pos.realized_pnl) if pos.realized_pnl else 0,
                "pattern_score": attempt.get('pattern_score', 0),
                "direction": attempt.get('direction'),
                "strategy": attempt.get('strategy_name'),
            }

            if pos.realized_pnl and pos.realized_pnl > 0:
                winning_signals.append(signal_info)
            else:
                losing_signals.append(signal_info)

        # 对比盈利vs亏损信号的特征
        if winning_signals and losing_signals:
            win_scores = [s["pattern_score"] for s in winning_signals if s["pattern_score"]]
            loss_scores = [s["pattern_score"] for s in losing_signals if s["pattern_score"]]

            return {
                "winning_signals": {
                    "count": len(winning_signals),
                    "avg_pattern_score": f"{sum(win_scores)/len(win_scores):.2f}" if win_scores else "N/A",
                },
                "losing_signals": {
                    "count": len(losing_signals),
                    "avg_pattern_score": f"{sum(loss_scores)/len(loss_scores):.2f}" if loss_scores else "N/A",
                },
                "score_correlation": "高分信号胜率更高" if (win_scores and loss_scores and sum(win_scores)/len(win_scores) > sum(loss_scores)/len(loss_scores)) else "评分与胜率无明显关联",
                "losing_signals_sample": losing_signals[:3],  # 前3笔亏损详情
            }

        return {"message": "样本不足以进行关联分析"}

    def _generate_insights(self, analysis: Dict) -> List[Dict]:
        """生成诊断洞察"""
        insights = []

        # 洞察1：信号过滤率分析
        funnel = analysis.get("signal_funnel", {})
        if funnel.get("filtered_rate"):
            filtered_rate = float(funnel["filtered_rate"].rstrip('%'))
            if filtered_rate > 80:
                insights.append({
                    "type": "INFO",
                    "title": "信号过滤率过高",
                    "content": f"{filtered_rate:.1f}%的信号被过滤，说明过滤器很严格",
                    "action": "检查过滤条件是否过于激进，可能错过有效信号",
                })
            elif filtered_rate < 20:
                insights.append({
                    "type": "WARNING",
                    "title": "信号过滤率过低",
                    "content": f"只有{filtered_rate:.1f}%的信号被过滤",
                    "action": "过滤器可能太松，导致假信号成交",
                })

        # 洞察2：形态评分与盈亏关联
        correlation = analysis.get("position_signal_correlation", {})
        if "winning_signals" in correlation and "losing_signals" in correlation:
            win_score = float(correlation["winning_signals"]["avg_pattern_score"]) if correlation["winning_signals"]["avg_pattern_score"] != "N/A" else 0
            loss_score = float(correlation["losing_signals"]["avg_pattern_score"]) if correlation["losing_signals"]["avg_pattern_score"] != "N/A" else 0

            if loss_score > win_score:
                insights.append({
                    "type": "CRITICAL",
                    "title": "形态评分失效！",
                    "content": f"亏损信号的平均评分({loss_score:.2f})高于盈利信号({win_score:.2f})",
                    "action": "形态评分没有区分度，需要调整评分算法或入场门槛",
                })
            elif win_score - loss_score < 0.1:
                insights.append({
                    "type": "WARNING",
                    "title": "形态评分区分度不足",
                    "content": f"盈利信号评分{win_score:.2f} vs 亏损信号{loss_score:.2f}",
                    "action": "考虑提高入场评分门槛至0.75或0.8",
                })

        # 洞察3：被过滤信号分析
        filtered = analysis.get("filtered_signals_analysis", {})
        if isinstance(filtered, dict) and not filtered.get("message"):
            # 检查是否有高评分信号被过滤
            for stage, data in filtered.items():
                if data.get("avg_score") != "N/A":
                    avg_score = float(data["avg_score"])
                    if avg_score > 0.75:
                        insights.append({
                            "type": "WARNING",
                            "title": f"高评分信号被{stage}过滤",
                            "content": f"平均评分{avg_score:.2f}的信号被过滤",
                            "action": f"检查{stage}过滤条件是否过于严格",
                        })

        # 洞察4：过滤原因分析
        if funnel.get("filter_reasons"):
            reasons = funnel["filter_reasons"]
            top_reason = max(reasons.items(), key=lambda x: x[1])
            insights.append({
                "type": "INFO",
                "title": "主要过滤原因",
                "content": f"'{top_reason[0]}' 过滤了 {top_reason[1]} 个信号",
                "action": "分析该过滤条件是否必要",
            })

        return insights

    def _ts_to_str(self, ts: int) -> str:
        """时间戳转字符串"""
        try:
            return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M')
        except:
            return str(ts)


async def main():
    parser = argparse.ArgumentParser(description="PMS回测深度诊断 - 信号分析版")
    parser.add_argument("--report-id", help="分析报告ID")
    parser.add_argument("--latest", action="store_true", help="分析最新报告")
    parser.add_argument("--db-path", default="data/v3_dev.db", help="数据库路径")

    args = parser.parse_args()

    # 初始化仓库
    backtest_repo = BacktestReportRepository(args.db_path)
    await backtest_repo.initialize()

    diagnoser = SignalAwareDiagnoser(backtest_repo, args.db_path)
    await diagnoser.initialize()

    try:
        if args.latest:
            reports = await backtest_repo.list_reports(page_size=1)
            if not reports["reports"]:
                print("没有找到回测报告")
                return
            report_id = reports["reports"][0]["id"]
            print(f"分析最新报告: {report_id}\n")
        elif args.report_id:
            report_id = args.report_id
        else:
            print("请指定 --report-id 或 --latest")
            return

        # 运行诊断
        analysis = await diagnoser.analyze_report_with_signals(report_id)

        if "error" in analysis:
            print(f"错误: {analysis['error']}")
            return

        # 打印报告
        print("=" * 75)
        print("              PMS 回测深度诊断报告（信号关联分析）")
        print("=" * 75)

        # 报告摘要
        print("\n📊 报告摘要")
        print("-" * 75)
        for key, value in analysis["report_summary"].items():
            print(f"  {key}: {value}")

        # 信号漏斗
        print("\n🔄 信号漏斗分析")
        print("-" * 75)
        funnel = analysis["signal_funnel"]
        if "error" not in funnel:
            print(f"  总信号尝试: {funnel['total_attempts']}")
            print(f"  成交信号:   {funnel['fired_count']} ({funnel['fired_rate']})")
            print(f"  被过滤:     {funnel['filtered_count']} ({funnel['filtered_rate']})")
            print(f"  无形态:     {funnel['no_pattern_count']}")
            if funnel.get('filter_reasons'):
                print(f"\n  过滤原因分布:")
                for reason, count in sorted(funnel['filter_reasons'].items(), key=lambda x: -x[1]):
                    print(f"    - {reason}: {count}")

        # 成交信号分析
        print("\n✅ 成交信号特征")
        print("-" * 75)
        fired = analysis["fired_signals_analysis"]
        if "error" not in fired:
            print(f"  平均形态评分: {fired['avg_pattern_score']}")
            print(f"  评分分布:")
            for grade, count in fired['score_distribution'].items():
                print(f"    - {grade}: {count}")
            print(f"  方向分布: {fired['direction_distribution']}")

        # 被过滤信号分析
        print("\n🚫 被过滤信号分析（关键！）")
        print("-" * 75)
        filtered = analysis["filtered_signals_analysis"]
        if "error" not in filtered and "message" not in filtered:
            for stage, data in filtered.items():
                print(f"\n  【{stage}】过滤:")
                print(f"    数量: {data['count']}")
                print(f"    平均评分: {data['avg_score']}")
                print(f"    主要原因: {data['top_reasons']}")

        # Position-Signal关联
        print("\n🔗 Position-Signal关联分析")
        print("-" * 75)
        corr = analysis["position_signal_correlation"]
        if "error" not in corr and "message" not in corr:
            print(f"  盈利信号:")
            for k, v in corr["winning_signals"].items():
                print(f"    - {k}: {v}")
            print(f"  亏损信号:")
            for k, v in corr["losing_signals"].items():
                print(f"    - {k}: {v}")
            print(f"\n  📌 {corr['score_correlation']}")

            if corr.get("losing_signals_sample"):
                print(f"\n  亏损信号样本（前3笔）:")
                for sig in corr["losing_signals_sample"]:
                    print(f"    - {sig['position_id']}: PnL={sig['pnl']:.2f}, Score={sig['pattern_score']:.2f}, Dir={sig['direction']}")

        # 洞察
        print("\n" + "=" * 75)
        print("                      💡 诊断洞察")
        print("=" * 75)

        if analysis["insights"]:
            for i, insight in enumerate(analysis["insights"], 1):
                emoji = {"CRITICAL": "🔴", "WARNING": "🟠", "INFO": "🔵"}.get(insight["type"], "⚪")
                print(f"\n{emoji} 洞察 {i}: {insight['title']}")
                print(f"   发现: {insight['content']}")
                print(f"   建议: {insight['action']}")
        else:
            print("\n  暂无特别洞察")

        print("\n" + "=" * 75)

    finally:
        await diagnoser.close()
        await backtest_repo.close()


if __name__ == "__main__":
    asyncio.run(main())
