"""Production-shaped queue regression: real CCXT weights and FIFO throttler."""

import asyncio
import time

import pytest
from ccxt.async_support import binanceusdm
from ccxt.async_support.base.throttler import Throttler

from src.trading_kernel.application.entry_fact_collection import collect_entry_facts
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    InstrumentRulesRequest,
)
from src.trading_kernel.infrastructure.entry_runtime_contract import (
    ENTRY_ACTION_FACT_VALIDITY_MS,
    ENTRY_TIMEOUT_SECONDS,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from tests.trading_kernel.support.venue_adapter import (
    AdmissionSnapshotExchange,
    InstrumentRulesExchange,
)


@pytest.mark.asyncio
async def test_real_weighted_queue_old_budget_times_out_then_two_new_reads_remain_fresh():
    exchange = AdmissionSnapshotExchange()
    limiter = Throttler({"refillRate": 1/50})
    description = binanceusdm().describe()["api"]
    routes = {
        "fetch_order_book": ("fapiPublic", "depth", {"limit": 5}),
        "fetch_open_orders": ("fapiPrivate", "openOrders", {}),
        "fetch_position_mode": ("fapiPrivate", "positionSide/dual", {}),
        "fapiPrivateV2GetAccount": ("fapiPrivateV2", "account", {}),
        "fapiPrivateV2GetPositionRisk": ("fapiPrivateV2", "positionRisk", {}),
        "fapiPrivateGetLeverageBracket": ("fapiPrivate", "leverageBracket", {}),
    }
    rules = InstrumentRulesExchange()
    rules.loaded = True
    exchange.market = lambda symbol: rules.market("BTC/USDT:USDT")

    async def brackets(params):
        rows=await rules.fapiPrivateGetLeverageBracket({"symbol":"BTCUSDT"})
        rows[0]["symbol"]="SOLUSDT"
        return rows

    exchange.fapiPrivateGetLeverageBracket = brackets
    completed=[]

    def charged(name, original):
        async def call(*args):
            api,path,_params = routes[name]
            if name == "fetch_open_orders" and args[3]["conditional"]:
                path="openAlgoOrders"
            config=description[api]["get"][path]
            cost=config if isinstance(config,(int,float)) else config.get("noSymbol",config.get("cost",1))
            await limiter(cost)
            value=await original(*args)
            completed.append(name)
            return value
        return call

    for name in routes:
        setattr(exchange,name,charged(name,getattr(exchange,name)))
    adapter=CcxtVenueAdapter(exchanges={("binance-usdm","experiment-1"):exchange}, clock_ms=lambda:int(time.time()*1000))

    async def read(timeout,validity,phase):
        now=int(time.time()*1000)
        args={"venue_id":"binance-usdm","account_id":"experiment-1",
            "exchange_instrument_id":"binance-usdm:SOLUSDT:perpetual","observed_at_ms":now,"valid_for_ms":validity}
        return await collect_entry_facts(adapter,snapshot_request=EntryAdmissionSnapshotRequest(**args),
            rules_request=InstrumentRulesRequest(**args),product_request=None,
            timeout_seconds=timeout,phase=phase,identity="signal:weighted-queue")

    with pytest.raises(TimeoutError):
        await read(5,5000,"admission")
    for phase in ("admission","dispatch"):
        previous_account_reads=completed.count("fapiPrivateV2GetAccount")
        facts=await read(ENTRY_TIMEOUT_SECONDS,ENTRY_ACTION_FACT_VALIDITY_MS,phase)
        snapshot,rule_facts=facts.snapshot,facts.rules
        now=int(time.time()*1000)
        assert snapshot.observed_at_ms < now < snapshot.valid_until_ms
        assert rule_facts.observed_at_ms < now < rule_facts.valid_until_ms
        assert len(snapshot.open_orders)==2  # Both account-wide order namespaces survive.
        assert completed.count("fapiPrivateV2GetAccount")==previous_account_reads+1
    while limiter.running:
        await asyncio.sleep(0.01)
