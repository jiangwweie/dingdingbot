#!/usr/bin/env python3
"""Query bounded PG runtime lineage and print one read-only JSON result."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from src.application.runtime_signal_forensics import (  # noqa: E402
    RuntimeSignalForensicsQuery,
    reduce_runtime_signal_forensics,
)
from src.infrastructure.runtime_signal_forensics_repository import (  # noqa: E402
    PgRuntimeSignalForensicsRepository,
)


SYSTEMD_UNITS = (
    "brc-runtime-signal-watcher.timer",
    "brc-runtime-signal-watcher.service",
    "brc-runtime-monitor.timer",
    "brc-runtime-monitor.service",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read PG signal lineage for an absolute time window; stdout only."
    )
    parser.add_argument("--start", required=True, help="ISO-8601 window start")
    parser.add_argument("--end", required=True, help="ISO-8601 window end")
    parser.add_argument("--strategy-group-id")
    parser.add_argument("--symbol")
    parser.add_argument("--side", choices=("long", "short"))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--database-url")
    parser.add_argument(
        "--include-systemd",
        action="store_true",
        help="Include a timeout-bounded local systemd snapshot.",
    )
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _iso_to_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include an explicit timezone offset")
    return int(parsed.timestamp() * 1000)


def _systemd_snapshot() -> dict[str, Any]:
    command = [
        "systemctl",
        "show",
        "--no-pager",
        "--property=Id,LoadState,ActiveState,SubState,Result",
        *SYSTEMD_UNITS,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return {
            "checked": True,
            "returncode": completed.returncode,
            "output": completed.stdout[:4000],
            "error": completed.stderr[:1000] or None,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "checked": True,
            "returncode": None,
            "output": "",
            "error": f"{type(exc).__name__}:{str(exc)[:240]}",
        }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        query = RuntimeSignalForensicsQuery(
            start_ms=_iso_to_ms(args.start),
            end_ms=_iso_to_ms(args.end),
            strategy_group_id=args.strategy_group_id,
            symbol=args.symbol,
            side=args.side,
            limit=args.limit,
        )
    except (ValueError, TypeError) as exc:
        raise SystemExit(str(exc)) from exc
    database_url = args.database_url or os.environ.get("BRC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("PG database configuration is required")
    database_url = normalize_sync_postgres_dsn(database_url)
    if not args.allow_non_postgres_for_test and not is_sync_postgres_dsn(database_url):
        raise SystemExit("runtime signal forensics requires a PostgreSQL DSN")
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = PgRuntimeSignalForensicsRepository(conn).query(query)
        result = reduce_runtime_signal_forensics(query, rows).model_dump(
            mode="json", by_alias=True
        )
    finally:
        engine.dispose()
    result["configuration"] = {"database_configured": True}
    result["systemd"] = (
        _systemd_snapshot() if args.include_systemd else {"checked": False}
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
