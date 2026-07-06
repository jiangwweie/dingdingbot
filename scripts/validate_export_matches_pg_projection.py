#!/usr/bin/env python3
"""Validate PG current projections are not backed by JSON export files."""

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


def validate_export_matches_pg_projection(conn: sa.engine.Connection) -> list[str]:
    metadata = sa.MetaData()
    snapshots = sa.Table("brc_control_read_model_snapshots", metadata, autoload_with=conn)
    rows = [
        dict(row)
        for row in conn.execute(
            sa.select(snapshots).where(snapshots.c.is_current.is_(True))
        ).mappings()
    ]
    errors: list[str] = []
    for row in rows:
        model_type = str(row.get("model_type") or "")
        output_path = str(row.get("output_path") or "")
        if output_path:
            errors.append(f"{model_type} current projection must not define export path: {output_path}")
    return errors


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
            errors = validate_export_matches_pg_projection(conn)
    finally:
        engine.dispose()
    report = {
        "status": "pg_current_projection_export_absent" if not errors else "blocked",
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
