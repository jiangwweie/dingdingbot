#!/usr/bin/env python3
"""Run one bounded ticket-bound lifecycle maintenance scheduler pass."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.lifecycle_maintenance_scheduler import (  # noqa: E402
    lifecycle_maintenance_scopes_require_exchange_gateway,
    run_ticket_bound_lifecycle_maintenance_scheduler,
    select_ticket_bound_lifecycle_maintenance_scopes,
)
from src.application.action_time.post_submit_reconciliation_tick import (  # noqa: E402
    select_ticket_bound_first_reconciliation_tick_scopes,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if args.require_database_url and not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url):
        print("ERROR: lifecycle maintenance scheduler requires PostgreSQL DSN", file=sys.stderr)
        return 2

    engine = sa.create_engine(database_url)
    gateway = None
    try:
        with engine.begin() as conn:
            first_tick_scopes = [
                {**scope, "scheduler_scope_kind": "first_post_submit"}
                for scope in select_ticket_bound_first_reconciliation_tick_scopes(
                    conn,
                    max_scopes=args.max_lifecycle_scopes,
                )
            ]
            scopes = select_ticket_bound_lifecycle_maintenance_scopes(
                conn,
                max_lifecycle_scopes=args.max_lifecycle_scopes,
            )
            if lifecycle_maintenance_scopes_require_exchange_gateway(
                first_tick_scopes + scopes,
                allow_exchange_mutation=args.allow_exchange_mutation,
                fetch_exchange_snapshot=args.fetch_exchange_snapshot,
            ):
                gateway_binding = await _runtime_exchange_gateway_binding()
                gateway = gateway_binding.get("gateway")
                if gateway is None:
                    payload = _blocked_gateway_payload(gateway_binding)
                    print(
                        json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        )
                    )
                    return 1
            payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
                conn,
                gateway=gateway,
                allow_exchange_mutation=args.allow_exchange_mutation,
                fetch_exchange_snapshot=args.fetch_exchange_snapshot,
                max_lifecycle_scopes=args.max_lifecycle_scopes,
                max_actions_per_scope=args.max_actions_per_scope,
                snapshot_timeout_seconds=args.snapshot_timeout_seconds,
            )
    finally:
        engine.dispose()
        close = getattr(gateway, "close", None)
        if callable(close):
            await close()

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if payload.get("status") in {"scheduler_complete", "no_maintainable_lifecycle"} else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


async def _runtime_exchange_gateway_binding() -> dict[str, Any]:
    from src.interfaces import api as api_module
    from src.interfaces.api_trading_console import (
        _runtime_exchange_submit_gateway_binding,
    )

    return await _runtime_exchange_submit_gateway_binding(api_module)


def _blocked_gateway_payload(gateway_binding: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        str(item)
        for item in (gateway_binding.get("blockers") or [])
        if str(item or "").strip()
    ]
    return {
        "schema": "brc.ticket_bound_lifecycle_maintenance_scheduler.v1",
        "status": "scheduler_blocked",
        "selected_scope_count": 0,
        "scopes": [],
        "runs": [],
        "first_blocker": blockers[0] if blockers else "runtime_exchange_gateway_unavailable",
        "blockers": blockers or ["runtime_exchange_gateway_unavailable"],
        "next_action": "repair_runtime_exchange_gateway_binding",
        "exchange_read_called": False,
        "exchange_write_called": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": (
            "ticket_bound_lifecycle_maintenance_scheduler_cli; gateway binding "
            "failed before lifecycle maintenance; no exchange call or file output"
        ),
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--fetch-exchange-snapshot", action="store_true")
    parser.add_argument("--allow-exchange-mutation", action="store_true")
    parser.add_argument("--max-lifecycle-scopes", type=int, default=4)
    parser.add_argument("--max-actions-per-scope", type=int, default=16)
    parser.add_argument("--snapshot-timeout-seconds", type=float, default=8.0)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
