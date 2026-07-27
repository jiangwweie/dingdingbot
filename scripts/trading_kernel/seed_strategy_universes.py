#!/usr/bin/env python3
"""Seed exact versioned Strategy Universes into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import sys

from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_universe_seed import (  # noqa: E402
    seed_strategy_universes,
)


async def _run(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            result = await seed_strategy_universes(
                uow,
                seeded_at_ms=int(datetime.now(UTC).timestamp() * 1_000),
            )
        print(result.model_dump_json())
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    database_url = parser.parse_args(argv).database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    return asyncio.run(_run(database_url))


if __name__ == "__main__":
    raise SystemExit(main())
