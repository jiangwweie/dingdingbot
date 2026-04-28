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
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.infrastructure.database import get_pg_session_maker, init_pg_core_db

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


def _sqlite_row_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(row[0]) if row else 0


def _sqlite_signal_id_map(db_path: Path) -> dict[int, str]:
    if "signals" not in _sqlite_tables(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, signal_id FROM signals").fetchall()
        return {int(row["id"]): row["signal_id"] for row in rows if row["signal_id"]}
    finally:
        conn.close()


def _coerce_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        if value == "":
            return None
        try:
            return json.dumps(json.loads(value), ensure_ascii=False, default=str)
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


def _load_json_artifact(ref: Any) -> Any:
    if not ref:
        return {}
    path = Path(str(ref))
    if not path.is_absolute():
        path = ROOT / path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


async def _copy_table(session, db_path: Path, table: str, truncate: bool) -> int:
    rows = _sqlite_rows(db_path, table)
    if table == "signal_take_profits":
        signal_id_map = _sqlite_signal_id_map(db_path)
        mapped_rows = []
        for row in rows:
            numeric_id = row.get("signal_id")
            signal_id = signal_id_map.get(int(numeric_id)) if numeric_id is not None else None
            if not signal_id:
                continue
            mapped = dict(row)
            mapped["signal_id"] = signal_id
            mapped_rows.append(mapped)
        rows = mapped_rows
    elif table == "runtime_profiles":
        rows = [
            {
                ("profile_payload" if key == "profile_json" else key): value
                for key, value in row.items()
            }
            for row in rows
        ]
    elif table == "backtest_reports":
        cleaned_rows = []
        for row in rows:
            cleaned = dict(row)
            sharpe_ratio = cleaned.get("sharpe_ratio")
            if isinstance(sharpe_ratio, str) and sharpe_ratio.lstrip().startswith(("[", "{")):
                if not cleaned.get("positions_summary"):
                    cleaned["positions_summary"] = sharpe_ratio
                cleaned["sharpe_ratio"] = None
            cleaned_rows.append(cleaned)
        rows = cleaned_rows
    elif table == "research_jobs":
        rows = [
            {
                ("spec_payload" if key == "spec_json" else key): value
                for key, value in row.items()
            }
            for row in rows
        ]
        for row in rows:
            if not row.get("spec_payload"):
                row["spec_payload"] = _load_json_artifact(row.get("spec_ref"))
    elif table == "research_run_results":
        rows = [
            {
                ("spec_snapshot" if key == "spec_snapshot_json" else
                 "summary_metrics" if key == "summary_metrics_json" else
                 "artifact_index" if key == "artifact_index_json" else key): value
                for key, value in row.items()
            }
            for row in rows
        ]
    elif table == "candidate_records":
        rows = [
            {
                ("risks" if key == "risks_json" else key): value
                for key, value in row.items()
            }
            for row in rows
        ]

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

    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            key: _coerce_value(key, value)
            for key, value in row.items()
            if key in pg_columns
        }
        if not payload:
            continue
        payloads.append(payload)

    if not payloads:
        return 0

    columns = list(payloads[0].keys())
    column_sql = ", ".join(f'"{col}"' for col in columns)
    value_sql = ", ".join(f":{col}" for col in columns)
    stmt = text(f'INSERT INTO "{target_table}" ({column_sql}) VALUES ({value_sql}) ON CONFLICT DO NOTHING')

    inserted = 0
    batch_size = 5000 if target_table == "klines" else 1000
    for start in range(0, len(payloads), batch_size):
        batch = payloads[start:start + batch_size]
        await session.execute(stmt, batch)
        inserted += len(batch)
        if target_table == "klines" and inserted % 100000 == 0:
            print(f"[progress] {target_table}: attempted {inserted}/{len(payloads)}", flush=True)

    await session.commit()
    print(f"[copy] {db_path.relative_to(ROOT)}:{table} -> {target_table}, attempted {inserted}", flush=True)
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
                if table == "klines":
                    print(f"[info] data/v3_dev.db:klines rows={_sqlite_row_count(db_path, table)}", flush=True)
                total += await _copy_table(session, db_path, table, args.truncate)

    print(f"[done] migration copy attempted rows={total}")


if __name__ == "__main__":
    asyncio.run(main())
