#!/usr/bin/env python3
"""Persist or read one exact runtime release classification fact."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.runtime import (
    RUNTIME_COMPATIBILITY_REASONS,
    RuntimeCompatibilityClassification,
    RuntimeReleaseCompatibilityFact,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    SelectionJobConflict,
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write")
    write.add_argument("--release-compatibility-id", required=True)
    write.add_argument("--from-commit", required=True)
    write.add_argument("--to-commit", required=True)
    write.add_argument("--from-schema-revision", required=True)
    write.add_argument("--to-schema-revision", required=True)
    write.add_argument(
        "--classification",
        choices=tuple(item.value for item in RuntimeCompatibilityClassification),
        required=True,
    )
    write.add_argument(
        "--reason-code",
        action="append",
        choices=tuple(sorted(RUNTIME_COMPATIBILITY_REASONS)),
        required=True,
    )
    write.add_argument("--compatibility-basis-digest", required=True)
    write.add_argument("--certification-manifest-digest", required=True)
    write.add_argument("--created-at-ms", type=int, required=True)
    read = subparsers.add_parser("read")
    read.add_argument("--release-compatibility-id", required=True)
    return parser


async def _write(
    database_url: str,
    fact: RuntimeReleaseCompatibilityFact,
) -> tuple[bool, RuntimeReleaseCompatibilityFact]:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            existing = (
                await uow.instrument_selection.get_runtime_release_compatibility_fact(
                    fact.release_compatibility_id
                )
            )
            if existing is not None:
                if existing != fact:
                    raise SelectionJobConflict(
                        "release compatibility identity already owns another fact"
                    )
                return False, existing
            await uow.instrument_selection.add_runtime_release_compatibility_fact(fact)
            persisted = (
                await uow.instrument_selection.get_runtime_release_compatibility_fact(
                    fact.release_compatibility_id
                )
            )
            if persisted != fact:
                raise SelectionJobConflict(
                    "release compatibility persistence did not round-trip"
                )
            return True, persisted
    finally:
        await engine.dispose()


async def _read(
    database_url: str,
    release_compatibility_id: str,
) -> RuntimeReleaseCompatibilityFact | None:
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            return (
                await uow.instrument_selection.get_runtime_release_compatibility_fact(
                    release_compatibility_id
                )
            )
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    database_url = str(args.database_url or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        parser.error("database URL must use postgresql+asyncpg")
    try:
        if args.command == "write":
            fact = RuntimeReleaseCompatibilityFact(
                release_compatibility_id=args.release_compatibility_id,
                from_commit=args.from_commit,
                to_commit=args.to_commit,
                from_schema_revision=args.from_schema_revision,
                to_schema_revision=args.to_schema_revision,
                classification=RuntimeCompatibilityClassification(args.classification),
                compatibility_basis_digest=args.compatibility_basis_digest,
                reason_codes=tuple(sorted(set(args.reason_code))),
                certification_manifest_digest=args.certification_manifest_digest,
                created_at_ms=args.created_at_ms,
            )
            created, persisted = asyncio.run(_write(database_url, fact))
            payload = {
                "status": "pass",
                "created": created,
                "fact": persisted.model_dump(mode="json"),
            }
        else:
            read_fact = asyncio.run(
                _read(database_url, str(args.release_compatibility_id))
            )
            payload = (
                {"status": "not_found", "fact": None}
                if read_fact is None
                else {
                    "status": "pass",
                    "fact": read_fact.model_dump(mode="json"),
                }
            )
    except (SelectionJobConflict, ValidationError, ValueError):
        print(
            json.dumps(
                {"status": "blocked", "reason": "release_compatibility_conflict"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except Exception:  # noqa: BLE001 - never expose database credentials or internals.
        print(
            json.dumps(
                {"status": "failed", "reason": "operation_failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
