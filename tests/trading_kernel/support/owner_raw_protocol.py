"""Exchange-shaped recording venue for PG -> collectors -> durable Owner commands."""

import json
from decimal import Decimal
from pathlib import Path

from src.trading_kernel.application.maintain_ticket_lifecycle import (
    TicketLifecycleFacts,
)
from src.trading_kernel.domain.commands import (
    CancelCommandPayload,
    ExchangeCommandResult,
)
from src.trading_kernel.domain.commands import ExchangeCommandKind as K
from src.trading_kernel.domain.commands import ExchangeCommandStatus as S
from src.trading_kernel.domain.exit_policy import LifecycleMarketFacts
from src.trading_kernel.infrastructure.owner_position_source import (
    collect_owner_position,
)
from src.trading_kernel.infrastructure.owner_reduction_source import (
    collect_owner_reduction,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures/management_protocol_v2'


class RawOwnerProtocol:
    def __init__(self, engine, quantity):
        self.engine = engine
        self.quantity = quantity
        self.at = 7000
        self.commands = ()
        self.refs = {}
        self.executed = {}
        self.cancelled = set()
        self.writes = []
        self.reads = []
        self.a = None
        self.fault = None

    def load(self, aggregate, commands, accepted_order_ids):
        self.a, self.commands, self.refs = aggregate, commands, accepted_order_ids

    def row(self, command):
        p = command.payload
        conditional = p.order_type in {'stop_market', 'take_profit_market'}
        oid = self.refs[command.command_id]
        row = json.loads((FIXTURES / ('bnb_stop_cancelled.json' if conditional else 'bnb_app_exit.json')).read_text())
        row.update(symbol='BTCUSDT', side=p.side.upper(), positionSide='LONG',
            price=str(p.limit_price or 0), reduceOnly=p.reduce_only,
            closePosition=p.close_position, timeInForce=p.time_in_force or 'GTC',
            workingType='CONTRACT_PRICE', priceProtect=False, priceMatch='NONE',
            selfTradePreventionMode='NONE', goodTillDate=0,
            updateTime=max(command.created_at_ms, self.at - 1))
        if conditional:
            row.update(algoId=oid, clientAlgoId=command.venue_client_order_id,
                orderType=p.order_type.upper(), quantity=str(0 if p.close_position else p.quantity),
                triggerPrice=str(p.stop_price), actualQty='0', actualOrderId='',
                algoStatus='CANCELED' if oid in self.cancelled else 'NEW',
                createTime=command.created_at_ms)
        else:
            fill = self.executed.get(command.command_id, Decimal(0))
            row.update(orderId=oid, clientOrderId=command.venue_client_order_id,
                type=p.order_type.upper(), origQty=str(p.quantity), executedQty=str(fill),
                status='FILLED' if fill == p.quantity else 'CANCELED' if oid in self.cancelled else 'NEW',
                stopPrice='0', time=command.created_at_ms)
        return row

    async def read(self, name, params):
        self.reads.append(name)
        selected = [c for c in self.commands if c.command_id in self.refs and c.kind is not K.CANCEL_ORDER]
        if name in {'algo_order', 'order', 'trades'}:
            oid = str(params.get('algoId') or params.get('orderId'))
            command = next(c for c in selected if self.refs[c.command_id] == oid)
            if name == 'trades':
                return [{'id': 'trade:' + command.command_id, 'orderId': oid,
                    'symbol': 'BTCUSDT', 'positionSide': 'LONG', 'side': 'SELL',
                    'qty': str(self.executed[command.command_id]), 'price': '61000',
                    'time': self.at - 2}]
            return self.row(command)
        if name == 'orders':
            return [self.row(c) for c in selected if c.kind is K.TAKE_PROFIT
                and self.refs[c.command_id] == self.a.tp1_exchange_order_id
                and self.refs[c.command_id] not in self.cancelled]
        if name == 'algos':
            if self.fault == 'missing_stop':
                return []
            return [self.row(c) for c in selected if self.refs[c.command_id] == self.a.active_stop_exchange_order_id]
        if name == 'positions':
            return [{'symbol': 'BTCUSDT', 'positionSide': 'LONG', 'positionAmt': str(self.quantity)}]
        if name == 'mode':
            return {'dualSidePosition': True}
        if name == 'ticker':
            return {'symbol': 'BTCUSDT', 'price': '61000', 'time': self.at}
        raise AssertionError(name)

    async def read_owner_position(self, *, aggregate, commands, accepted_order_ids, operation_id):
        self.load(aggregate, commands, accepted_order_ids)
        return await collect_owner_position(self, aggregate=aggregate, commands=commands,
            accepted_order_ids=accepted_order_ids, operation_id=operation_id, clock_ms=lambda: self.at)

    async def read_owner_reduction(self, *, aggregate, commands, accepted_order_ids, state, authorization_id):
        self.load(aggregate, commands, accepted_order_ids)
        return await collect_owner_reduction(self, aggregate=aggregate, commands=commands,
            accepted_order_ids=accepted_order_ids, state=state, authorization_id=authorization_id,
            clock_ms=lambda: self.at)

    async def read_lifecycle_facts(self, request):
        return TicketLifecycleFacts(position_quantity=self.quantity, tp1_filled_quantity=self.a.tp1_filled_qty,
            tp1_average_fill_price=self.a.ticket.take_profit_prices[0] if self.a.tp1_filled_qty else None, allocated_entry_fee_quote=Decimal(0), exit_taker_fee_rate=Decimal(0),
            price_tick=request.price_tick, observed_at_ms=self.at,
            market_facts=LifecycleMarketFacts(watermark_ms=self.at - 1,
                is_final_closed_candle=True, latest_close=Decimal(61000),
                structure_reference=Decimal(59000), atr=Decimal(1000), holding_bars=1))

    async def execute(self, request):
        # A separate connection proves the command claim committed before I/O.
        async with PostgresKernelUnitOfWork(self.engine) as u:
            command = await u.exchange_commands.get(request.command_id)
            assert command is not None and command.status is S.CLAIMED
            assert command.payload == request.payload
        self.writes.append(request)
        if isinstance(request.payload, CancelCommandPayload):
            oid = request.payload.exchange_order_id
            self.cancelled.add(oid)
        else:
            oid = 'owner-venue:' + request.command_id
            if request.kind is K.OWNER_REDUCE:
                self.quantity -= request.payload.quantity
                self.executed[request.command_id] = request.payload.quantity
        return ExchangeCommandResult(status=S.ACCEPTED, exchange_order_id=oid,
            observed_at_ms=self.at + 1)
