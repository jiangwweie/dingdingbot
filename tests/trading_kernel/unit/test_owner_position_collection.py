"""Raw Binance schema is parsed before any phone preview can use a fact."""
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from src.trading_kernel.domain.commands import ExchangeCommand, OrderCommandPayload
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.infrastructure.owner_position_source import (
    collect_owner_position,
)
from tests.trading_kernel.support.owner_reduction import aggregate

FIXTURES=Path(__file__).resolve().parents[1]/'fixtures/management_protocol_v2'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',[None,'wrong_client','wrong_quantity','unowned_open','stale_price','timeout','missing_stop','stop_no_longer_new','changed_stop_price','duplicate_stop','missing_tp','changed_tp','changed_tp_fill','wrong_tif','shared_order_number'])
async def test_raw_owner_position_collection_is_exact_and_bounded(fault):
    a=aggregate();
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
    if fault=='wrong_tif':tp['timeInForce']='IOC'
    if fault=='shared_order_number':
        stop['algoId']=tp['orderId']='12345'
        tp.update(status='FILLED',executedQty=str(a.tp1_target_qty))
        a=a.model_copy(update={'active_stop_exchange_order_id':'12345','tp1_exchange_order_id':'12345'})
    class Reader:
        async def read(self,name,params):
            if fault=='timeout':raise TimeoutError()
            if name=='algo_order':return stop
            if name=='order':return tp
            if name=='trades':return [{'symbol':'BTCUSDT','side':'SELL','positionSide':'LONG',
                'id':'fill-1','orderId':tp['orderId'],'qty':tp['executedQty'],
                'price':tp['price'],'time':3000}]
            if name=='orders':
                if fault=='shared_order_number':return []
                if fault=='missing_tp':return []
                if fault=='changed_tp':return [{**tp,'price':'64000'}]
                if fault=='changed_tp_fill':return [{**tp,'status':'PARTIALLY_FILLED','executedQty':'.0001'}]
                return [tp,{'orderId':'unknown','symbol':'BTCUSDT','positionSide':'LONG'}] if fault=='unowned_open' else [tp]
            if name=='algos':
                if fault=='missing_stop':return []
                if fault=='stop_no_longer_new':return [{**stop,'algoStatus':'CANCELED'}]
                if fault=='changed_stop_price':return [{**stop,'triggerPrice':'58000'}]
                return [stop,stop] if fault=='duplicate_stop' else [stop]
            if name=='mode':return {'dualSidePosition':True}
            if name=='positions':return [{'symbol':'BTCUSDT','positionSide':'LONG','positionAmt':str(a.position_qty)}]
            if name=='ticker':return {'symbol':'BTCUSDT','price':'60000','time':-100000 if fault=='stale_price' else 5000}
            raise AssertionError(name)
    call=collect_owner_position(Reader(),aggregate=a,commands=commands,accepted_order_ids={'our-stop':a.active_stop_exchange_order_id,'our-tp':a.tp1_exchange_order_id},
        operation_id=None,clock_ms=lambda:5000)
    if fault not in {None,'shared_order_number'}:
        with pytest.raises((ValueError,TimeoutError)):await call
    else:
        result=await call
        assert result.facts.protected_quantity==a.position_qty
        assert result.facts.tp_state==('filled' if fault=='shared_order_number' else 'open')
        assert result.facts.tp_filled_quantity==(a.tp1_target_qty if fault=='shared_order_number' else D(0))
        assert len(result.orders)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', ['runner', 'cancelled_manual_tp', 'waiting_after_reduction'])
async def test_retired_tp_keeps_recorded_fills_and_runner_can_be_reduced(stage):
    from src.trading_kernel.domain.aggregate import AggregateStatus
    from src.trading_kernel.domain.owner_reduction import preview_owner_reduction
    from tests.trading_kernel.support.owner_position import ProtectedPositionReader

    a = aggregate().model_copy(update={
        'status': AggregateStatus.RUNNER_PROTECTED,
        'tp1_filled_qty': D('.0002'),
        'tp1_exchange_order_id': None,
    })
    if stage == 'waiting_after_reduction':
        from src.trading_kernel.domain.owner_reduction_context import (
            OwnerReductionContext,
        )
        a = a.model_copy(update={'status': AggregateStatus.POSITION_PROTECTED,
            'tp1_filled_qty': D(0), 'owner_reduction_context': OwnerReductionContext(
                operation_id='earlier', cumulative_quantity=D('.0001'),
                original_tp_order_id='old-tp', original_tp_price=D(62000),
                last_reduction_observed_at_ms=4000)})
    if stage == 'cancelled_manual_tp':
        from src.trading_kernel.domain.manual_profit_plan import ManualProfitPlan
        a = a.model_copy(update={'manual_profit_plan': ManualProfitPlan(
            operation_id='old', command_id='old', exchange_order_id='old-tp',
            price=D(62000), target_quantity=D('.0002'), prior_tp_filled_quantity=D('.0003'),
            started_from_runner=True, cancelled=True)})
    reader = ProtectedPositionReader(a)
    result = await collect_owner_position(
        reader, aggregate=a, commands=(reader.command,),
        accepted_order_ids={'stop-client': a.active_stop_exchange_order_id},
        operation_id=None, clock_ms=lambda: 5000,
    )
    assert result.facts.tp_state == 'absent'
    assert result.facts.tp_filled_quantity == a.tp1_filled_qty
    p = preview_owner_reduction(
        aggregate=a, facts=result.facts, requested_quantity=a.position_qty / 2,
        quantity_step=D('.0001'), minimum_quantity=D('.0001'),
        minimum_notional=D(1), now_ms=5000,
    )
    assert p.continue_runner == (stage != 'waiting_after_reduction')
    assert p.cancel_tp_order_id is None


@pytest.mark.asyncio
async def test_missing_active_tp_identity_is_not_replaced_with_historical_fills():
    from tests.trading_kernel.support.owner_position import ProtectedPositionReader

    a = aggregate()
    reader = ProtectedPositionReader(a)
    with pytest.raises(ValueError, match='owner_active_order_identity_missing'):
        await collect_owner_position(
            reader, aggregate=a, commands=(reader.command,),
            accepted_order_ids={'stop-client': a.active_stop_exchange_order_id},
            operation_id=None, clock_ms=lambda: 5000,
        )


@pytest.mark.asyncio
async def test_signed_position_amount_cannot_be_hidden_by_absolute_value():
    from tests.trading_kernel.support.owner_position import ProtectedPositionReader

    a = aggregate().model_copy(update={'tp1_exchange_order_id': None})

    reader = ProtectedPositionReader(a)
    reader.position_amount = str(-a.position_qty)

    with pytest.raises(ValueError, match='owner_position_sign_differs'):
        await collect_owner_position(
            reader, aggregate=a, commands=(reader.command,),
            accepted_order_ids={'stop-client': a.active_stop_exchange_order_id},
            operation_id=None, clock_ms=lambda: 5000,
        )
