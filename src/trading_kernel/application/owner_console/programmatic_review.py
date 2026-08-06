"""Deterministic, evidence-linked review assembly for Owner Console."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    ExecutionClassification,
    MoneyMetric,
    PageCursor,
    ProgrammaticReviewFacts,
    ProgrammaticTradeReview,
    ReviewBreakdownItem,
    ReviewCenterFacts,
    ReviewCenterItemFacts,
    ReviewCenterSummary,
    ReviewEconomicSummary,
    ReviewSentence,
    StrategyGroupSampleState,
    encode_cursor,
)

TEMPLATES = {
    "execution_complete": "执行链完整。{entry_summary}；{exit_summary}。",
    "execution_recovered": (
        "执行链已终态，但发生并恢复了异常：{incident_summary}。"
    ),
    "economics_complete": (
        "Net PnL 为 {net_pnl} U，Net R 为 {net_r}R；"
        "订单、费用、Funding 与 Review 证据完整。"
    ),
    "economics_incomplete": "{reason}；因此不计算 Net PnL 与 Net R。",
    "review_waiting": "Ticket 已终态，当前仍在等待 Review。",
    "ticket_in_progress": "Ticket 尚未终态，当前阶段为 {stage}。",
}

_STAGE_LABELS = {
    "signal": "Signal",
    "admission": "Admission",
    "entry": "ENTRY",
    "protection": "Protection",
    "tp_runner": "TP1 / Runner",
    "exit": "EXIT",
    "reconciliation": "Reconciliation / Settlement",
    "review": "Review",
}
_EXIT_SUMMARIES = {
    "Initial Stop": "退出由 Initial Stop 触发",
    "TP1 + Runner Exit": "退出由 TP1 后 Runner EXIT 触发",
    "Controlled Exit": "退出由 Controlled EXIT 触发",
    "External Flat / Exit Fills Unavailable": "外部平仓已确认",
}


class ProgrammaticReviewContradiction(RuntimeError):
    """Persisted review facts disagree or exceed a hard read bound."""


def build_programmatic_review(
    facts: ProgrammaticReviewFacts,
) -> ProgrammaticTradeReview:
    """Render one fixed-template review without recomputing economics."""

    evidence = _deduplicate_evidence(facts.evidence)
    if not evidence:
        raise ProgrammaticReviewContradiction(
            "programmatic Review requires evidence"
        )
    _validate_incident_evidence(facts)
    _validate_review_evidence(facts)
    economic_summary = ReviewEconomicSummary(
        gross_pnl=facts.gross_pnl,
        fees=facts.fees,
        funding=facts.funding,
        net_pnl=facts.net_pnl,
        net_r=facts.net_r,
    )

    if facts.aggregate_status != "terminal":
        sentence = _sentence(
            "ticket_in_progress",
            evidence=_evidence_of_kinds(evidence, "ticket", "aggregate"),
            stage=_STAGE_LABELS[facts.lifecycle_stage],
        )
        return ProgrammaticTradeReview(
            ticket_id=facts.ticket_id,
            review_status="in_progress",
            execution_classification="in_progress",
            economic_summary=economic_summary,
            exit_reason=facts.exit_reason,
            attention_items=_attention_items(facts),
            sentences=(sentence,),
            final_conclusion=None,
            evidence=evidence,
        )

    if facts.current_review_id is None:
        sentence = _sentence(
            "review_waiting",
            evidence=_evidence_of_kinds(evidence, "ticket", "aggregate"),
        )
        return ProgrammaticTradeReview(
            ticket_id=facts.ticket_id,
            review_status="waiting_review",
            execution_classification="waiting_review",
            economic_summary=economic_summary,
            exit_reason=facts.exit_reason,
            attention_items=_attention_items(facts),
            sentences=(sentence,),
            final_conclusion=sentence.text,
            evidence=evidence,
        )

    classification = _terminal_classification(facts)
    sentences = _terminal_sentences(
        facts,
        classification=classification,
        evidence=evidence,
    )
    review_status: Literal["complete", "incomplete_evidence"] = (
        "complete"
        if classification in {"complete", "recovered_incident"}
        else "incomplete_evidence"
    )
    return ProgrammaticTradeReview(
        ticket_id=facts.ticket_id,
        review_status=review_status,
        execution_classification=classification,
        economic_summary=economic_summary,
        exit_reason=facts.exit_reason,
        attention_items=_attention_items(facts),
        sentences=sentences,
        final_conclusion="\n".join(sentence.text for sentence in sentences),
        evidence=evidence,
    )


def build_review_center(facts: ReviewCenterFacts) -> ReviewCenterSummary:
    """Aggregate one bounded terminal Ticket page without strategy judgment."""

    if len(facts.items) > facts.requested_limit + 1:
        raise ProgrammaticReviewContradiction(
            "Review Center page exceeded limit+1 bound"
        )
    page_items = facts.items[: facts.requested_limit]
    for item in page_items:
        if item.review.aggregate_status != "terminal":
            raise ProgrammaticReviewContradiction(
                "Review Center accepts only terminal Tickets"
            )
    reviews = tuple(
        (item, build_programmatic_review(item.review)) for item in page_items
    )
    next_cursor = None
    if len(facts.items) > facts.requested_limit and page_items:
        boundary = page_items[-1]
        next_cursor = encode_cursor(
            PageCursor(
                sort_ms=boundary.terminal_at_ms,
                identity=boundary.review.ticket_id,
            )
        )

    evidence = _deduplicate_evidence(
        ref for _item, review in reviews for ref in review.evidence
    )
    net_pnl, net_r, fees, funding = _center_economics(reviews)
    quality_breakdown = _quality_breakdown(reviews)
    exit_breakdown = _exit_breakdown(reviews)
    complete_count = sum(
        review.review_status == "complete" for _item, review in reviews
    )
    return ReviewCenterSummary(
        from_ms=facts.from_ms,
        to_ms=facts.to_ms,
        sample_count=len(reviews),
        next_cursor=next_cursor,
        net_pnl=net_pnl,
        net_r=net_r,
        fees=fees,
        funding=funding,
        exit_reason_breakdown=exit_breakdown,
        execution_quality_breakdown=quality_breakdown,
        complete_review_count=complete_count,
        incomplete_review_count=len(reviews) - complete_count,
        strategy_group_samples=_strategy_group_samples(
            reviews,
            requested_strategy_group_id=facts.requested_strategy_group_id,
        ),
        evidence=evidence,
    )


def _terminal_classification(
    facts: ProgrammaticReviewFacts,
) -> ExecutionClassification:
    chain_complete = all(
        (
            facts.entry_complete,
            facts.protection_complete,
            facts.exit_complete,
            facts.reconciliation_complete,
            facts.settlement_completed,
            facts.review_complete,
        )
    )
    incidents = set(facts.incident_ids)
    recovered = set(facts.recovered_incident_ids)
    incidents_recovered = incidents == recovered
    if (
        not chain_complete
        or not incidents_recovered
        or facts.exit_reason is None
        or not _economics_complete(facts)
    ):
        return "evidence_incomplete"
    if incidents:
        return "recovered_incident"
    return "complete"


def _terminal_sentences(
    facts: ProgrammaticReviewFacts,
    *,
    classification: ExecutionClassification,
    evidence: tuple[EvidenceRef, ...],
) -> tuple[ReviewSentence, ...]:
    review_evidence = _evidence_of_kinds(
        evidence,
        "ticket",
        "event",
        "command",
        "settlement",
        "review",
    )
    if classification == "complete":
        execution = _sentence(
            "execution_complete",
            evidence=review_evidence,
            entry_summary="ENTRY 后初始保护已确认",
            exit_summary=_exit_summary(facts.exit_reason),
        )
        economics = _sentence(
            "economics_complete",
            evidence=_evidence_of_kinds(evidence, "review", "settlement"),
            net_pnl=_required_value(facts.net_pnl, "Net PnL"),
            net_r=_required_value(facts.net_r, "Net R"),
        )
        return execution, economics
    if classification == "recovered_incident":
        incident_evidence = _incident_evidence(evidence, facts.incident_ids)
        execution = _sentence(
            "execution_recovered",
            evidence=incident_evidence,
            incident_summary="、".join(facts.incident_ids),
        )
        economics = _sentence(
            "economics_complete",
            evidence=_evidence_of_kinds(evidence, "review", "settlement"),
            net_pnl=_required_value(facts.net_pnl, "Net PnL"),
            net_r=_required_value(facts.net_r, "Net R"),
        )
        return execution, economics
    return (
        _sentence(
            "economics_incomplete",
            evidence=evidence,
            reason=_incomplete_reason(facts),
        ),
    )


def _economics_complete(facts: ProgrammaticReviewFacts) -> bool:
    return facts.economics_completeness == "complete" and all(
        metric.value is not None and metric.unavailable_reason is None
        for metric in (
            facts.gross_pnl,
            facts.fees,
            facts.funding,
            facts.net_pnl,
            facts.net_r,
        )
    )


def _incomplete_reason(facts: ProgrammaticReviewFacts) -> str:
    if set(facts.incident_ids) != set(facts.recovered_incident_ids):
        return "存在未恢复 Incident"
    if facts.economics_completeness == "funding_unavailable":
        return "Funding 不可归因"
    if facts.economics_completeness == "external_exit_unavailable":
        return "外部平仓成交事实不可获得"
    if not facts.review_complete:
        return "当前 Review 证据不完整"
    if facts.exit_reason is None:
        return "退出原因证据不完整"
    return "关键执行或经济证据不完整"


def _attention_items(facts: ProgrammaticReviewFacts) -> tuple[str, ...]:
    items = [
        f"open_incident:{incident_id}"
        for incident_id in facts.incident_ids
        if incident_id not in set(facts.recovered_incident_ids)
    ]
    if facts.economics_completeness == "funding_unavailable":
        items.append("funding_unavailable")
    elif facts.economics_completeness == "external_exit_unavailable":
        items.append("external_exit_unavailable")
    planned = facts.frozen_initial_stop_risk.value
    actual = facts.actual_stop_risk.value
    if planned is not None and actual is not None and actual > planned:
        items.append("actual_stop_risk_above_frozen_plan")
    runner = facts.runner_net_contribution.value
    if runner is not None and runner <= 0:
        items.append("runner_net_contribution_non_positive")
    return tuple(items)


def _center_economics(
    reviews: tuple[tuple[ReviewCenterItemFacts, ProgrammaticTradeReview], ...],
) -> tuple[MoneyMetric, MoneyMetric, MoneyMetric, MoneyMetric]:
    if not reviews:
        zero_quote = MoneyMetric(value=Decimal(0), unit="USDT")
        return (
            zero_quote,
            MoneyMetric(value=Decimal(0), unit="R"),
            zero_quote,
            zero_quote,
        )
    summaries = tuple(review.economic_summary for _item, review in reviews)
    if any(
        metric.value is None
        for summary in summaries
        for metric in (
            summary.net_pnl,
            summary.net_r,
            summary.fees,
            summary.funding,
        )
    ):
        reason = "incomplete_review_economics"
        return (
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="R", unavailable_reason=reason),
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
        )
    return (
        MoneyMetric(
            value=sum(
                (
                    _required_value(summary.net_pnl, "Net PnL")
                    for summary in summaries
                ),
                Decimal(0),
            ),
            unit="USDT",
        ),
        MoneyMetric(
            value=sum(
                (
                    _required_value(summary.net_r, "Net R")
                    for summary in summaries
                ),
                Decimal(0),
            ),
            unit="R",
        ),
        MoneyMetric(
            value=sum(
                (
                    _required_value(summary.fees, "Fees")
                    for summary in summaries
                ),
                Decimal(0),
            ),
            unit="USDT",
        ),
        MoneyMetric(
            value=sum(
                (
                    _required_value(summary.funding, "Funding")
                    for summary in summaries
                ),
                Decimal(0),
            ),
            unit="USDT",
        ),
    )


def _quality_breakdown(
    reviews: tuple[tuple[ReviewCenterItemFacts, ProgrammaticTradeReview], ...],
) -> tuple[ReviewBreakdownItem, ...]:
    return _breakdown(
        (
            (review.execution_classification, item.review.evidence)
            for item, review in reviews
        )
    )


def _exit_breakdown(
    reviews: tuple[tuple[ReviewCenterItemFacts, ProgrammaticTradeReview], ...],
) -> tuple[ReviewBreakdownItem, ...]:
    return _breakdown(
        (
            (review.exit_reason or "exit_reason_unavailable", item.review.evidence)
            for item, review in reviews
        )
    )


def _breakdown(
    labeled_evidence: Iterable[tuple[str, tuple[EvidenceRef, ...]]],
) -> tuple[ReviewBreakdownItem, ...]:
    counts: Counter[str] = Counter()
    evidence_by_label: defaultdict[str, list[EvidenceRef]] = defaultdict(list)
    for label, evidence in labeled_evidence:
        counts[label] += 1
        evidence_by_label[label].extend(evidence)
    return tuple(
        ReviewBreakdownItem(
            label=label,
            ticket_count=counts[label],
            evidence=_deduplicate_evidence(evidence_by_label[label]),
        )
        for label in sorted(counts)
    )


def _strategy_group_samples(
    reviews: tuple[tuple[ReviewCenterItemFacts, ProgrammaticTradeReview], ...],
    *,
    requested_strategy_group_id: str | None,
) -> tuple[StrategyGroupSampleState, ...]:
    grouped: defaultdict[str, list[EvidenceRef]] = defaultdict(list)
    for item, review in reviews:
        grouped[item.strategy_group_id].extend(review.evidence)
    if not grouped and requested_strategy_group_id is not None:
        return (
            StrategyGroupSampleState(
                strategy_group_id=requested_strategy_group_id,
                sample_count=0,
                evidence_state="no_evidence",
                evidence=(),
            ),
        )
    return tuple(
        StrategyGroupSampleState(
            strategy_group_id=strategy_group_id,
            sample_count=sum(
                item.strategy_group_id == strategy_group_id
                for item, _review in reviews
            ),
            evidence_state="observe_only",
            evidence=_deduplicate_evidence(grouped[strategy_group_id]),
        )
        for strategy_group_id in sorted(grouped)
    )


def _sentence(
    template_id: Literal[
        "execution_complete",
        "execution_recovered",
        "economics_complete",
        "economics_incomplete",
        "review_waiting",
        "ticket_in_progress",
    ],
    *,
    evidence: tuple[EvidenceRef, ...],
    **values: object,
) -> ReviewSentence:
    exact_evidence = evidence
    if not exact_evidence:
        raise ProgrammaticReviewContradiction(
            f"{template_id} sentence requires evidence"
        )
    return ReviewSentence(
        template_id=template_id,
        text=TEMPLATES[template_id].format(**values),
        evidence=exact_evidence,
    )


def _exit_summary(exit_reason: str | None) -> str:
    if exit_reason is None:
        return "退出原因证据不完整"
    return _EXIT_SUMMARIES.get(exit_reason, "退出由明确 Lifecycle 事实触发")


def _required_value(metric: MoneyMetric, label: str) -> Decimal:
    if metric.value is None:
        raise ProgrammaticReviewContradiction(
            f"complete Review lacks {label}"
        )
    return metric.value


def _evidence_of_kinds(
    evidence: tuple[EvidenceRef, ...],
    *kinds: str,
) -> tuple[EvidenceRef, ...]:
    selected = tuple(ref for ref in evidence if ref.kind in kinds)
    return selected or evidence


def _incident_evidence(
    evidence: tuple[EvidenceRef, ...],
    incident_ids: tuple[str, ...],
) -> tuple[EvidenceRef, ...]:
    identities = set(incident_ids)
    return tuple(
        ref
        for ref in evidence
        if ref.kind == "incident" and ref.identity in identities
    )


def _validate_incident_evidence(facts: ProgrammaticReviewFacts) -> None:
    incident_ids = set(facts.incident_ids)
    recovered_ids = set(facts.recovered_incident_ids)
    if not recovered_ids.issubset(incident_ids):
        raise ProgrammaticReviewContradiction(
            "recovered Incident identity is not attached to Ticket"
        )
    evidence_ids = {
        ref.identity for ref in facts.evidence if ref.kind == "incident"
    }
    if not incident_ids.issubset(evidence_ids):
        raise ProgrammaticReviewContradiction(
            "Incident classification lacks exact Incident evidence"
        )


def _validate_review_evidence(facts: ProgrammaticReviewFacts) -> None:
    review_ids = {
        ref.identity for ref in facts.evidence if ref.kind == "review"
    }
    if facts.current_review_id is None:
        if review_ids or facts.review_complete:
            raise ProgrammaticReviewContradiction(
                "current Review evidence identity mismatch"
            )
        return
    if review_ids != {facts.current_review_id}:
        raise ProgrammaticReviewContradiction(
            "current Review evidence identity mismatch"
        )


def _deduplicate_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int]] = set()
    exact: list[EvidenceRef] = []
    for item in evidence:
        key = (item.kind, item.identity, item.occurred_at_ms)
        if key not in seen:
            seen.add(key)
            exact.append(item)
    return tuple(exact)
