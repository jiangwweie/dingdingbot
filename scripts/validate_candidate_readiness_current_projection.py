#!/usr/bin/env python3
"""Validate active candidate scope has PG current readiness rows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


def validate_candidate_readiness_current_projection(
    conn: sa.engine.Connection,
) -> list[str]:
    metadata = sa.MetaData()
    scope = sa.Table("brc_strategy_group_candidate_scope", metadata, autoload_with=conn)
    readiness = sa.Table("brc_pretrade_readiness_rows", metadata, autoload_with=conn)
    active_scope = [
        dict(row)
        for row in conn.execute(
            sa.select(
                scope.c.candidate_scope_id,
                scope.c.strategy_group_id,
                scope.c.symbol,
                scope.c.side,
            ).where(scope.c.status == "active")
        ).mappings()
    ]
    readiness_rows = [
        dict(row)
        for row in conn.execute(
            sa.select(
                readiness.c.readiness_row_id,
                readiness.c.strategy_group_id,
                readiness.c.symbol,
                readiness.c.side,
                readiness.c.candidate_scope_id,
            )
        ).mappings()
    ]
    errors: list[str] = []
    readiness_by_lane: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in readiness_rows:
        readiness_by_lane.setdefault(_lane_key(row), []).append(row)
    for lane, rows in readiness_by_lane.items():
        if len(rows) > 1:
            errors.append(f"duplicate readiness row for {lane[0]}:{lane[1]}:{lane[2]}")
    for row in active_scope:
        lane = _lane_key(row)
        rows = readiness_by_lane.get(lane) or []
        if not rows:
            errors.append(f"missing readiness row for {lane[0]}:{lane[1]}:{lane[2]}")
            continue
        candidate_scope_id = str(rows[0].get("candidate_scope_id") or "")
        expected_scope_id = str(row.get("candidate_scope_id") or "")
        if candidate_scope_id and candidate_scope_id != expected_scope_id:
            errors.append(
                f"readiness scope mismatch for {lane[0]}:{lane[1]}:{lane[2]}"
            )
    return errors


def _lane_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("strategy_group_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("side") or ""),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            errors = validate_candidate_readiness_current_projection(conn)
    finally:
        engine.dispose()
    report = {
        "status": (
            "candidate_readiness_current_projection_valid"
            if not errors
            else "blocked"
        ),
        "errors": errors,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
