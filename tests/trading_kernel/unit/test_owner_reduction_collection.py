from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.owner_reduction import OwnerReductionPhase, OwnerReductionState
from src.trading_kernel.infrastructure.owner_reduction_source import collect_owner_reduction
from tests.trading_kernel.support.owner_reduction import preview
from tests.trading_kernel.support.owner_reduction import aggregate


class Reader:
    def __init__(self, a):
        self.a = a
        self.calls = []
        self.stop_changes = {}

    async def read(self, name, params):
        self.calls.append((name, params))
        a = self.a
        if name=='orders':return []
        if name=='algos':return [await self.read('algo_order',{})]
        if name == 'mode':
            return {'dualSidePosition': True}
        if name == 'positions':
            return [{'symbol': 'BTCUSDT', 'positionSide': 'LONG', 'positionAmt': str(a.position_qty)}]
        if name == 'ticker':
            return {'symbol': 'BTCUSDT', 'price': str(a.average_fill_price), 'time': 5000}
        if name == 'algo_order':
            return {'algoId': a.active_stop_exchange_order_id, 'clientAlgoId': 'stop-client',
                'symbol': 'BTCUSDT', 'side': 'SELL', 'positionSide': 'LONG', 'orderType': 'STOP_MARKET',
                'quantity': '0', 'closePosition': True, 'reduceOnly': False, 'triggerPrice': str(a.active_stop_price),
                'workingType':'CONTRACT_PRICE','priceProtect':False,'algoStatus': 'NEW', 'actualQty': '0', 'updateTime': 4000, **self.stop_changes}
        if name == 'order':
            return {'orderId': a.tp1_exchange_order_id, 'clientOrderId': 'tp-client', 'symbol': 'BTCUSDT',
                'side': 'SELL', 'positionSide': 'LONG', 'type': 'LIMIT', 'origQty': str(a.tp1_target_qty),
                'executedQty': '0', 'price': str(a.ticket.take_profit_prices[0]), 'timeInForce': 'GTC', 'status': 'NEW'}
        raise AssertionError(name)


def commands(a):
    from src.trading_kernel.domain.commands import ExchangeCommand, ExchangeCommandKind as K, ExchangeCommandStatus as S, OrderCommandPayload
    def make(kind, oid, client, payload):
        return ExchangeCommand(command_id=client, ticket_identity=a.identity, management_revision=1,
            kind=kind, generation=1, idempotency_key=client, venue_client_order_id=client, payload=payload,
            status=S.ACCEPTED, created_at_ms=1000, deadline_at_ms=30000)
    return (
        make(K.INITIAL_STOP, a.active_stop_exchange_order_id, 'stop-client', OrderCommandPayload(side='sell',
            quantity=a.position_qty, order_type='stop_market', reduce_only=False, close_position=True, stop_price=a.active_stop_price)),
        make(K.TAKE_PROFIT, a.tp1_exchange_order_id, 'tp-client', OrderCommandPayload(side='sell', quantity=a.tp1_target_qty,
            order_type='limit', reduce_only=True, limit_price=a.ticket.take_profit_prices[0], time_in_force='GTC')),
    )


@pytest.mark.asyncio
async def test_owner_facts_require_exact_close_all_protection_and_tp_terms():
    a = aggregate()
    state = OwnerReductionState(operation_id='op', preview=preview(a), phase=OwnerReductionPhase.PREVIEWED)
    reader = Reader(a)
    refs = { 'stop-client': a.active_stop_exchange_order_id, 'tp-client': a.tp1_exchange_order_id }
    o = await collect_owner_reduction(reader, aggregate=a, state=state, authorization_id='auth',
        commands=commands(a), accepted_order_ids=refs, clock_ms=lambda: 5000)
    assert o.protection_close_position
    assert o.facts.protected_quantity == a.position_qty
    assert o.facts.tp_state == 'open'
    reader.stop_changes['clientAlgoId'] = 'external'
    with pytest.raises(ValueError, match='identity'):
        await collect_owner_reduction(reader, aggregate=a, state=state, authorization_id='auth',
            commands=commands(a), accepted_order_ids=refs, clock_ms=lambda: 5000)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['missing','cancelled','quantity','price','client','duplicate','reference_price','price_protect','child'])
async def test_newer_open_order_snapshot_must_confirm_the_exact_live_stop(change):
    a=aggregate()
    state=OwnerReductionState(operation_id='op',preview=preview(a),phase=OwnerReductionPhase.PREVIEWED)
    class SnapshotReader(Reader):
        async def read(self,name,params):
            if name=='algos':
                stop=await super().read('algo_order',{})
                if change=='missing':return []
                if change=='cancelled':stop={**stop,'algoStatus':'CANCELED'}
                if change=='quantity':stop={**stop,'quantity':'.001'}
                if change=='price':stop={**stop,'triggerPrice':'58000'}
                if change=='client':stop={**stop,'clientAlgoId':'external'}
                if change=='reference_price':stop={**stop,'workingType':'MARK_PRICE'}
                if change=='price_protect':stop={**stop,'priceProtect':True}
                if change=='child':stop={**stop,'actualOrderId':'triggered-child'}
                return [stop,stop] if change=='duplicate' else [stop]
            return await super().read(name,params)
    with pytest.raises(ValueError,match='stop_snapshot'):
        await collect_owner_reduction(SnapshotReader(a),aggregate=a,state=state,authorization_id='auth',
            commands=commands(a),accepted_order_ids={'stop-client':a.active_stop_exchange_order_id,'tp-client':a.tp1_exchange_order_id},clock_ms=lambda:5000)
