from decimal import Decimal as D

from src.trading_kernel.domain.manual_position import assess_manual_exposure
from src.trading_kernel.domain.trade_management import OrderTerms


def stop(price="90", quantity="10"):
    return OrderTerms(
        venue_id="binance-usdm",
        account_id="test",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        order_namespace="conditional",
        exchange_order_id="s1",
        client_order_id="app",
        side="sell",
        order_type="STOP_MARKET",
        quantity=quantity,
        price=None,
        trigger_price=price,
        close_position=False,
        reduce_only=False,
        time_in_force="GTC",
        working_type="MARK_PRICE",
        price_protect=False,
        activation_price=None,
        callback_rate=None,
        price_match="NONE",
        self_trade_prevention_mode="NONE",
        good_till_date_ms=0,
    )


def assess(q="10", orders=None, complete=True):
    return assess_manual_exposure(
        quantity=D(q),
        initial_quantity=D(10),
        initial_risk=D(100),
        entry_price=D(100),
        position_side="long",
        orders=(stop(),) if orders is None else orders,
        facts_complete=complete,
    )


def test_manual_break_even_does_not_free_all_risk():
    assert assess(orders=(stop("101"),)).risk_at_stop == 100


def test_partial_exit_scales_original_risk_floor():
    assert assess(q="5", orders=(stop("101", "5"),)).risk_at_stop == 50


def test_widened_stop_increases_risk():
    assert assess(orders=(stop("80"),)).risk_at_stop == 200


def test_missing_partial_overlapping_and_stale_protection_block_new_entry():
    for result in [
        assess(orders=()),
        assess(orders=(stop(quantity="5"),)),
        assess(orders=(stop(), stop())),
        assess(complete=False),
    ]:
        assert result.entry_blocked and result.risk_at_stop is None


def test_zero_position_not_negative_budget():
    assert assess(q="0", orders=()).risk_at_stop == 0


def test_increase_outside_scope():
    assert assess(q="11").reason == "manual_exposure_increased"


def test_protection_with_non_market_stop_cannot_claim_loss_bound():
    unsupported = stop().model_copy(update={"order_type": "STOP", "price": D(89)})
    assert assess(orders=(unsupported,)).entry_blocked


def test_oversized_fixed_stop_after_manual_reduction_is_not_assumed_valid():
 assert assess(q='5',orders=(stop(quantity='10'),)).entry_blocked
