from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    MoneyMetric,
    ProgrammaticReviewFacts,
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


def _ref(kind: str, identity: str, occurred_at_ms: int) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,  # type: ignore[arg-type]
        identity=identity,
        occurred_at_ms=occurred_at_ms,
    )


_TICKET = _ref("ticket", "ticket:1", 1_799_999_900_000)
_AGGREGATE = _ref("aggregate", "ticket:1", 1_800_000_000_000)
_ENTRY = _ref("event", "event:entry-filled", 1_799_999_920_000)
_PARTIAL_ENTRY = _ref(
    "event",
    "event:entry-partially-filled",
    1_799_999_920_000,
)
_PROTECTION = _ref(
    "event",
    "event:initial-stop-confirmed",
    1_799_999_930_000,
)
_EXIT = _ref("event", "event:exit-requested", 1_799_999_970_000)
_FLAT = _ref("event", "event:position-flat-confirmed", 1_799_999_980_000)
_RECONCILIATION = _ref(
    "event",
    "event:reconciliation-matched",
    1_799_999_985_000,
)
_SETTLEMENT = _ref("settlement", "event:budget-settled", 1_799_999_990_000)
_REVIEW = _ref("review", "review:1", 1_800_000_000_000)
_LIFECYCLE_REFS = (
    _ENTRY,
    _PROTECTION,
    _EXIT,
    _FLAT,
    _RECONCILIATION,
    _SETTLEMENT,
)


def _facts(**overrides: object) -> ProgrammaticReviewFacts:
    base = programmatic_review_facts()
    values = base.model_dump(mode="python")
    ticket_id = str(overrides.get("ticket_id", base.ticket_id))
    ticket = _ref("ticket", ticket_id, _TICKET.occurred_at_ms)
    aggregate = _ref("aggregate", ticket_id, _AGGREGATE.occurred_at_ms)
    values.update(
        {
            "ticket_evidence": ticket,
            "aggregate_evidence": aggregate,
            "entry_fill_evidence": _ENTRY,
            "protection_confirmed_evidence": _PROTECTION,
            "exit_trigger_evidence": _EXIT,
            "flat_evidence": _FLAT,
            "reconciliation_matched_evidence": _RECONCILIATION,
            "settlement_evidence": _SETTLEMENT,
            "current_review_evidence": _REVIEW,
            "incident_evidence": (),
            "evidence": (
                ticket,
                aggregate,
                *_LIFECYCLE_REFS,
                _REVIEW,
            ),
        }
    )
    values.update(overrides)
    return ProgrammaticReviewFacts.model_validate(values)


def _unavailable_economics(reason: str) -> dict[str, object]:
    return {
        "economics_completeness": "incomplete_evidence",
        "gross_pnl": _metric(None, reason=reason),
        "fees": _metric(None, reason=reason),
        "funding": _metric(None, reason=reason),
        "net_pnl": _metric(None, reason=reason),
        "net_r": _metric(None, unit="R", reason=reason),
    }


def test_complete_review_uses_only_exact_claim_evidence() -> None:
    review = build_programmatic_review(_facts())

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
    assert review.sentences[0].evidence == _LIFECYCLE_REFS
    assert review.sentences[1].evidence == (_REVIEW,)


@pytest.mark.parametrize(
    ("missing_field", "missing_identity"),
    (
        ("entry_fill_evidence", "event:entry-filled"),
        ("protection_confirmed_evidence", "event:initial-stop-confirmed"),
        ("exit_trigger_evidence", "event:exit-requested"),
        ("flat_evidence", "event:position-flat-confirmed"),
        ("reconciliation_matched_evidence", "event:reconciliation-matched"),
        ("settlement_evidence", "event:budget-settled"),
    ),
)
def test_missing_positive_lifecycle_proof_is_evidence_incomplete(
    missing_field: str,
    missing_identity: str,
) -> None:
    facts = _facts(
        **{
            missing_field: None,
            "evidence": tuple(
                ref
                for ref in (_TICKET, _AGGREGATE, *_LIFECYCLE_REFS, _REVIEW)
                if ref.identity != missing_identity
            ),
        }
    )

    review = build_programmatic_review(facts)

    assert review.execution_classification == "evidence_incomplete"
    assert review.sentences[0].template_id == "economics_incomplete"


def test_partial_fill_without_incident_cannot_replace_entry_filled_proof() -> None:
    review = build_programmatic_review(
        _facts(
            entry_fill_evidence=None,
            evidence=(
                _TICKET,
                _AGGREGATE,
                _PARTIAL_ENTRY,
                *_LIFECYCLE_REFS[1:],
                _REVIEW,
            ),
        )
    )

    assert review.execution_classification == "evidence_incomplete"


def test_resolved_partial_fill_incident_remains_entry_evidence_incomplete() -> None:
    incident_id = "incident:ticket:1:unsupported-partial-entry-fill"
    incident = _ref("incident", incident_id, 1_799_999_925_000)
    review = build_programmatic_review(
        _facts(
            entry_fill_evidence=None,
            incident_ids=(incident_id,),
            recovered_incident_ids=(incident_id,),
            incident_evidence=(incident,),
            evidence=(
                _TICKET,
                _AGGREGATE,
                _PARTIAL_ENTRY,
                *_LIFECYCLE_REFS[1:],
                incident,
                _REVIEW,
            ),
        )
    )

    assert review.execution_classification == "evidence_incomplete"


def test_resolved_incident_uses_exact_lifecycle_and_incident_evidence() -> None:
    incident_id = "incident:ticket:1:entry-outcome"
    incident = _ref("incident", incident_id, 1_799_999_950_000)
    review = build_programmatic_review(
        _facts(
            incident_ids=(incident_id,),
            recovered_incident_ids=(incident_id,),
            incident_evidence=(incident,),
            evidence=(
                _TICKET,
                _AGGREGATE,
                *_LIFECYCLE_REFS,
                incident,
                _REVIEW,
            ),
        )
    )

    assert review.execution_classification == "recovered_incident"
    assert review.sentences[0].evidence == (*_LIFECYCLE_REFS, incident)


def test_open_incident_incomplete_sentence_uses_only_open_incident() -> None:
    incident_id = "incident:ticket:1:open"
    incident = _ref("incident", incident_id, 1_799_999_950_000)
    review = build_programmatic_review(
        _facts(
            incident_ids=(incident_id,),
            recovered_incident_ids=(),
            incident_evidence=(incident,),
            evidence=(
                _TICKET,
                _AGGREGATE,
                *_LIFECYCLE_REFS,
                incident,
                _REVIEW,
            ),
        )
    )

    assert review.execution_classification == "evidence_incomplete"
    assert review.sentences[0].evidence == (incident,)


def test_funding_unavailable_does_not_become_zero_or_net_r() -> None:
    review = build_programmatic_review(
        _facts(
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
    assert review.sentences[-1].evidence == (_REVIEW,)
    assert "0" not in review.sentences[-1].text


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "economics_completeness": "funding_unavailable",
            "funding": _metric(None, reason="funding_unavailable"),
            "net_pnl": _metric("3.51"),
            "net_r": _metric(None, unit="R", reason="funding_unavailable"),
        },
        {
            "economics_completeness": "external_exit_unavailable",
            "gross_pnl": _metric("4.00"),
            "fees": _metric(None, reason="external_exit_unavailable"),
            "funding": _metric(None, reason="external_exit_unavailable"),
            "net_pnl": _metric(None, reason="external_exit_unavailable"),
            "net_r": _metric(
                None,
                unit="R",
                reason="external_exit_unavailable",
            ),
        },
        {
            **_unavailable_economics("incomplete_review_economics"),
            "net_r": _metric("0.48", unit="R"),
        },
    ),
)
def test_unavailable_economic_shapes_reject_dependent_numeric_values(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(
        ProgrammaticReviewContradiction,
        match="economics shape",
    ):
        build_programmatic_review(_facts(**overrides))


def test_external_exit_unavailable_never_builds_final_economics() -> None:
    unavailable = _metric(None, reason="external_exit_unavailable")
    review = build_programmatic_review(
        _facts(
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
    assert review.sentences[-1].evidence == (_REVIEW,)


@pytest.mark.parametrize(
    "contradictory_overrides",
    (
        {"ticket_status": "terminal"},
        {"current_review_id": "review:1", "current_review_evidence": _REVIEW},
        {"settlement_completed": True, "settlement_evidence": _SETTLEMENT},
        {},
    ),
)
def test_active_ticket_rejects_terminal_only_shapes(
    contradictory_overrides: dict[str, object],
) -> None:
    active = {
        "ticket_status": "issued",
        "aggregate_status": "position_protected",
        "lifecycle_stage": "protection",
        "settlement_completed": False,
        "current_review_id": None,
        "entry_complete": True,
        "protection_complete": True,
        "exit_complete": False,
        "reconciliation_complete": False,
        "review_complete": False,
        "entry_fill_evidence": _ENTRY,
        "protection_confirmed_evidence": _PROTECTION,
        "exit_trigger_evidence": None,
        "flat_evidence": None,
        "reconciliation_matched_evidence": None,
        "settlement_evidence": None,
        "current_review_evidence": None,
        "evidence": (_TICKET, _AGGREGATE, _ENTRY, _PROTECTION),
        **_unavailable_economics("ticket_active"),
    }
    active.update(contradictory_overrides)
    if not contradictory_overrides:
        active.update(
            {
                "economics_completeness": "complete",
                "gross_pnl": _metric("4"),
                "fees": _metric("0.4"),
                "funding": _metric("-0.09"),
                "net_pnl": _metric("3.51"),
                "net_r": _metric("0.48", unit="R"),
            }
        )

    with pytest.raises(ProgrammaticReviewContradiction, match="active Ticket"):
        build_programmatic_review(_facts(**active))


def test_active_ticket_has_progress_summary_with_aggregate_evidence_only() -> None:
    review = build_programmatic_review(
        _facts(
            ticket_status="issued",
            aggregate_status="position_protected",
            lifecycle_stage="protection",
            settlement_completed=False,
            current_review_id=None,
            entry_complete=True,
            protection_complete=True,
            exit_complete=False,
            reconciliation_complete=False,
            review_complete=False,
            exit_trigger_evidence=None,
            flat_evidence=None,
            reconciliation_matched_evidence=None,
            settlement_evidence=None,
            current_review_evidence=None,
            evidence=(_TICKET, _AGGREGATE, _ENTRY, _PROTECTION),
            **_unavailable_economics("ticket_active"),
        )
    )

    assert review.execution_classification == "in_progress"
    assert review.sentences[0].evidence == (_TICKET, _AGGREGATE)
    assert review.final_conclusion is None


def test_terminal_ticket_without_aggregate_review_pointer_waits() -> None:
    review = build_programmatic_review(
        _facts(
            current_review_id=None,
            review_complete=False,
            current_review_evidence=None,
            evidence=(_TICKET, _AGGREGATE, *_LIFECYCLE_REFS),
            **_unavailable_economics("review_missing"),
        )
    )

    assert review.execution_classification == "waiting_review"
    assert review.sentences[0].evidence == (_TICKET, _AGGREGATE)


def test_current_review_requires_the_exact_review_evidence_identity() -> None:
    with pytest.raises(
        ProgrammaticReviewContradiction,
        match="current Review evidence identity mismatch",
    ):
        build_programmatic_review(
            _facts(
                current_review_id="review:current",
                current_review_evidence=_ref(
                    "review",
                    "review:stale",
                    1_800_000_000_000,
                ),
            )
        )


def test_missing_exit_reason_keeps_execution_evidence_incomplete() -> None:
    review = build_programmatic_review(_facts(exit_reason=None))

    assert review.execution_classification == "evidence_incomplete"
    assert "退出原因证据不完整" in review.final_conclusion


def test_review_center_is_bounded_observe_only_and_never_ranks() -> None:
    facts = ReviewCenterFacts(
        from_ms=1_799_999_000_000,
        to_ms=1_800_001_000_000,
        items=(
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:alpha",
                exchange_instrument_id="BTCUSDT",
                position_side="long",
                terminal_at_ms=1_800_000_000_000,
                review=_facts(ticket_id="ticket:z"),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:alpha",
                exchange_instrument_id="ETHUSDT",
                position_side="short",
                terminal_at_ms=1_799_999_999_000,
                review=_facts(ticket_id="ticket:y"),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:beta",
                exchange_instrument_id="BNBUSDT",
                position_side="long",
                terminal_at_ms=1_799_999_998_000,
                review=_facts(ticket_id="ticket:x"),
            ),
        ),
        requested_limit=2,
        requested_strategy_group_id=None,
    )

    center = build_review_center(facts)

    assert center.sample_count == 2
    assert center.next_cursor is not None
    assert [item.ticket_id for item in center.items] == ["ticket:z", "ticket:y"]
    assert center.items[0].exchange_instrument_id == "BTCUSDT"
    assert center.items[0].position_side == "long"
    assert center.items[0].strategy_group_id == "strategy-group:alpha"
    assert center.items[0].review.sentences[0].text.startswith("执行链完整")
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
                exchange_instrument_id="BTCUSDT",
                position_side="long",
                terminal_at_ms=1_800_000_000_000,
                review=_facts(),
            ),
            ReviewCenterItemFacts(
                strategy_group_id="strategy-group:beta",
                exchange_instrument_id="ETHUSDT",
                position_side="short",
                terminal_at_ms=1_799_999_999_000,
                review=_facts(
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


def test_empty_review_center_is_no_evidence_not_computed_zero() -> None:
    center = build_review_center(
        ReviewCenterFacts(
            from_ms=1_799_999_000_000,
            to_ms=1_800_001_000_000,
            items=(),
            requested_limit=50,
            requested_strategy_group_id="strategy-group:alpha",
        )
    )

    assert center.net_pnl.value is None
    assert center.net_pnl.unavailable_reason == "no_review_evidence"
    assert center.net_r.value is None
    assert center.fees.value is None
    assert center.funding.value is None
    assert center.strategy_group_samples[0].evidence_state == "no_evidence"
