#!/usr/bin/env python3
"""
PMS回测诊断分析器 - 挖掘亏损原因

用法：
    python3 scripts/analyze_backtest.py --report-id <报告ID>

或分析最新报告：
    python3 scripts/analyze_backtest.py --latest
"""
import argparse
import asyncio
import json
import sys
from decimal import Decimal
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

sys.path.insert(0, '/Users/jiangwei/Documents/final')

from src.infrastructure.backtest_repository import BacktestReportRepository


@dataclass
class TradeDiagnosis:
    """单笔交易的诊断信息"""
    position_id: str
    entry_time: str
    direction: str
    entry_price: Decimal
    exit_price: Optional[Decimal]
    realized_pnl: Decimal
    exit_reason: str

    # 诊断指标
    holding_bars: int = 0  # 持仓K线数（需要结合K线数据）
    pnl_pct: Decimal = Decimal('0')  # 盈亏百分比


class BacktestDiagnoser:
    """回测结果诊断分析器"""

    def __init__(self, repository: BacktestReportRepository):
        self.repo = repository

    async def analyze_report(self, report_id: str) -> Dict[str, Any]:
        """
        深度分析报告，找出亏损原因
        """
        report = await self.repo.get_report(report_id)
        if not report:
            return {"error": f"报告不存在: {report_id}"}

        positions = report.positions
        if not positions:
            return {"error": "报告中没有持仓数据"}

        # === 核心诊断 ===
        diagnosis = {
            "overview": self._analyze_overview(report),
            "exit_analysis": self._analyze_exit_patterns(positions),
            "pnl_distribution": self._analyze_pnl_distribution(positions),
            "trading_patterns": self._analyze_trading_patterns(positions),
            "suspect_problems": [],  # 疑似问题列表
        }

        # 自动识别问题
        diagnosis["suspect_problems"] = self._identify_problems(diagnosis)

        return diagnosis

    def _analyze_overview(self, report) -> Dict:
        """基础概览"""
        positions = report.positions
        total = len(positions)
        winning = sum(1 for p in positions if p.realized_pnl > 0)
        losing = total - winning

        # 计算平均盈亏
        winning_pnls = [p.realized_pnl for p in positions if p.realized_pnl > 0]
        losing_pnls = [p.realized_pnl for p in positions if p.realized_pnl < 0]

        avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else Decimal('0')
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else Decimal('0')

        return {
            "total_trades": total,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": f"{winning/total*100:.1f}%" if total > 0 else "0%",
            "avg_win": f"{avg_win:.2f} USDT",
            "avg_loss": f"{avg_loss:.2f} USDT",
            "profit_factor": f"{abs(sum(winning_pnls) / sum(losing_pnls)):.2f}" if losing_pnls and sum(losing_pnls) != 0 else "N/A",
            "actual_rr_ratio": f"{abs(avg_win / avg_loss):.2f}" if avg_loss != 0 else "N/A",
        }

    def _analyze_exit_patterns(self, positions: List[Any]) -> Dict:
        """分析出场模式 - 关键诊断"""
        exit_reasons = defaultdict(lambda: {"count": 0, "total_pnl": Decimal('0'), "wins": 0, "losses": 0})

        for p in positions:
            reason = p.exit_reason or "UNKNOWN"
            exit_reasons[reason]["count"] += 1
            exit_reasons[reason]["total_pnl"] += p.realized_pnl
            if p.realized_pnl > 0:
                exit_reasons[reason]["wins"] += 1
            else:
                exit_reasons[reason]["losses"] += 1

        # 计算每个出场原因的胜率和平均盈亏
        result = {}
        for reason, data in exit_reasons.items():
            count = data["count"]
            result[reason] = {
                "count": count,
                "percentage": f"{count/len(positions)*100:.1f}%",
                "total_pnl": f"{data['total_pnl']:.2f} USDT",
                "win_rate": f"{data['wins']/count*100:.1f}%" if count > 0 else "0%",
                "avg_pnl": f"{data['total_pnl']/count:.2f} USDT",
            }

        return result

    def _analyze_pnl_distribution(self, positions: List[Any]) -> Dict:
        """分析盈亏分布 - 找出异常值"""
        pnls = [p.realized_pnl for p in positions]
        sorted_pnls = sorted(pnls)

        winning_pnls = [p for p in pnls if p > 0]
        losing_pnls = [p for p in pnls if p < 0]

        return {
            "total_pnl": f"{sum(pnls):.2f} USDT",
            "max_profit": f"{max(pnls):.2f} USDT" if pnls else "0",
            "max_loss": f"{min(pnls):.2f} USDT" if pnls else "0",
            "median_pnl": f"{sorted_pnls[len(sorted_pnls)//2]:.2f} USDT" if sorted_pnls else "0",
            "top_3_profits": [f"{p:.2f}" for p in sorted(winning_pnls, reverse=True)[:3]] if winning_pnls else [],
            "top_3_losses": [f"{p:.2f}" for p in sorted(losing_pnls)[:3]] if losing_pnls else [],
            "small_losses": {  # 小亏损统计（可能是止损过紧的信号）
                "count": sum(1 for p in losing_pnls if abs(p) < 50),  # 假设50USDT以下算小亏
                "description": "如果有很多小亏损，可能是止损过紧",
            },
        }

    def _analyze_trading_patterns(self, positions: List[Any]) -> Dict:
        """分析交易模式"""
        # 按方向分析
        long_trades = [p for p in positions if p.direction.value == "LONG"]
        short_trades = [p for p in positions if p.direction.value == "SHORT"]

        def analyze_direction(trades, name):
            if not trades:
                return None
            wins = sum(1 for p in trades if p.realized_pnl > 0)
            total_pnl = sum(p.realized_pnl for p in trades)
            return {
                "count": len(trades),
                "win_rate": f"{wins/len(trades)*100:.1f}%",
                "total_pnl": f"{total_pnl:.2f} USDT",
            }

        # 按时间分析（如果有足够数据）
        hourly_distribution = defaultdict(lambda: {"count": 0, "wins": 0})
        for p in positions:
            if p.entry_time:
                hour = (p.entry_time // 3600000) % 24  # 转换为小时
                hourly_distribution[hour]["count"] += 1
                if p.realized_pnl > 0:
                    hourly_distribution[hour]["wins"] += 1

        return {
            "long_performance": analyze_direction(long_trades, "LONG"),
            "short_performance": analyze_direction(short_trades, "SHORT"),
            "hourly_distribution": dict(hourly_distribution),
        }

    def _identify_problems(self, diagnosis: Dict) -> List[Dict]:
        """自动识别疑似问题"""
        problems = []

        overview = diagnosis["overview"]
        exit_analysis = diagnosis["exit_analysis"]
        pnl_distribution = diagnosis["pnl_distribution"]

        # 问题1：止损过紧
        sl_exits = exit_analysis.get("SL", {}).get("count", 0)
        total_exits = overview["total_trades"]
        if sl_exits > total_exits * 0.6:  # 超过60%是止损出场
            problems.append({
                "severity": "HIGH",
                "problem": "止损出场过多",
                "evidence": f"{sl_exits}/{total_exits} 笔 ({sl_exits/total_exits*100:.1f}%) 是止损出场",
                "suspected_cause": "止损设置过紧，或市场正常波动就触发止损",
                "recommendation": "考虑放宽止损至1.5倍ATR，或添加'最小持有时间'过滤",
            })

        # 问题2：盈亏比失衡
        actual_rr = overview.get("actual_rr_ratio", "N/A")
        if actual_rr != "N/A" and float(actual_rr) < 1.0:
            problems.append({
                "severity": "CRITICAL",
                "problem": "盈亏比严重失衡",
                "evidence": f"实际盈亏比 {actual_rr} < 1.0，平均赚的小于平均亏的",
                "suspected_cause": "止盈目标难以达到，或止损过于频繁",
                "recommendation": "检查4h周期是否真的能跑到1.5R止盈，考虑降低至1.0R或0.8R",
            })

        # 问题3：小亏损过多
        small_losses = pnl_distribution.get("small_losses", {}).get("count", 0)
        if small_losses > 10:  # 超过10笔小亏损
            problems.append({
                "severity": "MEDIUM",
                "problem": "频繁小止损",
                "evidence": f"有 {small_losses} 笔小额亏损（<50USDT）",
                "suspected_cause": "假信号过多，或止损过紧导致'正常波动'触发止损",
                "recommendation": "添加震荡市场过滤器，或提高形态评分门槛",
            })

        # 问题4：方向偏差
        patterns = diagnosis.get("trading_patterns", {})
        long_perf = patterns.get("long_performance", {})
        short_perf = patterns.get("short_performance", {})

        if long_perf and short_perf:
            long_pnl = float(long_perf.get("total_pnl", "0").replace(" USDT", ""))
            short_pnl = float(short_perf.get("total_pnl", "0").replace(" USDT", ""))
            if long_pnl > 0 and short_pnl < -long_pnl:  # 做多赚钱，做空大亏
                problems.append({
                    "severity": "MEDIUM",
                    "problem": "方向性偏差",
                    "evidence": f"做多盈利 {long_pnl:.2f}，但做空亏损 {abs(short_pnl):.2f}",
                    "suspected_cause": "回测期间是上涨趋势，做空信号逆势操作",
                    "recommendation": "检查是否只在趋势明确时开单，或添加趋势过滤器",
                })

        return problems


async def list_recent_reports(repo: BacktestReportRepository, limit: int = 10):
    """列出最近的回测报告"""
    reports = await repo.list_reports(page_size=limit)

    print(f"\n最近 {len(reports['reports'])} 条回测报告:\n")
    print(f"{'ID':<50} {'策略':<20} {'总收益':<10} {'胜率':<8} {'交易数':<6}")
    print("-" * 100)

    for r in reports["reports"]:
        print(f"{r['id']:<50} {r['strategy_name']:<20} {r['total_return']:<10} {r['win_rate']:<8} {r['total_trades']:<6}")

    return reports["reports"]


async def main():
    parser = argparse.ArgumentParser(description="PMS回测诊断分析器")
    parser.add_argument("--report-id", help="分析报告ID")
    parser.add_argument("--latest", action="store_true", help="分析最新报告")
    parser.add_argument("--list", action="store_true", help="列出最近报告")

    args = parser.parse_args()

    # 初始化仓库
    repo = BacktestReportRepository()
    await repo.initialize()

    try:
        if args.list:
            await list_recent_reports(repo)
            return

        if args.latest:
            reports = await repo.list_reports(page_size=1)
            if not reports["reports"]:
                print("没有找到回测报告")
                return
            report_id = reports["reports"][0]["id"]
            print(f"分析最新报告: {report_id}\n")
        elif args.report_id:
            report_id = args.report_id
        else:
            print("请指定 --report-id 或 --latest")
            await list_recent_reports(repo)
            return

        # 运行诊断
        diagnoser = BacktestDiagnoser(repo)
        diagnosis = await diagnoser.analyze_report(report_id)

        if "error" in diagnosis:
            print(f"错误: {diagnosis['error']}")
            return

        # 打印报告
        print("=" * 70)
        print("                    PMS 回测诊断报告")
        print("=" * 70)

        # 概览
        print("\n📊 基础概览")
        print("-" * 70)
        for key, value in diagnosis["overview"].items():
            print(f"  {key}: {value}")

        # 出场分析
        print("\n🚪 出场原因分析（关键！）")
        print("-" * 70)
        for reason, data in diagnosis["exit_analysis"].items():
            print(f"\n  【{reason}】")
            for k, v in data.items():
                print(f"    {k}: {v}")

        # 盈亏分布
        print("\n💰 盈亏分布")
        print("-" * 70)
        for key, value in diagnosis["pnl_distribution"].items():
            if isinstance(value, dict):
                print(f"\n  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")

        # 交易模式
        print("\n📈 交易模式分析")
        print("-" * 70)
        patterns = diagnosis["trading_patterns"]
        if patterns.get("long_performance"):
            print(f"\n  做多表现:")
            for k, v in patterns["long_performance"].items():
                print(f"    {k}: {v}")
        if patterns.get("short_performance"):
            print(f"\n  做空表现:")
            for k, v in patterns["short_performance"].items():
                print(f"    {k}: {v}")

        # 疑似问题
        print("\n" + "=" * 70)
        print("                    ⚠️ 疑似问题（自动诊断）")
        print("=" * 70)

        if diagnosis["suspect_problems"]:
            for i, problem in enumerate(diagnosis["suspect_problems"], 1):
                severity_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡"}.get(problem["severity"], "⚪")
                print(f"\n{severity_emoji} 问题 {i}: {problem['problem']} [{problem['severity']}]")
                print(f"   证据: {problem['evidence']}")
                print(f"   疑似原因: {problem['suspected_cause']}")
                print(f"   建议: {problem['recommendation']}")
        else:
            print("\n  ✅ 未发现明显问题（但这不代表策略一定好）")

        print("\n" + "=" * 70)

    finally:
        await repo.close()


if __name__ == "__main__":
    asyncio.run(main())
