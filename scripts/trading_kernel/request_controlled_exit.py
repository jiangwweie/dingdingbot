#!/usr/bin/env python3
"""Request one bounded source-owned Controlled Exit operation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.controlled_exit import (
    ControlledExitAuthorization,
    ControlledExitRequest,
    ControlledExitResult,
    request_controlled_exits,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    OWNER_POLICY_ID,
    RUNTIME_PROFILE_ID,
    VENUE_ID,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.trading_kernel.controlled_exit.v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ControlledExitPreflightError(RuntimeError):
    """Current runtime identity cannot authorize a Controlled Exit request."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument(
        "--purpose",
        required=True,
        choices=("deployment_drain",),
    )
    parser.add_argument("--authorization-id", required=True)
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--requested-at-ms", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_execute(args))
    except (ControlledExitPreflightError, ValueError):
        print(
            json.dumps(
                {"schema": SCHEMA, "status": "failed", "reason": "preflight_failed"},
                sort_keys=True,
            )
        )
        return 1
    payload = {
        "schema": SCHEMA,
        "status": _result_status(result),
        **result.model_dump(mode="json"),
    }
    print(json.dumps(payload, sort_keys=True))
    return 2 if result.blocked_ticket_ids else 0


async def _execute(args: argparse.Namespace) -> ControlledExitResult:
    database_url = str(args.database_url or os.getenv("TRADING_KERNEL_DATABASE_URL", "")).strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ControlledExitPreflightError("database URL must use postgresql+asyncpg")
    account_id = _required_environment("TRADING_KERNEL_ACCOUNT_ID")
    if _required_environment("TRADING_KERNEL_ENVIRONMENT") != "live":
        raise ControlledExitPreflightError("runtime environment must be live")
    if _required_environment("TRADING_KERNEL_VENUE_ID") != VENUE_ID:
        raise ControlledExitPreflightError("runtime venue identity differs")
    if (
        _required_environment("TRADING_KERNEL_ACCOUNT_POSITION_MODE")
        != "independent_sides"
    ):
        raise ControlledExitPreflightError("runtime position mode differs")
    runtime_commit = _required_environment("TRADING_KERNEL_RUNTIME_COMMIT")
    if _COMMIT.fullmatch(runtime_commit) is None:
        raise ControlledExitPreflightError("runtime commit must be exact")
    schema_revision = _required_environment("TRADING_KERNEL_SCHEMA_REVISION")
    if schema_revision != CURRENT_SCHEMA_REVISION:
        raise ControlledExitPreflightError("native Controlled Exit requires current schema")

    requested_at_ms = (
        int(time.time() * 1_000)
        if args.requested_at_ms is None
        else int(args.requested_at_ms)
    )
    authorization = ControlledExitAuthorization(
        purpose=args.purpose,
        authorization_id=args.authorization_id,
        target_commit=args.target_commit,
    )
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            capability = await uow.signals.get_runtime_capability(
                "exchange_commands"
            )
            profile = await uow.signals.get_runtime_profile(RUNTIME_PROFILE_ID)
            policy = await uow.entry_admission.get_owner_policy(OWNER_POLICY_ID)
        if (
            capability is None
            or not capability.enabled
            or capability.certified_commit != runtime_commit
            or capability.schema_revision != schema_revision
        ):
            raise ControlledExitPreflightError("runtime capability identity differs")
        if (
            profile is None
            or profile.venue_id != VENUE_ID
            or profile.account_id != account_id
            or profile.environment != "live"
            or profile.position_mode != "independent_sides"
            or profile.status != "active"
        ):
            raise ControlledExitPreflightError("runtime profile identity differs")
        if policy is None or not policy.enabled:
            raise ControlledExitPreflightError("Owner Policy is inactive")
        return await request_controlled_exits(
            lambda: PostgresKernelUnitOfWork(engine),
            ControlledExitRequest(
                authorization=authorization,
                runtime_profile_id="account-wide",
                venue_id=VENUE_ID,
                account_id=account_id,
                max_active_tickets=min(policy.max_concurrent_tickets, 3),
                requested_at_ms=requested_at_ms,
            ),
        )
    finally:
        await engine.dispose()


def _required_environment(key: str) -> str:
    normalized = str(os.getenv(key) or "").strip()
    if not normalized:
        raise ControlledExitPreflightError(f"{key} is required")
    return normalized


def _result_status(result: ControlledExitResult) -> str:
    if result.blocked_ticket_ids:
        return "blocked"
    if result.requested_ticket_ids:
        return "requested"
    if result.in_progress_ticket_ids:
        return "in_progress"
    return "flat"


if __name__ == "__main__":
    raise SystemExit(main())
