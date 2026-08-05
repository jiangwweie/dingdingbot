from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.application.owner_console.models import (
    ApiEnvelope,
    BoundedWindowQuery,
    ChartAnnotation,
    EvidenceRef,
    Freshness,
    FrozenModel,
    LifecycleStageView,
    MoneyMetric,
    OwnerOverview,
    PageCursor,
    PageFacts,
    ProgrammaticTradeReview,
    ReviewCenterSummary,
    ReviewListQuery,
    SignalAdmissionDetail,
    SignalListItem,
    SignalListQuery,
    TradeCausalityDetail,
    TradeListItem,
    TradeListQuery,
    decode_cursor,
    encode_cursor,
)
from tests.trading_kernel.unit.owner_console.factories import (
    overview_facts,
    programmatic_review_facts,
    signal_item_facts,
    trade_causality_facts,
    trade_item_facts,
)


def test_money_and_evidence_serialize_without_float_conversion() -> None:
    metric = MoneyMetric(value=Decimal("3.5100"), unit="USDT")
    evidence = EvidenceRef(kind="review", identity="review:ticket-1", occurred_at_ms=5)

    assert metric.model_dump(mode="json", exclude_none=True) == {
        "value": "3.5100",
        "unit": "USDT",
    }
    assert evidence.kind == "review"


def test_cursor_round_trip_is_exact_and_rejects_invalid_input() -> None:
    encoded = encode_cursor(PageCursor(sort_ms=1_800_000_000_000, identity="ticket:1"))

    assert encoded == "eyJpZGVudGl0eSI6InRpY2tldDoxIiwic29ydF9tcyI6MTgwMDAwMDAwMDAwMH0"
    assert "=" not in encoded
    assert decode_cursor(encoded) == PageCursor(
        sort_ms=1_800_000_000_000,
        identity="ticket:1",
    )
    for malformed in (
        "not-base64",
        "e30",
        "W10",
        "eyJpZGVudGl0eSI6InRpY2tldDoxIn0",
    ):
        with pytest.raises(ValueError, match="^invalid page cursor$"):
            decode_cursor(malformed)


def test_freshness_values_are_closed() -> None:
    assert [item.value for item in Freshness] == [
        "fresh",
        "stale",
        "unavailable",
        "contradictory",
    ]


@pytest.mark.parametrize("query_type", [SignalListQuery, TradeListQuery, ReviewListQuery])
def test_public_list_queries_enforce_limit_and_ninety_day_window(query_type: type[BoundedWindowQuery]) -> None:
    exact_window = query_type(from_ms=0, to_ms=90 * 86_400_000, limit=100)

    assert exact_window.limit == 100
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        query_type(from_ms=0, to_ms=1, limit=101)
    with pytest.raises(ValidationError, match="time window exceeds 90 days"):
        query_type(from_ms=0, to_ms=90 * 86_400_000 + 1)
    with pytest.raises(ValidationError, match="time window must be increasing"):
        query_type(from_ms=1, to_ms=1)


def test_models_are_frozen_and_reject_extra_fields() -> None:
    metric = MoneyMetric(value=Decimal("1.00"), unit="USDT")

    with pytest.raises(ValidationError, match="frozen"):
        metric.value = Decimal("2.00")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MoneyMetric(value=Decimal("1.00"), unit="USDT", unexpected=True)  # type: ignore[call-arg]


def test_envelope_and_page_facts_keep_typed_immutable_payloads() -> None:
    page = PageFacts[SignalListItem](items=(), next_cursor=None)
    envelope = ApiEnvelope[PageFacts[SignalListItem]](
        snapshot_id="snapshot:1",
        generated_at="2026-08-05T10:42:08+08:00",
        source_watermark="2026-08-05T02:42:06.381Z",
        freshness=Freshness.FRESH,
        data=page,
    )

    assert envelope.model_dump(mode="json") == {
        "snapshot_id": "snapshot:1",
        "generated_at": "2026-08-05T10:42:08+08:00",
        "source_watermark": "2026-08-05T02:42:06.381Z",
        "freshness": "fresh",
        "data": {"items": [], "next_cursor": None},
    }


def test_every_conclusion_bearing_read_model_requires_evidence() -> None:
    conclusion_models: tuple[type[FrozenModel], ...] = (
        OwnerOverview,
        SignalListItem,
        SignalAdmissionDetail,
        TradeListItem,
        TradeCausalityDetail,
        LifecycleStageView,
        ChartAnnotation,
        ProgrammaticTradeReview,
        ReviewCenterSummary,
    )

    assert all("evidence" in model.model_fields for model in conclusion_models)
    assert all(model.model_fields["evidence"].is_required() for model in conclusion_models)


def test_named_factories_return_complete_frozen_facts_and_named_overrides() -> None:
    overview = overview_facts(max_concurrent_tickets=4)
    signal = signal_item_facts(first_blocker="capacity_exhausted", ticket_id=None)
    trade = trade_item_facts(exit_reason="Initial Stop")
    causality = trade_causality_facts(current_stage="exit")
    review = programmatic_review_facts(exit_reason="Controlled Exit")

    assert overview.max_concurrent_tickets == 4
    assert signal.first_blocker == "capacity_exhausted"
    assert trade.exit_reason == "Initial Stop"
    assert causality.current_stage == "exit"
    assert review.exit_reason == "Controlled Exit"
    with pytest.raises(TypeError, match="unknown fact override"):
        overview_facts(not_a_field=True)


def test_named_factories_reject_wrong_typed_overrides() -> None:
    with pytest.raises(ValidationError):
        overview_facts(max_concurrent_tickets="three")


def test_named_factories_normalize_mutable_container_overrides() -> None:
    active_ticket_ids = ["ticket:1"]

    facts = overview_facts(active_ticket_ids=active_ticket_ids)
    active_ticket_ids.append("ticket:2")

    assert facts.active_ticket_ids == ("ticket:1",)
    assert isinstance(facts.active_ticket_ids, tuple)


def test_nested_financial_values_serialize_as_exact_strings() -> None:
    trade = trade_item_facts()

    dumped = trade.model_dump(mode="json")

    assert dumped["net_pnl"]["value"] == "3.5100"
    assert dumped["net_r"]["value"] == "0.4800"
