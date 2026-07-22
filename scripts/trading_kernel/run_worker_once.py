#!/usr/bin/env python3
"""Run one bounded trading-kernel action and print its current result."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.runtime import RuntimeTickRequest  # noqa: E402
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.worker import run_worker_once  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument("--venue-factory", required=True, help="module:callable")
    parser.add_argument("--monitor-key", required=True)
    parser.add_argument("--owner-policy-id", required=True)
    parser.add_argument("--ticket-id")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--lease-ms", type=int, default=30_000)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser


def _load_factory(spec: str) -> Callable[[], object]:
    module_name, separator, attribute_name = spec.partition(":")
    if not separator or not module_name.strip() or not attribute_name.strip():
        raise ValueError("venue factory must use module:callable")
    factory = getattr(importlib.import_module(module_name), attribute_name)
    if not callable(factory):
        raise TypeError("venue factory target is not callable")
    return factory


async def _run(args: argparse.Namespace) -> int:
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    now_ms = args.now_ms or int(time.time() * 1_000)
    if args.lease_ms <= 0:
        raise ValueError("lease-ms must be positive")

    venue = _load_factory(args.venue_factory)()
    if inspect.isawaitable(venue):
        venue = await venue
    if not callable(getattr(venue, "execute", None)):
        raise TypeError("venue factory must return a VenuePort")

    engine = create_async_engine(database_url)
    try:
        result = await run_worker_once(
            lambda: PostgresKernelUnitOfWork(engine),
            venue,
            RuntimeTickRequest(
                monitor_key=args.monitor_key,
                owner_policy_id=args.owner_policy_id,
                ticket_id=args.ticket_id,
                worker_id=args.worker_id,
                now_ms=now_ms,
                lease_until_ms=now_ms + args.lease_ms,
                timeout_seconds=args.timeout_seconds,
            ),
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False))
        return 0
    finally:
        close = getattr(venue, "close", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
