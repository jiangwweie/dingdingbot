#!/usr/bin/env python3
"""Apply one fresh, eligible active-Ticket exit-policy adoption by digest CAS."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.preview_ticket_exit_policy_adoption import (  # noqa: E402
    _close_gateway,
    build_fresh_adoption_eligibility,
)
from src.application.action_time.ticket_exit_policy_adoption_service import (  # noqa: E402
    apply_ticket_exit_policy_adoption,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if not database_url or not is_sync_postgres_dsn(database_url):
        print("ERROR: a sync PostgreSQL PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    gateway = None
    now_ms = int(time.time() * 1000)
    try:
        eligibility, gateway = await build_fresh_adoption_eligibility(
            engine=engine,
            ticket_id=args.ticket_id,
            owner_authorization_ref=args.owner_authorization_ref,
            runtime_head=args.runtime_head,
            now_ms=now_ms,
        )
        if eligibility.status != "eligible":
            print(
                json.dumps(
                    {
                        "schema": "brc.ticket_exit_policy_adoption_apply.v1",
                        "status": "blocked",
                        "ticket_id": args.ticket_id,
                        "eligibility_hash": eligibility.eligibility_hash,
                        "blockers": list(eligibility.blockers),
                        "exchange_read_called": True,
                        "exchange_write_called": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 1
        if eligibility.eligibility_hash != args.expected_eligibility_hash:
            print("ERROR: fresh eligibility hash differs from expected hash", file=sys.stderr)
            return 1
        with engine.begin() as conn:
            result = apply_ticket_exit_policy_adoption(
                conn,
                eligibility=eligibility,
                expected_eligibility_hash=args.expected_eligibility_hash,
                now_ms=int(time.time() * 1000),
            )
        print(
            json.dumps(
                {
                    "schema": "brc.ticket_exit_policy_adoption_apply.v1",
                    **result,
                    "exchange_read_called": True,
                    "exchange_write_called": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    finally:
        engine.dispose()
        await _close_gateway(gateway)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("PG_DATABASE_URL", ""))
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--owner-authorization-ref", required=True)
    parser.add_argument("--runtime-head", required=True)
    parser.add_argument("--expected-eligibility-hash", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
