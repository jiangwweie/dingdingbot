#!/usr/bin/env python3
"""Verify PG lifecycle truth before enabling durable exchange mutation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.lifecycle_mutation_capability import (  # noqa: E402
    lifecycle_mutation_capability_decision,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


REQUIRED_TABLES = {
    "brc_exchange_account_modes_current",
    "brc_runtime_capabilities_current",
    "brc_ticket_bound_exchange_commands",
    "brc_ticket_bound_scope_freezes",
    "brc_ticket_bound_protected_submit_attempts",
    "brc_ticket_bound_order_lifecycle_runs",
    "brc_ticket_bound_exit_protection_sets",
}


def evaluate_phase_two_readiness(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
    allow_capability_enabled: bool = False,
) -> dict[str, Any]:
    inspector = sa.inspect(conn)
    blockers: list[str] = []
    missing = sorted(REQUIRED_TABLES - set(inspector.get_table_names()))
    blockers.extend(f"phase_two_required_table_missing:{name}" for name in missing)
    if missing:
        return _result(blockers, {})

    capability = lifecycle_mutation_capability_decision(conn)
    if capability.get("enabled") is True and not allow_capability_enabled:
        blockers.append("phase_two_capability_already_enabled")
    blockers.extend(
        blocker
        for blocker in capability.get("blockers") or []
        if blocker != "lifecycle_mutation_capability_not_ready"
    )

    safe_modes = _count(
        conn,
        """
        SELECT count(*)
        FROM brc_exchange_account_modes_current
        WHERE status = 'current'
          AND position_mode_safe = true
          AND valid_until_ms > :now_ms
        """,
        now_ms=now_ms,
    )
    if safe_modes != 1:
        blockers.append(f"phase_two_safe_account_mode_count:{safe_modes}")

    counts = {
        "critical_exchange_commands": _count(
            conn,
            """
            SELECT count(*) FROM brc_ticket_bound_exchange_commands
            WHERE command_state IN ('outcome_unknown', 'hard_stopped', 'dispatching')
            """,
        ),
        "active_domain_holds": _count(
            conn,
            "SELECT count(*) FROM brc_ticket_bound_scope_freezes WHERE status = 'active'",
        ),
        "active_real_lifecycles": _count(
            conn,
            """
            SELECT count(*)
            FROM brc_ticket_bound_order_lifecycle_runs AS l
            JOIN brc_ticket_bound_protected_submit_attempts AS a
              ON a.protected_submit_attempt_id = l.protected_submit_attempt_id
            WHERE a.submit_mode = 'real_gateway_action'
              AND a.exchange_write_called = true
              AND l.status <> 'lifecycle_closed'
            """,
        ),
        "unprotected_real_attempts": _count(
            conn,
            """
            SELECT count(*)
            FROM brc_ticket_bound_protected_submit_attempts AS a
            LEFT JOIN brc_ticket_bound_exit_protection_sets AS s
              ON s.protected_submit_attempt_id = a.protected_submit_attempt_id
             AND s.protection_complete = true
            WHERE a.submit_mode = 'real_gateway_action'
              AND a.exchange_write_called = true
              AND s.exit_protection_set_id IS NULL
            """,
        ),
    }
    for name, count in counts.items():
        if count:
            blockers.append(f"phase_two_{name}:{count}")
    return _result(blockers, {"safe_account_mode_count": safe_modes, **counts})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument(
        "--allow-capability-enabled",
        action="store_true",
        help=(
            "Read-only pre-switch safety mode: accept an already-enabled "
            "capability while still rejecting active lifecycle risk."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if args.require_database_url and not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url):
        print("ERROR: phase-two verifier requires PostgreSQL DSN", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            payload = evaluate_phase_two_readiness(
                conn,
                now_ms=int(args.now_ms or time.time() * 1000),
                allow_capability_enabled=args.allow_capability_enabled,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(json.dumps(payload, sort_keys=True) if args.json else payload["status"])
    return 0 if payload["status"] == "phase_two_ready" else 2


def _count(conn: sa.engine.Connection, statement: str, **params: Any) -> int:
    return int(conn.execute(sa.text(statement), params).scalar_one())


def _result(blockers: list[str], counts: dict[str, int]) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_lifecycle_phase_two_readiness.v1",
        "status": "phase_two_ready" if not blockers else "blocked",
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "counts": counts,
        "exchange_read_called": False,
        "exchange_write_called": False,
        "runtime_state_mutated": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
