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
    ReviewCenterItem,
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
    _validate_active_shape(facts)
    _validate_incident_evidence(facts)
    _validate_review_evidence(facts)
    _validate_exact_evidence(facts, evidence=evidence)
    _validate_lifecycle_conclusions(facts)
    _validate_economics_shape(facts)
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
            evidence=_ticket_aggregate_evidence(facts),
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
            evidence=_ticket_aggregate_evidence(facts),
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


def matches_review_status(
    review: ProgrammaticTradeReview,
    requested_status: str | None,
) -> bool:
    """Apply the sole Review Center status mapping after classification."""

    if requested_status is None:
        return True
    if requested_status == "in_progress":
        return review.execution_classification == "in_progress"
    if requested_status == "waiting_for_settlement":
        return False
    if requested_status == "waiting_for_review":
        return review.execution_classification == "waiting_review"
    if requested_status == "complete":
        return review.execution_classification in {
            "complete",
            "recovered_incident",
        }
    if requested_status == "incomplete_evidence":
        return review.execution_classification == "evidence_incomplete"
    raise ProgrammaticReviewContradiction(
        f"unknown Review status filter: {requested_status}"
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
        items=tuple(
            ReviewCenterItem(
                ticket_id=review.ticket_id,
                strategy_group_id=item.strategy_group_id,
                exchange_instrument_id=item.exchange_instrument_id,
                position_side=item.position_side,
                terminal_at_ms=item.terminal_at_ms,
                review=review,
            )
            for item, review in reviews
        ),
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
        ref is not None
        for ref in (
            facts.entry_fill_evidence,
            facts.protection_confirmed_evidence,
            facts.exit_trigger_evidence,
            facts.flat_evidence,
            facts.reconciliation_matched_evidence,
            facts.settlement_evidence,
        )
    )
    incidents = set(facts.incident_ids)
    recovered = set(facts.recovered_incident_ids)
    incidents_recovered = incidents == recovered
    if (
        not chain_complete
        or not incidents_recovered
        or facts.exit_reason is None
        or facts.current_review_evidence is None
        or facts.economics_completeness != "complete"
    ):
        return "evidence_incomplete"
    if incidents:
        return "recovered_incident"
    return "complete"


def _terminal_sentences(
    facts: ProgrammaticReviewFacts,
    *,
    classification: ExecutionClassification,
) -> tuple[ReviewSentence, ...]:
    lifecycle_evidence = _lifecycle_evidence(facts)
    if classification == "complete":
        execution = _sentence(
            "execution_complete",
            evidence=lifecycle_evidence,
            entry_summary="ENTRY 后初始保护已确认",
            exit_summary=_exit_summary(facts.exit_reason),
        )
        economics = _sentence(
            "economics_complete",
            evidence=_current_review_evidence(facts),
            net_pnl=_required_value(facts.net_pnl, "Net PnL"),
            net_r=_required_value(facts.net_r, "Net R"),
        )
        return execution, economics
    if classification == "recovered_incident":
        execution = _sentence(
            "execution_recovered",
            evidence=(*lifecycle_evidence, *facts.incident_evidence),
            incident_summary="、".join(facts.incident_ids),
        )
        economics = _sentence(
            "economics_complete",
            evidence=_current_review_evidence(facts),
            net_pnl=_required_value(facts.net_pnl, "Net PnL"),
            net_r=_required_value(facts.net_r, "Net R"),
        )
        return execution, economics
    return (
        _sentence(
            "economics_incomplete",
            evidence=_incomplete_evidence(facts),
            reason=_incomplete_reason(facts),
        ),
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
        reason = "no_review_evidence"
        return (
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="R", unavailable_reason=reason),
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
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


def _validate_active_shape(facts: ProgrammaticReviewFacts) -> None:
    if facts.aggregate_status == "terminal":
        if facts.ticket_status != "terminal":
            raise ProgrammaticReviewContradiction(
                "terminal Aggregate requires terminal Ticket"
            )
        return
    if (
        facts.ticket_status == "terminal"
        or facts.settlement_completed
        or facts.settlement_evidence is not None
        or facts.current_review_id is not None
        or facts.current_review_evidence is not None
        or facts.review_complete
        or facts.economics_completeness == "complete"
    ):
        raise ProgrammaticReviewContradiction(
            "active Ticket contains terminal-only facts"
        )


def _validate_exact_evidence(
    facts: ProgrammaticReviewFacts,
    *,
    evidence: tuple[EvidenceRef, ...],
) -> None:
    required_core = (
        (facts.ticket_evidence, "ticket", facts.ticket_id, "Ticket"),
        (facts.aggregate_evidence, "aggregate", facts.ticket_id, "Aggregate"),
    )
    for ref, kind, identity, label in required_core:
        if ref is None or ref.kind != kind or ref.identity != identity:
            raise ProgrammaticReviewContradiction(
                f"{label} evidence identity mismatch"
            )

    typed_refs = (
        (facts.entry_fill_evidence, "event", "ENTRY fill"),
        (facts.protection_confirmed_evidence, "event", "protection"),
        (facts.exit_trigger_evidence, "event", "exit trigger"),
        (facts.flat_evidence, "event", "flat"),
        (
            facts.reconciliation_matched_evidence,
            "event",
            "reconciliation",
        ),
        (facts.settlement_evidence, "settlement", "settlement"),
        (facts.current_review_evidence, "review", "current Review"),
    )
    for ref, kind, label in typed_refs:
        if ref is not None and ref.kind != kind:
            raise ProgrammaticReviewContradiction(
                f"{label} evidence kind mismatch"
            )
    for ref in facts.incident_evidence:
        if ref.kind != "incident":
            raise ProgrammaticReviewContradiction(
                "Incident evidence kind mismatch"
            )

    evidence_keys = {
        (ref.kind, ref.identity, ref.occurred_at_ms) for ref in evidence
    }
    explicit_refs = (
        facts.ticket_evidence,
        facts.aggregate_evidence,
        facts.entry_fill_evidence,
        facts.protection_confirmed_evidence,
        facts.exit_trigger_evidence,
        facts.flat_evidence,
        facts.reconciliation_matched_evidence,
        facts.settlement_evidence,
        facts.current_review_evidence,
        *facts.incident_evidence,
    )
    if any(
        ref is not None
        and (ref.kind, ref.identity, ref.occurred_at_ms) not in evidence_keys
        for ref in explicit_refs
    ):
        raise ProgrammaticReviewContradiction(
            "exact claim evidence is absent from Review evidence"
        )


def _validate_lifecycle_conclusions(facts: ProgrammaticReviewFacts) -> None:
    contradictions = (
        (not facts.entry_complete and facts.entry_fill_evidence is not None),
        (
            not facts.protection_complete
            and facts.protection_confirmed_evidence is not None
        ),
        (
            not facts.exit_complete
            and facts.exit_trigger_evidence is not None
            and facts.flat_evidence is not None
        ),
        (
            not facts.reconciliation_complete
            and facts.reconciliation_matched_evidence is not None
        ),
        (
            not facts.settlement_completed
            and facts.settlement_evidence is not None
        ),
        (
            not facts.review_complete
            and facts.current_review_evidence is not None
        ),
    )
    if any(contradictions):
        raise ProgrammaticReviewContradiction(
            "lifecycle conclusion contradicts exact evidence"
        )


def _validate_economics_shape(facts: ProgrammaticReviewFacts) -> None:
    metrics = (
        facts.gross_pnl,
        facts.fees,
        facts.funding,
        facts.net_pnl,
        facts.net_r,
    )
    completeness = facts.economics_completeness
    if completeness == "complete":
        valid = all(
            metric.value is not None
            and metric.value.is_finite()
            and metric.unavailable_reason is None
            for metric in metrics
        )
    elif completeness == "funding_unavailable":
        valid = all(
            metric.value is not None
            and metric.value.is_finite()
            and metric.unavailable_reason is None
            for metric in metrics[:2]
        ) and all(
            metric.value is None
            and metric.unavailable_reason == "funding_unavailable"
            for metric in metrics[2:]
        )
    elif completeness == "external_exit_unavailable":
        valid = all(
            metric.value is None
            and metric.unavailable_reason == "external_exit_unavailable"
            for metric in metrics
        )
    else:
        allowed_reasons = {
            "incomplete_review_economics",
            "review_missing",
            "ticket_active",
        }
        valid = all(
            metric.value is None
            and metric.unavailable_reason in allowed_reasons
            for metric in metrics
        ) and len({metric.unavailable_reason for metric in metrics}) == 1
    if not valid:
        raise ProgrammaticReviewContradiction(
            f"invalid {completeness} economics shape"
        )


def _lifecycle_evidence(
    facts: ProgrammaticReviewFacts,
) -> tuple[EvidenceRef, ...]:
    return tuple(
        ref
        for ref in (
            facts.entry_fill_evidence,
            facts.protection_confirmed_evidence,
            facts.exit_trigger_evidence,
            facts.flat_evidence,
            facts.reconciliation_matched_evidence,
            facts.settlement_evidence,
        )
        if ref is not None
    )


def _ticket_aggregate_evidence(
    facts: ProgrammaticReviewFacts,
) -> tuple[EvidenceRef, ...]:
    return tuple(
        ref
        for ref in (facts.ticket_evidence, facts.aggregate_evidence)
        if ref is not None
    )


def _current_review_evidence(
    facts: ProgrammaticReviewFacts,
) -> tuple[EvidenceRef, ...]:
    if facts.current_review_evidence is None:
        return ()
    return (facts.current_review_evidence,)


def _incomplete_evidence(
    facts: ProgrammaticReviewFacts,
) -> tuple[EvidenceRef, ...]:
    open_incident_ids = set(facts.incident_ids) - set(
        facts.recovered_incident_ids
    )
    if open_incident_ids:
        return tuple(
            ref
            for ref in facts.incident_evidence
            if ref.identity in open_incident_ids
        )
    if facts.economics_completeness != "complete":
        return _current_review_evidence(facts)
    if facts.exit_reason is None and facts.exit_trigger_evidence is not None:
        return (facts.exit_trigger_evidence,)
    lifecycle = _lifecycle_evidence(facts)
    return lifecycle or _ticket_aggregate_evidence(facts)


def _validate_incident_evidence(facts: ProgrammaticReviewFacts) -> None:
    incident_ids = set(facts.incident_ids)
    recovered_ids = set(facts.recovered_incident_ids)
    if not recovered_ids.issubset(incident_ids):
        raise ProgrammaticReviewContradiction(
            "recovered Incident identity is not attached to Ticket"
        )
    explicit_ids = {ref.identity for ref in facts.incident_evidence}
    if incident_ids != explicit_ids:
        raise ProgrammaticReviewContradiction(
            "Incident classification lacks exact Incident evidence"
        )


def _validate_review_evidence(facts: ProgrammaticReviewFacts) -> None:
    if facts.current_review_id is None:
        if facts.current_review_evidence is not None or facts.review_complete:
            raise ProgrammaticReviewContradiction(
                "current Review evidence identity mismatch"
            )
        return
    if (
        facts.current_review_evidence is None
        or facts.current_review_evidence.identity != facts.current_review_id
        or not facts.review_complete
    ):
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
