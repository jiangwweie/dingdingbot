#!/usr/bin/env python3
"""Run one complete ENTRY or protected-lifecycle worker tick."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
from pathlib import Path
import sys
import time
from typing import Callable, Literal, cast

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.ports import VenuePort  # noqa: E402
from src.trading_kernel.application.runtime_facts import (  # noqa: E402
    EntryFactsSource,
    LifecycleFactsSource,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.entry_worker import (  # noqa: E402
    EntryWorkerRequest,
    EntryWorkerResult,
    run_entry_worker_once,
)
from src.trading_kernel.interfaces.lifecycle_worker import (  # noqa: E402
    LifecycleWorkerRequest,
    LifecycleWorkerResult,
    run_lifecycle_worker_once,
)
from src.trading_kernel.interfaces.worker_process import (  # noqa: E402
    run_worker_process,
)


WorkerRole = Literal["entry", "lifecycle"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument("--venue-factory", required=True, help="module:callable")
    parser.add_argument(
        "--worker-role",
        required=True,
        choices=("entry", "lifecycle"),
    )
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
    parser.add_argument("--lease-ms", type=int, default=30_000)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--admission-snapshot-validity-ms", type=int, default=5_000)
    parser.add_argument("--idle-poll-interval-ms", type=int, default=2_000)
    parser.add_argument("--run-forever", action="store_true")
    parser.add_argument("--poll-interval-ms", type=int, default=2_000)
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
    if args.lease_ms <= 0:
        raise ValueError("lease-ms must be positive")

    adapter = _load_factory(args.venue_factory)()
    if inspect.isawaitable(adapter):
        adapter = await adapter
    if not callable(getattr(adapter, "execute", None)):
        raise TypeError("venue factory must return a VenuePort")
    venue_port = cast(VenuePort, adapter)

    engine = create_async_engine(database_url)
    try:
        role = cast(WorkerRole, args.worker_role)
        if role == "entry" and not callable(
            getattr(adapter, "read_entry_admission_snapshot", None)
        ):
            raise TypeError("ENTRY venue factory must provide EntryAdmissionFactsSource")
        if role == "entry" and not callable(
            getattr(adapter, "read_instrument_rules", None)
        ):
            raise TypeError("ENTRY venue factory must provide InstrumentRulesSource")
        if role == "lifecycle" and not callable(
            getattr(adapter, "read_lifecycle_facts", None)
        ):
            raise TypeError(
                "lifecycle venue factory must provide LifecycleFactsSource"
            )

        async def tick() -> EntryWorkerResult | LifecycleWorkerResult:
            now_ms = args.now_ms or int(time.time() * 1_000)
            if role == "entry":
                return await run_entry_worker_once(
                    lambda: PostgresKernelUnitOfWork(engine),
                    venue_port,
                    cast(EntryFactsSource, adapter),
                    EntryWorkerRequest(
                        worker_id=args.worker_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        now_ms=now_ms,
                        lease_until_ms=now_ms + args.lease_ms,
                        timeout_seconds=args.timeout_seconds,
                        admission_snapshot_validity_ms=(
                            args.admission_snapshot_validity_ms
                        ),
                    ),
                )
            return await run_lifecycle_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                venue_port,
                cast(LifecycleFactsSource, adapter),
                LifecycleWorkerRequest(
                    worker_id=args.worker_id,
                    runtime_commit=args.runtime_commit,
                    schema_revision=args.schema_revision,
                    now_ms=now_ms,
                    lease_until_ms=now_ms + args.lease_ms,
                    timeout_seconds=args.timeout_seconds,
                    idle_poll_interval_ms=args.idle_poll_interval_ms,
                ),
            )

        idle_statuses = (
            {"no_candidate", "entry_lane_busy"}
            if role == "entry"
            else {"no_work", "no_change"}
        )
        return await run_worker_process(
            tick,
            run_forever=args.run_forever,
            poll_interval_ms=args.poll_interval_ms,
            idle_log_interval_ms=args.idle_log_interval_ms,
            idle_statuses=idle_statuses,
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
