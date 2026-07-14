#!/usr/bin/env python3
"""Certify release-bound Action-Time capability into bounded PG outcomes."""

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
    certify_action_time_capabilities,
)
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_pg_certification(
        database_url=args.database_url,
        runtime_head=args.runtime_head,
        certification_ref=args.certification_ref,
        expected_lane_count=args.expected_lane_count,
        now_ms=args.now_ms,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if result.get("status") == "action_time_capability_certified" else 2


def run_pg_certification(
    *,
    database_url: str,
    runtime_head: str,
    certification_ref: str,
    expected_lane_count: int,
    now_ms: int,
) -> dict[str, object]:
    dsn = normalize_sync_postgres_dsn(database_url)
    if not dsn.startswith(("postgresql://", "postgresql+psycopg://")):
        return {
            "status": "blocked",
            "first_blocker": "postgresql_database_url_required",
            "certified_lane_count": 0,
            "exchange_write_called": False,
        }
    engine = sa.create_engine(dsn)
    try:
        with engine.begin() as conn:
            control_state = PgBackedRuntimeControlStateRepository(
                conn,
                now_ms=now_ms,
            ).read_control_state()
            return certify_action_time_capabilities(
                conn,
                control_state=control_state,
                runtime_head=runtime_head,
                certification_ref=certification_ref,
                expected_lane_count=expected_lane_count,
                now_ms=now_ms,
            )
    finally:
        engine.dispose()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write bounded release capability outcomes after the 22-scope "
            "production-shaped matrix passes. Prints stdout only."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        required=not bool(os.getenv("PG_DATABASE_URL")),
    )
    parser.add_argument("--runtime-head", required=True)
    parser.add_argument("--certification-ref", required=True)
    parser.add_argument("--expected-lane-count", type=int, required=True)
    parser.add_argument("--now-ms", type=int, default=int(time.time() * 1000))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
