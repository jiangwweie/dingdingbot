#!/usr/bin/env python3
"""Seed or monotonically transition Tokyo trading-kernel runtime authority."""

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

from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (  # noqa: E402
    ArmAcceptancePolicyRequest,
    PromoteFullPolicyRequest,
    RuntimeAuthoritySeedRequest,
    RuntimeAuthoritySeedResult,
    RuntimePolicyState,
    arm_acceptance_policy,
    promote_full_policy,
    seed_runtime_authority,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    seed = subparsers.add_parser("seed", help="install observation-only authority")
    seed.add_argument(
        "--account-id",
        default=os.getenv("TRADING_KERNEL_ACCOUNT_ID", ""),
    )
    seed.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    seed.add_argument(
        "--schema-revision",
        default=os.getenv("TRADING_KERNEL_SCHEMA_REVISION", "0001_initial"),
    )
    seed.add_argument("--now-ms", type=int)

    arm = subparsers.add_parser(
        "arm-acceptance",
        help="enable one 20 USDT / 2x acceptance Ticket",
    )
    arm.add_argument("--now-ms", type=int)

    promote = subparsers.add_parser(
        "promote-full",
        help="promote to two Tickets / 40 USDT after reviewed closure",
    )
    promote.add_argument("--acceptance-ticket-id", required=True)
    promote.add_argument("--now-ms", type=int)
    return parser


async def _run(args: argparse.Namespace) -> int:
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    now_ms = args.now_ms or int(time.time() * 1_000)
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            result: RuntimeAuthoritySeedResult | RuntimePolicyState
            if args.action == "seed":
                result = await seed_runtime_authority(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id=args.account_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        seeded_at_ms=now_ms,
                    ),
                )
            elif args.action == "arm-acceptance":
                result = await arm_acceptance_policy(
                    uow,
                    ArmAcceptancePolicyRequest(armed_at_ms=now_ms),
                )
            elif args.action == "promote-full":
                result = await promote_full_policy(
                    uow,
                    PromoteFullPolicyRequest(
                        acceptance_ticket_id=args.acceptance_ticket_id,
                        promoted_at_ms=now_ms,
                    ),
                )
            else:
                raise ValueError("unsupported runtime authority action")
        print(result.model_dump_json())
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
