import json
from decimal import Decimal

import ccxt
import pytest

from src.trading_kernel.application.runtime_facts import ReviewEconomicsRequest
from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.order_attribution import (
    ExternalExitOrderReference,
    TicketOrderReference,
)
from src.trading_kernel.domain.review import calculate_review_economics
from src.trading_kernel.domain.trade_management import OrderTerms
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter

MARKET={'id':'DOGEUSDT','symbol':'DOGE/USDT:USDT','base':'DOGE','quote':'USDT','settle':'USDT',
    'type':'swap','spot':False,'swap':True,'future':False,'option':False,'contract':True,
    'linear':True,'inverse':False,'contractSize':1,'precision':{'amount':1,'price':.00001}}


def external():
    return ExternalExitOrderReference(ticket_id='ticket',exposure_episode_id='episode',evidence_id='app-proof',
        order_created_at_ms=2500,evidence_at_ms=3000,terms=OrderTerms(
            venue_id='binance-usdm',account_id='manual',exchange_instrument_id='binance-usdm:DOGEUSDT:perpetual',
            position_side='short',order_namespace='regular',exchange_order_id='manual',client_order_id='app',
            side='buy',order_type='MARKET',quantity='16406',price=None,trigger_price=None,
            close_position=False,reduce_only=False,time_in_force='GTC',working_type='CONTRACT_PRICE',
            price_protect=False,activation_price=None,callback_rate=None,price_match='NONE',
            self_trade_prevention_mode='NONE',good_till_date_ms=0))


class Exchange:
    def __init__(self, fault=None):
        self.fault=fault
        self.parser=ccxt.binanceusdm()
        self.parser.set_markets([MARKET])
        self.requested=[]

    async def fetch_order(self, order_id, symbol, params):
        assert order_id=='manual'
        raw={'orderId':'manual','symbol':'DOGEUSDT','side':'BUY','origQty':'16406','executedQty':'16406',
            'time':2500,'updateTime':3000,'positionSide':'SHORT','status':'FILLED','type':'MARKET',
            'clientOrderId':'app','price':'0','avgPrice':'.0678','timeInForce':'GTC'}
        if self.fault=='wrong_order':raw['orderId']='other'
        return self.parser.parse_order(self.parser.on_json_response(json.dumps(raw)),MARKET)

    async def fetch_my_trades(self,symbol,since,limit,params):
        order=params['orderId'];self.requested.append(order)
        quantity,price,time,side={'entry':('32811','.06925',1100,'SELL'),
            'tp':('16405','.06848',2000,'BUY'),'manual':('16406','.0678',3000,'BUY')}[order]
        raw={'symbol':'DOGEUSDT','id':order+'-trade','orderId':order,'qty':quantity,'price':price,
            'time':time,'side':side,'positionSide':'SHORT','commission':'0.2',
            'commissionAsset':'USDT','realizedPnl':'0','buyer':side=='BUY','maker':False}
        if self.fault=='wrong_side' and order=='manual':raw['positionSide']='LONG'
        if self.fault=='trade_side' and order=='manual':raw['side']='SELL'
        if self.fault=='late' and order=='manual':raw['time']=4001
        if self.fault=='missing_fee' and order=='manual':del raw['commission']
        rows=[self.parser.parse_trade(self.parser.on_json_response(json.dumps(raw)),MARKET)]
        if self.fault=='truncated' and order=='manual':return rows*100
        return rows+rows

    async def fapiPrivateGetIncome(self,params):
        return [{'symbol':'DOGEUSDT','incomeType':'FUNDING_FEE','income':'.03648835','asset':'USDT','time':1500,'tranId':'funding'}]


def request():
    return ReviewEconomicsRequest(ticket_id='ticket',netting_domain=NettingDomain(venue_id='binance-usdm',
        account_id='manual',exchange_instrument_id='binance-usdm:DOGEUSDT:perpetual',position_side='short'),
        expected_entry_quantity='32811',entry_order_reference=TicketOrderReference(command_id='entry-cmd',command_kind='entry',
            role='entry',namespace='regular',venue_client_order_id='entry-client',submitted_exchange_order_id='entry',command_created_at_ms=1000),
        exit_order_references=(TicketOrderReference(command_id='tp-cmd',command_kind='take_profit',role='exit',namespace='regular',
            venue_client_order_id='tp-client',submitted_exchange_order_id='tp',command_created_at_ms=1500),external()),
        entry_time_ms=1000,exit_time_ms=3500,funding_attribution_exact=True,observed_at_ms=4000)


@pytest.mark.asyncio
async def test_raw_doge_tp_and_verified_app_exit_complete_quantity_and_economics():
    exchange=Exchange()
    adapter=CcxtVenueAdapter(exchanges={('binance-usdm','manual'):exchange},default_settlement_asset='USDT',clock_ms=lambda:4000)
    facts=await adapter.read_review_economics(request())
    result=calculate_review_economics(facts=facts,expected_entry_quantity=Decimal(32811),position_side='short',
        planned_risk_at_stop=Decimal(10),actual_risk_at_stop=None)
    assert sum(f.quantity for f in facts.exit_fills)==Decimal(32811)
    assert len(facts.exit_fills)==2
    assert result.funding_quote==Decimal('.03648835')
    app=next(f for f in facts.exit_fills if f.exchange_order_id=='manual')
    assert app.command_id is None and app.external_evidence_id=='app-proof'
    assert exchange.requested==['entry','tp','manual']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['wrong_order','wrong_side','trade_side','late','missing_fee','truncated'])
async def test_external_evidence_conflicts_never_become_complete_economics(fault):
    adapter=CcxtVenueAdapter(exchanges={('binance-usdm','manual'):Exchange(fault)},default_settlement_asset='USDT',clock_ms=lambda:4000)
    with pytest.raises((RuntimeError,ValueError)):
        await adapter.read_review_economics(request())
