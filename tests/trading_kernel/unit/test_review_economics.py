from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.review import (
    ReviewEconomicsCompleteness,
    ReviewEconomicsFacts,
    ReviewEconomicsUnavailable,
    ReviewFill,
    calculate_review_economics,
)


def test_complete_review_economics_reports_planned_and_actual_r_multiples() -> None:
    economics = calculate_review_economics(
        facts=ReviewEconomicsFacts(
            ticket_id="ticket-1",
            entry_fills=(
                _fill("entry-1", quantity="0.4", price="100", fee="0.04"),
                _fill("entry-2", quantity="0.6", price="102", fee="0.06"),
            ),
            exit_fills=(
                _fill("exit-1", quantity="0.5", price="104", fee="0.05"),
                _fill("exit-2", quantity="0.5", price="110", fee="0.05"),
            ),
            funding_quote=Decimal("-0.3"),
            funding_unavailable_reason=None,
            observed_at_ms=5_000,
        ),
        expected_entry_quantity=Decimal("1"),
        position_side="long",
        planned_risk_at_stop=Decimal("10"),
        actual_risk_at_stop=Decimal("8"),
    )

    assert economics.entry_average_price == Decimal("101.2")
    assert economics.exit_average_price == Decimal("107")
    assert economics.gross_realized_pnl_quote == Decimal("5.8")
    assert economics.trading_fees_quote == Decimal("0.20")
    assert economics.net_pnl_before_funding_quote == Decimal("5.60")
    assert economics.funding_quote == Decimal("-0.3")
    assert economics.net_pnl_quote == Decimal("5.30")
    assert economics.planned_r_multiple == Decimal("0.53")
    assert economics.actual_r_multiple == Decimal("0.6625")
    assert economics.economics_completeness is ReviewEconomicsCompleteness.COMPLETE


def test_short_review_economics_has_the_correct_pnl_direction() -> None:
    economics = calculate_review_economics(
        facts=ReviewEconomicsFacts(
            ticket_id="ticket-short",
            entry_fills=(_fill("entry", quantity="2", price="100", fee="0.1"),),
            exit_fills=(_fill("exit", quantity="2", price="90", fee="0.1"),),
            funding_quote=Decimal("0"),
            funding_unavailable_reason=None,
            observed_at_ms=5_000,
        ),
        expected_entry_quantity=Decimal("2"),
        position_side="short",
        planned_risk_at_stop=Decimal("20"),
        actual_risk_at_stop=Decimal("20"),
    )

    assert economics.gross_realized_pnl_quote == Decimal("20")
    assert economics.net_pnl_quote == Decimal("19.8")
    assert economics.planned_r_multiple == Decimal("0.99")
    assert economics.actual_r_multiple == Decimal("0.99")


def test_funding_unavailable_never_fabricates_net_pnl_or_r_multiples() -> None:
    economics = calculate_review_economics(
        facts=ReviewEconomicsFacts(
            ticket_id="ticket-overlap",
            entry_fills=(_fill("entry", quantity="1", price="100", fee="0.1"),),
            exit_fills=(_fill("exit", quantity="1", price="110", fee="0.1"),),
            funding_quote=None,
            funding_unavailable_reason="overlapping_instrument_exposure",
            observed_at_ms=5_000,
        ),
        expected_entry_quantity=Decimal("1"),
        position_side="long",
        planned_risk_at_stop=Decimal("10"),
        actual_risk_at_stop=Decimal("8"),
    )

    assert economics.net_pnl_before_funding_quote == Decimal("9.8")
    assert economics.funding_quote is None
    assert economics.net_pnl_quote is None
    assert economics.planned_r_multiple is None
    assert economics.actual_r_multiple is None
    assert (
        economics.economics_completeness
        is ReviewEconomicsCompleteness.FUNDING_UNAVAILABLE
    )


def test_missing_actual_stop_risk_keeps_only_the_planned_r_multiple() -> None:
    economics = calculate_review_economics(
        facts=ReviewEconomicsFacts(
            ticket_id="ticket-without-post-fill-risk",
            entry_fills=(_fill("entry", quantity="1", price="100", fee="0.1"),),
            exit_fills=(_fill("exit", quantity="1", price="110", fee="0.1"),),
            funding_quote=Decimal("0"),
            funding_unavailable_reason=None,
            observed_at_ms=5_000,
        ),
        expected_entry_quantity=Decimal("1"),
        position_side="long",
        planned_risk_at_stop=Decimal("10"),
        actual_risk_at_stop=None,
    )

    assert economics.planned_r_multiple == Decimal("0.98")
    assert economics.actual_r_multiple is None
    assert economics.risk_variance is None
    assert economics.risk_variance_fraction is None


def test_review_economics_rejects_incomplete_exit_quantity() -> None:
    with pytest.raises(
        ReviewEconomicsUnavailable,
        match="exit fill quantity does not equal Ticket quantity",
    ):
        calculate_review_economics(
            facts=ReviewEconomicsFacts(
                ticket_id="ticket-incomplete",
                entry_fills=(
                    _fill("entry", quantity="1", price="100", fee="0.1"),
                ),
                exit_fills=(
                    _fill("exit", quantity="0.5", price="110", fee="0.05"),
                ),
                funding_quote=Decimal("0"),
                funding_unavailable_reason=None,
                observed_at_ms=5_000,
            ),
            expected_entry_quantity=Decimal("1"),
            position_side="long",
            planned_risk_at_stop=Decimal("10"),
            actual_risk_at_stop=Decimal("10"),
        )


def _fill(
    trade_id: str,
    *,
    quantity: str,
    price: str,
    fee: str,
) -> ReviewFill:
    return ReviewFill(
        exchange_trade_id=trade_id,
        venue_client_order_id=f"client-{trade_id}",
        quantity=Decimal(quantity),
        price=Decimal(price),
        fee_quote=Decimal(fee),
        occurred_at_ms=4_000,
    )
