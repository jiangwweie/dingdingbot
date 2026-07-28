#!/usr/bin/env python3
"""Read bounded Strategy Universe status from PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.read_strategy_universe_status import (  # noqa: E402
    StrategyUniverseStatusRequest,
    StrategyUniverseStatusResult,
    read_strategy_universe_status,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.pg_universe_repository import (  # noqa: E402
    UniverseInstallConflict,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--runtime-profile-id", required=True)
    parser.add_argument("--event-spec-id")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if not str(args.database_url or "").startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    try:
        request = StrategyUniverseStatusRequest(
            runtime_profile_id=args.runtime_profile_id,
            event_id=args.event_spec_id,
        )
    except ValidationError:
        parser.error("status identities must be exact")
    try:
        result = asyncio.run(_read(args.database_url, request))
    except UniverseInstallConflict as exc:
        print(f"error={exc.reason_code}", file=sys.stderr)
        return 2
    except Exception:
        print("error=operation_failed", file=sys.stderr)
        return 1
    _print_status(result)
    return 0


async def _read(
    database_url: str,
    request: StrategyUniverseStatusRequest,
) -> StrategyUniverseStatusResult:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            return await read_strategy_universe_status(uow, request)
    finally:
        await engine.dispose()


def _print_status(result: StrategyUniverseStatusResult) -> None:
    print(f"runtime_profile_id={result.runtime_profile_id}")
    print(f"universe_count={len(result.universes)}")
    for universe in result.universes:
        generation = (
            "none"
            if universe.current_generation is None
            else str(universe.current_generation)
        )
        print(
            f"universe event_id={universe.event_id} "
            f"event_spec_id={universe.event_spec_id} "
            f"version_id={universe.universe_version_id} "
            f"lifecycle={universe.lifecycle_state} "
            f"current_generation={generation}"
        )
        for member in universe.members:
            print(
                f"member instrument={member.exchange_instrument_id} "
                f"certification={member.certification_status} "
                f"warm={'ready' if member.warm_ready else 'not_ready'} "
                f"monitor={member.monitor_status or 'none'} "
                f"blocker={member.blocker_code or 'none'}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
