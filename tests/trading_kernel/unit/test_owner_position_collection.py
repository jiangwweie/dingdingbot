"""Raw Binance schema is parsed before any phone preview can use a fact."""
import json
from pathlib import Path
from decimal import Decimal as D
import pytest

from src.trading_kernel.infrastructure.owner_position_source import collect_owner_position
from src.trading_kernel.domain.commands import ExchangeCommand,ExchangeCommandKind as K,ExchangeCommandStatus as S,OrderCommandPayload
from tests.trading_kernel.support.owner_reduction import aggregate

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures/management_protocol_v2'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',[None,'wrong_client','wrong_quantity','unowned_open','stale_price','timeout','missing_stop','stop_no_longer_new','changed_stop_price','duplicate_stop'])
async def test_raw_owner_position_collection_is_exact_and_bounded(fault):
    a=aggregate();d=a.identity.netting_domain
    stop=json.loads((FIXTURES/'bnb_stop_cancelled.json').read_text())
    stop.update(algoId='stop',clientAlgoId='our-stop',symbol='BTCUSDT',side='SELL',positionSide='LONG',
        quantity=str(a.position_qty),triggerPrice=str(a.active_stop_price),algoStatus='NEW',createTime=2000,updateTime=3000)
    tp=json.loads((FIXTURES/'bnb_app_exit.json').read_text())
    tp.update(orderId='tp',clientOrderId='our-tp',symbol='BTCUSDT',side='SELL',positionSide='LONG',type='LIMIT',status='NEW',
        origQty=str(a.tp1_target_qty),executedQty='0',price=str(a.ticket.take_profit_prices[0]),time=2000,updateTime=3000)
    a=a.model_copy(update={'active_stop_exchange_order_id':'stop','tp1_exchange_order_id':'tp'})
    def command(cid,kind,payload):
        return ExchangeCommand(command_id=cid,ticket_identity=a.identity,management_revision=1,kind=kind,generation=1,
            idempotency_key=cid,venue_client_order_id=cid,payload=payload,status=S.ACCEPTED,created_at_ms=1500,deadline_at_ms=10000)
    commands=(command('our-stop',K.INITIAL_STOP,OrderCommandPayload(side='sell',quantity=a.position_qty,order_type='stop_market',
        reduce_only=True,stop_price=a.active_stop_price)),command('our-tp',K.TAKE_PROFIT,OrderCommandPayload(side='sell',quantity=a.tp1_target_qty,
        order_type='limit',reduce_only=True,limit_price=a.ticket.take_profit_prices[0],time_in_force='GTC')))
    if fault=='wrong_client':stop['clientAlgoId']='external'
    if fault=='wrong_quantity':stop['quantity']=str(a.position_qty*2)
    class Reader:
        async def read(self,name,params):
            if fault=='timeout':raise TimeoutError()
            if name=='algo_order':return stop
            if name=='order':return tp
            if name=='orders':return [tp,{'orderId':'unknown','symbol':'BTCUSDT','positionSide':'LONG'}] if fault=='unowned_open' else [tp]
            if name=='algos':
                if fault=='missing_stop':return []
                if fault=='stop_no_longer_new':return [{**stop,'algoStatus':'CANCELED'}]
                if fault=='changed_stop_price':return [{**stop,'triggerPrice':'58000'}]
                return [stop,stop] if fault=='duplicate_stop' else [stop]
            if name=='mode':return {'dualSidePosition':True}
            if name=='positions':return [{'symbol':'BTCUSDT','positionSide':'LONG','positionAmt':str(a.position_qty)}]
            if name=='ticker':return {'symbol':'BTCUSDT','price':'60000','time':-100000 if fault=='stale_price' else 5000}
            raise AssertionError(name)
    call=collect_owner_position(Reader(),aggregate=a,commands=commands,accepted_order_ids={'our-stop':'stop','our-tp':'tp'},
        operation_id=None,clock_ms=lambda:5000)
    if fault is not None:
        with pytest.raises((ValueError,TimeoutError)):await call
    else:
        result=await call
        assert result.facts.tp_state=='open' and result.facts.protected_quantity==a.position_qty
        assert len(result.orders)==2
