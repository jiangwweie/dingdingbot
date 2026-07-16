#!/usr/bin/env python3
"""Preview one active-Ticket policy adoption from fresh PG/exchange truth."""

from __future__ import annotations

import argparse
import asyncio
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

from src.application.action_time.exchange_scope import (  # noqa: E402
    resolve_ticket_bound_exchange_scope,
)
from src.application.action_time.exchange_snapshot_provider import (  # noqa: E402
    AUTHORITY_BOUNDARY,
    fetch_resolved_ticket_bound_exchange_snapshot,
    load_ticket_conditional_parent_order_ids,
)
from src.application.action_time.ticket_exit_policy_adoption_service import (  # noqa: E402
    evaluate_ticket_exit_policy_adoption_eligibility,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)


async def build_fresh_adoption_eligibility(
    *,
    engine: sa.Engine,
    ticket_id: str,
    owner_authorization_ref: str,
    runtime_head: str,
    now_ms: int,
) -> tuple[Any, Any]:
    """Fetch exchange truth outside PG transaction, then evaluate exact facts."""

    from src.infrastructure.runtime_exchange_gateway_binding import (
        bind_runtime_exchange_submit_gateway,
    )

    with engine.begin() as conn:
        resolution = resolve_ticket_bound_exchange_scope(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )
        if resolution.status != "resolved" or resolution.scope is None:
            raise RuntimeError(
                "adoption_exchange_scope_unresolved:"
                + ",".join(resolution.blockers)
            )
        sets = sa.Table(
            "brc_ticket_bound_exit_protection_sets",
            sa.MetaData(),
            autoload_with=conn,
        )
        set_row = conn.execute(
            sa.select(sets).where(sets.c.ticket_id == ticket_id)
        ).mappings().first()
        if set_row is None:
            raise RuntimeError("adoption_exit_protection_set_missing")
        conditional_ids = load_ticket_conditional_parent_order_ids(
            conn,
            ticket_id=ticket_id,
        )
        snapshot_identity = str(set_row["exit_protection_set_id"])

    binding = await bind_runtime_exchange_submit_gateway(
        sys.modules[__name__],
        lifecycle_readonly=True,
    )
    gateway = binding.get("gateway")
    if gateway is None:
        raise RuntimeError(
            "adoption_runtime_exchange_gateway_unavailable:"
            + ",".join(binding.get("blockers") or [])
        )
    try:
        core = await fetch_resolved_ticket_bound_exchange_snapshot(
            scope=resolution.scope,
            snapshot_identity=snapshot_identity,
            gateway=gateway,
            timeout_seconds=8.0,
            recent_fill_limit=100,
            conditional_parent_order_ids=conditional_ids,
            now_ms=now_ms,
            authority_boundary=AUTHORITY_BOUNDARY,
        )
        if core["status"] != "snapshot_ready":
            raise RuntimeError(
                "adoption_exchange_snapshot_blocked:"
                + ",".join(core.get("blockers") or [])
            )
        with engine.begin() as conn:
            eligibility = evaluate_ticket_exit_policy_adoption_eligibility(
                conn,
                ticket_id=ticket_id,
                exchange_snapshot=core["snapshot"],
                owner_authorization_ref=owner_authorization_ref,
                runtime_head=runtime_head,
                now_ms=now_ms,
            )
        return eligibility, gateway
    except Exception:
        await _close_gateway(gateway)
        raise


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if not database_url or not is_sync_postgres_dsn(database_url):
        print("ERROR: a sync PostgreSQL PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    gateway = None
    try:
        eligibility, gateway = await build_fresh_adoption_eligibility(
            engine=engine,
            ticket_id=args.ticket_id,
            owner_authorization_ref=args.owner_authorization_ref,
            runtime_head=args.runtime_head,
            now_ms=int(time.time() * 1000),
        )
        payload = {
            "schema": "brc.ticket_exit_policy_adoption_preview.v1",
            "status": eligibility.status,
            "ticket_id": args.ticket_id,
            "eligibility_hash": eligibility.eligibility_hash,
            "blockers": list(eligibility.blockers),
            "snapshot": eligibility.snapshot.model_dump(mode="json", by_alias=True),
            "exchange_read_called": True,
            "exchange_write_called": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if eligibility.status == "eligible" else 1
    finally:
        engine.dispose()
        await _close_gateway(gateway)


async def _close_gateway(gateway: Any) -> None:
    close = getattr(gateway, "close", None)
    if callable(close):
        await close()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("PG_DATABASE_URL", ""))
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--owner-authorization-ref", required=True)
    parser.add_argument("--runtime-head", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
