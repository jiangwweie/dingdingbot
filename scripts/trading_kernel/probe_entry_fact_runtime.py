#!/usr/bin/env python3
"""Read both real Entry fact phases under certified timing, with GET-only transport."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.entry_fact_collection import collect_entry_facts
from src.trading_kernel.application.runtime_facts import (
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
)
from src.trading_kernel.infrastructure.entry_runtime_contract import (
    ENTRY_ACTION_FACT_VALIDITY_MS,
    ENTRY_TIMEOUT_SECONDS,
    require_entry_runtime_contract,
)


async def probe_entry_fact_runtime(source: EntryFactsSource, *, account_id: str,
                                   members: tuple[str, ...]) -> dict:
    if not members or len(members) > 70 or len(set(members)) != len(members):
        raise ValueError("Entry probe requires exact bounded members")
    rows=[]
    for instrument in members:
        for phase in ("admission", "dispatch"):
            start=int(time.time()*1000)
            args={"venue_id":"binance-usdm", "account_id":account_id,
                  "exchange_instrument_id":instrument, "observed_at_ms":start,
                  "valid_for_ms":ENTRY_ACTION_FACT_VALIDITY_MS}
            facts=await collect_entry_facts(source,
                snapshot_request=EntryAdmissionSnapshotRequest.model_validate(args),
                rules_request=InstrumentRulesRequest.model_validate(args),product_request=None,
                timeout_seconds=ENTRY_TIMEOUT_SECONDS,phase=phase,identity=instrument)
            finished=int(time.time()*1000)
            if min(facts.snapshot.valid_until_ms,facts.rules.valid_until_ms)<=finished:
                raise ValueError("Entry probe returned expired facts")
            rows.append({"instrument":instrument,"phase":phase,"started_at_ms":start,
                         "elapsed_ms":finished-start,"remaining_validity_ms":min(facts.snapshot.valid_until_ms,facts.rules.valid_until_ms)-finished})
    return {"status":"pass","account_id":account_id,"members":members,
            "timeout_seconds":ENTRY_TIMEOUT_SECONDS,"fact_validity_ms":ENTRY_ACTION_FACT_VALIDITY_MS,
            "round_count":len(rows),"rounds":rows,"observed_at_ms":int(time.time()*1000)}


async def main() -> None:
    from scripts.trading_kernel.probe_production_runtime import (
        load_entry_recovery_probe_manifest,
    )
    from src.trading_kernel.infrastructure.production_runtime import (
        ProductionRuntimeSettings,
        build_binance_usdm_venue_adapter,
    )

    settings=ProductionRuntimeSettings.from_environment()
    require_entry_runtime_contract(timeout_seconds=settings.timeout_seconds,
        validity_ms=int(os.environ.get("TRADING_KERNEL_ACTION_FACT_VALIDITY_MS","0")))
    members=await load_entry_recovery_probe_manifest(os.environ["TRADING_KERNEL_DATABASE_URL"])
    adapter=build_binance_usdm_venue_adapter()
    exchange=cast(Any, next(iter(adapter._exchanges.values())))
    fetch2=exchange.fetch2
    async def readonly(path,api="public",method="GET",params=None,headers=None,body=None,config=None):
        if method!="GET":
            raise RuntimeError("Entry diagnostic forbids exchange mutation")
        return await fetch2(path,api,method,params or {},headers,body,config or {})
    exchange.fetch2=readonly
    try:
        print(json.dumps(await probe_entry_fact_runtime(adapter,account_id=settings.account_id,members=members)))
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
