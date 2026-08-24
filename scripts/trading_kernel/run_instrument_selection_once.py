#!/usr/bin/env python3
"""Run one bounded Dynamic Selection Plane attempt and print display-only JSON."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.application.run_instrument_selection import (
    RunInstrumentSelectionRequest,
    run_instrument_selection_once,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.production_runtime import (
    build_binance_usdm_market_source,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL"),
    )
    parser.add_argument(
        "--selection-spec-id",
        default="sor-dynamic-selection-v0",
    )
    parser.add_argument("--session-start-ms", required=True, type=int)
    parser.add_argument("--worker-id", default="selection-runner:manual-once")
    parser.add_argument("--max-concurrency", default=6, type=int)
    return parser


async def _run(args: argparse.Namespace) -> int:
    database_url = str(args.database_url or "").strip()
    if not database_url:
        raise ValueError("TRADING_KERNEL_DATABASE_URL or --database-url is required")
    engine = create_async_engine(database_url)
    market_source = build_binance_usdm_market_source()
    try:
        result = await run_instrument_selection_once(
            uow_factory=lambda: PostgresKernelUnitOfWork(engine),
            market_source=market_source,
            request=RunInstrumentSelectionRequest(
                selection_spec_id=args.selection_spec_id,
                session_start_ms=args.session_start_ms,
                worker_id=args.worker_id,
                max_concurrency=args.max_concurrency,
            ),
            clock_ms=lambda: int(time.time() * 1_000),
        )
        print(json.dumps(result.model_dump(), sort_keys=True))
        return 0 if result.outcome in {"SNAPSHOT_READY", "ALREADY_READY"} else 2
    finally:
        await market_source.close()
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
