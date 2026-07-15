#!/usr/bin/env python3
"""Capture one bounded read-only PG mutation sentinel to stdout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.readmodels.canary_mutation_sentinel import (  # noqa: E402
    CanaryMutationSentinelScopeV1,
)
from src.infrastructure.canary_mutation_sentinel_repository import (  # noqa: E402
    capture_canary_mutation_sentinel,
    database_clock_ms,
    discover_canary_mutation_scope,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dsn = normalize_sync_postgres_dsn(args.database_url)
    if not dsn.startswith(("postgresql://", "postgresql+psycopg://")):
        print(json.dumps({"status": "blocked", "error": "postgresql_database_url_required"}))
        return 2
    engine = sa.create_engine(dsn)
    try:
        with engine.connect() as conn:
            with conn.begin():
                now_ms = database_clock_ms(conn)
                scope = (
                    CanaryMutationSentinelScopeV1.model_validate_json(args.scope_json)
                    if args.scope_json
                    else discover_canary_mutation_scope(
                        conn, target_runtime_head=args.target_runtime_head
                    )
                )
                floor_ms = (
                    int(args.canary_window_floor_ms)
                    if args.canary_window_floor_ms is not None
                    else max(0, now_ms - 1000)
                )
                projection = capture_canary_mutation_sentinel(
                    conn,
                    scope=scope,
                    canary_db_now_ms=now_ms,
                    canary_window_floor_ms=floor_ms,
                )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "status": "canary_mutation_sentinel_captured",
                "scope": scope.model_dump(mode="json"),
                "canary_db_now_ms": projection.canary_db_now_ms,
                "canary_window_floor_ms": projection.canary_window_floor_ms,
                "digest": projection.digest,
                "slice_digests": {
                    slice_id: _slice_digest(rows)
                    for slice_id, rows in projection.slices.items()
                },
                "slice_counts": {
                    slice_id: len(rows)
                    for slice_id, rows in projection.slices.items()
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _slice_digest(rows) -> str:
    import hashlib

    raw = json.dumps(
        rows,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        required=not bool(os.getenv("PG_DATABASE_URL")),
    )
    parser.add_argument("--target-runtime-head", required=True)
    parser.add_argument("--scope-json", default="")
    parser.add_argument("--canary-window-floor-ms", type=int)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
