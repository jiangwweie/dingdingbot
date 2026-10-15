#!/usr/bin/env python3
"""Read one Signal-owned price path and exact effective Review association."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.interfaces.read_signal_path import read_signal_path


def _parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',default=os.getenv('TRADING_KERNEL_DATABASE_URL',''))
    parser.add_argument('--signal-event-id',required=True)
    return parser


async def _run(args: argparse.Namespace) -> str:
    if not str(args.database_url).startswith('postgresql+asyncpg://'):
        raise ValueError('research read requires postgresql+asyncpg URL')
    engine=create_async_engine(args.database_url)
    try:
        result=await read_signal_path(engine,signal_event_id=args.signal_event_id)
        return '{}' if result is None else result.model_dump_json()
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    print(asyncio.run(_run(_parser().parse_args(argv))))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
