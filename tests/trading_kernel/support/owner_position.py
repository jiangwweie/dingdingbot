"""Raw exchange-shaped Owner position reader; never invents historical TP orders."""

import json
from pathlib import Path

from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)


class ProtectedPositionReader:
    def __init__(self, aggregate):
        self.a = aggregate
        self.position_amount = str(aggregate.position_qty)
        fixtures = Path(__file__).resolve().parents[1] / 'fixtures/management_protocol_v2'
        self.stop = json.loads((fixtures / 'bnb_stop_cancelled.json').read_text())
        self.stop.update(algoId=aggregate.active_stop_exchange_order_id,
            clientAlgoId='stop-client', symbol='BTCUSDT', side='SELL', positionSide='LONG',
            quantity='0', closePosition=True, reduceOnly=False, triggerPrice=str(aggregate.active_stop_price),
            algoStatus='NEW', createTime=2000, updateTime=3000, actualQty='0')
        self.command = ExchangeCommand(command_id='stop-client', ticket_identity=aggregate.identity,
            management_revision=1, kind=ExchangeCommandKind.INITIAL_STOP, generation=1,
            idempotency_key='stop-client', venue_client_order_id='stop-client',
            payload=OrderCommandPayload(side='sell', quantity=aggregate.position_qty,
                order_type='stop_market', reduce_only=False, close_position=True,
                stop_price=aggregate.active_stop_price), status=ExchangeCommandStatus.ACCEPTED,
            created_at_ms=1500, deadline_at_ms=30000)

    async def read(self, name, params):
        if name == 'algo_order':
            return self.stop
        if name == 'algos':
            return [self.stop]
        if name == 'orders':
            return []
        if name == 'mode':
            return {'dualSidePosition': True}
        if name == 'positions':
            return [{'symbol': 'BTCUSDT', 'positionSide': 'LONG', 'positionAmt': self.position_amount}]
        if name == 'ticker':
            return {'symbol': 'BTCUSDT', 'price': str(self.a.average_fill_price), 'time': 5000}
        raise AssertionError(name)
