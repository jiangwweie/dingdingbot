from decimal import Decimal

import pytest

from src.trading_kernel.application.notice_templates import (
    format_amount,
    format_number,
    render_notice,
)
from src.trading_kernel.domain.notices import NoticeKind, NoticeSnapshot, StopView


def snapshot(**changes):
    values = {
        "ticket_id": "ticket:INTERNAL-NOT-FOR-PHONE",
        "event_id": "event:INTERNAL",
        "state_version": 9,
        "kind": NoticeKind.OPENED,
        "severity": "info",
        "symbol": "BTC",
        "side": "long",
        "mode": "AUTO",
        "quantity": Decimal("0.006000000000000000"),
        "entry_price": Decimal("66666.700000"),
        "price_tick": Decimal(".1"),
        "stops": (
            StopView(
                price=Decimal("65500.0000"),
                quantity=Decimal(".006"),
                full_position=True,
            ),
        ),
        "protection": "full",
        "protected_quantity": Decimal(".006"),
        "strategy": "MPG",
        "strategy_semantics": "领涨动量突破",
        "event_at_ms": 1794182400000,
        "facts_at_ms": 1794182400000,
    }
    return NoticeSnapshot.model_validate({**values, **changes})


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0.003000000000000000", "0.003"),
        ("65000.00000000", "65,000"),
        ("0.0000123000", "0.0000123"),
        ("0", "0"),
    ],
)
def test_number_display_preserves_real_value_without_trailing_zeroes(value, expected):
    assert format_number(Decimal(value)) == expected


def test_tiny_money_is_not_reported_as_zero():
    assert format_amount(Decimal(".00007")) == "<0.01U"
    assert format_amount(Decimal("400.000")) == "400U"
    assert format_amount(Decimal("-0.00007")) == "-<0.01U"


def test_open_template_is_compact_exact_and_has_strategy_semantics_but_no_internal_ids():
    message = render_notice(snapshot())
    assert len(message.splitlines()) <= 5
    for text in [
        "【首尔】BTC 多",
        "自动",
        "0.006 BTC",
        "入场计 400U",
        "66,666.7",
        "65,500",
        "全仓",
        "MPG｜领涨动量突破",
    ]:
        assert text in message
    assert "INTERNAL" not in message and "Ticket" not in message
    assert "00000000" not in message


def test_manual_unknown_stop_never_reuses_old_automatic_stop_or_claims_protection():
    message = render_notice(
        snapshot(
            kind=NoticeKind.TAKEOVER,
            mode="MANUAL",
            stops=(),
            protection="unknown",
            protected_quantity=None,
        )
    )
    assert "止损待核实" in message
    assert "65,500" not in message and "全仓" not in message
    assert "后续退出由你管理" in message


def test_flat_residual_template_never_says_protection_restored_or_fully_finished():
    message = render_notice(
        snapshot(
            kind=NoticeKind.RESIDUAL,
            mode="MANUAL",
            quantity=Decimal(0),
            stops=(),
            protection="none",
            protected_quantity=Decimal(0),
            residual_order_count=2,
        )
    )
    assert "余仓 0" in message and "残单 2" in message
    assert "恢复" not in message and "已结束" not in message


def test_partial_protection_is_visible_without_planned_orders():
    message = render_notice(
        snapshot(
            kind=NoticeKind.RISK,
            severity="critical",
            mode="MANUAL",
            protection="partial",
            protected_quantity=Decimal(".002"),
            new_entry_restricted=True,
            stops=(
                StopView(
                    price=Decimal(65000), quantity=Decimal(".002"), full_position=False
                ),
            ),
        )
    )
    assert "0.004 BTC" in message and "新开仓受限" in message
    assert "全仓" not in message


def test_tp1_reports_actual_fill_and_risk_increase_has_amount():
    message = render_notice(
        snapshot(
            kind=NoticeKind.TP1,
            fill_quantity=Decimal(".002"),
            fill_price=Decimal(68000),
        )
    )
    assert "TP1 成交 0.002 BTC" in message and "68,000" in message
    message = render_notice(snapshot(kind=NoticeKind.RISK, risk_at_stop=Decimal("9.2")))
    assert "止损风险 9.2U" in message
