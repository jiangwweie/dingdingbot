from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.infrastructure.readonly_closure_source import (
    collect_readonly_closure,
)


def wire():
    # Public-shape fixture: two exact order fills, both sides flat, no residual.
    result={
        'positions':[], 'orders':[], 'algos':[], 'mode':{'dualSidePosition':True},
        'all_orders':[
            {'symbol':'BNBUSDT','orderId':'11','clientOrderId':'brc-entry','side':'SELL','positionSide':'SHORT','type':'MARKET','status':'FILLED','origQty':'2','executedQty':'2','time':'1000','updateTime':'1000'},
            {'symbol':'BNBUSDT','orderId':'22','clientOrderId':'app','side':'BUY','positionSide':'SHORT','type':'MARKET','status':'FILLED','origQty':'2','executedQty':'2','time':'2000','updateTime':'2000'}],
        'all_algos':[], 'trades':[
            {'symbol':'BNBUSDT','id':'1','orderId':'11','side':'SELL','positionSide':'SHORT','qty':'2','price':'680','time':'1000'},
            {'symbol':'BNBUSDT','id':'2','orderId':'22','side':'BUY','positionSide':'SHORT','qty':'2','price':'685','time':'2000'}],
    }
    for row in result['all_orders']:
        row.update(price='0',stopPrice='0',closePosition=False,reduceOnly=row['side']=='BUY',timeInForce='GTC',workingType='CONTRACT_PRICE',priceProtect=False,priceMatch='NONE',selfTradePreventionMode='EXPIRE_MAKER',goodTillDate='0')
    return result


async def read_fixture(data):
    reader=AsyncMock();reader.read.side_effect=lambda name,params:data[name]
    return await collect_readonly_closure(reader,ticket_id='t',domain=NettingDomain(venue_id='binance-usdm',account_id='a',exchange_instrument_id='binance-usdm:BNBUSDT:perpetual',position_side='short'),
        entry_order_id='11',own_orders=frozenset({('regular','11')}),since_ms=900,clock_ms=lambda:3000)


@pytest.mark.asyncio
async def test_exact_external_fill_and_account_flatness_form_independent_proof():
    proof=await read_fixture(wire())
    assert proof.exit_order_id=='22'
    assert proof.exit_fills[0].quantity==2
    assert proof.snapshot.orders_complete and proof.snapshot.quantity==0


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['position','open_order','truncated','wrong_mode','wrong_fill','second_exit'])
async def test_closure_source_rejects_unsafe_or_ambiguous_account(fault):
    x=wire()
    if fault=='position':x['positions']=[{'positionAmt':'1'}]
    elif fault=='open_order':x['orders']=[{'orderId':'99'}]
    elif fault=='truncated':x['all_orders']=[x['all_orders'][0]]*100
    elif fault=='wrong_mode':x['mode']={'dualSidePosition':False}
    elif fault=='wrong_fill':x['trades'][1]['side']='SELL'
    else:x['all_orders'].append({**x['all_orders'][1],'orderId':'33'})
    with pytest.raises(ValueError):await read_fixture(x)
