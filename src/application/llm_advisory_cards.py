"""Feishu push-only card templates for LLM advisory output."""

from __future__ import annotations

from src.domain.llm_advisory import (
    LlmAdvisoryRecommendation,
    LlmAdvisoryRecommendationType,
    LlmConsumableEvent,
    LlmConsumableEventType,
    LlmFeishuAdvisoryCard,
    LlmFeishuCardType,
)


def build_feishu_advisory_card(
    *,
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
    language: str = "zh_cn",
) -> LlmFeishuAdvisoryCard:
    card_type = recommendation.feishu_card_type
    if card_type == LlmFeishuCardType.GENERIC_ADVISORY:
        card_type = _card_type_for_event(event, recommendation)
    title = _title(card_type, language=language)
    subtitle = f"{event.event_type.value} · {event.source_type}/{event.source_id}"
    lines = _common_lines(event=event, recommendation=recommendation, language=language)
    lines.extend(
        _type_specific_lines(
            card_type=card_type,
            event=event,
            recommendation=recommendation,
            language=language,
        )
    )
    markdown = "\n".join([title, subtitle, *lines, _boundary_line(language=language)])
    return LlmFeishuAdvisoryCard(
        card_type=card_type,
        language="zh_cn" if language == "zh_cn" else "en",
        title=title,
        subtitle=subtitle,
        lines=lines,
        markdown=markdown,
    )


def format_feishu_advisory_markdown(
    *,
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
) -> str:
    return build_feishu_advisory_card(
        event=event,
        recommendation=recommendation,
    ).markdown


def _card_type_for_event(
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
) -> LlmFeishuCardType:
    if event.event_type in {
        LlmConsumableEventType.STRATEGY_CANDIDATE_OBSERVED,
        LlmConsumableEventType.ORDER_CANDIDATE_CREATED,
    }:
        return LlmFeishuCardType.CANDIDATE_REVIEW
    if event.event_type == LlmConsumableEventType.FINAL_GATE_BLOCKED:
        return LlmFeishuCardType.FINAL_GATE_BLOCKED
    if event.event_type == LlmConsumableEventType.TRADE_CLOSED:
        return LlmFeishuCardType.TRADE_CLOSED_REVIEW
    if event.event_type == LlmConsumableEventType.DAILY_AUDIT_DIGEST:
        return LlmFeishuCardType.DAILY_AUDIT_DIGEST
    if recommendation.recommendation_type == LlmAdvisoryRecommendationType.MARKET_CONTEXT:
        return LlmFeishuCardType.MARKET_CONTEXT
    return LlmFeishuCardType.GENERIC_ADVISORY


def _title(card_type: LlmFeishuCardType, *, language: str) -> str:
    if language == "zh_cn":
        return {
            LlmFeishuCardType.CANDIDATE_REVIEW: "BRC LLM 建议：候选策略复核",
            LlmFeishuCardType.FINAL_GATE_BLOCKED: "BRC LLM 建议：FinalGate 阻断",
            LlmFeishuCardType.DAILY_AUDIT_DIGEST: "BRC LLM 建议：每日审计摘要",
            LlmFeishuCardType.TRADE_CLOSED_REVIEW: "BRC LLM 建议：已平仓复盘",
            LlmFeishuCardType.MARKET_CONTEXT: "BRC LLM 建议：市场上下文",
            LlmFeishuCardType.GENERIC_ADVISORY: "BRC LLM Advisory 建议",
        }[card_type]
    return {
        LlmFeishuCardType.CANDIDATE_REVIEW: "BRC Advisory: Candidate Review",
        LlmFeishuCardType.FINAL_GATE_BLOCKED: "BRC Advisory: FinalGate Blocked",
        LlmFeishuCardType.DAILY_AUDIT_DIGEST: "BRC Advisory: Daily Audit Digest",
        LlmFeishuCardType.TRADE_CLOSED_REVIEW: "BRC Advisory: Trade Review",
        LlmFeishuCardType.MARKET_CONTEXT: "BRC Advisory: Market Context",
        LlmFeishuCardType.GENERIC_ADVISORY: "BRC LLM Advisory",
    }[card_type]


def _common_lines(
    *,
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
    language: str,
) -> list[str]:
    strategies = recommendation.recommended_strategy_family_ids or ["none"]
    observe_only = recommendation.observe_only_strategy_family_ids or ["none"]
    if language == "zh_cn":
        return [
            f"标的: {event.symbol or 'n/a'} {event.timeframe or ''}".strip(),
            f"建议类型: {recommendation.recommendation_type.value}",
            f"建议关注策略族: {', '.join(strategies)}",
            f"仅观察策略族: {', '.join(observe_only)}",
            f"置信度: {recommendation.confidence}",
            f"摘要: {recommendation.summary}",
        ]
    return [
        f"Symbol: {event.symbol or 'n/a'} {event.timeframe or ''}".strip(),
        f"Recommendation: {recommendation.recommendation_type.value}",
        f"Strategies: {', '.join(strategies)}",
        f"Observe only: {', '.join(observe_only)}",
        f"Confidence: {recommendation.confidence}",
        f"Summary: {recommendation.summary}",
    ]


def _type_specific_lines(
    *,
    card_type: LlmFeishuCardType,
    event: LlmConsumableEvent,
    recommendation: LlmAdvisoryRecommendation,
    language: str,
) -> list[str]:
    if card_type == LlmFeishuCardType.TRADE_CLOSED_REVIEW:
        review = dict(event.context_artifact.review or {})
        right_tail = dict(review.get("right_tail_review") or {})
        if language == "zh_cn":
            return [
                f"右尾盈利次数: {right_tail.get('right_tail_win_count', 0)}",
                f"小亏次数: {right_tail.get('small_loss_count', 0)}",
                f"最大 R 倍数: {right_tail.get('max_r_multiple', 'n/a')}",
                f"是否存在 payoff asymmetry: {right_tail.get('payoff_asymmetry_present', False)}",
                f"复盘备注: {'; '.join(recommendation.review_notes[:5] or ['none'])}",
            ]
        return [
            f"Right-tail wins: {right_tail.get('right_tail_win_count', 0)}",
            f"Small losses: {right_tail.get('small_loss_count', 0)}",
            f"Max R: {right_tail.get('max_r_multiple', 'n/a')}",
            f"Payoff asymmetry: {right_tail.get('payoff_asymmetry_present', False)}",
            f"Review notes: {'; '.join(recommendation.review_notes[:5] or ['none'])}",
        ]
    if card_type == LlmFeishuCardType.FINAL_GATE_BLOCKED:
        if language == "zh_cn":
            return [
                f"缺失事实: {', '.join(recommendation.missing_facts[:5] or ['none'])}",
                f"风险备注: {'; '.join(recommendation.risk_notes[:5] or ['none'])}",
            ]
        return [
            f"Missing facts: {', '.join(recommendation.missing_facts[:5] or ['none'])}",
            f"Risks: {'; '.join(recommendation.risk_notes[:5] or ['none'])}",
        ]
    if card_type == LlmFeishuCardType.DAILY_AUDIT_DIGEST:
        if language == "zh_cn":
            return [
                f"原因码: {', '.join(recommendation.reason_codes[:6] or ['none'])}",
                f"研究想法: {'; '.join(recommendation.research_idea_notes[:3] or ['none'])}",
            ]
        return [
            f"Reason codes: {', '.join(recommendation.reason_codes[:6] or ['none'])}",
            f"Research ideas: {'; '.join(recommendation.research_idea_notes[:3] or ['none'])}",
        ]
    if language == "zh_cn":
        return [
            f"风险备注: {'; '.join(recommendation.risk_notes[:5] or ['none'])}",
            f"缺失事实: {', '.join(recommendation.missing_facts[:5] or ['none'])}",
        ]
    return [
        f"Risks: {'; '.join(recommendation.risk_notes[:5] or ['none'])}",
        f"Missing facts: {', '.join(recommendation.missing_facts[:5] or ['none'])}",
    ]


def _boundary_line(*, language: str) -> str:
    if language == "zh_cn":
        return (
            "边界: Feishu is push-only；如需 Owner 行动必须打开 Console 并回到正式治理链。"
            "No ExecutionIntent, order, exchange call, transfer, or withdrawal."
        )
    return (
        "Boundary: Feishu is push-only; open Console for canonical Owner action. "
        "No ExecutionIntent, order, exchange call, transfer, or withdrawal."
    )
