import asyncio
import json
from types import SimpleNamespace

import pytest

from src.trading_kernel.application.entry_fact_collection import collect_entry_facts


@pytest.mark.asyncio
async def test_failed_fact_stage_cancels_and_awaits_sibling_without_leaking_secret(caplog):
    cancelled = asyncio.Event()

    class Source:
        async def read_entry_admission_snapshot(self, request):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def read_instrument_rules(self, request):
            await asyncio.sleep(0)
            raise ValueError("api-key-do-not-log")

    with pytest.raises(ValueError):
        await collect_entry_facts(Source(), snapshot_request=SimpleNamespace(),
            rules_request=SimpleNamespace(), product_request=None,
            timeout_seconds=0.1, phase="admission", identity="signal:regression")
    assert cancelled.is_set()
    assert "api-key-do-not-log" not in caplog.text
    row=json.loads(caplog.records[-1].message)
    assert row["phase"] == "admission"
    assert row["identity"] == "signal:regression"
    assert row["error_type"] == "ValueError"
    assert row["stages"]["rules"]["status"] == "ValueError"


@pytest.mark.asyncio
async def test_timeout_and_next_collection_have_independent_context(caplog):
    class Source:
        async def read_entry_admission_snapshot(self, request):
            await asyncio.Event().wait()
        async def read_instrument_rules(self, request):
            return "rules"

    for phase in ("admission", "dispatch"):
        with pytest.raises(TimeoutError):
            await collect_entry_facts(Source(), snapshot_request=SimpleNamespace(),
                rules_request=SimpleNamespace(), product_request=None,
                timeout_seconds=0.001, phase=phase, identity="signal:timeout")
    rows=[json.loads(r.message) for r in caplog.records]
    assert [r["phase"] for r in rows] == ["admission", "dispatch"]
    assert all(r["error_type"] == "TimeoutError" for r in rows)


@pytest.mark.asyncio
async def test_read_diagnostics_separates_http_from_throttle_without_urls(caplog):
    from src.trading_kernel.infrastructure.entry_read_telemetry import (
        instrument_entry_reads,
    )

    class Exchange:
        async def throttle(self, cost=None):
            await asyncio.sleep(0.002)
        async def fetch(self, *args, **kwargs):
            await asyncio.sleep(0.002)

    exchange=Exchange()
    instrument_entry_reads(exchange)

    class Source:
        async def read_entry_admission_snapshot(self, request):
            await exchange.throttle(40)
            await exchange.fetch("https://secret/?signature=do-not-log")
            raise TimeoutError("secret-url")
        async def read_instrument_rules(self, request):
            return "rules"

    with pytest.raises(TimeoutError):
        await collect_entry_facts(Source(), snapshot_request=SimpleNamespace(),
            rules_request=SimpleNamespace(), product_request=None,
            timeout_seconds=0.1, phase="dispatch", identity="command:timed")
    row=json.loads(caplog.records[-1].message)
    assert row["throttle_wait_ms"] >= 1
    assert row["http_ms"] >= 1
    assert row["http_reads"] == 1
    assert "signature" not in caplog.text
