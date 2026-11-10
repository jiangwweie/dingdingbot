"""GET-only signed closure facts; no order, cancellation, transfer or stream API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import json
import time
import urllib.parse
from collections.abc import Callable
from decimal import Decimal
from typing import Any, ClassVar, Protocol, cast

from pydantic import SecretStr

from src.trading_kernel.domain.identities import NettingDomain
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.readonly_closure import (
    ClosureFill,
    ReadonlyClosureProof,
    TerminalOrder,
)
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_rest_order,
)


class ClosureReader(Protocol):
    async def read(self, name: str, params: dict[str, object]) -> object: ...


class BinanceClosureReader:
    ENDPOINTS: ClassVar[dict[str,str]] = {
        'positions':'/fapi/v3/positionRisk','orders':'/fapi/v1/openOrders',
        'algos':'/fapi/v1/openAlgoOrders','mode':'/fapi/v1/positionSide/dual',
        'all_orders':'/fapi/v1/allOrders','all_algos':'/fapi/v1/allAlgoOrders',
        'trades':'/fapi/v1/userTrades',
    }

    def __init__(self, *, api_key: SecretStr, api_secret: SecretStr):
        self.key=api_key
        self.secret=api_secret

    async def read(self,name: str,params: dict[str,object]) -> object:
        return await asyncio.to_thread(self._read,name,params)

    def _read(self,name: str,params: dict[str,object]) -> object:
        path=self.ENDPOINTS[name]
        query=urllib.parse.urlencode({**params,'timestamp':int(time.time()*1000),'recvWindow':5000})
        sig=hmac.new(self.secret.get_secret_value().encode(),query.encode(),hashlib.sha256).hexdigest()
        connection=http.client.HTTPSConnection('fapi.binance.com',timeout=10)
        try:
            connection.request('GET',path+'?'+query+'&signature='+sig,
                headers={'X-MBX-APIKEY':self.key.get_secret_value()})
            response=connection.getresponse()
            if response.status!=200:
                raise ValueError('readonly closure endpoint rejected')
            data=response.read(2*1024*1024+1)
            if len(data)>2*1024*1024:
                raise ValueError('readonly closure response exceeds bound')
            return json.loads(data)
        except (OSError,http.client.HTTPException,ValueError):
            raise ValueError('readonly closure facts unavailable: '+name) from None
        finally:
            connection.close()


async def collect_readonly_closure(reader: ClosureReader, *, ticket_id: str,
    domain: NettingDomain,entry_order_id: str,own_orders: frozenset[tuple[str,str]],
    since_ms: int,clock_ms: Callable[[],int]) -> ReadonlyClosureProof:
    start=clock_ms()
    if not 0<since_ms<=start or start-since_ms>3*86400000:
        raise ValueError('closure historical window unavailable')
    symbol=parse_binance_usdm_instrument_id(domain.exchange_instrument_id).symbol
    query={'symbol':symbol,'startTime':since_ms,'endTime':start,'limit':100}
    values=await asyncio.gather(*(reader.read(name,query if name in {'all_orders','all_algos','trades'} else {})
        for name in ['positions','orders','algos','mode','all_orders','all_algos','trades']))
    positions,orders,algos,mode,regular,conditional,trades=values
    if mode!={'dualSidePosition':True}:
        raise ValueError('closure requires independent sides')
    if any(not isinstance(v,list) for v in [positions,orders,algos,regular,conditional,trades]):
        raise ValueError('closure response shape differs')
    assert isinstance(positions,list) and isinstance(orders,list) and isinstance(algos,list)
    assert isinstance(regular,list) and isinstance(conditional,list) and isinstance(trades,list)
    if len(positions)>2000 or orders or algos or any(Decimal(str(p['positionAmt']))!=0 for p in positions):
        raise ValueError('closure requires globally flat order-free account')
    if any(len(v)>=100 for v in [regular,conditional,trades]):
        raise ValueError('closure history is truncated')
    rows=[r for r in regular if r['symbol']==symbol and r['positionSide'].lower()==domain.position_side]
    if len(rows)!=len(regular) or any(r['symbol']!=symbol for r in conditional):
        raise ValueError('closure history scope differs')
    if any(str(r.get('actualOrderId') or '') not in {'','0'} for r in conditional):
        raise ValueError('closure has triggered conditional child requiring exact attribution')
    exit_side='SELL' if domain.position_side=='long' else 'BUY'
    exits=[r for r in rows if r['side']==exit_side and r['status']=='FILLED'
        and ('regular',str(r['orderId'])) not in own_orders]
    if len(exits)!=1 or exits[0]['type']!='MARKET':
        raise ValueError('closure external exit is ambiguous')
    exit_id=str(exits[0]['orderId'])
    terminal=[]
    for ns,page,id_key,status_key,qty_key in [('regular',rows,'orderId','status','executedQty'),('conditional',conditional,'algoId','algoStatus','actualQty')]:
        for row in page:
            if row['positionSide'].lower()!=domain.position_side:
                raise ValueError('closure historical side differs')
            terminal.append(TerminalOrder.model_validate({'namespace':ns,'order_id':str(row[id_key]),
                'status':row[status_key],'executed_quantity':Decimal(str(row.get(qty_key,'0') or '0'))}))
    fills=[]
    for order_id,side in [(entry_order_id,'BUY' if domain.position_side=='long' else 'SELL'),(exit_id,exit_side)]:
        selected=[]
        for row in trades:
            if str(row['orderId'])!=order_id:
                continue
            if row['symbol']!=symbol or row['positionSide'].lower()!=domain.position_side or row['side']!=side:
                raise ValueError('closure fill identity differs')
            selected.append(ClosureFill(trade_id=str(row['id']),order_id=order_id,
                quantity=Decimal(str(row['qty'])),price=Decimal(str(row['price'])),occurred_at_ms=int(row['time'])))
        fills.append(tuple(selected))
    # Recheck current account state after historical I/O. These new observations
    # define current flatness, never reset timestamps of old market/entry facts.
    current_at=clock_ms()
    current=await asyncio.gather(*(reader.read(name,{}) for name in ['positions','orders','algos']))
    if not all(isinstance(v,list) for v in current) or current[1] or current[2] or any(Decimal(str(p['positionAmt']))!=0 for p in cast(list[dict[str,Any]],current[0])):
        raise ValueError('closure account changed during collection')
    return ReadonlyClosureProof(ticket_id=ticket_id,domain=domain,entry_order_id=entry_order_id,exit_order_id=exit_id,
        exit_evidence=parse_rest_order(exits[0],account_id=domain.account_id,conditional=False,received_at_ms=current_at,coverage_complete=True),
        entry_fills=fills[0],exit_fills=fills[1],terminal_orders=tuple(terminal),
        snapshot=PositionSnapshot(netting_domain=domain,quantity=Decimal(0),average_entry_price=None,
            open_orders=(),orders_complete=True,observed_at_ms=current_at),observed_at_ms=current_at,valid_until_ms=current_at+30000)
