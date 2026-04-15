"""
Attribution Engine - 策略归因引擎（方案 B：非侵入式）。

基于 SignalAttempt 的 dict 数据计算每个组件的信心评分，
聚合为最终归因结果。不修改任何现有接口。

数据格式兼容：
- 回测引擎序列化格式: {"filter": name, "passed": bool, ...}
- 直接对象格式: [(filter_name, FilterResult), ...]
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Any, Optional
import logging

from src.domain.attribution_config import AttributionConfig
from src.domain.models import FilterResult, PatternResult

logger = logging.getLogger(__name__)


@dataclass
class FilterScore:
    """过滤器评分（内部使用，不序列化）"""
    filter_name: str
    score: Decimal
    weight: Decimal
    contribution: Decimal
    reason: str
    metadata: Dict[str, Any]
    confidence_basis: str
    status: str = "passed"  # "passed" 或 "rejected"


class AttributionComponent:
    """归因组件 — 每个组件的评分和贡献"""
    name: str
    score: float
    weight: float
    contribution: float
    percentage: float
    confidence_basis: str
    status: str

    def __init__(
        self,
        name: str,
        score: float,
        weight: float,
        contribution: float,
        percentage: float,
        confidence_basis: str,
        status: str = "passed",
    ):
        self.name = name
        self.score = score
        self.weight = weight
        self.contribution = contribution
        self.percentage = percentage
        self.confidence_basis = confidence_basis
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "contribution": self.contribution,
            "percentage": self.percentage,
            "confidence_basis": self.confidence_basis,
            "status": self.status,
        }


class SignalAttribution:
    """单信号的归因分析结果"""
    final_score: float
    components: List[AttributionComponent]
    percentages: Dict[str, float]
    explanation: str

    def __init__(
        self,
        final_score: float,
        components: List[AttributionComponent],
        percentages: Dict[str, float],
        explanation: str,
    ):
        self.final_score = final_score
        self.components = components
        self.percentages = percentages
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_score": self.final_score,
            "components": [c.to_dict() for c in self.components],
            "percentages": self.percentages,
            "explanation": self.explanation,
        }


class AggregateAttribution:
    """聚合归因（回测报告级别）"""
    avg_pattern_contribution: float
    avg_filter_contributions: Dict[str, float]
    top_performing_filters: List[str]
    worst_performing_filters: List[str]

    def __init__(
        self,
        avg_pattern_contribution: float,
        avg_filter_contributions: Dict[str, float],
        top_performing_filters: List[str],
        worst_performing_filters: List[str],
    ):
        self.avg_pattern_contribution = avg_pattern_contribution
        self.avg_filter_contributions = avg_filter_contributions
        self.top_performing_filters = top_performing_filters
        self.worst_performing_filters = worst_performing_filters

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_pattern_contribution": self.avg_pattern_contribution,
            "avg_filter_contributions": self.avg_filter_contributions,
            "top_performing_filters": self.top_performing_filters,
            "worst_performing_filters": self.worst_performing_filters,
        }


class AttributionEngine:
    """
    非侵入式归因引擎，基于 SignalAttempt dict 数据计算组件贡献。

    不修改任何现有接口，纯分析层。
    权重通过 AttributionConfig.from_kv() 从 KV 配置加载并校验。
    """

    # 默认信心值（metadata 不完整时）
    _DEFAULT_CONFIDENCE = Decimal("0.5")

    def __init__(self, config: AttributionConfig):
        self.config = config

    def attribute(self, attempt_dict: Dict[str, Any]) -> SignalAttribution:
        """
        对单个 SignalAttempt dict 计算归因。

        兼容两种 dict 格式：
        1. 回测引擎格式: {"pattern_score": float, "filter_results": [{"filter": name, ...}]}
        2. 直接格式: {"pattern": {"score": float}, "filter_results": [(name, FilterResult)]}

        Args:
            attempt_dict: 序列化的 SignalAttempt 字典。

        Returns:
            SignalAttribution 归因分析结果。
        """
        # Step 1: 提取形态基础分（兼容两种格式）
        pattern_score = self._extract_pattern_score(attempt_dict)

        # Step 2: 形态基础贡献
        pattern_weight = Decimal(str(self.config.weights["pattern"]))
        pattern_contrib = pattern_score * pattern_weight

        # Step 3: 过滤器信心评分（处理所有过滤器，包括被拒绝的）
        filter_scores = self._score_filters(attempt_dict)

        # Step 4: 聚合
        total_filter_contrib = sum(fs.contribution for fs in filter_scores)
        final_score = pattern_contrib + total_filter_contrib
        final_score = min(final_score, Decimal("1.0"))

        # Step 5: 计算百分比
        percentages = self._calc_percentages(pattern_contrib, filter_scores, final_score)

        # Step 6: 构建响应
        components = self._build_components(
            pattern_score, pattern_weight, pattern_contrib,
            filter_scores, percentages,
        )
        explanation = self._build_explanation(percentages)

        return SignalAttribution(
            final_score=float(final_score),
            components=components,
            percentages=percentages,
            explanation=explanation,
        )

    def attribute_batch(
        self, attempts: List[Dict[str, Any]]
    ) -> List[SignalAttribution]:
        """批量归因"""
        return [self.attribute(a) for a in attempts]

    def get_aggregate_attribution(
        self, attributions: List[SignalAttribution]
    ) -> AggregateAttribution:
        """
        聚合归因（回测报告摘要级别）。

        Args:
            attributions: 单信号归因结果列表。

        Returns:
            AggregateAttribution 聚合归因。
        """
        if not attributions:
            return AggregateAttribution(
                avg_pattern_contribution=0.0,
                avg_filter_contributions={},
                top_performing_filters=[],
                worst_performing_filters=[],
            )

        # 平均形态贡献
        avg_pattern = sum(
            c.contribution for a in attributions
            for c in a.components if c.name == "pattern"
        ) / len(attributions)

        # 平均过滤器贡献
        filter_contrib_map: Dict[str, List[float]] = {}
        for a in attributions:
            for c in a.components:
                if c.name != "pattern" and c.status == "passed":
                    filter_contrib_map.setdefault(c.name, []).append(c.contribution)

        avg_filter_contributions = {
            k: sum(v) / len(v) for k, v in filter_contrib_map.items()
        }

        # 排序
        sorted_filters = sorted(
            avg_filter_contributions.items(), key=lambda x: x[1], reverse=True
        )
        top_performing = [k for k, _ in sorted_filters[:3]]
        worst_performing = [k for k, _ in sorted_filters[-3:]]

        return AggregateAttribution(
            avg_pattern_contribution=float(avg_pattern),
            avg_filter_contributions=avg_filter_contributions,
            top_performing_filters=top_performing,
            worst_performing_filters=worst_performing,
        )

    # ---------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------

    def _extract_pattern_score(self, attempt_dict: Dict[str, Any]) -> Decimal:
        """
        提取形态基础分，兼容两种格式。

        优先级：
        1. attempt_dict["pattern"]["score"] （直接格式）
        2. attempt_dict["pattern_score"] （回测引擎格式）
        3. 默认 0
        """
        # 格式 1: pattern 是 dict
        pattern_info = attempt_dict.get("pattern")
        if isinstance(pattern_info, dict):
            raw_score = pattern_info.get("score", 0)
            return Decimal(str(raw_score))

        # 格式 1b: pattern 是 PatternResult 对象
        if isinstance(pattern_info, PatternResult):
            return pattern_info.score

        # 格式 2: pattern_score 是标量（回测引擎序列化格式）
        pattern_score = attempt_dict.get("pattern_score")
        if pattern_score is not None:
            return Decimal(str(pattern_score))

        return Decimal("0")

    def _parse_filter_results(
        self, attempt_dict: Dict[str, Any]
    ) -> List[tuple]:
        """
        解析 filter_results，兼容两种格式。

        返回: List[(filter_name, passed: bool, reason: str, metadata: dict)]
        """
        raw_results = attempt_dict.get("filter_results", [])
        parsed = []

        for item in raw_results:
            if isinstance(item, dict):
                # 回测引擎格式: {"filter": name, "passed": bool, ...}
                name = item.get("filter", "unknown")
                passed = item.get("passed", False)
                reason = item.get("reason", "")
                metadata = item.get("metadata", {})
                parsed.append((name, passed, reason, metadata))

            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # 直接格式: (name, FilterResult_or_dict)
                name = item[0]
                data = item[1]

                if isinstance(data, FilterResult):
                    passed = data.passed
                    reason = data.reason
                    metadata = data.metadata or {}
                elif isinstance(data, dict):
                    passed = data.get("passed", False)
                    reason = data.get("reason", "")
                    metadata = data.get("metadata", {})
                else:
                    logger.warning(
                        f"[ATTRIBUTION] Unknown filter data type for {name}: {type(data)}"
                    )
                    continue

                parsed.append((name, passed, reason, metadata))

            else:
                logger.warning(
                    f"[ATTRIBUTION] Unparseable filter result: {type(item)}"
                )

        return parsed

    def _score_filters(self, attempt_dict: Dict[str, Any]) -> List[FilterScore]:
        """
        对所有过滤器计算信心评分。
        被拒绝的过滤器 score=0, weight=0, status="rejected"。
        """
        parsed = self._parse_filter_results(attempt_dict)
        scores = []

        for filter_name, passed, reason, metadata in parsed:
            if passed:
                confidence = self._calculate_filter_confidence(
                    filter_name, metadata
                )
                weight = Decimal(str(
                    self.config.weights.get(filter_name, 0.10)
                ))
                scores.append(FilterScore(
                    filter_name=filter_name,
                    score=confidence,
                    weight=weight,
                    contribution=confidence * weight,
                    reason=reason,
                    metadata=metadata,
                    confidence_basis=self._explain_confidence(
                        filter_name, metadata
                    ),
                    status="passed",
                ))
            else:
                scores.append(FilterScore(
                    filter_name=filter_name,
                    score=Decimal("0"),
                    weight=Decimal("0"),
                    contribution=Decimal("0"),
                    reason=reason,
                    metadata=metadata,
                    confidence_basis=f"REJECTED: {reason}",
                    status="rejected",
                ))

        return scores

    def _calculate_filter_confidence(
        self, filter_name: str, metadata: Dict[str, Any]
    ) -> Decimal:
        """
        根据过滤器类型和 metadata 计算信心强度。
        每个信心函数都是数学可验证的确定性函数。
        """
        if filter_name in ("ema_trend", "ema"):
            price = metadata.get("price")
            ema = metadata.get("ema_value")
            distance_pct = metadata.get("distance_pct")

            if price is not None and ema is not None and distance_pct is not None:
                # confidence = min(distance_pct / 0.05, 1.0)
                return min(
                    Decimal(str(distance_pct)) / Decimal("0.05"),
                    Decimal("1.0"),
                )

            logger.warning(
                f"[ATTRIBUTION] EMA metadata incomplete for attribution, "
                f"default confidence=0.5"
            )
            return self._DEFAULT_CONFIDENCE

        elif filter_name == "mtf":
            aligned = metadata.get("aligned_count")
            total = metadata.get("total_count")

            if aligned is not None and total is not None and total > 0:
                return Decimal(str(aligned)) / Decimal(str(total))

            logger.warning(
                f"[ATTRIBUTION] MTF metadata incomplete for attribution, "
                f"default confidence=0.5"
            )
            return self._DEFAULT_CONFIDENCE

        elif filter_name in ("atr", "atr_volatility"):
            atr_ratio = metadata.get("volatility_ratio")

            if atr_ratio is not None:
                return min(
                    Decimal(str(atr_ratio)) / Decimal("2.0"),
                    Decimal("1.0"),
                )

            logger.warning(
                f"[ATTRIBUTION] ATR metadata incomplete for attribution, "
                f"default confidence=0.5"
            )
            return self._DEFAULT_CONFIDENCE

        else:
            # 未知过滤器：默认中等信心
            return self._DEFAULT_CONFIDENCE

    def _explain_confidence(
        self, filter_name: str, metadata: Dict[str, Any]
    ) -> str:
        """生成信心评分的人类可读解释（数学可验证）"""
        if filter_name in ("ema_trend", "ema"):
            price = metadata.get("price")
            ema = metadata.get("ema_value")
            distance_pct = metadata.get("distance_pct")

            if price is not None and ema is not None and distance_pct is not None:
                score = min(distance_pct / 0.05, 1.0)
                direction = "above" if price > ema else "below"
                return (
                    f"price {price} is {distance_pct:.2%} {direction} EMA {ema}, "
                    f"score=min({distance_pct:.4f}/0.05, 1.0)={score:.3f}"
                )
            return "metadata incomplete, default confidence=0.5"

        elif filter_name == "mtf":
            aligned = metadata.get("aligned_count", 0)
            total = metadata.get("total_count", 0)
            if total > 0:
                score = aligned / total
                return (
                    f"{aligned}/{total} higher timeframes aligned, "
                    f"score={aligned}/{total}={score:.3f}"
                )
            return "no higher timeframe data, default confidence=0.5"

        elif filter_name in ("atr", "atr_volatility"):
            atr_ratio = metadata.get("volatility_ratio")
            if atr_ratio is not None:
                score = min(atr_ratio / 2.0, 1.0)
                return (
                    f"volatility ratio={atr_ratio:.3f}, "
                    f"score=min({atr_ratio:.3f}/2.0, 1.0)={score:.3f}"
                )
            return "metadata incomplete, default confidence=0.5"

        return "confidence function not defined for this filter"

    def _calc_percentages(
        self,
        pattern_contrib: Decimal,
        filter_scores: List[FilterScore],
        final_score: Decimal,
    ) -> Dict[str, float]:
        """
        计算各组件的百分比贡献。
        final_score=0 时返回 {}，不伪造百分比。
        贡献为 0 的组件不计入 percentages。
        """
        if final_score > 0:
            percentages: Dict[str, float] = {}
            # 只有 pattern 有贡献才加入
            if pattern_contrib > 0:
                percentages["pattern"] = float(
                    pattern_contrib / final_score * 100
                )
            for fs in filter_scores:
                if fs.status == "passed" and fs.contribution > 0:
                    percentages[fs.filter_name] = float(
                        fs.contribution / final_score * 100
                    )
            return percentages
        return {}

    def _build_components(
        self,
        pattern_score: Decimal,
        pattern_weight: Decimal,
        pattern_contrib: Decimal,
        filter_scores: List[FilterScore],
        percentages: Dict[str, float],
    ) -> List[AttributionComponent]:
        """构建归因组件列表"""
        components = [
            AttributionComponent(
                name="pattern",
                score=float(pattern_score),
                weight=float(pattern_weight),
                contribution=float(pattern_contrib),
                percentage=percentages.get("pattern", 0),
                confidence_basis="pattern_score × pattern_weight",
                status="passed",
            ),
        ]
        for fs in filter_scores:
            components.append(
                AttributionComponent(
                    name=fs.filter_name,
                    score=float(fs.score),
                    weight=float(fs.weight),
                    contribution=float(fs.contribution),
                    percentage=percentages.get(fs.filter_name, 0),
                    confidence_basis=fs.confidence_basis,
                    status=fs.status,
                )
            )
        return components

    def _build_explanation(self, percentages: Dict[str, float]) -> str:
        """构建人类可读的归因解释"""
        parts = []
        name_map = {
            "pattern": "Pinbar 形态",
            "ema_trend": "EMA 趋势确认",
            "mtf": "多周期对齐",
            "atr": "ATR 波动",
            "atr_volatility": "ATR 波动",
        }
        for name, pct in sorted(percentages.items(), key=lambda x: x[1], reverse=True):
            label = name_map.get(name, name)
            parts.append(f"{label}({pct:.1f}%)")
        return " + ".join(parts) if parts else "无有效归因"
