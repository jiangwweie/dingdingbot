#!/usr/bin/env python3
"""Materialize the PG action-time fact-to-Ticket unit atomically."""

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

from scripts.publish_runtime_control_current_projections import (  # noqa: E402
    publish_action_time_pretrade_readiness,
)
from src.application.action_time.ticket_materialization_sequence import (  # noqa: E402
    materialize_action_time_ticket_sequence,
)
from src.application.runtime_process_outcome import (  # noqa: E402
    runtime_process_exit_code,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG URLs only for unit tests.",
    )
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if args.require_database_url and not database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for atomic Action-Time Ticket sequence",
            file=sys.stderr,
        )
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not args.allow_non_postgres_for_test and not is_sync_postgres_dsn(database_url):
        print(
            "ERROR: atomic Action-Time Ticket sequence requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            report = materialize_action_time_ticket_sequence(
                conn,
                now_ms=args.now_ms,
                projection_publisher=publish_action_time_pretrade_readiness,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return runtime_process_exit_code(report["process_outcome"])


if __name__ == "__main__":
    raise SystemExit(main())
