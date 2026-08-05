from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_console.models import (
    TradeListQuery,
    TradePageFacts,
)
from src.trading_kernel.application.owner_console.trades import (
    TradeFactsContradiction,
    aggregate_stage,
    build_trade_item,
    build_trade_page,
)
from src.trading_kernel.domain.aggregate import AggregateStatus
from tests.trading_kernel.unit.owner_console.factories import trade_item_facts

COMPLETE_METRICS = {
    "economics_completeness": "complete",
    "gross_realized_pnl_quote": "4.0000",
    "trading_fees_quote": "0.4000",
    "funding_quote": "-0.0900",
    "net_pnl_quote": "3.5100",
    "planned_r_multiple": "0.4800",
}


@pytest.mark.parametrize(
    "field_name",
    ("strategy_group_id", "exchange_instrument_id"),
)
def test_trade_filter_ids_use_shared_persisted_identity_bounds(
    field_name: str,
) -> None:
    with pytest.raises(ValidationError):
        TradeListQuery(
            from_ms=0,
            to_ms=1,
            **{field_name: ""},
        )
    with pytest.raises(ValidationError):
        TradeListQuery(
            from_ms=0,
            to_ms=1,
            **{field_name: "x" * 161},
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (AggregateStatus.LEVERAGE_PENDING.value, "entry"),
        (AggregateStatus.ENTRY_OUTCOME_UNKNOWN.value, "entry"),
        (AggregateStatus.PARTIAL_FILL_INCIDENT.value, "entry"),
        (AggregateStatus.PROTECTION_PENDING.value, "protection"),
        (AggregateStatus.POSITION_PROTECTED.value, "protection"),
        (AggregateStatus.TP1_PENDING.value, "tp_runner"),
        (AggregateStatus.RUNNER_PROTECTED.value, "tp_runner"),
        (AggregateStatus.EXIT_PENDING.value, "exit"),
        (AggregateStatus.CONTROLLED_FLATTEN_OUTCOME_UNKNOWN.value, "exit"),
        (AggregateStatus.RECONCILIATION_PENDING.value, "reconciliation"),
        (AggregateStatus.SETTLEMENT_PENDING.value, "reconciliation"),
        (AggregateStatus.REVIEW_PENDING.value, "review"),
        (AggregateStatus.TERMINAL.value, "review"),
    ),
)
def test_aggregate_status_maps_to_one_closed_lifecycle_stage(
    status: str,
    expected: str,
) -> None:
    assert aggregate_stage(status) == expected


def test_unknown_persisted_aggregate_status_is_contradictory() -> None:
    with pytest.raises(
        TradeFactsContradiction,
        match="unknown aggregate status",
    ):
        aggregate_stage("future_status_not_in_current_kernel")


def test_trade_list_uses_aggregate_current_review_pointer() -> None:
    item = build_trade_item(
        trade_item_facts(
            ticket_id="ticket:1",
            aggregate_status="terminal",
            aggregate_review_id="review:2",
            review_id="review:2",
            review_ticket_id="ticket:1",
            review_revision=2,
            review_metrics=COMPLETE_METRICS,
        )
    )

    assert item.review_id == "review:2"
    assert item.review_revision == 2
    assert item.net_pnl.value == Decimal("3.5100")
    assert item.net_r.value == Decimal("0.4800")


def test_review_row_not_owned_by_current_aggregate_pointer_is_contradictory() -> None:
    with pytest.raises(
        TradeFactsContradiction,
        match="current Review identity mismatch",
    ):
        build_trade_item(
            trade_item_facts(
                aggregate_review_id="review:2",
                review_id="review:1",
                review_ticket_id="ticket:1",
                review_revision=1,
                review_metrics=COMPLETE_METRICS,
            )
        )


def test_active_ticket_has_stage_but_no_final_economic_conclusion() -> None:
    item = build_trade_item(
        trade_item_facts(
            ticket_status="issued",
            terminal_at_ms=None,
            aggregate_status="position_protected",
            aggregate_review_id=None,
            review_id=None,
            review_ticket_id=None,
            review_revision=None,
            review_created_at_ms=None,
            review_metrics=None,
        )
    )

    assert item.lifecycle_stage == "protection"
    assert item.review_id is None
    assert item.net_pnl.value is None
    assert item.net_pnl.unavailable_reason == "ticket_active"
    assert item.net_r.unavailable_reason == "ticket_active"


def test_terminal_ticket_without_review_is_explicitly_unavailable() -> None:
    item = build_trade_item(
        trade_item_facts(
            aggregate_review_id=None,
            review_id=None,
            review_ticket_id=None,
            review_revision=None,
            review_created_at_ms=None,
            review_metrics=None,
        )
    )

    assert item.economics_completeness is None
    assert item.net_pnl.unavailable_reason == "review_missing"
    assert item.fees.unavailable_reason == "review_missing"


def test_funding_unavailable_keeps_known_review_values_but_never_invents_zero() -> None:
    item = build_trade_item(
        trade_item_facts(
            review_metrics={
                "economics_completeness": "funding_unavailable",
                "gross_realized_pnl_quote": "4.0000",
                "trading_fees_quote": "0.4000",
                "funding_quote": None,
                "net_pnl_quote": None,
                "planned_r_multiple": None,
                "funding_unavailable_reason": "overlapping_instrument_exposure",
            }
        )
    )

    assert item.economics_completeness == "funding_unavailable"
    assert item.gross_pnl.value == Decimal("4.0000")
    assert item.fees.value == Decimal("0.4000")
    assert item.funding.value is None
    assert item.funding.unavailable_reason == "funding_unavailable"
    assert item.net_pnl.unavailable_reason == "funding_unavailable"
    assert item.net_r.unavailable_reason == "funding_unavailable"


def test_external_exit_unavailable_never_exposes_final_economics() -> None:
    item = build_trade_item(
        trade_item_facts(
            review_metrics={
                "economics_completeness": "external_exit_unavailable",
                "unavailable_reason": "external_flat_exit_fills_unavailable",
                "entry_quantity": "1",
                "entry_time_ms": 1_799_999_910_000,
                "external_flat_detected_at_ms": 1_799_999_990_000,
                "visibility_grace_ms": 60_000,
            }
        )
    )

    assert item.economics_completeness == "external_exit_unavailable"
    assert item.exit_reason == "External Flat / Exit Fills Unavailable"
    assert item.gross_pnl.unavailable_reason == "external_exit_unavailable"
    assert item.net_pnl.unavailable_reason == "external_exit_unavailable"
    assert item.net_r.unavailable_reason == "external_exit_unavailable"


@pytest.mark.parametrize(
    "metrics",
    (
        {**COMPLETE_METRICS, "net_pnl_quote": None},
        {**COMPLETE_METRICS, "net_pnl_quote": 3.51},
        {key: value for key, value in COMPLETE_METRICS.items() if key != "trading_fees_quote"},
        {**COMPLETE_METRICS, "economics_completeness": "future_shape"},
    ),
)
def test_malformed_or_incomplete_review_economics_never_contributes_zero(
    metrics: dict[str, object],
) -> None:
    item = build_trade_item(trade_item_facts(review_metrics=metrics))

    assert item.economics_completeness is None
    assert item.gross_pnl.value is None
    assert item.gross_pnl.unavailable_reason == "incomplete_review_economics"
    assert item.fees.unavailable_reason == "incomplete_review_economics"
    assert item.net_pnl.unavailable_reason == "incomplete_review_economics"


def test_open_incident_identity_is_not_hidden_by_a_newer_resolved_incident() -> None:
    item = build_trade_item(
        trade_item_facts(
            open_incident_id="incident:older-open",
            open_incident_opened_at_ms=1_799_999_920_000,
            latest_incident_id="incident:newer-resolved",
            latest_incident_opened_at_ms=1_799_999_990_000,
        )
    )

    assert item.attention_items == ("open_incident:incident:older-open",)
    assert [ref.identity for ref in item.evidence if ref.kind == "incident"] == [
        "incident:older-open",
        "incident:newer-resolved",
    ]


def test_trade_page_removes_limit_plus_one_and_uses_exact_ticket_cursor() -> None:
    facts = TradePageFacts(
        items=(
            trade_item_facts(
                ticket_id="ticket:z",
                review_ticket_id="ticket:z",
                issued_at_ms=10,
            ),
            trade_item_facts(
                ticket_id="ticket:y",
                review_ticket_id="ticket:y",
                issued_at_ms=10,
            ),
            trade_item_facts(
                ticket_id="ticket:x",
                review_ticket_id="ticket:x",
                issued_at_ms=10,
            ),
        ),
        requested_limit=2,
    )

    page = build_trade_page(facts)

    assert [item.ticket_id for item in page.items] == ["ticket:z", "ticket:y"]
    assert page.next_cursor is not None
