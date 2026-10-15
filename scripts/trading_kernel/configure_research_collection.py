#!/usr/bin/env python3
"""Apply one exact, audited research collection control revision."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_models import (
    research_collection_control,
    research_collection_daily,
    research_collection_events,
)


def _parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',default=os.getenv('TRADING_KERNEL_DATABASE_URL',''))
    parser.add_argument('--show',action='store_true')
    parser.add_argument('--day-start-ms',type=int)
    parser.add_argument('--expected-version',type=int)
    parser.add_argument('--daily-limit',type=int)
    parser.add_argument('--enabled',action='store_true')
    parser.add_argument('--owner-identity',default='')
    parser.add_argument('--reason',default='')
    return parser


async def configure(args: argparse.Namespace) -> dict[str,object]:
    if not str(args.database_url).startswith('postgresql+asyncpg://'):
        raise ValueError('research control requires postgresql+asyncpg URL')
    if args.show:
        return await read_control(args)
    if (args.expected_version is None or args.expected_version<=0
        or args.daily_limit is None or not 0<=args.daily_limit<=1000
        or (args.enabled and args.daily_limit==0)
        or not args.owner_identity.strip() or not args.reason.strip()):
        raise ValueError('research control input invalid')
    engine=create_async_engine(args.database_url)
    try:
        async with engine.begin() as connection:
            row=(await connection.execute(sa.select(research_collection_control)
                .where(research_collection_control.c.control_id=='generic_signal_path_v1')
                .with_for_update())).mappings().one()
            if int(row['control_version'])!=args.expected_version:
                raise ValueError('research control version changed')
            next_version=args.expected_version+1
            now=int(time.time()*1000)
            event_id='research-control:'+sha256(f'{next_version}:{args.owner_identity}:{args.reason}'.encode()).hexdigest()
            await connection.execute(sa.update(research_collection_control)
                .where(research_collection_control.c.control_id=='generic_signal_path_v1')
                .values(enabled=args.enabled,daily_limit=args.daily_limit,control_version=next_version))
            await connection.execute(sa.insert(research_collection_events).values(
                event_id=event_id,control_version=next_version,enabled=args.enabled,
                daily_limit=args.daily_limit,owner_identity=args.owner_identity.strip(),
                reason=args.reason.strip(),occurred_at_ms=now))
            return {'control_version':next_version,'enabled':args.enabled,'daily_limit':args.daily_limit,
                    'event_id':event_id}
    finally:
        await engine.dispose()


async def read_control(args: argparse.Namespace) -> dict[str,object]:
    day=args.day_start_ms if args.day_start_ms is not None else int(time.time()*1000)//86_400_000*86_400_000
    if day<0 or day%86_400_000:
        raise ValueError("research coverage day must be UTC midnight")
    engine=create_async_engine(args.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            control=(await connection.execute(sa.select(research_collection_control))).mappings().one()
            coverage=(await connection.execute(sa.select(research_collection_daily)
                .where(research_collection_daily.c.day_start_ms==day))).mappings().one_or_none()
            return {"control":dict(control),
                    "sample_population":"quota_limited_prospective",
                    "coverage":None if coverage is None else {
                        **dict(coverage),"skipped_budget":coverage["skipped_count"]},
                    "failure_evidence":"research_collection_failed logs keyed by signal_event_id; not included in quota counts"}
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args=_parser().parse_args(argv)
    print(json.dumps(asyncio.run(configure(args))))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
