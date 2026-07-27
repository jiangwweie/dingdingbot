#!/usr/bin/env python3
"""Dry-run or apply the guarded forward Strategy-Universe DML cutover."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_unit_of_work import (  # noqa: E402
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.strategy_universe_cutover import (  # noqa: E402
    StrategyUniverseCutoverRequest,
    apply_strategy_universe_cutover,
    inspect_strategy_universe_cutover,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
    )
    parser.add_argument("--cutover-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--target-runtime-commit", required=True)
    parser.add_argument(
        "--target-schema-revision",
        default="0002_strategy_universe_us_equity",
    )
    parser.add_argument("--target-seed-identity", required=True)
    parser.add_argument(
        "--external-flat-verification-digest",
        required=True,
    )
    parser.add_argument(
        "--terminal-ticket-id",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--resolved-incident-id",
        action="append",
        default=[],
    )
    parser.add_argument("--applied-at-ms", required=True, type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Mutate PostgreSQL; omitted means transaction-readonly dry-run.",
    )
    parser.add_argument(
        "--owner-confirmation-id",
        default="",
        help="Required with --apply and must equal AUTHORIZE:<cutover-id>.",
    )
    return parser


def _request(args: argparse.Namespace) -> StrategyUniverseCutoverRequest:
    return StrategyUniverseCutoverRequest(
        cutover_id=args.cutover_id,
        account_id=args.account_id,
        target_runtime_commit=args.target_runtime_commit,
        target_schema_revision=args.target_schema_revision,
        target_seed_identity=args.target_seed_identity,
        external_flat_verification_digest=(
            args.external_flat_verification_digest
        ),
        terminal_ticket_ids=tuple(args.terminal_ticket_id),
        resolved_incident_ids=tuple(args.resolved_incident_id),
        applied_at_ms=args.applied_at_ms,
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if not args.database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    request = _request(args)
    if args.apply and args.owner_confirmation_id != (
        f"AUTHORIZE:{request.cutover_id}"
    ):
        raise ValueError("apply requires the exact Owner confirmation identity")

    engine = create_async_engine(args.database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            if not args.apply:
                await uow._require_connection().execute(
                    sa.text("SET TRANSACTION READ ONLY")
                )
                result = await inspect_strategy_universe_cutover(
                    uow,
                    request,
                )
            else:
                result = await apply_strategy_universe_cutover(uow, request)
    finally:
        await engine.dispose()
    return {
        "schema": "brc.strategy_universe_cutover.v1",
        "mode": "apply" if args.apply else "dry_run",
        **result.model_dump(mode="json"),
    }


def main() -> None:
    args = _parser().parse_args()
    print(
        json.dumps(
            asyncio.run(_run(args)),
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
