#!/usr/bin/env python3
"""Validate one owner projector per production current projection."""

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


REQUIRED_OWNERS = {
    "candidate_pool": "pg_candidate_pool_projector",
    "daily_live_enablement_table": "pg_daily_table_projector",
    "goal_status": "pg_goal_status_projector",
    "runtime_safety_state": "pg_runtime_safety_projector",
    "server_monitor": "pg_server_monitor_projector",
    "tradeability_decision": "pg_tradeability_projector",
}


def validate_current_projection_ownership(conn: sa.engine.Connection) -> list[str]:
    metadata = sa.MetaData()
    table = sa.Table("brc_current_projection_ownership", metadata, autoload_with=conn)
    rows = [dict(row) for row in conn.execute(sa.select(table)).mappings()]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    owners_by_model: dict[str, str] = {}
    for row in rows:
        model_type = str(row.get("model_type") or "")
        scope_key = str(row.get("projection_scope_key") or "")
        key = (model_type, scope_key)
        if not model_type or not scope_key:
            errors.append("ownership row missing model_type/projection_scope_key")
            continue
        if key in seen:
            errors.append(f"duplicate ownership: {model_type}:{scope_key}")
        seen.add(key)
        if scope_key == "global":
            owners_by_model[model_type] = str(row.get("owner_projector") or "")
        if row.get("legacy_writer_allowed") is not False:
            errors.append(f"{model_type}:{scope_key} allows legacy writer")
        if row.get("current_source_mode") != "db_backed":
            errors.append(f"{model_type}:{scope_key} is not db_backed")
        if row.get("sunset_condition"):
            errors.append(f"{model_type}:{scope_key} has sunset_condition")
    for model_type, expected_owner in REQUIRED_OWNERS.items():
        actual = owners_by_model.get(model_type)
        if actual != expected_owner:
            errors.append(
                f"owner mismatch for {model_type}: expected={expected_owner}:actual={actual}"
            )
    errors.extend(_validate_runtime_process_outcomes(conn))
    return errors


def _validate_runtime_process_outcomes(
    conn: sa.engine.Connection,
) -> list[str]:
    if not sa.inspect(conn).has_table("brc_runtime_process_outcomes"):
        return []
    table = sa.Table(
        "brc_runtime_process_outcomes",
        sa.MetaData(),
        autoload_with=conn,
    )
    expected_runtime_head = str(os.getenv("BRC_RUNTIME_HEAD") or "").strip()
    errors: list[str] = []
    for row in conn.execute(sa.select(table)).mappings():
        process_name = str(row.get("process_name") or "unknown")
        scope_key = str(row.get("scope_key") or "unknown")
        identity = f"{process_name}:{scope_key}"
        if row.get("projector_owner") != "runtime_process_outcome_projector":
            errors.append(f"runtime process projector mismatch: {identity}")
        if not str(row.get("source_watermark") or "").strip():
            errors.append(f"runtime process source watermark missing: {identity}")
        if int(row.get("completed_at_ms") or 0) > int(row.get("updated_at_ms") or 0):
            errors.append(f"runtime process timestamp invalid: {identity}")
        if expected_runtime_head and row.get("runtime_head") != expected_runtime_head:
            errors.append(
                f"runtime process head mismatch: {identity}:"
                f"expected={expected_runtime_head}:actual={row.get('runtime_head')}"
            )
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
            errors = validate_current_projection_ownership(conn)
    finally:
        engine.dispose()
    report: dict[str, Any] = {
        "status": "current_projection_ownership_valid" if not errors else "blocked",
        "errors": errors,
        "required_owners": REQUIRED_OWNERS,
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
