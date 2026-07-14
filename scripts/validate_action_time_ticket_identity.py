#!/usr/bin/env python3
"""Validate open action-time state has a unique PG ticket identity."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


OPEN_TICKET_STATUSES = {"created", "preflight_pending", "finalgate_ready"}
OPEN_LANE_STATUSES = {"opened", "facts_refreshing", "ticket_pending", "ticket_created"}


def validate_action_time_ticket_identity(conn: sa.engine.Connection) -> list[str]:
    metadata = sa.MetaData()
    tickets = sa.Table("brc_action_time_tickets", metadata, autoload_with=conn)
    lanes = sa.Table("brc_action_time_lane_inputs", metadata, autoload_with=conn)
    open_lanes = [
        dict(row)
        for row in conn.execute(
            sa.select(lanes)
            .where(lanes.c.lane_scope == "real_submit_candidate")
            .where(lanes.c.status.in_(sorted(OPEN_LANE_STATUSES)))
        ).mappings()
    ]
    open_tickets = [
        dict(row)
        for row in conn.execute(
            sa.select(tickets).where(tickets.c.status.in_(sorted(OPEN_TICKET_STATUSES)))
        ).mappings()
    ]
    errors: list[str] = []
    if len(open_lanes) > 1:
        lane_ids = ",".join(sorted(str(row["action_time_lane_input_id"]) for row in open_lanes))
        errors.append(f"multiple open action-time lanes: {lane_ids}")
    if len(open_tickets) > 1:
        ticket_ids = ",".join(sorted(str(row["ticket_id"]) for row in open_tickets))
        errors.append(f"multiple open action-time tickets: {ticket_ids}")
    if open_lanes and not open_tickets:
        lane_ids = ",".join(sorted(str(row["action_time_lane_input_id"]) for row in open_lanes))
        errors.append(f"open action-time lane missing ticket: {lane_ids}")
    lane_by_id = {
        str(row["action_time_lane_input_id"]): row
        for row in open_lanes
    }
    for ticket in open_tickets:
        lane_id = str(ticket.get("action_time_lane_input_id") or "")
        lane = lane_by_id.get(lane_id)
        if not lane:
            errors.append(f"open ticket references non-open lane: {ticket['ticket_id']}")
            continue
        mismatches = _identity_mismatch_fields(ticket, lane)
        if mismatches:
            errors.append(
                f"ticket identity mismatch for {ticket['ticket_id']}:"
                f"{','.join(mismatches)}"
            )
    return errors


def _identity_mismatch_fields(
    ticket: dict[str, Any],
    lane: dict[str, Any],
) -> list[str]:
    fields = (
        "promotion_candidate_id",
        "signal_event_id",
        "strategy_group_id",
        "symbol",
        "side",
        "runtime_profile_id",
    )
    return [
        field
        for field in fields
        if str(ticket.get(field) or "") != str(lane.get(field) or "")
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            errors = validate_action_time_ticket_identity(conn)
    finally:
        engine.dispose()
    report = {
        "status": "action_time_ticket_identity_valid" if not errors else "blocked",
        "errors": errors,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    else:
        print(report["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
