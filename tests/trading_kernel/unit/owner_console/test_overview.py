from decimal import Decimal

import pytest

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    Freshness,
    OverviewEvidenceGap,
)
from src.trading_kernel.application.owner_console.overview import (
    build_owner_overview,
)
from tests.trading_kernel.unit.owner_console.factories import overview_facts


def test_overview_never_labels_claim_snapshot_as_realtime_balance() -> None:
    overview = build_owner_overview(
        overview_facts(
            latest_wallet_balance_at_claim=Decimal("100.00"),
            latest_available_margin_at_claim=Decimal("76.00"),
            latest_claim_created_at_ms=1_800_000_000_000,
        ),
        now_ms=1_800_000_010_000,
    )

    assert overview.account_snapshot.label == "Latest Admission Snapshot"
    assert overview.account_snapshot.is_realtime is False
    assert overview.account_snapshot.captured_at_ms == 1_800_000_000_000
    assert overview.account_snapshot.wallet_balance.value == Decimal("100.00")


def test_no_capacity_claim_is_unavailable_instead_of_zero() -> None:
    overview = build_owner_overview(
        overview_facts(
            latest_capacity_claim_id=None,
            latest_wallet_balance_at_claim=None,
            latest_available_margin_at_claim=None,
            latest_claim_created_at_ms=None,
        ),
        now_ms=1_800_000_010_000,
    )

    assert overview.account_snapshot.wallet_balance.value is None
    assert (
        overview.account_snapshot.wallet_balance.unavailable_reason
        == "no_capacity_claim"
    )
    assert overview.account_snapshot.available_margin.value is None
    assert (
        overview.account_snapshot.available_margin.unavailable_reason
        == "no_capacity_claim"
    )


def test_open_owner_incident_wins_over_normal_monitor_rows() -> None:
    facts = overview_facts(
        open_owner_incident_id="incident:1",
        open_owner_incident_opened_at_ms=1_800_000_009_000,
        monitor_statuses=("running", "waiting_for_opportunity"),
    )
    overview = build_owner_overview(facts, now_ms=1_800_000_010_000)

    assert overview.conclusion.level == "intervention"
    assert overview.conclusion.evidence[0].identity == "incident:1"


@pytest.mark.parametrize(
    (
        "overrides",
        "expected_level",
        "expected_evidence_identity",
    ),
    (
        (
            {
                "contradictory_fact_reasons": ("active_ticket_count_mismatch",),
                "contradictory_evidence_identity": "account:binance-usdm:test",
                "monitor_statuses": ("needs_intervention",),
                "monitor_keys": ("monitor:owner",),
            },
            "intervention",
            "account:binance-usdm:test",
        ),
        (
            {
                "monitor_statuses": ("needs_intervention",),
                "monitor_keys": ("monitor:owner",),
                "monitor_updated_at_ms": (1_800_000_009_000,),
                "runtime_freshness": Freshness.STALE,
                "freshness_evidence_identity": "account:binance-usdm:test",
            },
            "intervention",
            "monitor:owner",
        ),
        (
            {
                "runtime_freshness": Freshness.STALE,
                "freshness_evidence_identity": "account:binance-usdm:test",
                "attention_incident_ids": ("incident:attention",),
                "attention_incident_opened_at_ms": (1_800_000_009_000,),
            },
            "attention",
            "account:binance-usdm:test",
        ),
        (
            {
                "attention_incident_ids": ("incident:attention",),
                "attention_incident_opened_at_ms": (1_800_000_009_000,),
                "evidence_gaps": (
                    OverviewEvidenceGap(
                        reason="incomplete_review_economics",
                        evidence=EvidenceRef(
                            kind="review",
                            identity="review:missing-economics",
                            occurred_at_ms=1_800_000_008_000,
                        ),
                    ),
                ),
            },
            "attention",
            "incident:attention",
        ),
        (
            {
                "evidence_gaps": (
                    OverviewEvidenceGap(
                        reason="incomplete_review_economics",
                        evidence=EvidenceRef(
                            kind="review",
                            identity="review:missing-economics",
                            occurred_at_ms=1_800_000_008_000,
                        ),
                    ),
                ),
            },
            "attention",
            "review:missing-economics",
        ),
        ({}, "no_action", "account:binance-usdm:test"),
    ),
)
def test_overview_conclusion_priority_is_deterministic(
    overrides: dict[str, object],
    expected_level: str,
    expected_evidence_identity: str,
) -> None:
    overview = build_owner_overview(
        overview_facts(**overrides),
        now_ms=1_800_000_010_000,
    )

    assert overview.conclusion.level == expected_level
    assert overview.conclusion.evidence[0].identity == expected_evidence_identity


def test_capacity_uses_current_policy_and_exposure_not_claim_snapshot() -> None:
    overview = build_owner_overview(
        overview_facts(
            max_concurrent_tickets=3,
            active_ticket_count=2,
            latest_wallet_balance_at_claim=Decimal("1000000.00"),
            latest_available_margin_at_claim=Decimal("999999.00"),
        ),
        now_ms=1_800_000_010_000,
    )

    assert overview.ticket_capacity == 1
    assert overview.active_ticket_count == 2


def test_first_evidence_gap_keeps_its_matching_boundary_fact() -> None:
    facts = overview_facts(
        evidence_gaps=(
            OverviewEvidenceGap(
                reason="active_ticket_limit_reached",
                evidence=EvidenceRef(
                    kind="ticket",
                    identity="ticket:boundary:21",
                    occurred_at_ms=1_800_000_001_000,
                ),
            ),
            OverviewEvidenceGap(
                reason="monitor_limit_reached",
                evidence=EvidenceRef(
                    kind="event",
                    identity="monitor:boundary:101",
                    occurred_at_ms=1_800_000_000_500,
                ),
            ),
        )
    )

    overview = build_owner_overview(facts, now_ms=1_800_000_010_000)

    assert overview.attention_summary[:2] == (
        "active_ticket_limit_reached",
        "monitor_limit_reached",
    )
    assert overview.conclusion.level == "attention"
    assert overview.conclusion.evidence == (
        EvidenceRef(
            kind="ticket",
            identity="ticket:boundary:21",
            occurred_at_ms=1_800_000_001_000,
        ),
    )
