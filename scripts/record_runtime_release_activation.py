#!/usr/bin/env python3
"""Project an exact postdeploy-verified runtime release into PG current truth."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Sequence

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.capability_certification import (  # noqa: E402
    record_runtime_release_activation,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_pg_release_activation(
        database_url=args.database_url,
        runtime_head=args.runtime_head,
        release_name=args.release_name,
        verification_ref=args.verification_ref,
        now_ms=args.now_ms,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("status") == "runtime_release_activation_completed" else 2


def run_pg_release_activation(
    *,
    database_url: str,
    runtime_head: str,
    release_name: str,
    verification_ref: str,
    now_ms: int,
) -> dict[str, object]:
    dsn = normalize_sync_postgres_dsn(database_url)
    if not dsn.startswith(("postgresql://", "postgresql+psycopg://")):
        return {
            "status": "blocked",
            "first_blocker": "postgresql_database_url_required",
            "runtime_head": runtime_head,
            "exchange_write_called": False,
        }
    engine = sa.create_engine(dsn)
    try:
        with engine.begin() as conn:
            return record_runtime_release_activation(
                conn,
                runtime_head=runtime_head,
                release_name=release_name,
                verification_ref=verification_ref,
                now_ms=now_ms,
            )
    finally:
        engine.dispose()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record the exact postdeploy-verified release in bounded PG truth. "
            "Prints stdout only."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        required=not bool(os.getenv("PG_DATABASE_URL")),
    )
    parser.add_argument("--runtime-head", required=True)
    parser.add_argument("--release-name", required=True)
    parser.add_argument("--verification-ref", required=True)
    parser.add_argument("--now-ms", type=int, default=int(time.time() * 1000))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
