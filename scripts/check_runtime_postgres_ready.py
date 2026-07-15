#!/usr/bin/env python3
"""Bounded PostgreSQL SELECT readiness probe with stdout-only evidence."""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import os
import time
from typing import Any

import sqlalchemy as sa
from sqlalchemy.pool import NullPool


ReadyRunner = Callable[[str], object]


def _normalize_sync_postgres_dsn(value: str) -> str:
    dsn = str(value or "").strip()
    if dsn.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + dsn.removeprefix(
            "postgresql+asyncpg://"
        )
    return dsn


def _select_one(database_url: str) -> object:
    engine = sa.create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return conn.execute(sa.text("SELECT 1")).scalar_one()
    finally:
        engine.dispose()


def check_postgres_ready(
    *,
    database_url: str,
    timeout_seconds: float,
    runner: ReadyRunner | None = None,
) -> dict[str, Any]:
    normalized = _normalize_sync_postgres_dsn(database_url)
    if not normalized:
        return {"status": "unavailable", "error": "database_url_missing"}
    deadline = time.monotonic() + max(float(timeout_seconds), 0.1)
    last_error = ""
    select_one = runner or _select_one
    while time.monotonic() < deadline:
        try:
            value = select_one(normalized)
            if type(value) is int and value == 1:
                return {"status": "ready", "select_one": 1}
            last_error = "select_one_invalid_result"
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{str(exc)[-200:]}"
        remaining = max(deadline - time.monotonic(), 0.0)
        if remaining:
            time.sleep(min(1.0, remaining))
    return {"status": "unavailable", "error": last_error or "deadline_elapsed"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL") or "",
    )
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = check_postgres_ready(
        database_url=args.database_url,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(report["status"])
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
