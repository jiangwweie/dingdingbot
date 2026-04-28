#!/usr/bin/env python3
"""Copy remaining SQLite state tables into PostgreSQL.

This is an operational migration helper for the PG full-state window. It is
intentionally conservative:
- it only copies known state/history tables;
- it skips missing SQLite files/tables;
- by default it uses `ON CONFLICT DO NOTHING` and never truncates PG data;
- pass `--truncate` only for a fresh local/dev PG rebuild.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import text

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db


ROOT = Path(__file__).resolve().parents[1]

TABLE_SOURCES: dict[str, list[str]] = {
    "data/v3_dev.db": [
        "orders",
        "execution_intents",
        "positions",
        "execution_recovery_tasks",
        "signals",
        "signal_take_profits",
        "signal_attempts",
        "runtime_profiles",
        "config_entries_v2",
        "config_profiles",
        "config_snapshots",
        "config_entries",
        "backtest_reports",
        "position_close_events",
        "backtest_attributions",
        "klines",
    ],
    "data/config_snapshots.db": [
        "config_snapshots",
        "config_entries",
    ],
    "data/research_control_plane.db": [
        "research_jobs",
        "research_run_results",
        "candidate_records",
    ],
    "data/reconciliation.db": [
        "reconciliation_reports",
        "reconciliation_details",
    ],
    "data/optimization_history.db": [
        "optimization_history",
    ],
}

JSON_COLUMNS = {
    "details",
    "trace_tree",
    "profile_json",
    "snapshot_data",
    "spec_payload",
    "spec_snapshot",
    "summary_metrics",
    "artifact_index",
    "risks",
    "actions_taken",
    "local_data",
    "exchange_data",
    "action_result",
    "params",
    "signal_attributions",
    "aggregate_attribution",
    "analysis_dimensions",
}

BOOL_COLUMNS = {
    "is_active",
    "is_readonly",
    "is_closed",
    "is_consistent",
    "resolved",
    "reduce_only",
    "is_closed_only",
}


def _sqlite_tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row[0] for row in rows}


def _sqlite_rows(db_path: Path, table: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()]
    finally:
        conn.close()


def _coerce_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS:
        if isinstance(value, (dict, list)):
            return value
        if value == "":
            return None
        try:
            return json.loads(value)
        except Exception:
            return value
    if column in BOOL_COLUMNS:
        return bool(value)
    return value


async def _pg_columns(session, table: str) -> set[str]:
    result = await session.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    )
    return {row[0] for row in result.fetchall()}


def _target_table(table: str, rows: list[dict[str, Any]]) -> str:
    if table == "config_snapshots" and rows:
        sample = rows[0]
        if "version" in sample and "config_json" in sample:
            return "config_snapshot_versions"
    return table


async def _copy_table(session, db_path: Path, table: str, truncate: bool) -> int:
    rows = _sqlite_rows(db_path, table)
    target_table = _target_table(table, rows)
    pg_columns = await _pg_columns(session, target_table)
    if not pg_columns:
        print(f"[skip] PG table missing: {target_table}")
        return 0

    if not rows:
        print(f"[skip] empty: {db_path.relative_to(ROOT)}:{table}")
        return 0

    if truncate:
        await session.execute(text(f'TRUNCATE TABLE "{target_table}" RESTART IDENTITY CASCADE'))

    inserted = 0
    for row in rows:
        payload = {
            key: _coerce_value(key, value)
            for key, value in row.items()
            if key in pg_columns
        }
        if not payload:
            continue
        columns = list(payload.keys())
        column_sql = ", ".join(f'"{col}"' for col in columns)
        value_sql = ", ".join(f":{col}" for col in columns)
        stmt = text(f'INSERT INTO "{target_table}" ({column_sql}) VALUES ({value_sql}) ON CONFLICT DO NOTHING')
        await session.execute(stmt, payload)
        inserted += 1

    print(f"[copy] {db_path.relative_to(ROOT)}:{table} -> {target_table}, attempted {inserted}")
    return inserted


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--truncate", action="store_true", help="truncate PG target tables before copy")
    args = parser.parse_args()

    await init_pg_core_db()
    maker = get_pg_session_maker()

    async with maker() as session:
        total = 0
        for db_rel, tables in TABLE_SOURCES.items():
            db_path = ROOT / db_rel
            if not db_path.exists():
                print(f"[skip] SQLite file missing: {db_rel}")
                continue
            existing = _sqlite_tables(db_path)
            for table in tables:
                if table not in existing:
                    print(f"[skip] SQLite table missing: {db_rel}:{table}")
                    continue
                total += await _copy_table(session, db_path, table, args.truncate)
        await session.commit()

    print(f"[done] migration copy attempted rows={total}")


if __name__ == "__main__":
    asyncio.run(main())
