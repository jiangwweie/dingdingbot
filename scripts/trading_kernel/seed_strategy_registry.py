#!/usr/bin/env python3
"""Seed the exact six registered StrategyGroup Event contracts into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os

from sqlalchemy.ext.asyncio import create_async_engine

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.strategy_registry_seed import (
    seed_strategy_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    args = parser.parse_args()
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    return asyncio.run(_seed(database_url))


async def _seed(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        seeded_at_ms = int(datetime.now(UTC).timestamp() * 1000)
        async with PostgresKernelUnitOfWork(engine) as uow:
            result = await seed_strategy_registry(uow, seeded_at_ms=seeded_at_ms)
        print(
            "strategy Registry seeded "
            f"hash={result.registry_semantic_hash} "
            f"inserted={result.total_inserted_count}"
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
