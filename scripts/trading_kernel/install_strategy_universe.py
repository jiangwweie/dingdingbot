#!/usr/bin/env python3
"""Install one reviewed immutable Strategy Universe as warming authority."""

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

from src.trading_kernel.application.install_strategy_universe import (  # noqa: E402
    InstallStrategyUniverseRequest,
    install_strategy_universe,
)
from src.trading_kernel.domain.strategy_universe import (  # noqa: E402
    StrategyUniverseVersion,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)


async def _run(
    database_url: str,
    request: InstallStrategyUniverseRequest,
) -> int:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            counts = await install_strategy_universe(uow, request)
        print(json.dumps(counts.model_dump(mode="json"), sort_keys=True))
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument(
        "--position-side",
        choices=("long", "short"),
        required=True,
    )
    parser.add_argument("--installed-at-ms", type=int)
    args = parser.parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    universe = StrategyUniverseVersion.model_validate(
        json.loads(args.input_json.read_text(encoding="utf-8"))
    )
    return asyncio.run(
        _run(
            database_url,
            InstallStrategyUniverseRequest(
                universe=universe,
                position_side=args.position_side,
                installed_at_ms=(
                    args.installed_at_ms or int(time.time() * 1_000)
                ),
            ),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
