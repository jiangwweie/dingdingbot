#!/usr/bin/env python3
"""Run a local ticket-bound L2-L9 full-chain simulation against PG.

This command constructs PG input rows and runs the ticket-bound lifecycle chain
with a mock exchange result. It does not call FinalGate, Operation Layer, the
exchange, live profile mutation, sizing mutation, withdrawal, or transfer.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pg_dsn import is_sync_postgres_dsn, normalize_sync_postgres_dsn  # noqa: E402
from scripts.publish_runtime_control_current_projections import (  # noqa: E402
    publish_runtime_control_current_projections,
)
from src.application.action_time.full_chain_simulation_harness import (  # noqa: E402
    FullChainSimulationInput,
    run_ticket_bound_full_chain_simulation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--strategy-group-id", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=("long", "short"))
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    args = parser.parse_args(argv)

    database_url = normalize_sync_postgres_dsn(str(args.database_url or ""))
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not args.allow_non_postgres_for_test and not is_sync_postgres_dsn(database_url):
        print("ERROR: full-chain simulation requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            payload = run_ticket_bound_full_chain_simulation(
                conn,
                FullChainSimulationInput(
                    strategy_group_id=args.strategy_group_id,
                    symbol=args.symbol,
                    side=args.side,
                    now_ms=args.now_ms or 1_770_000_000_000,
                ),
                projection_publisher=publish_runtime_control_current_projections,
            )
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(payload["final"]["status"])
    return 0 if payload["final"]["status"] == "closed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
