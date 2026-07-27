#!/usr/bin/env python3
"""Atomically activate one fully warmed Strategy Universe."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.activate_strategy_universe import (  # noqa: E402
    ActivateStrategyUniverseRequest,
    activate_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)


async def _run(
    database_url: str,
    request: ActivateStrategyUniverseRequest,
) -> int:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            activation = await activate_strategy_universe(uow, request)
        print(json.dumps(activation.model_dump(mode="json"), sort_keys=True))
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--event-spec-id", required=True)
    parser.add_argument("--universe-version-id", required=True)
    parser.add_argument("--expected-current-universe-version-id")
    parser.add_argument("--activated-at-ms", type=int)
    args = parser.parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    return asyncio.run(
        _run(
            database_url,
            ActivateStrategyUniverseRequest(
                event_spec_id=args.event_spec_id,
                universe_version_id=args.universe_version_id,
                expected_current_universe_version_id=(
                    args.expected_current_universe_version_id
                ),
                activated_at_ms=(
                    args.activated_at_ms or int(time.time() * 1_000)
                ),
            ),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
