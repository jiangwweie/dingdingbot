#!/usr/bin/env python3
"""Validate PG production current projection runs have authority lineage."""

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


def validate_pg_current_projection_lineage(conn: sa.engine.Connection) -> list[str]:
    metadata = sa.MetaData()
    table = sa.Table("brc_projection_runs", metadata, autoload_with=conn)
    rows = [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(table.c.projection_target == "production_current")
        ).mappings()
    ]
    errors: list[str] = []
    if not rows:
        return ["missing production_current projection runs"]
    for row in rows:
        run_id = str(row.get("projection_run_id") or "<missing>")
        if row.get("source_mode") != "db_backed":
            errors.append(f"{run_id} source_mode is not db_backed")
        if not str(row.get("owner_projector") or ""):
            errors.append(f"{run_id} missing owner_projector")
        if not str(row.get("code_version") or ""):
            errors.append(f"{run_id} missing code_version")
        if not _non_empty_json(row.get("input_watermark")):
            errors.append(f"{run_id} missing input_watermark")
        if not _non_empty_json(row.get("source_priority")):
            errors.append(f"{run_id} missing source_priority")
        if row.get("legacy_diagnostics_affected_current") is not False:
            errors.append(f"{run_id} legacy diagnostics affected current")
        if row.get("status") != "succeeded":
            errors.append(f"{run_id} status is not succeeded")
    return errors


def _non_empty_json(value: Any) -> bool:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return bool(value)
    return bool(value)


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
            errors = validate_pg_current_projection_lineage(conn)
    finally:
        engine.dispose()
    report: dict[str, Any] = {
        "status": "pg_current_projection_lineage_valid" if not errors else "blocked",
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
