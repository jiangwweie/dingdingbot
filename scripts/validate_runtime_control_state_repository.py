#!/usr/bin/env python3
"""Validate DB-backed RuntimeControlStateRepository production read shape."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.infrastructure.runtime_control_state_repository import (  # noqa: E402
    PgBackedRuntimeControlStateRepository,
    RuntimeControlStateRepositoryError,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite or other SQLAlchemy URLs only for local unit tests.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("ERROR: PG_DATABASE_URL or --database-url is required", file=sys.stderr)
        return 2
    args.database_url = normalize_sync_postgres_dsn(args.database_url)
    if (
        not args.allow_non_postgres_for_test
        and not is_sync_postgres_dsn(args.database_url)
    ):
        print("ERROR: repository validation requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.connect() as conn:
            state = PgBackedRuntimeControlStateRepository(conn).read_control_state()
    except (RuntimeControlStateRepositoryError, sa.exc.SQLAlchemyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    report = _report(state)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
    return 0


def _report(state: dict[str, Any]) -> dict[str, Any]:
    table_counts = state.get("table_counts")
    if not isinstance(table_counts, dict):
        table_counts = {}
    return {
        "schema": "brc.runtime_control_state_repository_validation.v1",
        "status": "runtime_control_state_repository_valid",
        "source_mode": state.get("source_mode"),
        "projection_target": state.get("projection_target"),
        "strategy_group_count": table_counts.get("strategy_groups", 0),
        "event_spec_count": table_counts.get("strategy_side_event_specs", 0),
        "candidate_scope_count": table_counts.get("candidate_scope", 0),
        "runtime_scope_binding_count": table_counts.get("runtime_scope_bindings", 0),
        "current_projection_ownership_count": table_counts.get(
            "current_projection_ownership",
            0,
        ),
        "forbidden_effects": {
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
