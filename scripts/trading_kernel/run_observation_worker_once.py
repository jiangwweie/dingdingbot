#!/usr/bin/env python3
"""Run one PostgreSQL-selected closed-bar observation worker tick."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.market_ports import (
    InstrumentSelectionMarketSource,
    PublicMarketSource,
)
from src.trading_kernel.domain.instrument_selection import SOR_STRATEGY_GROUP_ID
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.authority_gap_audit_source import (
    PublicMarketAuthorityGapAuditSource,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerRequest,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.selection_runtime_worker import (
    SelectionRuntimeRequest,
    run_materialization_runtime_once,
    run_selection_runtime_once,
)
from src.trading_kernel.interfaces.worker_process import (
    WorkerProcessLoop,
    run_worker_process,
    run_worker_process_group,
)

_SELECTION_SPEC_ID = "sor-dynamic-selection-v0"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    parser.add_argument("--market-source-factory", required=True, help="module:callable")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--selection-worker-id")
    parser.add_argument("--materialization-worker-id")
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
    parser.add_argument("--retry-interval-ms", type=int, default=30_000)
    parser.add_argument("--run-forever", action="store_true")
    parser.add_argument("--poll-interval-ms", type=int, default=5_000)
    parser.add_argument("--selection-poll-interval-ms", type=int, default=5_000)
    parser.add_argument("--materialization-poll-interval-ms", type=int, default=2_000)
    parser.add_argument("--idle-log-interval-ms", type=int, default=300_000)
    return parser


def _load_factory(spec: str) -> Callable[[], object]:
    module_name, separator, attribute_name = spec.partition(":")
    if not separator or not module_name.strip() or not attribute_name.strip():
        raise ValueError("market source factory must use module:callable")
    factory = getattr(importlib.import_module(module_name), attribute_name)
    if not callable(factory):
        raise TypeError("market source factory target is not callable")
    return factory


async def _run(args: argparse.Namespace) -> int:
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    if args.run_forever and args.now_ms is not None:
        raise ValueError("fixed now-ms is incompatible with run-forever")
    if args.lease_ms <= 0:
        raise ValueError("lease-ms must be positive")
    if args.selection_poll_interval_ms <= 0 or args.materialization_poll_interval_ms <= 0:
        raise ValueError("Selection runtime poll intervals must be positive")

    source = _load_factory(args.market_source_factory)()
    if inspect.isawaitable(source):
        source = await source
    if not callable(getattr(source, "fetch_closed_candles", None)):
        raise TypeError("market source factory must return a PublicMarketSource")

    engine = create_async_engine(database_url)
    try:
        uow_factory = lambda: PostgresKernelUnitOfWork(engine)
        selection_worker_id = str(args.selection_worker_id or "").strip() or (
            f"{args.worker_id}:selection"
        )
        materialization_worker_id = str(
            args.materialization_worker_id or ""
        ).strip() or f"{args.worker_id}:materialization"
        audit_source = PublicMarketAuthorityGapAuditSource(
            cast(PublicMarketSource, source)
        )

        async def observation_tick():
            now_ms = args.now_ms or int(time.time() * 1_000)
            return await run_observation_worker_once(
                uow_factory,
                cast(PublicMarketSource, source),
                ObservationWorkerRequest(
                    worker_id=args.worker_id,
                    runtime_commit=args.runtime_commit,
                    schema_revision=args.schema_revision,
                    now_ms=now_ms,
                    lease_until_ms=now_ms + args.lease_ms,
                    timeout_seconds=args.timeout_seconds,
                    retry_interval_ms=args.retry_interval_ms,
                ),
            )

        async def selection_tick():
            now_ms = args.now_ms or int(time.time() * 1_000)
            return await run_selection_runtime_once(
                uow_factory=uow_factory,
                market_source=cast(InstrumentSelectionMarketSource, source),
                request=SelectionRuntimeRequest(
                    selection_spec_id=_SELECTION_SPEC_ID,
                    strategy_group_id=SOR_STRATEGY_GROUP_ID,
                    worker_id=selection_worker_id,
                    now_ms=now_ms,
                ),
                clock_ms=lambda: int(time.time() * 1_000),
            )

        async def materialization_tick():
            now_ms = args.now_ms or int(time.time() * 1_000)
            return await run_materialization_runtime_once(
                uow_factory=uow_factory,
                audit_source=audit_source,
                request=SelectionRuntimeRequest(
                    selection_spec_id=_SELECTION_SPEC_ID,
                    strategy_group_id=SOR_STRATEGY_GROUP_ID,
                    worker_id=materialization_worker_id,
                    now_ms=now_ms,
                ),
                clock_ms=lambda: int(time.time() * 1_000),
            )

        if not args.run_forever:
            return await run_worker_process(
                observation_tick,
                run_forever=False,
                poll_interval_ms=args.poll_interval_ms,
                idle_log_interval_ms=args.idle_log_interval_ms,
                idle_statuses={"no_work"},
            )
        return await run_worker_process_group(
            (
                WorkerProcessLoop(
                    component_id=selection_worker_id,
                    tick=selection_tick,
                    poll_interval_ms=args.selection_poll_interval_ms,
                    idle_statuses=frozenset({"not_due", "already_ready"}),
                ),
                WorkerProcessLoop(
                    component_id=materialization_worker_id,
                    tick=materialization_tick,
                    poll_interval_ms=args.materialization_poll_interval_ms,
                    idle_statuses=frozenset({"not_due", "waiting"}),
                ),
                WorkerProcessLoop(
                    component_id=args.worker_id,
                    tick=observation_tick,
                    poll_interval_ms=args.poll_interval_ms,
                    idle_statuses=frozenset({"no_work"}),
                ),
            ),
            run_forever=True,
            idle_log_interval_ms=args.idle_log_interval_ms,
        )
    finally:
        close = getattr(source, "close", None)
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
