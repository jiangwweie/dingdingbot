#!/usr/bin/env python3
"""Print one exact Dynamic Selection runtime period as display-only JSON."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_owner_read_repository import (
    create_owner_read_engine,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.interfaces.readonly_api import (
    SelectionRuntimeReadonlyRequest,
    get_selection_runtime_view,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--strategy-group-id", required=True)
    parser.add_argument("--selection-spec-id", required=True)
    parser.add_argument("--session-start-ms", required=True, type=int)
    parser.add_argument("--release-compatibility-id")
    return parser


def _request(args: argparse.Namespace) -> SelectionRuntimeReadonlyRequest:
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    return SelectionRuntimeReadonlyRequest(
        strategy_group_id=args.strategy_group_id,
        selection_spec_id=args.selection_spec_id,
        session_start_ms=args.session_start_ms,
        release_compatibility_id=args.release_compatibility_id,
    )


async def _run(args: argparse.Namespace) -> int:
    request = _request(args)
    engine = create_owner_read_engine(str(args.database_url))
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            view = await get_selection_runtime_view(uow, request)
        print(view.model_dump_json())
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
