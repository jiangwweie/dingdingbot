#!/usr/bin/env python3
"""Recover one exact expired, Owner-paused first Dynamic activation attempt."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.recover_expired_dynamic_activation import (
    ExpiredDynamicActivationRecoveryBlocked,
    RecoverExpiredDynamicActivationRequest,
    recover_expired_dynamic_activation,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--strategy-group-id", required=True)
    parser.add_argument("--selection-spec-id", required=True)
    parser.add_argument("--session-start-ms", type=int, required=True)
    parser.add_argument("--materialization-generation-id", required=True)
    parser.add_argument("--entry-vacuum-id", required=True)
    parser.add_argument("--authority-gap-audit-id", required=True)
    parser.add_argument("--expected-long-universe-version-id", required=True)
    parser.add_argument("--expected-short-universe-version-id", required=True)
    parser.add_argument("--expected-selection-control-version", type=int, required=True)
    parser.add_argument("--expected-owner-control-version", type=int, required=True)
    parser.add_argument("--recovered-at-ms", type=int)
    return parser


async def _run(
    database_url: str,
    request: RecoverExpiredDynamicActivationRequest,
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            result = await recover_expired_dynamic_activation(uow, request)
        return result.model_dump(mode="json")
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    try:
        request = RecoverExpiredDynamicActivationRequest(
            strategy_group_id=args.strategy_group_id,
            selection_spec_id=args.selection_spec_id,
            session_start_ms=args.session_start_ms,
            materialization_generation_id=args.materialization_generation_id,
            entry_vacuum_id=args.entry_vacuum_id,
            authority_gap_audit_id=args.authority_gap_audit_id,
            expected_long_universe_version_id=(
                args.expected_long_universe_version_id
            ),
            expected_short_universe_version_id=(
                args.expected_short_universe_version_id
            ),
            expected_selection_control_version=(
                args.expected_selection_control_version
            ),
            expected_owner_control_version=args.expected_owner_control_version,
            recovered_at_ms=(
                int(time.time() * 1_000)
                if args.recovered_at_ms is None
                else args.recovered_at_ms
            ),
        )
        result = asyncio.run(_run(database_url, request))
    except (ValidationError, ExpiredDynamicActivationRecoveryBlocked, ValueError):
        print(
            json.dumps(
                {"status": "blocked", "reason": "recovery_contract_not_satisfied"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception:  # noqa: BLE001 - never reveal database internals or credentials.
        print(
            json.dumps(
                {"status": "failed", "reason": "operation_failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"status": "pass", "recovery": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
