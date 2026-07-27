#!/usr/bin/env python3
"""Persist complete warm-readiness evidence for one candidate scope."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import time

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.mark_strategy_universe_warm_ready import (  # noqa: E402
    MarkStrategyUniverseWarmReadyRequest,
    mark_strategy_universe_warm_ready,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)


async def _run(
    database_url: str,
    request: MarkStrategyUniverseWarmReadyRequest,
) -> int:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            digest = await mark_strategy_universe_warm_ready(uow, request)
        print(f'{{"readiness_digest":"{digest}"}}')
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--runtime-scope-id", required=True)
    parser.add_argument("--universe-version-id", required=True)
    parser.add_argument("--observation-fact-digest", required=True)
    parser.add_argument("--ready-at-ms", type=int)
    args = parser.parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    return asyncio.run(
        _run(
            database_url,
            MarkStrategyUniverseWarmReadyRequest(
                runtime_scope_id=args.runtime_scope_id,
                universe_version_id=args.universe_version_id,
                observation_fact_digest=args.observation_fact_digest,
                ready_at_ms=args.ready_at_ms or int(time.time() * 1_000),
            ),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
