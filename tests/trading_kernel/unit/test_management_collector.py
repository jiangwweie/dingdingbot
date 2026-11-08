from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.management_observation import ManagementScanRequest
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.infrastructure.management_collector import (
    collect_management_scan,
)


def raw(**kw):
    return {
        "symbol": "BTCUSDT",
        "orderId": 12,
        "clientOrderId": "app-new",
        "side": "SELL",
        "positionSide": "LONG",
        "type": "LIMIT",
        "origQty": "1",
        "executedQty": "0",
        "price": "110",
        "stopPrice": "0",
        "status": "NEW",
        "reduceOnly": False,
        "closePosition": False,
        "timeInForce": "GTC",
        "workingType": "CONTRACT_PRICE",
        "priceProtect": False,
        "priceMatch": "NONE",
        "selfTradePreventionMode": "NONE",
        "goodTillDate": 0,
        "time": 1500,
        "updateTime": 1500,
        **kw,
    }


def request():
    return ManagementScanRequest(
        ticket_id="t",
        domain=NettingDomain(
            venue_id="binance-usdm",
            account_id="test",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            position_side="long",
        ),
        since_ms=1000,
        now_ms=2000,
    )


@pytest.mark.asyncio
async def test_new_unfilled_order_is_collected_without_mutation():
    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = [raw()]
    x.fapiPrivateGetAllAlgoOrders.return_value = []
    x.fapiPrivateGetOrderAmendment.return_value = []
    req = request()
    position = PositionSnapshot(
        netting_domain=req.domain,
        quantity=Decimal(1),
        average_entry_price=Decimal(100),
        observed_at_ms=2000,
    )
    b = await collect_management_scan(x, req, position)
    assert len(b.evidence) == 1 and b.evidence[0].action.value == "new"
    assert b.evidence[0].executed_quantity == 0
    x.create_order.assert_not_called()
    x.cancel_order.assert_not_called()


@pytest.mark.asyncio
async def test_same_id_modified_back_retains_both_amendments():
    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = [raw(clientOrderId="brc-old")]
    x.fapiPrivateGetAllAlgoOrders.return_value = []
    x.fapiPrivateGetOrderAmendment.return_value = [
        {
            "amendmentId": 1,
            "symbol": "BTCUSDT",
            "orderId": 12,
            "time": 1600,
            "amendment": {
                "price": {"before": "110", "after": "111"},
                "origQty": {"before": "1", "after": "1"},
                "count": 1,
            },
        },
        {
            "amendmentId": 2,
            "symbol": "BTCUSDT",
            "orderId": 12,
            "time": 1700,
            "amendment": {
                "price": {"before": "111", "after": "110"},
                "origQty": {"before": "1", "after": "1"},
                "count": 2,
            },
        },
    ]
    req = request()
    b = await collect_management_scan(
        x,
        req,
        PositionSnapshot(
            netting_domain=req.domain,
            quantity=Decimal(1),
            average_entry_price=Decimal(100),
            observed_at_ms=2000,
        ),
    )
    assert [e.action.value for e in b.evidence].count("amendment") == 2


@pytest.mark.asyncio
async def test_expired_history_window_is_not_complete():
    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = []
    x.fapiPrivateGetAllAlgoOrders.return_value = []
    req = request().model_copy(update={"now_ms": 4 * 86400000})
    b = await collect_management_scan(
        x,
        req,
        PositionSnapshot(
            netting_domain=req.domain,
            quantity=Decimal(1),
            average_entry_price=Decimal(100),
            observed_at_ms=req.now_ms,
        ),
    )
    assert not b.complete and b.reason == "management_history_retention_gap"


@pytest.mark.asyncio
async def test_order_created_before_window_is_still_queried_when_open():
    from src.trading_kernel.domain.position import VenueOrderSnapshot

    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = []
    x.fapiPrivateGetAllAlgoOrders.return_value = []
    x.fapiPrivateGetOrder.return_value = raw(time=500, updateTime=1500, price="111")
    x.fapiPrivateGetOrderAmendment.return_value = []
    req = request()
    order = VenueOrderSnapshot(
        exchange_order_id="12",
        venue_client_order_id="app-new",
        position_side="long",
        reduce_only=False,
        order_namespace="regular",
    )
    b = await collect_management_scan(
        x,
        req,
        PositionSnapshot(
            netting_domain=req.domain,
            quantity=Decimal(1),
            average_entry_price=Decimal(100),
            open_orders=(order,),
            observed_at_ms=2000,
        ),
    )
    assert b.orders[0].price == 111
    x.fapiPrivateGetOrder.assert_awaited_once()


@pytest.mark.asyncio
async def test_triggered_algo_child_is_not_an_external_manual_order():
    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = [
        raw(
            orderId=99,
            clientOrderId="venue-child",
            type="MARKET",
            status="FILLED",
            price="0",
            executedQty="1",
            time=1700,
            updateTime=1700,
        )
    ]
    x.fapiPrivateGetAllAlgoOrders.return_value = [
        {
            "symbol": "BTCUSDT",
            "algoId": 12,
            "clientAlgoId": "brc-stop",
            "side": "SELL",
            "positionSide": "LONG",
            "orderType": "STOP_MARKET",
            "quantity": "1",
            "price": "0",
            "triggerPrice": "95",
            "algoStatus": "FINISHED",
            "reduceOnly": False,
            "closePosition": False,
            "timeInForce": "GTC",
            "workingType": "CONTRACT_PRICE",
            "priceProtect": False,
            "priceMatch": "NONE",
            "selfTradePreventionMode": "NONE",
            "goodTillDate": 0,
            "createTime": 1200,
            "updateTime": 1700,
            "actualOrderId": "99",
            "actualQty": "1",
        }
    ]
    req = request()
    b = await collect_management_scan(
        x,
        req,
        PositionSnapshot(
            netting_domain=req.domain,
            quantity=Decimal(0),
            average_entry_price=None,
            observed_at_ms=2000,
        ),
    )
    assert not any(e.terms.client_order_id == "venue-child" for e in b.evidence)
    assert any(e.terms.exchange_order_id == "12" for e in b.evidence)


@pytest.mark.asyncio
async def test_full_history_page_is_followed_by_exact_id_cursor():
 x=AsyncMock();x.management_started_ms=None;x.management_covers=lambda **kw: False
 first=[raw(orderId=i,clientOrderId=f'app-{i}',status='CANCELED') for i in range(1,101)]
 x.fapiPrivateGetAllOrders.side_effect=[first,[]];x.fapiPrivateGetAllAlgoOrders.return_value=[];x.fapiPrivateGetOrderAmendment.return_value=[]
 req=request();b=await collect_management_scan(x,req,PositionSnapshot(netting_domain=req.domain,quantity=Decimal(1),average_entry_price=Decimal(100),observed_at_ms=2000))
 assert x.fapiPrivateGetAllOrders.await_count==2
 assert x.fapiPrivateGetAllOrders.await_args_list[1].args[0]['orderId']==101
 assert b.reason!='management_history_page_full'


@pytest.mark.asyncio
async def test_stream_buffer_loss_does_not_claim_complete_history():
 x=AsyncMock();x.management_started_ms=None;x.management_covers=lambda **kw: False;x.management_lost_before_ms=1700
 x.fapiPrivateGetAllOrders.return_value=[];x.fapiPrivateGetAllAlgoOrders.return_value=[]
 req=request();b=await collect_management_scan(x,req,PositionSnapshot(netting_domain=req.domain,quantity=Decimal(1),average_entry_price=Decimal(100),observed_at_ms=2000))
 assert not b.complete and b.reason=='management_stream_buffer_gap'


@pytest.mark.asyncio
async def test_conditional_snapshot_cannot_prove_missing_stream_interval():
    x = AsyncMock()
    x.management_started_ms = 1500
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = []
    x.fapiPrivateGetAllAlgoOrders.return_value = [{
        "symbol": "BTCUSDT", "algoId": 12, "clientAlgoId": "brc-stop",
        "side": "SELL", "positionSide": "LONG", "orderType": "STOP_MARKET",
        "quantity": "1", "price": "0", "triggerPrice": "95", "algoStatus": "NEW",
        "reduceOnly": False, "closePosition": False, "timeInForce": "GTC",
        "workingType": "CONTRACT_PRICE", "priceProtect": False, "priceMatch": "NONE",
        "selfTradePreventionMode": "NONE", "goodTillDate": 0,
        "createTime": 1200, "updateTime": 1200,
    }]
    x.management_events = lambda **kw: ()
    req = request()
    b = await collect_management_scan(x, req, PositionSnapshot(
        netting_domain=req.domain, quantity=Decimal(1),
        average_entry_price=Decimal(100), observed_at_ms=2000))
    assert not b.complete
    assert b.reason == "conditional_stream_coverage_unproven"


@pytest.mark.asyncio
async def test_two_day_regular_history_uses_bounded_amendment_windows():
    x = AsyncMock()
    x.management_started_ms = None
    x.management_covers = lambda **kw: False
    x.fapiPrivateGetAllOrders.return_value = [raw(clientOrderId="brc-old")]
    x.fapiPrivateGetAllAlgoOrders.return_value = []
    x.fapiPrivateGetOrderAmendment.return_value = []
    req = request().model_copy(update={"now_ms": 2 * 86400000})
    b = await collect_management_scan(x, req, PositionSnapshot(
        netting_domain=req.domain, quantity=Decimal(1),
        average_entry_price=Decimal(100), observed_at_ms=req.now_ms))
    assert b.complete
    assert x.fapiPrivateGetOrderAmendment.await_count == 2
    for call in x.fapiPrivateGetOrderAmendment.await_args_list:
        query = call.args[0]
        assert query["endTime"] - query["startTime"] <= 86400000
