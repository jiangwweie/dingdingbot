from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    PageCursor,
    SignalDetailFacts,
    SignalFactSnapshotFacts,
    SignalPageFacts,
    decode_cursor,
)
from src.trading_kernel.application.owner_console.signals import (
    SignalFactsContradiction,
    build_signal_detail,
    build_signal_item,
    build_signal_page,
)
from tests.trading_kernel.unit.owner_console.factories import (
    signal_detail_facts,
    signal_item_facts,
)

_REJECTED_SHADOW_BASE = {
    "decision_status": "rejected",
    "first_blocker": "gross_stop_risk_capacity_exhausted",
    "ticket_id": None,
    "shadow_outcome_id": "shadow:1",
}


def test_rejected_signal_has_first_blocker_and_no_ticket_link() -> None:
    item = build_signal_item(
        signal_item_facts(
            decision_status="rejected",
            first_blocker="gross_stop_risk_capacity_exhausted",
            ticket_id=None,
            shadow_outcome_id="shadow:1",
            shadow_status="completed",
            shadow_mfe_r="1.25",
            shadow_mae_r="-0.40",
            shadow_completion_reason="horizon_complete",
            shadow_observed_through_ms=1_800_000_000_000,
            shadow_completed_at_ms=1_800_000_000_000,
        )
    )

    assert item.first_blocker == "gross_stop_risk_capacity_exhausted"
    assert item.ticket_id is None
    assert item.shadow_summary is not None
    assert item.shadow_summary.mfe_r == Decimal("1.25")
    assert item.shadow_summary.mae_r == Decimal("-0.40")


def test_admitted_signal_links_exact_ticket_and_never_uses_shadow_as_execution() -> None:
    item = build_signal_item(
        signal_item_facts(
            decision_status="admitted",
            first_blocker=None,
            ticket_id="ticket:1",
            shadow_outcome_id=None,
            shadow_status=None,
            shadow_completion_reason=None,
        )
    )

    assert item.ticket_id == "ticket:1"
    assert item.shadow_summary is None


def test_not_evaluated_signal_keeps_strategy_observation_without_admission() -> None:
    item = build_signal_item(
        signal_item_facts(
            admission_decision_id=None,
            decision_status="not_evaluated",
            first_blocker=None,
            binding_constraint=None,
            ticket_id=None,
            decided_at_ms=None,
            shadow_outcome_id="shadow:observation:1",
            shadow_source_kind="strategy_observation",
            shadow_evaluation_kind="sor_path_observation_v1",
            shadow_status="completed",
            shadow_mfe_r="1.25",
            shadow_mae_r="0.40",
            shadow_completion_reason="sor_path_observed",
            shadow_observed_through_ms=1_800_000_000_000,
            shadow_completed_at_ms=1_800_000_000_000,
            shadow_first_path="tp1_first",
            shadow_first_path_at_ms=1_800_000_000_000,
            shadow_observed_bar_count=3,
            shadow_spread_bps="2.50",
        )
    )

    assert item.admission_decision_id is None
    assert item.decision_status == "not_evaluated"
    assert item.ticket_id is None
    assert item.shadow_summary is not None
    assert item.shadow_summary.source_kind == "strategy_observation"
    assert item.shadow_summary.first_path == "tp1_first"


def test_admitted_signal_can_retain_strategy_observation_for_comparison() -> None:
    item = build_signal_item(
        signal_item_facts(
            shadow_outcome_id="shadow:observation:1",
            shadow_source_kind="strategy_observation",
            shadow_evaluation_kind="sor_path_observation_v1",
            shadow_status="pending",
        )
    )

    assert item.ticket_id == "ticket:1"
    assert item.shadow_summary is not None
    assert item.shadow_summary.source_kind == "strategy_observation"


def test_signal_page_uses_last_returned_identity_and_excludes_extra_row() -> None:
    facts = SignalPageFacts(
        items=(
            signal_item_facts(
                signal_event_id="signal:z",
                occurred_at_ms=1_800_000_000_000,
            ),
            signal_item_facts(
                signal_event_id="signal:y",
                occurred_at_ms=1_800_000_000_000,
            ),
            signal_item_facts(
                signal_event_id="signal:x",
                occurred_at_ms=1_800_000_000_000,
            ),
        ),
        requested_limit=2,
    )

    page = build_signal_page(facts)

    assert [item.signal_event_id for item in page.items] == [
        "signal:z",
        "signal:y",
    ]
    assert page.next_cursor is not None
    assert decode_cursor(page.next_cursor) == PageCursor(
        sort_ms=1_800_000_000_000,
        identity="signal:y",
    )


def test_signal_detail_keeps_persisted_facts_and_shadow_observational() -> None:
    detail = build_signal_detail(
        signal_detail_facts(
            signal=signal_item_facts(
                decision_status="rejected",
                first_blocker="gross_stop_risk_capacity_exhausted",
                ticket_id=None,
                shadow_outcome_id="shadow:1",
                shadow_status="completed",
                shadow_mfe_r="1.250000000000000001",
                shadow_mae_r="-0.400000000000000001",
                shadow_completion_reason="horizon_complete",
                shadow_observed_through_ms=1_800_000_000_000,
                shadow_completed_at_ms=1_800_000_000_000,
            )
        )
    )

    assert detail.why_no_ticket == "gross_stop_risk_capacity_exhausted"
    assert [fact.fact_definition_id for fact in detail.fact_snapshots] == [
        "fact:condition",
        "fact:reference",
    ]
    assert detail.shadow_summary is not None
    assert detail.shadow_summary.mfe_r == Decimal("1.250000000000000001")
    assert "observation" in detail.shadow_summary.interpretation.lower()
    assert "not execution" in detail.shadow_summary.interpretation.lower()


@pytest.mark.parametrize(
    ("status", "status_facts"),
    (
        (
            "pending",
            {
                "shadow_mfe_r": None,
                "shadow_mae_r": None,
                "shadow_completion_reason": None,
                "shadow_observed_through_ms": None,
                "shadow_completed_at_ms": None,
            },
        ),
        (
            "claimed",
            {
                "shadow_mfe_r": None,
                "shadow_mae_r": None,
                "shadow_completion_reason": None,
                "shadow_observed_through_ms": None,
                "shadow_completed_at_ms": None,
            },
        ),
        (
            "completed",
            {
                "shadow_mfe_r": "1.25",
                "shadow_mae_r": "-0.40",
                "shadow_completion_reason": "horizon_complete",
                "shadow_observed_through_ms": 1_800_000_000_000,
                "shadow_completed_at_ms": 1_800_000_000_000,
            },
        ),
        (
            "unavailable",
            {
                "shadow_mfe_r": None,
                "shadow_mae_r": None,
                "shadow_completion_reason": "market_facts_unavailable",
                "shadow_observed_through_ms": None,
                "shadow_completed_at_ms": 1_800_000_000_000,
            },
        ),
    ),
)
def test_shadow_status_matrix_accepts_only_complete_persisted_shapes(
    status: str,
    status_facts: dict[str, object],
) -> None:
    item = build_signal_item(
        signal_item_facts(
            **_REJECTED_SHADOW_BASE,
            shadow_status=status,
            **status_facts,
        )
    )

    assert item.shadow_summary is not None
    assert item.shadow_summary.status == status
    assert item.shadow_summary.observed_through_ms == status_facts[
        "shadow_observed_through_ms"
    ]


@pytest.mark.parametrize(
    ("status", "invalid_facts"),
    (
        ("pending", {"shadow_completed_at_ms": 1}),
        ("pending", {"shadow_completion_reason": "partial"}),
        ("pending", {"shadow_observed_through_ms": 1}),
        ("pending", {"shadow_mfe_r": "0.1"}),
        ("pending", {"shadow_mae_r": "-0.1"}),
        ("claimed", {"shadow_completed_at_ms": 1}),
        ("claimed", {"shadow_completion_reason": "partial"}),
        ("claimed", {"shadow_observed_through_ms": 1}),
        ("claimed", {"shadow_mfe_r": "0.1"}),
        ("claimed", {"shadow_mae_r": "-0.1"}),
        ("completed", {"shadow_completed_at_ms": None}),
        ("completed", {"shadow_completion_reason": None}),
        ("completed", {"shadow_observed_through_ms": None}),
        ("completed", {"shadow_mfe_r": None}),
        ("completed", {"shadow_mae_r": None}),
        ("unavailable", {"shadow_completed_at_ms": None}),
        ("unavailable", {"shadow_completion_reason": None}),
        ("unavailable", {"shadow_observed_through_ms": 1}),
        ("unavailable", {"shadow_mfe_r": "0.1"}),
        ("unavailable", {"shadow_mae_r": "-0.1"}),
    ),
)
def test_shadow_status_matrix_rejects_partial_observational_evidence(
    status: str,
    invalid_facts: dict[str, object],
) -> None:
    valid_shapes: dict[str, dict[str, object]] = {
        "pending": {
            "shadow_mfe_r": None,
            "shadow_mae_r": None,
            "shadow_completion_reason": None,
            "shadow_observed_through_ms": None,
            "shadow_completed_at_ms": None,
        },
        "claimed": {
            "shadow_mfe_r": None,
            "shadow_mae_r": None,
            "shadow_completion_reason": None,
            "shadow_observed_through_ms": None,
            "shadow_completed_at_ms": None,
        },
        "completed": {
            "shadow_mfe_r": "1.25",
            "shadow_mae_r": "-0.40",
            "shadow_completion_reason": "horizon_complete",
            "shadow_observed_through_ms": 1,
            "shadow_completed_at_ms": 1,
        },
        "unavailable": {
            "shadow_mfe_r": None,
            "shadow_mae_r": None,
            "shadow_completion_reason": "market_facts_unavailable",
            "shadow_observed_through_ms": None,
            "shadow_completed_at_ms": 1,
        },
    }
    valid_facts = valid_shapes[status]

    with pytest.raises(
        SignalFactsContradiction,
        match="Shadow Outcome status shape mismatch",
    ):
        build_signal_item(
            signal_item_facts(
                **_REJECTED_SHADOW_BASE,
                shadow_status=status,
                **(valid_facts | invalid_facts),
            )
        )


def test_signal_detail_rejects_fact_snapshot_identity_mismatch() -> None:
    facts = signal_detail_facts()
    mismatched = facts.model_copy(
        update={
            "fact_snapshots": (
                SignalFactSnapshotFacts(
                    signal_event_id="signal:other",
                    fact_definition_id="fact:condition",
                    role="condition",
                    value=True,
                    satisfied=True,
                    observed_at_ms=1_799_999_800_000,
                    valid_until_ms=1_800_000_100_000,
                    projection_version=1,
                ),
            )
        }
    )

    with pytest.raises(
        SignalFactsContradiction,
        match="fact snapshot signal identity mismatch",
    ):
        build_signal_detail(SignalDetailFacts.model_validate(mismatched))
