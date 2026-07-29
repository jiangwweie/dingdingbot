#!/usr/bin/env python3
"""Seed or monotonically transition Tokyo trading-kernel runtime authority."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    ArmAcceptancePolicyRequest,
    PromoteFullPolicyRequest,
    RuntimeAuthoritySeedRequest,
    RuntimeAuthoritySeedResult,
    RuntimeDeploymentIdentityResult,
    RuntimePolicyState,
    arm_acceptance_policy,
    deploy_closure_identity,
    deploy_protected_identity,
    deploy_recovery_identity,
    deploy_runtime_identity,
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
        default=os.getenv(
            "TRADING_KERNEL_SCHEMA_REVISION",
            "0001_trading_kernel_baseline_v2",
        ),
    )
    seed.add_argument("--now-ms", type=int)

    deploy = subparsers.add_parser(
        "deploy-identity",
        help="install or refresh exact flat-state deployment identity",
    )
    deploy.add_argument(
        "--account-id",
        default=os.getenv("TRADING_KERNEL_ACCOUNT_ID", ""),
    )
    deploy.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    deploy.add_argument(
        "--schema-revision",
        default=os.getenv(
            "TRADING_KERNEL_SCHEMA_REVISION",
            "0001_trading_kernel_baseline_v2",
        ),
    )
    deploy.add_argument("--now-ms", type=int)

    recovery = subparsers.add_parser(
        "deploy-recovery-identity",
        help="rotate identity only to reconcile one zero-exposure leverage unknown",
    )
    recovery.add_argument("--recovery-ticket-id", required=True)
    recovery.add_argument(
        "--account-id",
        default=os.getenv("TRADING_KERNEL_ACCOUNT_ID", ""),
    )
    recovery.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    recovery.add_argument(
        "--schema-revision",
        default=os.getenv(
            "TRADING_KERNEL_SCHEMA_REVISION",
            "0001_trading_kernel_baseline_v2",
        ),
    )
    recovery.add_argument("--now-ms", type=int)

    protected = subparsers.add_parser(
        "deploy-protected-identity",
        help="rotate identity only across exact fully protected active Tickets",
    )
    protected.add_argument(
        "--protected-ticket-id",
        action="append",
        required=True,
    )
    protected.add_argument(
        "--account-id",
        default=os.getenv("TRADING_KERNEL_ACCOUNT_ID", ""),
    )
    protected.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    protected.add_argument(
        "--schema-revision",
        default=os.getenv(
            "TRADING_KERNEL_SCHEMA_REVISION",
            "0001_trading_kernel_baseline_v2",
        ),
    )
    protected.add_argument("--now-ms", type=int)

    closure = subparsers.add_parser(
        "deploy-closure-identity",
        help="rotate identity only for one exact zero-exposure pending closure Ticket",
    )
    closure.add_argument("--closure-ticket-id", required=True)
    closure.add_argument(
        "--account-id",
        default=os.getenv("TRADING_KERNEL_ACCOUNT_ID", ""),
    )
    closure.add_argument(
        "--runtime-commit",
        default=os.getenv("TRADING_KERNEL_RUNTIME_COMMIT", ""),
    )
    closure.add_argument(
        "--schema-revision",
        default=os.getenv(
            "TRADING_KERNEL_SCHEMA_REVISION",
            "0001_trading_kernel_baseline_v2",
        ),
    )
    closure.add_argument("--now-ms", type=int)

    arm = subparsers.add_parser(
        "arm-acceptance",
        help="enable new ENTRY under the approved dynamic budget policy",
    )
    arm.add_argument("--now-ms", type=int)

    promote = subparsers.add_parser(
        "promote-full",
        help="certify normal three-Ticket authority after reviewed closure",
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
            result: (
                RuntimeAuthoritySeedResult
                | RuntimeDeploymentIdentityResult
                | RuntimePolicyState
            )
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
            elif args.action == "deploy-identity":
                result = await deploy_runtime_identity(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id=args.account_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        seeded_at_ms=now_ms,
                    ),
                )
            elif args.action == "deploy-recovery-identity":
                result = await deploy_recovery_identity(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id=args.account_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        seeded_at_ms=now_ms,
                    ),
                    recovery_ticket_id=args.recovery_ticket_id,
                )
            elif args.action == "deploy-protected-identity":
                result = await deploy_protected_identity(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id=args.account_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        seeded_at_ms=now_ms,
                    ),
                    protected_ticket_ids=tuple(args.protected_ticket_id),
                )
            elif args.action == "deploy-closure-identity":
                result = await deploy_closure_identity(
                    uow,
                    RuntimeAuthoritySeedRequest(
                        account_id=args.account_id,
                        runtime_commit=args.runtime_commit,
                        schema_revision=args.schema_revision,
                        seeded_at_ms=now_ms,
                    ),
                    closure_ticket_id=args.closure_ticket_id,
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
