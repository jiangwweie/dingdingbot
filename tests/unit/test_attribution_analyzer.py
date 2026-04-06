"""
AttributionAnalyzer 单元测试

测试策略归因分析引擎的四个维度：
- B: 形态质量归因
- C: 过滤器归因
- D: 市场趋势归因
- F: 盈亏比归因
"""

import pytest
from decimal import Decimal
from typing import List, Dict, Any
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_backtest_report() -> Dict[str, Any]:
    """创建模拟回测报告用于测试"""
    return {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "1h",
        "candles_analyzed": 100,
        "attempts": [
            # 高分组信号 (score > 0.7) - 盈利
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "long",
                "kline_timestamp": 1711785600000,
                "pattern_score": 0.85,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bullish"}},
                    {"filter": "mtf", "passed": True, "reason": "mtf_confirmed", "metadata": {"higher_trend": "bullish"}},
                ],
                "pnl_ratio": 2.0,
                "exit_reason": "TAKE_PROFIT",
            },
            # 高分组信号 - 亏损
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "short",
                "kline_timestamp": 1711789200000,
                "pattern_score": 0.75,
                "filter_results": [
                    {"filter": "ema_trend", "passed": False, "reason": "bearish_trend_blocks_short", "metadata": {"trend_direction": "bearish"}},
                ],
                "pnl_ratio": -1.0,
                "exit_reason": "STOP_LOSS",
            },
            # 低分组信号 (score < 0.5) - 盈利
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "long",
                "kline_timestamp": 1711792800000,
                "pattern_score": 0.45,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bullish"}},
                ],
                "pnl_ratio": 1.5,
                "exit_reason": "TAKE_PROFIT",
            },
            # 低分组信号 - 亏损
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "short",
                "kline_timestamp": 1711796400000,
                "pattern_score": 0.35,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bearish"}},
                ],
                "pnl_ratio": -1.0,
                "exit_reason": "STOP_LOSS",
            },
            # 中等分组信号 (0.5 <= score <= 0.7)
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "long",
                "kline_timestamp": 1711800000000,
                "pattern_score": 0.60,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bullish"}},
                ],
                "pnl_ratio": 1.0,
                "exit_reason": "TIME_EXIT",
            },
            # 被过滤器拒绝的信号
            {
                "strategy_name": "pinbar",
                "final_result": "FILTERED",
                "direction": "long",
                "kline_timestamp": 1711803600000,
                "pattern_score": 0.70,
                "filter_results": [
                    {"filter": "ema_trend", "passed": False, "reason": "bearish_trend_blocks_long", "metadata": {"trend_direction": "bearish"}},
                ],
                "pnl_ratio": None,
                "exit_reason": None,
            },
        ],
    }


# ============================================================
# Tests: AttributionAnalyzer 基本结构
# ============================================================

class TestAttributionAnalyzerInit:
    """AttributionAnalyzer 初始化测试"""

    def test_analyzer_can_be_imported(self):
        """测试 AttributionAnalyzer 可以被导入"""
        from src.application.attribution_analyzer import AttributionAnalyzer
        assert AttributionAnalyzer is not None

    def test_analyzer_can_be_instantiated(self):
        """测试 AttributionAnalyzer 可以被实例化"""
        from src.application.attribution_analyzer import AttributionAnalyzer
        analyzer = AttributionAnalyzer()
        assert analyzer is not None

    def test_analyzer_has_analyze_method(self):
        """测试 AttributionAnalyzer 有 analyze 方法"""
        from src.application.attribution_analyzer import AttributionAnalyzer
        analyzer = AttributionAnalyzer()
        assert hasattr(analyzer, 'analyze')
        assert callable(analyzer.analyze)


# ============================================================
# Tests: 维度 B - 形态质量归因
# ============================================================

class TestShapeQualityAttribution:
    """形态质量归因测试"""

    def test_shape_quality_groups_by_score_threshold(self, sample_backtest_report):
        """测试形态质量按评分阈值分组"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证高分组 (score > 0.7)
        assert "high_score" in report.shape_quality
        assert report.shape_quality["high_score"]["count"] == 2
        assert report.shape_quality["high_score"]["threshold"] == "> 0.7"

        # 验证低分组 (score < 0.5)
        assert "low_score" in report.shape_quality
        assert report.shape_quality["low_score"]["count"] == 2
        assert report.shape_quality["low_score"]["threshold"] == "< 0.5"

        # 验证中等分组 (0.5 <= score <= 0.7)
        assert "medium_score" in report.shape_quality
        assert report.shape_quality["medium_score"]["count"] == 1
        assert report.shape_quality["medium_score"]["threshold"] == "0.5 - 0.7"

    def test_high_score_has_better_win_rate(self, sample_backtest_report):
        """测试高分组胜率高于低分组"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        high_score_win_rate = report.shape_quality["high_score"]["win_rate"]
        low_score_win_rate = report.shape_quality["low_score"]["win_rate"]

        # 高分组：1 胜 1 负 = 50% 胜率
        assert high_score_win_rate == 0.5

        # 低分组：1 胜 1 负 = 50% 胜率
        assert low_score_win_rate == 0.5

    def test_shape_quality_includes_pnl_stats(self, sample_backtest_report):
        """测试形态质量包含盈亏统计"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        high_score = report.shape_quality["high_score"]
        assert "avg_pnl_ratio" in high_score
        assert "total_trades" in high_score
        assert "winning_trades" in high_score
        assert "losing_trades" in high_score


# ============================================================
# Tests: 维度 C - 过滤器归因
# ============================================================

class TestFilterAttribution:
    """过滤器归因测试"""

    def test_filter_attribution_shows_impact(self, sample_backtest_report):
        """测试过滤器归因显示影响"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证 EMA 过滤器归因
        assert "ema_filter" in report.filter_attribution
        ema = report.filter_attribution["ema_filter"]
        assert "enabled_trades" in ema
        assert "disabled_trades" in ema
        assert "impact_on_win_rate" in ema

    def test_filter_attribution_shows_rejection_stats(self, sample_backtest_report):
        """测试过滤器归因显示拒绝统计"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证过滤器拒绝统计
        assert "rejection_stats" in report.filter_attribution
        assert "ema_trend" in report.filter_attribution["rejection_stats"]


# ============================================================
# Tests: 维度 D - 市场趋势归因
# ============================================================

class TestTrendAttribution:
    """市场趋势归因测试"""

    def test_trend_attribution_separates_bullish_bearish(self, sample_backtest_report):
        """测试市场趋势归因分离牛市和熊市"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证牛市趋势归因
        assert "bullish_trend" in report.trend_attribution
        bullish = report.trend_attribution["bullish_trend"]
        assert "trade_count" in bullish
        assert "win_rate" in bullish
        assert "avg_pnl" in bullish

        # 验证熊市趋势归因
        assert "bearish_trend" in report.trend_attribution
        bearish = report.trend_attribution["bearish_trend"]
        assert "trade_count" in bearish

    def test_trend_attribution_shows_alignment(self, sample_backtest_report):
        """测试市场趋势归因显示顺势/逆势交易"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证顺势/逆势统计
        assert "alignment_stats" in report.trend_attribution
        assert "aligned_trades" in report.trend_attribution["alignment_stats"]
        assert "against_trend_trades" in report.trend_attribution["alignment_stats"]


# ============================================================
# Tests: 维度 F - 盈亏比归因
# ============================================================

class TestRRAttribution:
    """盈亏比归因测试"""

    def test_rr_attribution_groups_by_ratio(self, sample_backtest_report):
        """测试盈亏比归因按比率分组"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证高盈亏比组 (> 2:1)
        assert "high_rr" in report.rr_attribution
        high_rr = report.rr_attribution["high_rr"]
        assert "threshold" in high_rr
        assert high_rr["threshold"] == "> 2:1"  # 使用 int 转换后的格式

        # 验证中等盈亏比组 (1:1 - 2:1)
        assert "medium_rr" in report.rr_attribution
        medium_rr = report.rr_attribution["medium_rr"]
        assert medium_rr["threshold"] == "1:1 - 2:1"

        # 验证低盈亏比组 (< 1:1)
        assert "low_rr" in report.rr_attribution
        low_rr = report.rr_attribution["low_rr"]
        assert low_rr["threshold"] == "< 1:1 (盈利)"  # 0 < pnl < 1 是微利

    def test_rr_attribution_shows_optimal_range(self, sample_backtest_report):
        """测试盈亏比归因显示最优区间"""
        from src.application.attribution_analyzer import AttributionAnalyzer

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证最优区间建议
        assert "optimal_range" in report.rr_attribution
        optimal = report.rr_attribution["optimal_range"]
        assert "suggested_rr" in optimal
        assert "reasoning" in optimal


# ============================================================
# Tests: AttributionReport 模型
# ============================================================

class TestAttributionReportModel:
    """AttributionReport 模型测试"""

    def test_attribution_report_has_all_dimensions(self):
        """测试 AttributionReport 包含所有维度"""
        from src.domain.models import AttributionReport

        report = AttributionReport(
            shape_quality={},
            filter_attribution={},
            trend_attribution={},
            rr_attribution={},
        )

        assert hasattr(report, 'shape_quality')
        assert hasattr(report, 'filter_attribution')
        assert hasattr(report, 'trend_attribution')
        assert hasattr(report, 'rr_attribution')


# ============================================================
# Integration Tests: 端到端测试
# ============================================================

class TestAttributionAnalysisE2E:
    """归因分析端到端测试"""

    def test_full_attribution_analysis(self, sample_backtest_report):
        """测试完整的归因分析流程"""
        from src.application.attribution_analyzer import AttributionAnalyzer
        from src.domain.models import AttributionReport

        analyzer = AttributionAnalyzer()
        report = analyzer.analyze(sample_backtest_report)

        # 验证报告类型
        assert isinstance(report, AttributionReport)

        # 验证所有维度都有数据
        assert len(report.shape_quality) > 0
        assert len(report.filter_attribution) > 0
        assert len(report.trend_attribution) > 0
        assert len(report.rr_attribution) > 0

        # 验证报告可以序列化为 JSON
        report_dict = report.model_dump(mode='json')
        assert "shape_quality" in report_dict
        assert "filter_attribution" in report_dict
        assert "trend_attribution" in report_dict
        assert "rr_attribution" in report_dict
