#!/usr/bin/env python3
"""Verify the exact clean trading-kernel PostgreSQL table allowlist."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.pg_models import metadata  # noqa: E402


SCHEMA = "brc.trading_kernel.schema_verification.v1"
EXPECTED_ALEMBIC_REVISION = "0001_initial"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TRADING_KERNEL_DATABASE_URL", ""),
        help="PostgreSQL SQLAlchemy URL; defaults to TRADING_KERNEL_DATABASE_URL",
    )
    return parser


async def _verify(database_url: str) -> dict[str, object]:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            revision = str(
                (
                    await connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                ).scalar_one()
            )
            actual_tables = {
                str(name)
                for name in (
                    await connection.execute(
                        text(
                            """
                            SELECT relname
                              FROM pg_catalog.pg_class
                             WHERE relkind IN ('r', 'p')
                               AND relnamespace = current_schema()::regnamespace
                               AND relname LIKE 'brc\\_%' ESCAPE '\\'
                             ORDER BY relname
                            """
                        )
                    )
                ).scalars()
            }
            await connection.rollback()
    finally:
        await engine.dispose()

    expected_tables = set(metadata.tables)
    missing_tables = sorted(expected_tables - actual_tables)
    unexpected_tables = sorted(actual_tables - expected_tables)
    passed = (
        revision == EXPECTED_ALEMBIC_REVISION
        and not missing_tables
        and not unexpected_tables
    )
    return {
        "schema": SCHEMA,
        "status": "pass" if passed else "fail",
        "alembic_revision": revision,
        "expected_table_count": len(expected_tables),
        "actual_table_count": len(actual_tables),
        "missing_tables": missing_tables,
        "unexpected_tables": unexpected_tables,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = asyncio.run(_verify(str(args.database_url or "").strip()))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
