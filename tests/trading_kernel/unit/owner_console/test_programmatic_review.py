from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    MoneyMetric,
    ReviewCenterFacts,
    ReviewCenterItemFacts,
)
from src.trading_kernel.application.owner_console.programmatic_review import (
    ProgrammaticReviewContradiction,
    build_programmatic_review,
    build_review_center,
)
from tests.trading_kernel.unit.owner_console.factories import (
    programmatic_review_facts,
)


def _metric(
    value: str | None,
    *,
    unit: str = "USDT",
    reason: str | None = None,
) -> MoneyMetric:
    return MoneyMetric(
        value=None if value is None else Decimal(value),
        unit=unit,  # type: ignore[arg-type]
        unavailable_reason=reason,
    )


def _incident_evidence(identity: str, occurred_at_ms: int) -> EvidenceRef:
    return EvidenceRef(
        kind="incident",
        identity=identity,
        occurred_at_ms=occurred_at_ms,
    )


def test_complete_review_uses_fixed_templates_and_exact_evidence() -> None:
    review = build_programmatic_review(programmatic_review_facts())

    assert review.execution_classification == "complete"
    assert review.economic_summary.net_pnl.value == Decimal("3.5100")
    assert review.economic_summary.net_r.value == Decimal("0.4800")
    assert [sentence.template_id for sentence in review.sentences] == [
        "execution_complete",
        "economics_complete",
    ]
    assert review.sentences[0].text == (
        "执行链完整。ENTRY 后初始保护已确认；退出由 TP1 后 Runner EXIT 触发。"
    )
    assert review.sentences[1].text == (
        "Net PnL 为 3.5100 U，Net R 为 0.4800R；"
        "订单、费用、Funding 与 Review 证据完整。"
    )
    assert all(sentence.evidence for sentence in review.sentences)
    assert review.final_conclusion is not None


def test_resolved_incident_is_recovered_and_links_exact_incident() -> None:
    incident_id = "incident:ticket:1:entry-outcome"
    facts = programmatic_review_facts(
        incident_ids=(incident_id,),
        recovered_incident_ids=(incident_id,),
        evidence=(
            *programmatic_review_facts().evidence,
            _incident_evidence(incident_id, 1_799_999_950_000),
        ),
    )

    review = build_programmatic_review(facts)

    assert review.execution_classification == "recovered_incident"
    assert review.sentences[0].template_id == "execution_recovered"
    assert [
        ref.identity
        for ref in review.sentences[0].evidence
        if ref.kind == "incident"
    ] == [incident_id]


def test_open_incident_keeps_terminal_review_evidence_incomplete() -> None:
    incident_id = "incident:ticket:1:open"
    review = build_programmatic_review(
        programmatic_review_facts(
            incident_ids=(incident_id,),
            recovered_incident_ids=(),
            evidence=(
                *programmatic_review_facts().evidence,
                _incident_evidence(incident_id, 1_799_999_950_000),
            ),
        )
    )

    assert review.execution_classification == "evidence_incomplete"
    assert review.final_conclusion is not None
    assert "Incident" in review.final_conclusion


def test_funding_unavailable_does_not_become_zero_or_net_r() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(
            economics_completeness="funding_unavailable",
            funding=_metric(None, reason="funding_unavailable"),
            net_pnl=_metric(None, reason="funding_unavailable"),
            net_r=_metric(None, unit="R", reason="funding_unavailable"),
        )
    )

    assert review.execution_classification == "evidence_incomplete"
    assert review.economic_summary.funding.value is None
    assert review.economic_summary.net_pnl.value is None
    assert review.economic_summary.net_r.value is None
    assert review.sentences[-1].template_id == "economics_incomplete"
    assert "0" not in review.sentences[-1].text


def test_external_exit_unavailable_never_builds_final_economics() -> None:
    unavailable = _metric(None, reason="external_exit_unavailable")
    review = build_programmatic_review(
        programmatic_review_facts(
            economics_completeness="external_exit_unavailable",
            gross_pnl=unavailable,
            fees=unavailable,
            funding=unavailable,
            net_pnl=unavailable,
            net_r=_metric(
                None,
                unit="R",
                reason="external_exit_unavailable",
            ),
            exit_reason="External Flat / Exit Fills Unavailable",
        )
    )

    assert review.execution_classification == "evidence_incomplete"
    assert review.economic_summary.net_pnl.value is None
    assert "外部平仓成交事实不可获得" in review.sentences[-1].text


def test_active_ticket_has_progress_summary_not_final_review() -> None:
    ticket_evidence = (programmatic_review_facts().evidence[0],)
    review = build_programmatic_review(
        programmatic_review_facts(
            ticket_status="issued",
            aggregate_status="position_protected",
            lifecycle_stage="protection",
            settlement_completed=False,
            current_review_id=None,
            review_complete=False,
            evidence=ticket_evidence,
        )
    )

    assert review.execution_classification == "in_progress"
    assert review.sentences[0].template_id == "ticket_in_progress"
    assert review.final_conclusion is None


def test_terminal_ticket_without_current_review_waits_for_review() -> None:
    ticket_evidence = (programmatic_review_facts().evidence[0],)
    review = build_programmatic_review(
        programmatic_review_facts(
            current_review_id=None,
            review_complete=False,
            evidence=ticket_evidence,
        )
    )

    assert review.execution_classification == "waiting_review"
    assert review.sentences[0].template_id == "review_waiting"
    assert review.final_conclusion == "Ticket 已终态，当前仍在等待 Review。"


def test_current_review_requires_the_exact_review_evidence_identity() -> None:
    with pytest.raises(
        ProgrammaticReviewContradiction,
        match="current Review evidence identity mismatch",
    ):
        build_programmatic_review(
            programmatic_review_facts(
                current_review_id="review:current",
                evidence=(
                    programmatic_review_facts().evidence[0],
                    EvidenceRef(
                        kind="review",
                        identity="review:stale",
                        occurred_at_ms=1_800_000_000_000,
                    ),
                ),
            )
        )


def test_missing_exit_reason_keeps_execution_evidence_incomplete() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(exit_reason=None)
    )

    assert review.execution_classification == "evidence_incomplete"
    assert "退出原因证据不完整" in review.final_conclusion


def test_malformed_review_economics_has_its_own_incomplete_state() -> None:
    review = build_programmatic_review(
        programmatic_review_facts(
            economics_completeness="incomplete_evidence",
            gross_pnl=_metric(None, reason="incomplete_review_economics"),
            fees=_metric(None, reason="incomplete_review_economics"),
            funding=_metric(None, reason="incomplete_review_economics"),
            net_pnl=_metric(None, reason="incomplete_review_economics"),
            net_r=_metric(
                None,
                unit="R",
                reason="incomplete_review_economics",
            ),
        )
    )

    assert review.execution_classification == "evidence_incomplete"
    assert "关键执行或经济证据不完整" in review.final_conclusion


def test_review_center_is_bounded_observe_only_and_never_ranks() -> None:
    facts = ReviewCenterFacts(
        from_ms=1_799_999_000_000,
        to_ms=1_800_001_000_000,
        items=(
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:alpha",
                terminal_at_ms=1_800_000_000_000,
                review=programmatic_review_facts(ticket_id="ticket:z"),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:alpha",
                terminal_at_ms=1_799_999_999_000,
                review=programmatic_review_facts(ticket_id="ticket:y"),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:beta",
                terminal_at_ms=1_799_999_998_000,
                review=programmatic_review_facts(ticket_id="ticket:x"),
            ),
        ),
        requested_limit=2,
        requested_strategy_group_id=None,
    )

    center = build_review_center(facts)

    assert center.sample_count == 2
    assert center.next_cursor is not None
    assert center.net_pnl.value == Decimal("7.0200")
    assert center.strategy_group_samples[0].sample_count == 2
    assert center.strategy_group_samples[0].evidence_state == "observe_only"
    dumped = center.model_dump(mode="json")
    assert not {"rank", "score", "recommendation", "sample_warning"}.intersection(
        dumped
    )


def test_incomplete_center_economics_never_contributes_as_zero() -> None:
    facts = ReviewCenterFacts(
        from_ms=1_799_999_000_000,
        to_ms=1_800_001_000_000,
        items=(
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:alpha",
                terminal_at_ms=1_800_000_000_000,
                review=programmatic_review_facts(),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:beta",
                terminal_at_ms=1_799_999_999_000,
                review=programmatic_review_facts(
                    economics_completeness="funding_unavailable",
                    funding=_metric(None, reason="funding_unavailable"),
                    net_pnl=_metric(None, reason="funding_unavailable"),
                    net_r=_metric(
                        None,
                        unit="R",
                        reason="funding_unavailable",
                    ),
                ),
            ),
        ),
        requested_limit=2,
        requested_strategy_group_id=None,
    )

    center = build_review_center(facts)

    assert center.net_pnl.value is None
    assert center.net_r.value is None
    assert center.funding.value is None
    assert center.incomplete_review_count == 1
