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
    apply_prepared_action_time_capability_certification,
    prepare_action_time_capability_certification,
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
        fact_snapshot_ids=tuple(args.fact_snapshot_id),
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
    fact_snapshot_ids: tuple[str, ...],
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
        with engine.connect() as prepare_conn:
            with prepare_conn.begin():
                prepare_repository = PgBackedRuntimeControlStateRepository(
                    prepare_conn,
                    now_ms=now_ms,
                )
                prepare_state = (
                    prepare_repository
                    .read_action_time_capability_certification_state()
                )
                prepare_fact_rows = (
                    prepare_repository.read_action_time_fact_digest_rows(
                        expected_fact_snapshot_ids=fact_snapshot_ids,
                    )
                )
                prepared = prepare_action_time_capability_certification(
                    prepare_state,
                    runtime_head=runtime_head,
                    fact_digest_rows=prepare_fact_rows,
                )
        with engine.connect().execution_options(
            isolation_level="SERIALIZABLE"
        ) as apply_conn:
            with apply_conn.begin():
                apply_repository = PgBackedRuntimeControlStateRepository(
                    apply_conn,
                    now_ms=now_ms,
                )
                apply_state = (
                    apply_repository
                    .reread_action_time_capability_certification_state_for_apply()
                )
                apply_fact_rows = (
                    apply_repository.reread_action_time_fact_digest_rows_for_apply(
                        expected_fact_snapshot_ids=fact_snapshot_ids,
                    )
                )
                return apply_prepared_action_time_capability_certification(
                    apply_conn,
                    prepared=prepared,
                    control_state=apply_state,
                    fact_digest_rows=apply_fact_rows,
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
    parser.add_argument(
        "--fact-snapshot-id",
        action="append",
        required=True,
        help="Exact fact snapshot ID from the bounded refresh; repeat as needed.",
    )
    parser.add_argument("--now-ms", type=int, default=int(time.time() * 1000))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
