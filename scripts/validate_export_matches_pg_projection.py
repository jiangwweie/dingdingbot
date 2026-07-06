#!/usr/bin/env python3
"""Validate JSON exports match PG current read-model snapshots."""

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
        if not output_path:
            continue
        path = Path(output_path)
        if not path.exists():
            errors.append(f"{model_type} export missing: {output_path}")
            continue
        try:
            export_payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{model_type} export invalid json: {exc}")
            continue
        if _normalized_payload(export_payload) != _normalized_payload(row.get("payload")):
            errors.append(f"{model_type} export does not match PG snapshot")
    return errors


def _normalized_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return json.loads(json.dumps(payload, sort_keys=True, default=str))


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
        "status": "export_matches_pg_projection_valid" if not errors else "blocked",
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
