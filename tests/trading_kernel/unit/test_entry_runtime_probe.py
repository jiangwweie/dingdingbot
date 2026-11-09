import asyncio
import time

import pytest

from scripts.trading_kernel.probe_entry_fact_runtime import probe_entry_fact_runtime
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from tests.trading_kernel.support.capacity import rules, snapshot


@pytest.mark.asyncio
async def test_probe_requires_both_actual_read_rounds_and_original_fact_expiry():
    calls=[]

    class Source:
        async def read_entry_admission_snapshot(self, request):
            calls.append(("snapshot",request.exchange_instrument_id,request.observed_at_ms))
            base=snapshot()
            window={"observed_at_ms":request.observed_at_ms,"valid_until_ms":request.observed_at_ms+request.valid_for_ms}
            return base.model_copy(update={**window,"account_risk_snapshot":base.account_risk_snapshot.model_copy(update=window)})
        async def read_instrument_rules(self, request):
            calls.append(("rules",request.exchange_instrument_id,request.observed_at_ms))
            return InstrumentRulesFacts.model_validate({k:v for k,v in rules().model_dump().items() if k in InstrumentRulesFacts.model_fields}).model_copy(update={"valid_until_ms":request.observed_at_ms+request.valid_for_ms})

    result=await probe_entry_fact_runtime(Source(),account_id="account",members=("binance-usdm:SOLUSDT:perpetual",))
    assert result["status"]=="pass"
    assert result["round_count"]==2
    assert len(calls)==4

    class Expired(Source):
        async def read_instrument_rules(self, request):
            return InstrumentRulesFacts.model_validate({k:v for k,v in rules().model_dump().items() if k in InstrumentRulesFacts.model_fields}).model_copy(update={"valid_until_ms":int(time.time()*1000)-1})

    with pytest.raises(ValueError,match="expired"):
        await probe_entry_fact_runtime(Expired(),account_id="account",members=("binance-usdm:SOLUSDT:perpetual",))


@pytest.mark.asyncio
async def test_probe_failure_does_not_advance_to_next_member():
    calls=[]
    class Source:
        async def read_entry_admission_snapshot(self, request):
            calls.append(request.exchange_instrument_id)
            raise TimeoutError("private transport input")
        async def read_instrument_rules(self, request):
            await asyncio.sleep(1)
    with pytest.raises(TimeoutError):
        await probe_entry_fact_runtime(Source(),account_id="account",members=("binance-usdm:SOLUSDT:perpetual","binance-usdm:ETHUSDT:perpetual"))
    assert calls==["binance-usdm:SOLUSDT:perpetual"]
