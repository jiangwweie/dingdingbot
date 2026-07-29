#!/usr/bin/env python3
"""Permanently abandon one exact Warming StrategyUniverse after a bounded failure."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.abandon_strategy_universe import (
    AbandonStrategyUniverseRequest,
    abandon_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (
    UniverseInstallConflict,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--universe-version-id", required=True)
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--attempted-at-ms", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = str(args.database_url or "")
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    attempted_at_ms = (
        int(time.time() * 1_000)
        if args.attempted_at_ms is None
        else int(args.attempted_at_ms)
    )
    try:
        request = AbandonStrategyUniverseRequest(
            universe_version_id=str(args.universe_version_id),
            reason_code=str(args.reason_code),
            attempted_at_ms=attempted_at_ms,
        )
    except ValidationError:
        parser.error("abandonment identity, reason, and time must be exact")
    try:
        asyncio.run(_abandon(database_url, request))
    except UniverseInstallConflict as exc:
        print(f"status=blocked reason={exc.reason_code}", file=sys.stderr)
        return 2
    except Exception:  # noqa: BLE001 - operational errors must not reveal DSN contents.
        print("status=failed reason=operation_failed", file=sys.stderr)
        return 1
    print(f"status=abandoned universe_version_id={request.universe_version_id}")
    return 0


async def _abandon(
    database_url: str,
    request: AbandonStrategyUniverseRequest,
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            await abandon_strategy_universe(uow, request)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
