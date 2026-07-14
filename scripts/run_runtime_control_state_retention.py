#!/usr/bin/env python3
"""Run PG runtime-control-state retention cleanup.

Default mode is dry-run. Apply mode only deletes allowlisted runtime noise:
fact snapshots, non-current watcher coverage rows, and old server monitor runs.
Signal events, promotion candidates, action-time lanes, tickets, orders,
notifications, policy, scope, and review evidence are never deleted here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402


SCHEMA = "brc.runtime_control_state_retention_run.v1"
AUTHORITY_BOUNDARY = (
    "retention_cleanup_only; no_signal_ticket_order_policy_or_credential_mutation; "
    "no_finalgate_no_operation_layer_no_exchange_write"
)
RETENTION_RUN_TABLE = "brc_runtime_retention_runs"
LOCK_KEY = 7_405_090
MS_PER_DAY = 86_400_000


@dataclass(frozen=True)
class CleanupTarget:
    table_name: str
    id_column: str
    timestamp_column: str
    retention_days: int
    description: str


TARGETS = (
    CleanupTarget(
        table_name="brc_runtime_fact_snapshots",
        id_column="fact_snapshot_id",
        timestamp_column="created_at_ms",
        retention_days=14,
        description="raw public/account/action-time fact snapshots",
    ),
    CleanupTarget(
        table_name="brc_watcher_runtime_coverage",
        id_column="runtime_coverage_id",
        timestamp_column="created_at_ms",
        retention_days=14,
        description="historical non-current watcher runtime coverage rows",
    ),
    CleanupTarget(
        table_name="brc_server_monitor_runs",
        id_column="monitor_run_id",
        timestamp_column="created_at_ms",
        retention_days=90,
        description="server monitor run history",
    ),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = _database_url(args)
    if not database_url:
        print("ERROR: PG_DATABASE_URL_or_DATABASE_URL_required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url):
        if not args.allow_sqlite_for_tests:
            print("ERROR: sync_postgres_database_url_required", file=sys.stderr)
            return 2
        normalized_url = database_url
    else:
        normalized_url = normalize_sync_postgres_dsn(database_url)

    engine = sa.create_engine(normalized_url, future=True)
    now_ms = args.now_ms or _now_ms()
    with engine.begin() as conn:
        _ensure_retention_run_table(conn)
        locked = _try_advisory_lock(conn)
        if not locked:
            payload = _blocked_payload(
                now_ms=now_ms,
                apply=args.apply,
                blocker="retention_advisory_lock_busy",
            )
            _print_payload(payload, args.json)
            return 1
        try:
            payload = run_retention(conn, now_ms=now_ms, apply=args.apply, batch_size=args.batch_size)
        finally:
            _release_advisory_lock(conn)
    _print_payload(payload, args.json)
    return 0


def run_retention(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
    apply: bool,
    batch_size: int,
) -> dict[str, Any]:
    _ensure_retention_run_table(conn)
    run_id = f"runtime-retention:{now_ms}:{uuid4().hex[:12]}"
    table_results: list[dict[str, Any]] = []
    for target in TARGETS:
        table_results.append(
            _cleanup_target(
                conn,
                target=target,
                now_ms=now_ms,
                apply=apply,
                batch_size=batch_size,
            )
        )
    deleted_total = sum(int(row.get("deleted_count") or 0) for row in table_results)
    eligible_total = sum(int(row.get("eligible_count") or 0) for row in table_results)
    status = "retention_applied" if apply else "retention_dry_run"
    payload = {
        "schema": SCHEMA,
        "status": status,
        "run_id": run_id,
        "mode": "apply" if apply else "dry_run",
        "started_at_ms": now_ms,
        "finished_at_ms": _now_ms(),
        "allowlisted_tables": [target.table_name for target in TARGETS],
        "eligible_total": eligible_total,
        "deleted_total": deleted_total,
        "table_results": table_results,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    _insert_retention_run(
        conn,
        run_id=run_id,
        started_at_ms=now_ms,
        finished_at_ms=int(payload["finished_at_ms"]),
        status=status,
        apply_mode=apply,
        eligible_total=eligible_total,
        deleted_total=deleted_total,
        details=payload,
    )
    return payload


def _cleanup_target(
    conn: sa.engine.Connection,
    *,
    target: CleanupTarget,
    now_ms: int,
    apply: bool,
    batch_size: int,
) -> dict[str, Any]:
    if not _has_table(conn, target.table_name):
        return {
            "table_name": target.table_name,
            "status": "skipped_missing_table",
            "retention_days": target.retention_days,
            "cutoff_ms": now_ms - target.retention_days * MS_PER_DAY,
            "eligible_count": 0,
            "deleted_count": 0,
            "guards": _target_guards(target.table_name),
        }
    cutoff_ms = now_ms - target.retention_days * MS_PER_DAY
    where_sql = _target_where_sql(conn, target)
    params = {
        "cutoff_ms": cutoff_ms,
        "batch_size": int(batch_size),
    }
    eligible_count = int(
        conn.execute(
            sa.text(
                f"""
                SELECT COUNT(*)
                FROM {target.table_name}
                WHERE {where_sql}
                """
            ),
            params,
        ).scalar()
        or 0
    )
    deleted_count = 0
    if apply and eligible_count:
        result = conn.execute(
            sa.text(
                f"""
                DELETE FROM {target.table_name}
                WHERE {target.id_column} IN (
                  SELECT {target.id_column}
                  FROM {target.table_name}
                  WHERE {where_sql}
                  ORDER BY {target.timestamp_column} ASC, {target.id_column} ASC
                  LIMIT :batch_size
                )
                """
            ),
            params,
        )
        deleted_count = int(result.rowcount or 0)
    return {
        "table_name": target.table_name,
        "status": "applied" if apply else "dry_run",
        "description": target.description,
        "retention_days": target.retention_days,
        "cutoff_ms": cutoff_ms,
        "eligible_count": eligible_count,
        "deleted_count": deleted_count,
        "batch_size": int(batch_size),
        "guards": _target_guards(target.table_name),
    }


def _target_where_sql(conn: sa.engine.Connection, target: CleanupTarget) -> str:
    base = f"{target.timestamp_column} < :cutoff_ms"
    if target.table_name == "brc_watcher_runtime_coverage":
        return f"{base} AND is_current = false"
    if target.table_name == "brc_runtime_fact_snapshots":
        clauses = [base]
        if _has_table(conn, "brc_live_signal_events"):
            clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM brc_live_signal_events e "
                "  WHERE e.fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id"
                ")"
            )
        if _has_table(conn, "brc_promotion_candidates"):
            clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM brc_promotion_candidates p "
                "  WHERE p.facts_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id"
                ")"
            )
        if _has_table(conn, "brc_action_time_lane_inputs"):
            clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM brc_action_time_lane_inputs l "
                "  WHERE l.public_fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id "
                "     OR l.action_time_fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id"
                ")"
            )
        if _has_table(conn, "brc_action_time_tickets"):
            clauses.append(
                "NOT EXISTS ("
                "  SELECT 1 FROM brc_action_time_tickets t "
                "  WHERE t.public_fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id "
                "     OR t.action_time_fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id "
                "     OR t.account_safe_fact_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id "
                "     OR t.account_mode_snapshot_id = brc_runtime_fact_snapshots.fact_snapshot_id"
                ")"
            )
        return " AND ".join(clauses)
    return base


def _target_guards(table_name: str) -> list[str]:
    if table_name == "brc_watcher_runtime_coverage":
        return ["allowlist", "batch_delete", "preserve_is_current_true"]
    if table_name == "brc_runtime_fact_snapshots":
        return [
            "allowlist",
            "batch_delete",
            "preserve_live_signal_event_refs",
            "preserve_promotion_candidate_refs",
            "preserve_action_time_lane_refs",
            "preserve_action_time_ticket_refs",
        ]
    return ["allowlist", "batch_delete"]


def _ensure_retention_run_table(conn: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    json_type: sa.types.TypeEngine
    if str(conn.dialect.name) == "postgresql":
        json_type = postgresql.JSONB(astext_type=sa.Text())
    else:
        json_type = sa.JSON()
    table = sa.Table(
        RETENTION_RUN_TABLE,
        metadata,
        sa.Column("retention_run_id", sa.String(192), primary_key=True),
        sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("apply_mode", sa.Boolean(), nullable=False),
        sa.Column("eligible_total", sa.Integer(), nullable=False),
        sa.Column("deleted_total", sa.Integer(), nullable=False),
        sa.Column("details", json_type, nullable=False),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
    )
    table.create(conn, checkfirst=True)


def _insert_retention_run(
    conn: sa.engine.Connection,
    *,
    run_id: str,
    started_at_ms: int,
    finished_at_ms: int,
    status: str,
    apply_mode: bool,
    eligible_total: int,
    deleted_total: int,
    details: dict[str, Any],
) -> None:
    json_type: sa.types.TypeEngine
    if str(conn.dialect.name) == "postgresql":
        json_type = postgresql.JSONB(astext_type=sa.Text())
    else:
        json_type = sa.JSON()
    table = sa.Table(
        RETENTION_RUN_TABLE,
        sa.MetaData(),
        sa.Column("retention_run_id", sa.String(192), primary_key=True),
        sa.Column("started_at_ms", sa.BIGINT(), nullable=False),
        sa.Column("finished_at_ms", sa.BIGINT(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("apply_mode", sa.Boolean(), nullable=False),
        sa.Column("eligible_total", sa.Integer(), nullable=False),
        sa.Column("deleted_total", sa.Integer(), nullable=False),
        sa.Column("details", json_type, nullable=False),
        sa.Column("authority_boundary", sa.Text(), nullable=False),
        sa.Column("created_at_ms", sa.BIGINT(), nullable=False),
    )
    conn.execute(
        table.insert().values(
            retention_run_id=run_id,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            status=status,
            apply_mode=apply_mode,
            eligible_total=eligible_total,
            deleted_total=deleted_total,
            details=details,
            authority_boundary=AUTHORITY_BOUNDARY,
            created_at_ms=finished_at_ms,
        )
    )


def _has_table(conn: sa.engine.Connection, table_name: str) -> bool:
    return sa.inspect(conn).has_table(table_name)


def _try_advisory_lock(conn: sa.engine.Connection) -> bool:
    if str(conn.dialect.name) != "postgresql":
        return True
    return bool(
        conn.execute(
            sa.text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": LOCK_KEY},
        ).scalar()
    )


def _release_advisory_lock(conn: sa.engine.Connection) -> None:
    if str(conn.dialect.name) != "postgresql":
        return
    conn.execute(sa.text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": LOCK_KEY})


def _blocked_payload(*, now_ms: int, apply: bool, blocker: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "blocked",
        "mode": "apply" if apply else "dry_run",
        "started_at_ms": now_ms,
        "finished_at_ms": _now_ms(),
        "blockers": [blocker],
        "deleted_total": 0,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _database_url(args: argparse.Namespace) -> str:
    return str(
        args.database_url
        or os.getenv("PG_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-sqlite-for-tests", action="store_true")
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
