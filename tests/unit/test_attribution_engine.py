"""
AttributionEngine 单元测试

覆盖场景:
- UT-001: 正常信号 — pattern + ema_trend + mtf 都通过
- UT-002: 被拒绝的信号 — 某个过滤器 failed
- UT-003: 空 pattern — pattern 为 None
- UT-004: zero-score — final_score 为 0 时 percentages 应为 {}
- UT-005: 批量归因 — 多个 attempts
- UT-006: 聚合归因 — AggregateAttribution 计算
- UT-007: metadata 不完整 — 降级为默认值 0.5
- UT-008: 回测引擎序列化格式兼容 — {"filter": name, ...}
- UT-009: 直接格式兼容 — [(name, FilterResult), ...]
- UT-010: 未知过滤器 — 默认信心 0.5
- UT-011: ATR 过滤器（atr_volatility 名称）
- UT-012: confidence_basis 数学可验证
- UT-013: explanation 人类可读
- UT-014: final_score 上限为 1.0
- UT-015: 空 attempts 列表 — aggregate 返回零值
- UT-016: 仅有 pattern 无过滤器
- UT-017: pattern_score 为 0 但有通过的过滤器
- UT-018: FilterResult 对象格式输入
- UT-019: EMA 信心函数 — distance_pct 边界
- UT-020: MTF 信心函数 — 对齐比例计算
"""

import pytest
from decimal import Decimal

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.application.attribution_engine import (
    AttributionEngine,
    AttributionComponent,
    SignalAttribution,
    AggregateAttribution,
    FilterScore,
)
from src.domain.attribution_config import AttributionConfig
from src.domain.models import FilterResult


def _default_config() -> AttributionConfig:
    return AttributionConfig.default()


def _make_backtest_attempt(
    strategy_name="pinbar",
    pattern_score=0.72,
    filter_results=None,
    final_result="SIGNAL_FIRED",
    kline_timestamp=1234567890,
) -> dict:
    """构建回测引擎序列化格式的 attempt dict"""
    if filter_results is None:
        filter_results = [
            {
                "filter": "ema_trend",
                "passed": True,
                "reason": "trend_match",
                "metadata": {
                    "price": 65432.10,
                    "ema_value": 64200.00,
                    "distance_pct": 0.0192,
                },
            },
            {
                "filter": "mtf",
                "passed": True,
                "reason": "mtf_confirmed_bullish",
                "metadata": {
                    "aligned_count": 2,
                    "total_count": 3,
                    "higher_tf_trends": {"1h": "bullish", "4h": "bullish", "1d": "bearish"},
                },
            },
        ]
    return {
        "strategy_name": strategy_name,
        "final_result": final_result,
        "kline_timestamp": kline_timestamp,
        "pattern_score": pattern_score,
        "filter_results": filter_results,
    }


def _make_direct_attempt(
    pattern_score=0.72,
    filter_results=None,
) -> dict:
    """构建直接格式的 attempt dict（pattern dict + tuple filter_results）"""
    if filter_results is None:
        filter_results = [
            (
                "ema_trend",
                FilterResult(
                    passed=True,
                    reason="trend_match",
                    metadata={
                        "price": 65432.10,
                        "ema_value": 64200.00,
                        "distance_pct": 0.0192,
                    },
                ),
            ),
            (
                "mtf",
                FilterResult(
                    passed=True,
                    reason="mtf_confirmed_bullish",
                    metadata={
                        "aligned_count": 2,
                        "total_count": 3,
                    },
                ),
            ),
        ]
    return {
        "strategy_name": "pinbar",
        "pattern": {"score": pattern_score, "direction": "LONG"},
        "filter_results": filter_results,
        "final_result": "SIGNAL_FIRED",
        "kline_timestamp": 1234567890,
    }


# ============================================================
# UT-001: 正常信号 — pattern + ema_trend + mtf 都通过
# ============================================================
class TestNormalSignal:
    """正常信号归因"""

    def test_basic_attribution(self):
        """UT-001: 正常信号 — pattern + ema_trend + mtf 都通过"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(pattern_score=0.72)

        result = engine.attribute(attempt)

        # final_score = 0.72 * 0.55 + ema_conf * 0.25 + mtf_conf * 0.20
        # ema_conf = min(0.0192 / 0.05, 1.0) = 0.384
        # mtf_conf = 2/3 = 0.6667
        # final = 0.396 + 0.096 + 0.1333 = 0.6253
        assert result.final_score > 0
        assert result.final_score <= 1.0

        # 应该有 3 个组件: pattern, ema_trend, mtf
        assert len(result.components) == 3

        # pattern 组件
        pattern_comp = result.components[0]
        assert pattern_comp.name == "pattern"
        assert pattern_comp.score == 0.72
        assert pattern_comp.weight == 0.55
        assert pattern_comp.status == "passed"

        # ema_trend 组件
        ema_comp = result.components[1]
        assert ema_comp.name == "ema_trend"
        assert ema_comp.status == "passed"
        # ema_confidence = min(0.0192 / 0.05, 1.0) = 0.384
        assert abs(ema_comp.score - 0.384) < 0.001

        # mtf 组件
        mtf_comp = result.components[2]
        assert mtf_comp.name == "mtf"
        assert mtf_comp.status == "passed"
        # mtf_confidence = 2/3
        assert abs(mtf_comp.score - 2 / 3) < 0.001

        # percentages 总和应接近 100%
        total_pct = sum(result.percentages.values())
        assert abs(total_pct - 100.0) < 0.1

    def test_backtest_format_compatible(self):
        """UT-008: 回测引擎序列化格式兼容"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(pattern_score=0.50)

        result = engine.attribute(attempt)

        assert result.final_score > 0
        assert "pattern" in result.percentages

    def test_direct_format_compatible(self):
        """UT-009: 直接格式兼容 — pattern dict + tuple filter_results"""
        engine = AttributionEngine(_default_config())
        attempt = _make_direct_attempt(pattern_score=0.50)

        result = engine.attribute(attempt)

        assert result.final_score > 0
        assert "pattern" in result.percentages


# ============================================================
# UT-002: 被拒绝的信号 — 某个过滤器 failed
# ============================================================
class TestRejectedFilter:
    """被拒绝过滤器场景"""

    def test_one_filter_rejected(self):
        """UT-002: ema_trend 通过，mtf 被拒绝"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            pattern_score=0.72,
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 65432.10,
                        "ema_value": 64200.00,
                        "distance_pct": 0.0192,
                    },
                },
                {
                    "filter": "mtf",
                    "passed": False,
                    "reason": "mtf_rejected_bearish_higher_tf",
                    "metadata": {
                        "aligned_count": 0,
                        "total_count": 2,
                    },
                },
            ],
        )

        result = engine.attribute(attempt)

        # 被拒绝的 mtf 应该 score=0, status="rejected"
        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert mtf_comp.status == "rejected"
        assert mtf_comp.score == 0.0
        assert mtf_comp.contribution == 0.0
        assert "REJECTED" in mtf_comp.confidence_basis

        # percentages 不应包含 mtf（rejected 的不计入）
        assert "mtf" not in result.percentages

    def test_all_filters_rejected(self):
        """所有过滤器都被拒绝"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            pattern_score=0.50,
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": False,
                    "reason": "bearish_trend_blocks_long",
                    "metadata": {},
                },
                {
                    "filter": "mtf",
                    "passed": False,
                    "reason": "higher_tf_data_unavailable",
                    "metadata": {},
                },
            ],
        )

        result = engine.attribute(attempt)

        # 所有过滤器都 rejected
        for comp in result.components:
            if comp.name != "pattern":
                assert comp.status == "rejected"
                assert comp.score == 0.0


# ============================================================
# UT-003: 空 pattern
# ============================================================
class TestEmptyPattern:
    """空 pattern 场景"""

    def test_pattern_none(self):
        """UT-003: pattern 为 None（回测格式无 pattern_score 字段）"""
        engine = AttributionEngine(_default_config())
        attempt = {
            "strategy_name": "pinbar",
            "pattern_score": None,
            "filter_results": [],
            "final_result": "NO_PATTERN",
        }

        result = engine.attribute(attempt)

        assert result.final_score == 0.0
        assert result.percentages == {}
        assert result.explanation == "无有效归因"


# ============================================================
# UT-004: zero-score — percentages 应为 {}
# ============================================================
class TestZeroScore:
    """zero-score 场景"""

    def test_zero_final_score_empty_percentages(self):
        """UT-004: final_score 为 0 时 percentages 应为 {}"""
        engine = AttributionEngine(_default_config())
        attempt = {
            "strategy_name": "pinbar",
            "pattern_score": 0.0,
            "filter_results": [
                {
                    "filter": "ema_trend",
                    "passed": False,
                    "reason": "no_data",
                    "metadata": {},
                },
            ],
            "final_result": "FILTERED",
        }

        result = engine.attribute(attempt)

        assert result.final_score == 0.0
        assert result.percentages == {}


# ============================================================
# UT-005: 批量归因
# ============================================================
class TestBatchAttribution:
    """批量归因"""

    def test_batch_multiple(self):
        """UT-005: 批量归因 — 多个 attempts"""
        engine = AttributionEngine(_default_config())
        attempts = [
            _make_backtest_attempt(pattern_score=0.72),
            _make_backtest_attempt(pattern_score=0.50),
            _make_backtest_attempt(pattern_score=0.90),
        ]

        results = engine.attribute_batch(attempts)

        assert len(results) == 3
        for r in results:
            assert isinstance(r, SignalAttribution)
            assert r.final_score > 0

    def test_batch_empty(self):
        """空列表批量归因"""
        engine = AttributionEngine(_default_config())
        results = engine.attribute_batch([])
        assert results == []


# ============================================================
# UT-006: 聚合归因
# ============================================================
class TestAggregateAttribution:
    """聚合归因"""

    def test_aggregate_multiple(self):
        """UT-006: AggregateAttribution 计算"""
        engine = AttributionEngine(_default_config())
        attempts = [
            _make_backtest_attempt(pattern_score=0.72),
            _make_backtest_attempt(pattern_score=0.50),
            _make_backtest_attempt(pattern_score=0.90),
        ]
        attributions = engine.attribute_batch(attempts)

        agg = engine.get_aggregate_attribution(attributions)

        assert agg.avg_pattern_contribution > 0
        assert "ema_trend" in agg.avg_filter_contributions
        assert "mtf" in agg.avg_filter_contributions
        assert len(agg.top_performing_filters) > 0
        assert len(agg.worst_performing_filters) > 0

    def test_aggregate_empty(self):
        """空列表聚合归因"""
        engine = AttributionEngine(_default_config())
        agg = engine.get_aggregate_attribution([])

        assert agg.avg_pattern_contribution == 0.0
        assert agg.avg_filter_contributions == {}
        assert agg.top_performing_filters == []
        assert agg.worst_performing_filters == []


# ============================================================
# UT-007: metadata 不完整 — 降级为默认值 0.5
# ============================================================
class TestIncompleteMetadata:
    """metadata 不完整场景"""

    def test_ema_missing_price(self):
        """UT-007: EMA 缺少 price，降级为默认 0.5"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        # 缺少 price
                        "ema_value": 64200.00,
                        "distance_pct": 0.02,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)

        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        assert ema_comp.score == 0.5
        assert "metadata incomplete" in ema_comp.confidence_basis

    def test_mtf_missing_aligned(self):
        """MTF 缺少 aligned_count，降级为默认 0.5"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "mtf",
                    "passed": True,
                    "reason": "mtf_confirmed",
                    "metadata": {
                        # 缺少 aligned_count
                        "total_count": 3,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)

        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert mtf_comp.score == 0.5

    def test_atr_missing_volatility_ratio(self):
        """ATR 缺少 volatility_ratio，降级为默认 0.5"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "atr_volatility",
                    "passed": True,
                    "reason": "volatility_sufficient",
                    "metadata": {
                        # 缺少 volatility_ratio
                        "atr_value": 150.0,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)

        atr_comp = [c for c in result.components if c.name == "atr_volatility"][0]
        assert atr_comp.score == 0.5


# ============================================================
# UT-010: 未知过滤器
# ============================================================
class TestUnknownFilter:
    """未知过滤器场景"""

    def test_unknown_filter_default_confidence(self):
        """UT-010: 未知过滤器 — 默认信心 0.5"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "volume_surge",
                    "passed": True,
                    "reason": "volume_sufficient",
                    "metadata": {},
                },
            ]
        )

        result = engine.attribute(attempt)

        vol_comp = [c for c in result.components if c.name == "volume_surge"][0]
        assert vol_comp.score == 0.5
        assert vol_comp.weight == 0.10  # 默认权重


# ============================================================
# UT-011: ATR 过滤器（atr_volatility 名称）
# ============================================================
class TestAtrFilter:
    """ATR 过滤器场景"""

    def test_atr_volatility_name(self):
        """UT-011: ATR 过滤器使用 atr_volatility 名称"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "atr_volatility",
                    "passed": True,
                    "reason": "volatility_sufficient",
                    "metadata": {
                        "volatility_ratio": 1.5,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)

        atr_comp = [c for c in result.components if c.name == "atr_volatility"][0]
        assert atr_comp.status == "passed"
        # confidence = min(1.5 / 2.0, 1.0) = 0.75
        assert abs(atr_comp.score - 0.75) < 0.001

    def test_atr_short_name(self):
        """ATR 过滤器使用 atr 短名称"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "atr",
                    "passed": True,
                    "reason": "volatility_sufficient",
                    "metadata": {"volatility_ratio": 1.0},
                },
            ]
        )

        result = engine.attribute(attempt)

        atr_comp = [c for c in result.components if c.name == "atr"][0]
        # confidence = min(1.0 / 2.0, 1.0) = 0.5
        assert abs(atr_comp.score - 0.5) < 0.001

    def test_atr_capped_at_one(self):
        """ATR 信心上限为 1.0"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "atr_volatility",
                    "passed": True,
                    "reason": "volatility_sufficient",
                    "metadata": {
                        "volatility_ratio": 3.0,  # > 2.0, 应 cap 到 1.0
                    },
                },
            ]
        )

        result = engine.attribute(attempt)

        atr_comp = [c for c in result.components if c.name == "atr_volatility"][0]
        assert atr_comp.score == 1.0


# ============================================================
# UT-012: confidence_basis 数学可验证
# ============================================================
class TestConfidenceBasis:
    """confidence_basis 可验证性"""

    def test_ema_basis_formula(self):
        """UT-012: EMA confidence_basis 包含公式"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt()
        result = engine.attribute(attempt)

        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        assert "min(" in ema_comp.confidence_basis
        assert "/0.05" in ema_comp.confidence_basis

    def test_mtf_basis_formula(self):
        """MTF confidence_basis 包含对齐比例"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt()
        result = engine.attribute(attempt)

        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert "/" in mtf_comp.confidence_basis
        assert "higher timeframes aligned" in mtf_comp.confidence_basis


# ============================================================
# UT-013: explanation 人类可读
# ============================================================
class TestExplanation:
    """explanation 可读性"""

    def test_explanation_format(self):
        """UT-013: explanation 格式为 '组件(百分比%) + 组件(百分比%)'"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt()
        result = engine.attribute(attempt)

        assert "(" in result.explanation
        assert "%" in result.explanation
        assert " + " in result.explanation or len(result.percentages) == 1

    def test_explanation_empty(self):
        """无有效归因时 explanation"""
        engine = AttributionEngine(_default_config())
        attempt = {
            "strategy_name": "pinbar",
            "pattern_score": 0.0,
            "filter_results": [],
        }
        result = engine.attribute(attempt)
        assert result.explanation == "无有效归因"


# ============================================================
# UT-014: final_score 上限为 1.0
# ============================================================
class TestFinalScoreCap:
    """final_score 上限测试"""

    def test_score_capped_at_one(self):
        """UT-014: final_score 上限为 1.0"""
        engine = AttributionEngine(_default_config())
        # 极高的 pattern_score + 所有过滤器都满分
        attempt = _make_backtest_attempt(
            pattern_score=1.0,
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 70000.0,
                        "ema_value": 60000.0,
                        "distance_pct": 0.1667,  # > 0.05, confidence = 1.0
                    },
                },
                {
                    "filter": "mtf",
                    "passed": True,
                    "reason": "mtf_confirmed",
                    "metadata": {
                        "aligned_count": 3,
                        "total_count": 3,  # 100% 对齐
                    },
                },
            ],
        )

        result = engine.attribute(attempt)
        assert result.final_score <= 1.0


# ============================================================
# UT-016: 仅有 pattern 无过滤器
# ============================================================
class TestPatternOnly:
    """仅有 pattern 场景"""

    def test_no_filters(self):
        """UT-016: 仅有 pattern 无过滤器"""
        engine = AttributionEngine(_default_config())
        attempt = {
            "strategy_name": "pinbar",
            "pattern_score": 0.80,
            "filter_results": [],
        }

        result = engine.attribute(attempt)

        assert len(result.components) == 1
        assert result.components[0].name == "pattern"
        assert result.percentages == {"pattern": 100.0}


# ============================================================
# UT-017: pattern_score 为 0 但有通过的过滤器
# ============================================================
class TestZeroPatternWithFilters:
    """pattern=0 但有通过过滤器的场景"""

    def test_zero_pattern_passed_filters(self):
        """UT-017: pattern_score 为 0 但有通过的过滤器"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            pattern_score=0.0,
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 65432.10,
                        "ema_value": 64200.00,
                        "distance_pct": 0.0192,
                    },
                },
            ],
        )

        result = engine.attribute(attempt)

        # pattern=0, 但 ema 有贡献
        pattern_comp = result.components[0]
        assert pattern_comp.score == 0.0
        assert pattern_comp.contribution == 0.0

        # 最终评分仅来自过滤器
        assert result.final_score > 0
        assert "pattern" not in result.percentages  # 0 贡献不应出现在 percentages


# ============================================================
# UT-018: FilterResult 对象格式输入
# ============================================================
class TestFilterResultObject:
    """FilterResult 对象格式"""

    def test_filter_result_object(self):
        """UT-018: FilterResult 对象格式输入"""
        engine = AttributionEngine(_default_config())
        attempt = _make_direct_attempt(pattern_score=0.60)

        result = engine.attribute(attempt)

        assert result.final_score > 0
        assert len(result.components) >= 3  # pattern + ema_trend + mtf

        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        assert ema_comp.status == "passed"


# ============================================================
# UT-019: EMA 信心函数边界
# ============================================================
class TestEmaConfidenceFunction:
    """EMA 信心函数边界测试"""

    def test_distance_at_threshold(self):
        """UT-019: distance_pct = 0.05 时 confidence = 1.0"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 66000.0,
                        "ema_value": 63000.0,
                        "distance_pct": 0.05,  # 恰好阈值
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        assert ema_comp.score == 1.0

    def test_distance_below_threshold(self):
        """distance_pct < 0.05 时 confidence < 1.0"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 64500.0,
                        "ema_value": 64000.0,
                        "distance_pct": 0.0078,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        # confidence = 0.0078 / 0.05 = 0.156
        assert abs(ema_comp.score - 0.156) < 0.001

    def test_distance_above_threshold(self):
        """distance_pct > 0.05 时 confidence = 1.0 (capped)"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "ema_trend",
                    "passed": True,
                    "reason": "trend_match",
                    "metadata": {
                        "price": 70000.0,
                        "ema_value": 60000.0,
                        "distance_pct": 0.1667,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        ema_comp = [c for c in result.components if c.name == "ema_trend"][0]
        assert ema_comp.score == 1.0


# ============================================================
# UT-020: MTF 信心函数
# ============================================================
class TestMtfConfidenceFunction:
    """MTF 信心函数测试"""

    def test_full_alignment(self):
        """UT-020: 全部对齐时 confidence = 1.0"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "mtf",
                    "passed": True,
                    "reason": "mtf_confirmed",
                    "metadata": {
                        "aligned_count": 3,
                        "total_count": 3,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert mtf_comp.score == 1.0

    def test_partial_alignment(self):
        """部分对齐时 confidence = aligned/total"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "mtf",
                    "passed": True,
                    "reason": "mtf_confirmed",
                    "metadata": {
                        "aligned_count": 1,
                        "total_count": 3,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert abs(mtf_comp.score - 1 / 3) < 0.001

    def test_no_alignment(self):
        """无对齐时 confidence = 0"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt(
            filter_results=[
                {
                    "filter": "mtf",
                    "passed": True,
                    "reason": "mtf_confirmed",
                    "metadata": {
                        "aligned_count": 0,
                        "total_count": 3,
                    },
                },
            ]
        )

        result = engine.attribute(attempt)
        mtf_comp = [c for c in result.components if c.name == "mtf"][0]
        assert mtf_comp.score == 0.0


# ============================================================
# Additional: Serialization tests
# ============================================================
class TestSerialization:
    """序列化测试"""

    def test_attribution_to_dict(self):
        """SignalAttribution.to_dict() 返回可序列化字典"""
        engine = AttributionEngine(_default_config())
        attempt = _make_backtest_attempt()
        result = engine.attribute(attempt)

        d = result.to_dict()
        assert "final_score" in d
        assert "components" in d
        assert "percentages" in d
        assert "explanation" in d
        assert isinstance(d["components"], list)

    def test_aggregate_to_dict(self):
        """AggregateAttribution.to_dict() 返回可序列化字典"""
        engine = AttributionEngine(_default_config())
        attributions = engine.attribute_batch([_make_backtest_attempt()])
        agg = engine.get_aggregate_attribution(attributions)

        d = agg.to_dict()
        assert "avg_pattern_contribution" in d
        assert "avg_filter_contributions" in d
        assert "top_performing_filters" in d
        assert "worst_performing_filters" in d

    def test_component_to_dict(self):
        """AttributionComponent.to_dict() 返回可序列化字典"""
        comp = AttributionComponent(
            name="test",
            score=0.5,
            weight=0.25,
            contribution=0.125,
            percentage=50.0,
            confidence_basis="test basis",
            status="passed",
        )
        d = comp.to_dict()
        assert d["name"] == "test"
        assert d["score"] == 0.5
        assert d["status"] == "passed"
