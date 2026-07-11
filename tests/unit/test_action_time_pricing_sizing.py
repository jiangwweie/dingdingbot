from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.action_time.pricing_sizing import (
    RISK_RESERVATION_BASIS,
    materialize_action_time_pricing_reference,
    materialize_ticket_sizing_risk_decision,
    sizing_risk_decision_from_budget,
)


NOW_MS = 1_770_001_000_000


def _production_public_values(**fact_overrides: str | None) -> dict:
    facts = {
        "mark_price": "2000",
        "bid_price": "1999.5",
        "ask_price": "2000.5",
        "qty_step": "0.001",
        "min_notional": "5",
    }
    facts.update(fact_overrides)
    return {
        "public_facts_ready": True,
        "mark_price_fresh": True,
        "spread_ok": True,
        "min_notional_ok": True,
        "qty_step_ok": True,
        "facts": facts,
    }


@pytest.mark.parametrize(
    ("side", "expected_price", "expected_kind"),
    [
        ("long", Decimal("2000.5"), "best_ask"),
        ("short", Decimal("1999.5"), "best_bid"),
    ],
)
def test_materializes_side_specific_reference_from_production_public_fact_shape(
    side: str,
    expected_price: Decimal,
    expected_kind: str,
) -> None:
    result = materialize_action_time_pricing_reference(
        side=side,
        source_values=_production_public_values(),
        source_fact_snapshot_id="fact:public:1",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    )

    assert result.blockers == ()
    assert result.reference is not None
    assert result.reference.entry_reference_price == expected_price
    assert result.reference.entry_reference_kind == expected_kind
    assert result.reference.mark_price == Decimal("2000")
    assert result.reference.qty_step == Decimal("0.001")
    assert result.reference.min_notional == Decimal("5")
    assert result.reference.source_fact_snapshot_id == "fact:public:1"


def test_does_not_accept_privileged_top_level_price_aliases() -> None:
    result = materialize_action_time_pricing_reference(
        side="long",
        source_values={
            "last_price": "2000",
            "mark_price": "2000",
            "qty_step": "0.001",
            "min_notional": "5",
        },
        source_fact_snapshot_id="fact:legacy-shape",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    )

    assert result.reference is None
    assert "action_time_public_facts_object_missing" in result.blockers
    assert "action_time_entry_reference_missing:best_ask" in result.blockers


def test_mark_only_data_cannot_substitute_for_executable_side_quote() -> None:
    result = materialize_action_time_pricing_reference(
        side="short",
        source_values=_production_public_values(bid_price=None),
        source_fact_snapshot_id="fact:public:mark-only",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    )

    assert result.reference is None
    assert "action_time_entry_reference_missing:best_bid" in result.blockers


def test_sizing_decision_floors_quantity_once_and_computes_stop_risk() -> None:
    pricing = materialize_action_time_pricing_reference(
        side="long",
        source_values=_production_public_values(
            mark_price="1998",
            bid_price="1999",
            ask_price="2000",
        ),
        source_fact_snapshot_id="fact:public:2",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    ).reference
    assert pricing is not None

    result = materialize_ticket_sizing_risk_decision(
        pricing_reference=pricing,
        target_notional=Decimal("20.9"),
        stop_price=Decimal("1900"),
    )

    assert result.blockers == ()
    assert result.decision is not None
    assert result.decision.raw_qty == Decimal("0.01045")
    assert result.decision.intended_qty == Decimal("0.010")
    assert result.decision.rounded_notional == Decimal("20.000")
    assert result.decision.risk_at_stop == Decimal("1.000")


def test_budget_decision_rejects_step_aligned_quantity_from_a_different_notional() -> None:
    pricing = materialize_action_time_pricing_reference(
        side="long",
        source_values=_production_public_values(
            mark_price="1998",
            bid_price="1999",
            ask_price="2000",
        ),
        source_fact_snapshot_id="fact:public:budget-lineage",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    ).reference
    assert pricing is not None

    result = sizing_risk_decision_from_budget(
        budget={
            "side": "long",
            "target_notional": "20.9",
            "entry_reference_price": "2000",
            "stop_price": "1900",
            "intended_qty": "0.009",
            "risk_at_stop": "0.9",
            "risk_reservation_basis": RISK_RESERVATION_BASIS,
        },
        pricing_reference=pricing,
    )

    assert result.decision is None
    assert (
        "risk_reservation_intended_qty_target_notional_mismatch"
        in result.blockers
    )


def test_budget_decision_rejects_rounded_notional_below_exchange_minimum() -> None:
    pricing = materialize_action_time_pricing_reference(
        side="long",
        source_values=_production_public_values(
            mark_price="1998",
            bid_price="1999",
            ask_price="2000",
        ),
        source_fact_snapshot_id="fact:public:min-notional-lineage",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    ).reference
    assert pricing is not None

    result = sizing_risk_decision_from_budget(
        budget={
            "side": "long",
            "target_notional": "5.1",
            "entry_reference_price": "2000",
            "stop_price": "1900",
            "intended_qty": "0.002",
            "risk_at_stop": "0.2",
            "risk_reservation_basis": RISK_RESERVATION_BASIS,
        },
        pricing_reference=pricing,
    )

    assert result.decision is None
    assert (
        "risk_reservation_rounded_notional_below_exchange_minimum"
        in result.blockers
    )


@pytest.mark.parametrize(
    ("side", "target_notional", "stop_price", "expected_blocker"),
    [
        ("long", Decimal("4"), Decimal("1900"), "risk_reservation_intended_qty_invalid"),
        ("long", Decimal("20"), Decimal("2100"), "risk_reservation_stop_side_not_protective"),
        ("short", Decimal("20"), Decimal("1900"), "risk_reservation_stop_side_not_protective"),
    ],
)
def test_sizing_decision_fails_closed_before_lane(
    side: str,
    target_notional: Decimal,
    stop_price: Decimal,
    expected_blocker: str,
) -> None:
    pricing = materialize_action_time_pricing_reference(
        side=side,
        source_values=_production_public_values(
            mark_price="2000",
            bid_price="2000",
            ask_price="2000",
            qty_step="0.01",
        ),
        source_fact_snapshot_id=f"fact:public:{side}",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 60_000,
        now_ms=NOW_MS,
    ).reference
    assert pricing is not None

    result = materialize_ticket_sizing_risk_decision(
        pricing_reference=pricing,
        target_notional=target_notional,
        stop_price=stop_price,
    )

    assert result.decision is None
    assert expected_blocker in result.blockers
