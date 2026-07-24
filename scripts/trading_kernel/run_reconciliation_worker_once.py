#!/usr/bin/env python3
"""Run one venue-truth, reconciliation, settlement, or review worker tick."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
from pathlib import Path
import sys
import time
from typing import Callable, cast

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.ports import VenueTruthPort  # noqa: E402
from src.trading_kernel.application.runtime_facts import (  # noqa: E402
    PositionSnapshotSource,
    ReviewEconomicsSource,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.reconciliation_worker import (  # noqa: E402
    ReconciliationWorkerRequest,
    run_reconciliation_worker_once,
)
from src.trading_kernel.interfaces.worker_process import (  # noqa: E402
    run_worker_process,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument("--venue-factory", required=True, help="module:callable")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    parser.add_argument(
        "--schema-revision",
        default=os.getenv("TRADING_KERNEL_SCHEMA_REVISION", ""),
    )
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--unknown-visibility-grace-ms", type=int, default=30_000)
    parser.add_argument("--idle-poll-interval-ms", type=int, default=2_000)
    parser.add_argument("--run-forever", action="store_true")
    parser.add_argument("--poll-interval-ms", type=int, default=5_000)
    parser.add_argument("--idle-log-interval-ms", type=int, default=300_000)
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
    if args.run_forever and args.now_ms is not None:
        raise ValueError("fixed now-ms is incompatible with run-forever")

    adapter = _load_factory(args.venue_factory)()
    if inspect.isawaitable(adapter):
        adapter = await adapter
    if not callable(getattr(adapter, "lookup_command_truth", None)):
        raise TypeError("venue factory must provide VenueTruthPort")
    if not callable(getattr(adapter, "read_position_snapshot", None)):
        raise TypeError("venue factory must provide PositionSnapshotSource")
    if not callable(getattr(adapter, "read_review_economics", None)):
        raise TypeError("venue factory must provide ReviewEconomicsSource")

    engine = create_async_engine(database_url)
    try:
        async def tick():
            now_ms = args.now_ms or int(time.time() * 1_000)
            return await run_reconciliation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                cast(VenueTruthPort, adapter),
                cast(PositionSnapshotSource, adapter),
                ReconciliationWorkerRequest(
                    worker_id=args.worker_id,
                    runtime_commit=args.runtime_commit,
                    schema_revision=args.schema_revision,
                    now_ms=now_ms,
                    timeout_seconds=args.timeout_seconds,
                    unknown_visibility_grace_ms=(
                        args.unknown_visibility_grace_ms
                    ),
                    idle_poll_interval_ms=args.idle_poll_interval_ms,
                ),
                review_economics_source=cast(ReviewEconomicsSource, adapter),
            )

        return await run_worker_process(
            tick,
            run_forever=args.run_forever,
            poll_interval_ms=args.poll_interval_ms,
            idle_log_interval_ms=args.idle_log_interval_ms,
            idle_statuses={"no_work"},
        )
    finally:
        close = getattr(adapter, "close", None)
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
