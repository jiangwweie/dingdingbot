"""
AttributionAnalyzer - 策略归因分析引擎

基于回测报告数据，进行四个维度的归因分析：
- B: 形态质量归因（Pinbar 评分与表现的关系）
- C: 过滤器归因（各过滤器对策略表现的影响）
- D: 市场趋势归因（不同市场趋势下的交易表现）
- F: 盈亏比归因（不同盈亏比设置下的表现）

使用示例:
    analyzer = AttributionAnalyzer()
    report = analyzer.analyze(backtest_report)
"""

from typing import Dict, Any, List, Optional
from decimal import Decimal
from src.domain.models import AttributionReport


class AttributionAnalyzer:
    """
    策略归因分析引擎

    从回测报告中提取并分析四个维度的数据：
    1. 形态质量归因 - 分析 Pinbar 评分与交易表现的关系
    2. 过滤器归因 - 分析各过滤器对胜率/回撤的影响
    3. 市场趋势归因 - 分析顺势/逆势交易的表现差异
    4. 盈亏比归因 - 分析最优盈亏比区间
    """

    # 形态评分阈值
    HIGH_SCORE_THRESHOLD = 0.7
    LOW_SCORE_THRESHOLD = 0.5

    # 盈亏比阈值
    HIGH_RR_THRESHOLD = 2.0
    MEDIUM_RR_THRESHOLD = 1.0

    # 盈亏比区间映射
    RR_RANGE_MAP = {
        "high_rr": "2:1 以上",
        "medium_rr": "1:1 - 2:1",
        "low_rr": "0:1 - 1:1",
    }

    def analyze(self, backtest_report: Dict[str, Any]) -> AttributionReport:
        """
        执行完整的归因分析

        Args:
            backtest_report: 回测报告字典（包含 attempts 字段）

        Returns:
            AttributionReport 包含四个维度的分析结果
        """
        from datetime import datetime, timezone

        attempts = backtest_report.get("attempts", [])

        return AttributionReport(
            version="1.0.0",
            shape_quality=self._analyze_shape_quality(attempts),
            filter_attribution=self._analyze_filters(attempts),
            trend_attribution=self._analyze_trend(attempts),
            rr_attribution=self._analyze_rr(attempts),
            metadata={
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "total_attempts": len(attempts),
                "fired_signals": len([a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]),
            },
        )

    def _analyze_shape_quality(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        维度 B: 形态质量归因分析

        按 Pinbar 评分分组统计交易表现：
        - 高分组 (score > 0.7)
        - 中等组 (0.5 <= score <= 0.7)
        - 低分组 (score < 0.5)
        """
        fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]

        # 按评分分组
        high_score = [s for s in fired_signals if s.get("pattern_score", 0) > self.HIGH_SCORE_THRESHOLD]
        medium_score = [s for s in fired_signals if self.LOW_SCORE_THRESHOLD <= s.get("pattern_score", 0) <= self.HIGH_SCORE_THRESHOLD]
        low_score = [s for s in fired_signals if s.get("pattern_score", 0) < self.LOW_SCORE_THRESHOLD]

        def calculate_group_stats(signals: List[Dict]) -> Dict[str, Any]:
            """计算分组的统计数据"""
            if not signals:
                return {
                    "count": 0,
                    "win_rate": 0.0,
                    "avg_pnl_ratio": 0.0,
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                }

            winning = [s for s in signals if s.get("pnl_ratio") is not None and s.get("pnl_ratio", 0) > 0]
            losing = [s for s in signals if s.get("pnl_ratio") is not None and s.get("pnl_ratio", 0) < 0]

            total_trades = len([s for s in signals if s.get("pnl_ratio") is not None])
            win_rate = len(winning) / total_trades if total_trades > 0 else 0.0

            pnl_ratios = [s.get("pnl_ratio", 0) for s in signals if s.get("pnl_ratio") is not None]
            avg_pnl = sum(pnl_ratios) / len(pnl_ratios) if pnl_ratios else 0.0

            return {
                "count": len(signals),
                "win_rate": win_rate,
                "avg_pnl_ratio": avg_pnl,
                "total_trades": total_trades,
                "winning_trades": len(winning),
                "losing_trades": len(losing),
            }

        return {
            "high_score": {
                **calculate_group_stats(high_score),
                "threshold": f"> {self.HIGH_SCORE_THRESHOLD}",
            },
            "medium_score": {
                **calculate_group_stats(medium_score),
                "threshold": f"{self.LOW_SCORE_THRESHOLD} - {self.HIGH_SCORE_THRESHOLD}",
            },
            "low_score": {
                **calculate_group_stats(low_score),
                "threshold": f"< {self.LOW_SCORE_THRESHOLD}",
            },
            "analysis": {
                "high_score_performs_better": self._compare_score_performance(high_score, low_score),
            },
        }

    def _analyze_filters(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        维度 C: 过滤器归因分析

        分析各过滤器对策略表现的影响：
        - EMA 过滤器的影响
        - MTF 过滤器的影响
        - 过滤器拒绝统计
        """
        fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]
        filtered_signals = [a for a in attempts if a.get("final_result") == "FILTERED"]

        # 分析 EMA 过滤器
        ema_enabled = [s for s in fired_signals if self._has_filter(s, "ema_trend")]
        ema_passed = [s for s in fired_signals if self._filter_passed(s, "ema_trend")]
        ema_disabled = [s for s in fired_signals if self._has_filter(s, "ema_trend") and not self._filter_passed(s, "ema_trend")]

        # 分析 MTF 过滤器
        mtf_enabled = [s for s in fired_signals if self._has_filter(s, "mtf")]
        mtf_passed = [s for s in fired_signals if self._filter_passed(s, "mtf")]
        mtf_disabled = [s for s in fired_signals if self._has_filter(s, "mtf") and not self._filter_passed(s, "mtf")]

        # 过滤器拒绝统计
        rejection_stats = self._calculate_rejection_stats(filtered_signals)

        # 计算过滤器影响（通过过滤器的胜率 - 被过滤器拒绝的模拟胜率）
        ema_impact = self._calculate_filter_impact(ema_passed, ema_disabled)
        mtf_impact = self._calculate_filter_impact(mtf_passed, mtf_disabled)

        return {
            "ema_filter": {
                "enabled_trades": len(ema_enabled),
                "passed_trades": len(ema_passed),
                "disabled_trades": len(ema_disabled),
                "win_rate_with_ema": self._calculate_win_rate(ema_passed),
                "win_rate_without_ema": self._calculate_win_rate(ema_disabled),
                "impact_on_win_rate": ema_impact,
            },
            "mtf_filter": {
                "enabled_trades": len(mtf_enabled),
                "passed_trades": len(mtf_passed),
                "disabled_trades": len(mtf_disabled),
                "win_rate_with_mtf": self._calculate_win_rate(mtf_passed),
                "win_rate_without_mtf": self._calculate_win_rate(mtf_disabled),
                "impact_on_win_rate": mtf_impact,
            },
            "rejection_stats": rejection_stats,
        }

    def _analyze_trend(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        维度 D: 市场趋势归因分析

        分析不同市场趋势下的交易表现：
        - 牛市趋势中的表现
        - 熊市趋势中的表现
        - 顺势/逆势交易统计
        """
        fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED"]

        # 按趋势分组
        bullish_trend = [s for s in fired_signals if self._get_trend_direction(s) == "bullish"]
        bearish_trend = [s for s in fired_signals if self._get_trend_direction(s) == "bearish"]

        # 顺势/逆势统计
        aligned_trades = self._count_aligned_trades(fired_signals)
        against_trend = len(fired_signals) - aligned_trades

        return {
            "bullish_trend": {
                "trade_count": len(bullish_trend),
                "win_rate": self._calculate_win_rate(bullish_trend),
                "avg_pnl": self._calculate_avg_pnl(bullish_trend),
            },
            "bearish_trend": {
                "trade_count": len(bearish_trend),
                "win_rate": self._calculate_win_rate(bearish_trend),
                "avg_pnl": self._calculate_avg_pnl(bearish_trend),
            },
            "alignment_stats": {
                "aligned_trades": aligned_trades,
                "against_trend_trades": against_trend,
                "alignment_ratio": self._calculate_alignment_ratio(aligned_trades, len(fired_signals)),
            },
        }

    def _analyze_rr(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        维度 F: 盈亏比归因分析

        分析不同盈亏比设置下的交易表现：
        - 高盈亏比 (> 2:1)
        - 中等盈亏比 (1:1 - 2:1)
        - 低盈亏比 (< 1:1)
        """
        fired_signals = [a for a in attempts if a.get("final_result") == "SIGNAL_FIRED" and a.get("pnl_ratio") is not None]

        # 按盈亏比分组
        high_rr = [s for s in fired_signals if s.get("pnl_ratio", 0) > self.HIGH_RR_THRESHOLD]
        medium_rr = [s for s in fired_signals if self.MEDIUM_RR_THRESHOLD <= s.get("pnl_ratio", 0) <= self.HIGH_RR_THRESHOLD]
        low_rr = [s for s in fired_signals if 0 < s.get("pnl_ratio", 0) < self.MEDIUM_RR_THRESHOLD]
        stop_loss = [s for s in fired_signals if s.get("pnl_ratio", 0) < 0]

        def group_stats(signals: List[Dict]) -> Dict[str, Any]:
            return {
                "count": len(signals),
                "win_rate": self._calculate_win_rate(signals),
                "avg_pnl": self._calculate_avg_pnl(signals),
            }

        # 识别最优盈亏比区间（按胜率排序，而非交易数量）
        groups = {
            "high_rr": high_rr,
            "medium_rr": medium_rr,
            "low_rr": low_rr,
        }

        # 计算各组胜率，找出最优组
        group_win_rates = {k: self._calculate_win_rate(v) for k, v in groups.items() if v}
        optimal_group = max(group_win_rates.keys(), key=lambda k: group_win_rates[k]) if group_win_rates else "medium_rr"

        # 计算最优组的平均 PnL
        optimal_avg_pnl = self._calculate_avg_pnl(groups.get(optimal_group, []))

        return {
            "high_rr": {
                **group_stats(high_rr),
                "threshold": f"> {int(self.HIGH_RR_THRESHOLD)}:1",
            },
            "medium_rr": {
                **group_stats(medium_rr),
                "threshold": f"{int(self.MEDIUM_RR_THRESHOLD)}:1 - {int(self.HIGH_RR_THRESHOLD)}:1",
            },
            "low_rr": {
                **group_stats(low_rr),
                "threshold": f"< {int(self.MEDIUM_RR_THRESHOLD)}:1 (盈利)",
            },
            "stop_loss": {
                **group_stats(stop_loss),
                "threshold": "< 0:1 (止损)",
            },
            "optimal_range": {
                "suggested_rr": self.RR_RANGE_MAP.get(optimal_group, "1:1 - 2:1"),
                "reasoning": f"该区间胜率最高 ({group_win_rates.get(optimal_group, 0):.1%})，平均盈亏比 {optimal_avg_pnl:.2f}",
                "optimal_group": optimal_group.replace("_rr", ""),
            },
        }

    # ========== 辅助方法 ==========

    def _has_filter(self, signal: Dict[str, Any], filter_name: str) -> bool:
        """检查信号是否包含指定过滤器"""
        filter_results = signal.get("filter_results", [])
        return any(f.get("filter") == filter_name for f in filter_results)

    def _filter_passed(self, signal: Dict[str, Any], filter_name: str) -> bool:
        """检查指定过滤器是否通过"""
        filter_results = signal.get("filter_results", [])
        for f in filter_results:
            if f.get("filter") == filter_name:
                return f.get("passed", False)
        return False

    def _get_trend_direction(self, signal: Dict[str, Any]) -> Optional[str]:
        """获取信号的 EMA 趋势方向"""
        filter_results = signal.get("filter_results", [])
        for f in filter_results:
            if f.get("filter") == "ema_trend":
                metadata = f.get("metadata", {})
                return metadata.get("trend_direction")
        return None

    def _calculate_rejection_stats(self, filtered_signals: List[Dict]) -> Dict[str, int]:
        """计算各过滤器的拒绝统计"""
        stats = {}
        for signal in filtered_signals:
            for f in signal.get("filter_results", []):
                if not f.get("passed", True):
                    filter_name = f.get("filter", "unknown")
                    stats[filter_name] = stats.get(filter_name, 0) + 1
        return stats

    def _calculate_filter_impact(self, passed: List[Dict], disabled: List[Dict]) -> float:
        """计算过滤器对胜率的影响"""
        passed_win_rate = self._calculate_win_rate(passed)
        disabled_win_rate = self._calculate_win_rate(disabled)
        # 正向影响：通过过滤器的胜率高于被拒绝的
        return round(passed_win_rate - disabled_win_rate, 4)

    def _calculate_win_rate(self, signals: List[Dict]) -> float:
        """计算胜率"""
        if not signals:
            return 0.0
        winning = [s for s in signals if s.get("pnl_ratio") is not None and s.get("pnl_ratio", 0) > 0]
        total = len([s for s in signals if s.get("pnl_ratio") is not None])
        return len(winning) / total if total > 0 else 0.0

    def _calculate_avg_pnl(self, signals: List[Dict]) -> float:
        """计算平均盈亏比"""
        if not signals:
            return 0.0
        pnl_ratios = [s.get("pnl_ratio", 0) for s in signals if s.get("pnl_ratio") is not None]
        return sum(pnl_ratios) / len(pnl_ratios) if pnl_ratios else 0.0

    def _count_aligned_trades(self, signals: List[Dict]) -> int:
        """计算顺势交易数量"""
        aligned = 0
        for s in signals:
            trend = self._get_trend_direction(s)
            direction = s.get("direction")
            if trend and direction:
                # 顺势：牛市趋势 + 做多，熊市趋势 + 做空
                if (trend == "bullish" and direction == "long") or (trend == "bearish" and direction == "short"):
                    aligned += 1
        return aligned

    def _calculate_alignment_ratio(self, aligned_trades: int, total_trades: int) -> float:
        """计算顺势交易比例"""
        if total_trades == 0:
            return 0.0
        return aligned_trades / total_trades

    def _compare_score_performance(self, high_score: List[Dict], low_score: List[Dict]) -> str:
        """比较高分组和低分组的表现"""
        if not high_score and not low_score:
            return "数据不足"
        if not high_score:
            return "仅有低分组数据"
        if not low_score:
            return "仅有高分组数据"

        high_win_rate = self._calculate_win_rate(high_score)
        low_win_rate = self._calculate_win_rate(low_score)

        if high_win_rate > low_win_rate:
            return "高分组表现更优"
        elif low_win_rate > high_win_rate:
            return "低分组表现更优"
        else:
            return "两组表现相近"
