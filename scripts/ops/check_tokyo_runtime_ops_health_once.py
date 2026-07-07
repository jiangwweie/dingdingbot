#!/usr/bin/env python3
"""One-shot Tokyo runtime ops health command plan/check helper.

By default this prints the readonly commands an operator should run on Tokyo.
It can execute locally with --execute-local, which is intended for tests and for
running directly on the server. It never mutates runtime state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402


SCHEMA = "brc.ops.tokyo_runtime_ops_health_once.v1"
LOW_PRIORITY_PREFIX = ("timeout", "3s", "ionice", "-c3", "nice", "-n", "19")
PG_ROW_COUNT_TABLES = (
    "brc_runtime_fact_snapshots",
    "brc_watcher_runtime_coverage",
    "brc_server_monitor_runs",
)

COMMANDS = (
    ("disk_df", ("df", "-h")),
    ("inode_df", ("df", "-ih", "/")),
    (
        "reports_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/reports"),
    ),
    (
        "releases_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/releases"),
    ),
    (
        "backups_du",
        LOW_PRIORITY_PREFIX + ("du", "-sh", "/home/ubuntu/brc-deploy/backups"),
    ),
    ("journald_usage", ("journalctl", "--disk-usage")),
    ("backend_status", ("systemctl", "is-active", "brc-owner-console-backend.service")),
    ("watcher_timer_status", ("systemctl", "is-active", "brc-runtime-signal-watcher.timer")),
    ("monitor_timer_status", ("systemctl", "is-active", "brc-runtime-monitor.timer")),
    ("pg_listener", ("ss", "-ltnp")),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_payload(execute_local=args.execute_local)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] != "critical" else 2


def build_payload(*, execute_local: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, command in COMMANDS:
        if not execute_local:
            results.append({"name": name, "command": list(command), "status": "planned"})
            continue
        executable = shutil.which(command[0])
        if not executable:
            results.append({"name": name, "command": list(command), "status": "missing_binary"})
            continue
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=8,
        )
        results.append(
            {
                "name": name,
                "command": list(command),
                "status": "ok" if completed.returncode == 0 else "warn",
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
    results.append(_pg_runtime_row_counts_result(execute_local=execute_local))
    statuses = {row["status"] for row in results}
    status = "ok"
    if "warn" in statuses or "missing_binary" in statuses:
        status = "warn"
    return {
        "schema": SCHEMA,
        "status": status,
        "mode": "execute_local" if execute_local else "plan_only",
        "results": results,
        "checks": {
            "no_pg_runtime_truth_write": True,
            "no_trade_runtime_mutation": True,
            "pg_row_count_check_is_readonly": True,
            "pg_retention_apply_not_run": True,
            "readonly_commands_only": True,
        },
    }


def _pg_runtime_row_counts_result(*, execute_local: bool) -> dict[str, Any]:
    base = {
        "name": "pg_runtime_row_counts",
        "command": ["internal_sqlalchemy_readonly_row_counts"],
    }
    if not execute_local:
        return {**base, "status": "planned"}
    raw_dsn = os.environ.get("PG_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    if not raw_dsn:
        return {**base, "status": "warn", "stderr_tail": "PG_DATABASE_URL missing"}
    database_url = normalize_sync_postgres_dsn(raw_dsn)
    if not is_sync_postgres_dsn(database_url):
        return {**base, "status": "warn", "stderr_tail": "PG DSN is not sync PostgreSQL"}
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            counts = {
                table_name: int(
                    conn.execute(sa.text(f"SELECT count(*) FROM {table_name}")).scalar_one()
                )
                for table_name in PG_ROW_COUNT_TABLES
            }
    except Exception as exc:
        return {
            **base,
            "status": "warn",
            "stderr_tail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        engine.dispose()
    return {
        **base,
        "status": "ok",
        "stdout_tail": "\n".join(
            f"{table_name}={count}" for table_name, count in counts.items()
        ),
        "stderr_tail": "",
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-local", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
