"""Synthetic fixtures use documented Binance raw fields, never live orders."""

from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.trade_management import OrderAction
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_order_update,
    read_order_amendments,
)


def message():
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 2001,
        "T": 2000,
        "o": {
            "s": "BTCUSDT",
            "c": "app-one",
            "S": "SELL",
            "o": "LIMIT",
            "f": "GTC",
            "q": "1",
            "p": "110",
            "sp": "0",
            "x": "NEW",
            "X": "NEW",
            "i": 123,
            "z": "0",
            "T": 2000,
            "R": False,
            "ps": "LONG",
            "cp": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
        },
    }


def parse(m, **kwargs):
    return parse_order_update(
        m, account_id="test", received_at_ms=2002, coverage_complete=True, **kwargs
    )


def test_unfilled_order_update_is_retained():
    e = parse(message())
    assert e.action is OrderAction.NEW and e.executed_quantity == 0
    assert e.terms.exchange_order_id == "123" and e.terms.position_side == "long"
    assert e.terms.price == 110 and e.terms.quantity == 1


def test_regular_amendment_without_old_terms_remains_explicit():
    m = message()
    m["o"]["x"] = "AMENDMENT"
    e = parse(m)
    assert e.action is OrderAction.AMENDMENT and e.before_terms is None


def test_same_id_price_change_not_erased_by_generic_position_snapshot():
    before = parse(message()).terms
    m = message()
    m["o"]["p"] = "111"
    m["o"]["x"] = "AMENDMENT"
    after = parse(m, before_terms=before)
    assert after.terms.identity == before.identity and after.terms.price != before.price


def test_algo_activation_new_is_status_not_owner_new():
    m = {
        "e": "ALGO_UPDATE",
        "E": 2001,
        "T": 2000,
        "o": {
            "s": "BTCUSDT",
            "caid": "brc-stop",
            "aid": 123,
            "S": "SELL",
            "ps": "LONG",
            "o": "TRAILING_STOP_MARKET",
            "f": "GTC",
            "q": "1",
            "p": "0",
            "tp": "0",
            "X": "NEW",
            "R": False,
            "cp": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
            "cr": "1",
            "AP": "115",
            "ia": True,
        },
    }
    e = parse(m)
    assert e.action is OrderAction.STATUS
    assert e.terms.order_namespace == "conditional"


def test_triggered_algo_is_not_manual_cancel():
    m = {
        "e": "ALGO_UPDATE",
        "E": 2001,
        "T": 2000,
        "o": {
            "s": "BTCUSDT",
            "caid": "brc-stop",
            "aid": 123,
            "S": "SELL",
            "ps": "LONG",
            "o": "STOP_MARKET",
            "f": "GTC",
            "q": "1",
            "p": "0",
            "tp": "95",
            "X": "TRIGGERED",
            "R": False,
            "cp": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
            "ia": False,
        },
    }
    assert parse(m).action is OrderAction.TRIGGERED


@pytest.mark.parametrize("field", ["ps", "R", "cp", "q", "S", "s"])
def test_missing_required_facts_are_not_defaulted(field):
    m = message()
    del m["o"][field]
    with pytest.raises((ValueError, KeyError)):
        parse(m)


def test_wrong_position_mode_is_not_silently_long():
    m = message()
    m["o"]["ps"] = "BOTH"
    with pytest.raises(ValueError):
        parse(m)


def test_expiry_reason_is_not_a_manual_cancel():
    m = message()
    m["o"].update(x="EXPIRED", X="EXPIRED", er="8")
    assert parse(m).action is OrderAction.EXPIRED


@pytest.mark.asyncio
async def test_amendment_read_has_exact_order_and_bounded_window():
    exchange = AsyncMock()
    exchange.fapiPrivateGetOrderAmendment.return_value = []
    page = await read_order_amendments(
        exchange, symbol="BTCUSDT", order_id="123", start_ms=1000, end_ms=2000, limit=50
    )
    assert page.rows == () and not page.possibly_truncated
    exchange.fapiPrivateGetOrderAmendment.assert_awaited_once_with(
        {
            "symbol": "BTCUSDT",
            "orderId": 123,
            "startTime": 1000,
            "endTime": 2000,
            "limit": 50,
        }
    )
    exchange.create_order.assert_not_called()


@pytest.mark.asyncio
async def test_full_page_never_proves_complete_history():
    exchange = AsyncMock()
    exchange.fapiPrivateGetOrderAmendment.return_value = [
        {
            "amendmentId": 1,
            "symbol": "BTCUSDT",
            "orderId": 123,
            "time": 1500,
            "amendment": {
                "price": {"before": "110", "after": "111"},
                "origQty": {"before": "1", "after": "1"},
                "count": 1,
            },
        }
    ]
    page = await read_order_amendments(
        exchange, symbol="BTCUSDT", order_id="123", start_ms=1000, end_ms=2000, limit=1
    )
    assert page.possibly_truncated


@pytest.mark.asyncio
async def test_history_wrong_order_fails_closed():
    exchange = AsyncMock()
    exchange.fapiPrivateGetOrderAmendment.return_value = [
        {
            "amendmentId": 1,
            "symbol": "BTCUSDT",
            "orderId": 999,
            "time": 1500,
            "amendment": {
                "price": {"before": "110", "after": "111"},
                "origQty": {"before": "1", "after": "1"},
                "count": 1,
            },
        }
    ]
    with pytest.raises(ValueError):
        await read_order_amendments(
            exchange, symbol="BTCUSDT", order_id="123", start_ms=1000, end_ms=2000
        )


def test_same_millisecond_changes_have_distinct_evidence_ids():
    first = message()
    second = message()
    second["o"]["p"] = "111"
    assert parse(first).evidence_id != parse(second).evidence_id


def test_transport_redelivery_is_idempotent():
    assert parse(message()).evidence_id == parse(message()).evidence_id


def test_missing_creation_time_stays_unknown_not_current_event_time():
    assert parse(message()).created_at_ms is None


def test_explicit_missing_algo_activation_is_not_guessed():
    m = {
        "e": "ALGO_UPDATE",
        "E": 2001,
        "T": 2000,
        "o": {
            "s": "BTCUSDT",
            "caid": "brc-stop",
            "aid": 123,
            "S": "SELL",
            "ps": "LONG",
            "o": "STOP_MARKET",
            "f": "GTC",
            "q": "1",
            "p": "0",
            "tp": "95",
            "X": "NEW",
            "R": False,
            "cp": False,
            "wt": "CONTRACT_PRICE",
            "pP": False,
            "pm": "NONE",
            "V": "NONE",
            "gtd": 0,
        },
    }
    with pytest.raises(ValueError, match="activation discriminator"):
        parse(m)
