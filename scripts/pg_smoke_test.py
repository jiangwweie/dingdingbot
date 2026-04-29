#!/usr/bin/env python3
"""PG Repository smoke test for migration validation."""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.database import probe_pg_connectivity, get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_runtime_profile_repository import PgRuntimeProfileRepository
from src.infrastructure.pg_research_repository import PgResearchRepository
from src.infrastructure.pg_backtest_repository import PgBacktestReportRepository
from src.infrastructure.pg_historical_data_repository import PgHistoricalDataRepository
from src.infrastructure.pg_signal_repository import PgSignalRepository
from src.infrastructure.pg_order_repository import PgOrderRepository


async def main():
    print("=" * 60)
    print("PG Repository Smoke Test")
    print("=" * 60)

    # 1. probe_pg_connectivity
    print("\n[1] probe_pg_connectivity()")
    try:
        result = await probe_pg_connectivity()
        print(f"    ✓ Result: {result}")
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return

    # Initialize PG
    await init_pg_core_db()

    # 2. PgRuntimeProfileRepository.get_active_profile
    print("\n[2] PgRuntimeProfileRepository.get_active_profile()")
    try:
        repo = PgRuntimeProfileRepository()
        await repo.initialize()
        profile = await repo.get_active_profile()
        print(f"    ✓ Result: {profile}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 3. PgResearchRepository.list_jobs
    print("\n[3] PgResearchRepository.list_jobs()")
    try:
        repo = PgResearchRepository()
        await repo.initialize()
        jobs, total = await repo.list_jobs(limit=5)
        print(f"    ✓ Result: {len(jobs)} jobs / total={total}")
        if jobs:
            print(f"    Sample: {jobs[0].id}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 4. PgResearchRepository.list_run_results
    print("\n[4] PgResearchRepository.list_run_results()")
    try:
        repo = PgResearchRepository()
        await repo.initialize()
        results, total = await repo.list_run_results(limit=5)
        print(f"    ✓ Result: {len(results)} results / total={total}")
        if results:
            print(f"    Sample: {results[0].id}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 5. PgResearchRepository.list_candidates
    print("\n[5] PgResearchRepository.list_candidates()")
    try:
        repo = PgResearchRepository()
        await repo.initialize()
        candidates, total = await repo.list_candidates(limit=5)
        print(f"    ✓ Result: {len(candidates)} candidates / total={total}")
        if candidates:
            print(f"    Sample: {candidates[0].id}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 6. PgBacktestReportRepository.list_reports
    print("\n[6] PgBacktestReportRepository.list_reports()")
    try:
        repo = PgBacktestReportRepository()
        await repo.initialize()
        reports = await repo.list_reports(page_size=5)
        items = reports.get("reports", [])
        print(f"    ✓ Result: {len(items)} reports / total={reports.get('total')}")
        if items:
            print(f"    Sample: {items[0]['id']}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 7. PgHistoricalDataRepository.get_kline_range
    print("\n[7] PgHistoricalDataRepository.get_kline_range('ETH/USDT:USDT', '1h')")
    try:
        repo = PgHistoricalDataRepository()
        await repo.initialize()
        first_ts, last_ts = await repo.get_kline_range("ETH/USDT:USDT", "1h")
        print(f"    ✓ Result: first_ts={first_ts}, last_ts={last_ts}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 8. PgSignalRepository.get_signals
    print("\n[8] PgSignalRepository.get_signals(limit=2)")
    try:
        repo = PgSignalRepository()
        await repo.initialize()
        signals = await repo.get_signals(limit=2)
        data = signals.get("data", [])
        print(f"    ✓ Result: {len(data)} signals / total={signals.get('total')}")
        if data:
            print(f"    Sample: {data[0]['signal_id']}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # 9. PgOrderRepository.get_orders
    print("\n[9] PgOrderRepository.get_orders(limit=2)")
    try:
        repo = PgOrderRepository()
        await repo.initialize()
        result = await repo.get_orders(limit=2)
        orders = result.get("items", [])
        print(f"    ✓ Result: {len(orders)} orders")
        if orders:
            sample = orders[0]
            try:
                sample_id = sample.id
            except Exception:
                sample_id = str(sample)
            print(f"    Sample: {sample_id}")
        await repo.close()
    except Exception as e:
        print(f"    ✗ Error: {e}")

    print("\n" + "=" * 60)
    print("Smoke test completed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
