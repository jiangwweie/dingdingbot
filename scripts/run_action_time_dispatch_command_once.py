#!/usr/bin/env python3
"""Claim one durable Action-Time command and prepare its official submit path.

This process is deliberately a no-network command worker.  It claims only the
command committed by the typed coordinator, materializes the PG SubmitMode
Decision and ProtectedSubmitAttempt through application services, and commits
the Entry Exchange Command before a separate leased exchange worker performs
any exchange I/O.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.durable_dispatch_command import (  # noqa: E402
    claim_next_action_time_dispatch_command,
    complete_claimed_action_time_dispatch_command,
)
from src.application.action_time.protected_submit_attempt import (  # noqa: E402
    materialize_ticket_bound_submit_mode_decision,
    prepare_ticket_bound_protected_submit_attempt,
)


def run_once(
    engine: sa.Engine,
    *,
    worker_id: str,
    production_submit_execution_policy: str,
    now_ms: int | None = None,
    lease_ms: int = 15_000,
) -> dict[str, object]:
    """Claim -> durable prepare -> commit result, with no exchange side effect."""

    now_ms = int(now_ms or time.time() * 1000)
    with engine.begin() as conn:
        claim = claim_next_action_time_dispatch_command(
            conn,
            worker_id=worker_id,
            now_ms=now_ms,
            lease_ms=lease_ms,
        )
    if claim.get("status") != "claimed":
        return {
            **claim,
            "exchange_write_called": False,
            "official_application_port_called": False,
        }

    dispatch_command_id = str(claim.get("dispatch_command_id") or "")
    claim_token = str(claim.get("claim_token") or "")
    ticket_id = str(claim.get("ticket_id") or "")
    operation_submit_command_id = str(claim.get("operation_submit_command_id") or "")
    try:
        with engine.begin() as conn:
            decision = materialize_ticket_bound_submit_mode_decision(
                conn,
                ticket_id=ticket_id,
                operation_submit_command_id=operation_submit_command_id,
                production_submit_execution_policy=production_submit_execution_policy,
                now_ms=now_ms,
            )
            decision_value = str(decision.get("decision") or "blocked")
            attempt = prepare_ticket_bound_protected_submit_attempt(
                conn,
                ticket_id=ticket_id,
                operation_submit_command_id=operation_submit_command_id,
                submit_mode=decision_value,
                now_ms=now_ms,
            )
            blockers = [str(item) for item in attempt.get("blockers") or [] if str(item)]
            completed = complete_claimed_action_time_dispatch_command(
                conn,
                dispatch_command_id=dispatch_command_id,
                claim_token=claim_token,
                protected_submit_attempt_id=str(
                    attempt.get("protected_submit_attempt_id") or ""
                ),
                blockers=(
                    blockers
                    if str(attempt.get("status") or "") not in {
                        "submit_prepared",
                        "disabled_smoke_passed",
                    }
                    else []
                ),
                now_ms=now_ms,
            )
    except Exception as exc:  # noqa: BLE001 - persist exact worker failure.
        with engine.begin() as conn:
            completed = complete_claimed_action_time_dispatch_command(
                conn,
                dispatch_command_id=dispatch_command_id,
                claim_token=claim_token,
                blockers=[f"action_time_dispatch_prepare_failed:{type(exc).__name__}"],
                now_ms=now_ms,
            )
        return {
            **completed,
            "submit_mode_decision": {},
            "protected_submit_attempt": {},
            "exchange_write_called": False,
            "official_application_port_called": True,
        }
    return {
        **completed,
        "submit_mode_decision": decision,
        "protected_submit_attempt": attempt,
        "exchange_write_called": False,
        "official_application_port_called": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--worker-id", default="runtime-signal-watcher-dispatcher")
    parser.add_argument("--lease-ms", type=int, default=15_000)
    parser.add_argument(
        "--production-submit-execution-policy",
        choices=("disabled", "armed"),
        default=os.getenv("BRC_PRODUCTION_SUBMIT_EXECUTION_POLICY", "disabled"),
    )
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if args.require_database_url and not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        print("ERROR: durable Action-Time dispatcher requires PostgreSQL DSN", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    try:
        report = run_once(
            engine,
            worker_id=args.worker_id,
            production_submit_execution_policy=args.production_submit_execution_policy,
            lease_ms=args.lease_ms,
        )
    finally:
        engine.dispose()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if str(report.get("status") or "") in {
        "no_pending_command",
        "submit_prepared",
        "blocked",
        "already_terminal",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
