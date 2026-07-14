#!/usr/bin/env python3
"""Enable or disable the PG-current durable lifecycle mutation capability."""

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

from src.application.action_time.lifecycle_mutation_capability import (  # noqa: E402
    lifecycle_mutation_capability_decision,
    set_lifecycle_mutation_capability,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.add_argument("--certification-ref", default="")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if args.require_database_url and not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url):
        print("ERROR: lifecycle capability update requires PostgreSQL DSN", file=sys.stderr)
        return 2
    if not args.status and not str(args.certification_ref or "").strip():
        print("ERROR: --certification-ref is required for capability mutation", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    try:
        with engine.begin() as conn:
            payload = (
                lifecycle_mutation_capability_decision(conn)
                if args.status
                else set_lifecycle_mutation_capability(
                    conn,
                    enabled=args.enable,
                    certification_ref=args.certification_ref,
                    now_ms=int(args.now_ms or time.time() * 1000),
                )
            )
    except (sa.exc.SQLAlchemyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    output = {
        **payload,
        "exchange_write_called": False,
        "order_created": False,
        "runtime_profile_changed": False,
        "order_sizing_changed": False,
        "authority_boundary": (
            "PG current lifecycle capability only; no exchange/order authority"
        ),
    }
    print(json.dumps(output, sort_keys=True) if args.json else output["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
