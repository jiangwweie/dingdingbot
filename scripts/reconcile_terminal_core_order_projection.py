#!/usr/bin/env python3
"""Dry-run or apply terminal ticket-bound truth to core ``orders`` rows.

This is a bounded PG repair utility, not a trading command.  It never calls an
exchange, creates an order, deletes data, or changes profile/sizing/policy.
Only a closed post-submit closure plus an exact terminal protection identity can
advance a stale non-terminal core order.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.core_order_terminal_projection import (
    project_terminal_ticket_bound_orders_to_core,
)
from src.infrastructure.sync_pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(str(args.database_url or ""))
    if not database_url:
        raise SystemExit("PG_DATABASE_URL is required")
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        raise SystemExit("terminal core-order projection requires PostgreSQL")

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            candidates = _closed_terminal_candidates(conn)
            if not args.apply:
                print({"status": "dry_run", "candidate_count": len(candidates), "candidates": candidates})
                return 0
            projected: list[dict[str, str]] = []
            for ticket_id, candidate in candidates.items():
                if _has_active_core_position(conn, symbol=candidate["symbol"]):
                    continue
                projected.extend(
                    project_terminal_ticket_bound_orders_to_core(
                        conn,
                        ticket_id=ticket_id,
                        symbol=candidate["symbol"],
                        protection_orders=candidate["orders"],
                        lifecycle_status="lifecycle_closed",
                        now_ms=int(candidate["updated_at_ms"]),
                    )
                )
            print(
                {
                    "status": "applied",
                    "candidate_count": len(candidates),
                    "projected_count": len(projected),
                    "projected": projected,
                    "exchange_write_called": False,
                }
            )
            return 0
    finally:
        engine.dispose()


def _closed_terminal_candidates(conn: sa.engine.Connection) -> dict[str, dict[str, Any]]:
    required = {
        "brc_ticket_bound_post_submit_closures",
        "brc_ticket_bound_exit_protection_sets",
        "brc_ticket_bound_exit_protection_orders",
    }
    if not required.issubset(set(sa.inspect(conn).get_table_names())):
        raise RuntimeError("terminal_core_order_projection_schema_missing")
    rows = conn.execute(
        sa.text(
            """
            SELECT closure.ticket_id, protection_set.symbol, closure.updated_at_ms,
                   protection.local_order_id, protection.exchange_order_id,
                   protection.role, protection.status
            FROM brc_ticket_bound_post_submit_closures AS closure
            JOIN brc_ticket_bound_exit_protection_sets AS protection_set
              ON protection_set.ticket_id = closure.ticket_id
            JOIN brc_ticket_bound_exit_protection_orders AS protection
              ON protection.ticket_id = closure.ticket_id
            WHERE closure.status = 'closed'
              AND protection.status IN ('filled', 'cancelled', 'replaced', 'expired', 'rejected')
            ORDER BY closure.ticket_id, protection.local_order_id
            """
        )
    ).mappings()
    candidates: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticket_id = str(row["ticket_id"])
        candidate = candidates.setdefault(
            ticket_id,
            {
                "symbol": str(row["symbol"]),
                "updated_at_ms": int(row["updated_at_ms"] or 0),
                "orders": [],
            },
        )
        candidate["orders"].append(dict(row))
    return candidates


def _has_active_core_position(conn: sa.engine.Connection, *, symbol: str) -> bool:
    if not sa.inspect(conn).has_table("positions"):
        return False
    columns = {column["name"] for column in sa.inspect(conn).get_columns("positions")}
    if not {"symbol", "is_closed"}.issubset(columns):
        return True
    row = conn.execute(
        sa.text("SELECT 1 FROM positions WHERE symbol = :symbol AND is_closed = false LIMIT 1"),
        {"symbol": symbol},
    ).first()
    return row is not None


if __name__ == "__main__":
    raise SystemExit(main())
