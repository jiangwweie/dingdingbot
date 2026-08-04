#!/usr/bin/env python3
"""Bounded stdin bridge from the release control plane to exact 0002 code."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CURRENT_RELEASE = "/opt/brc/current"
SOURCE_SCHEMA_REVISION = "0002_sor_v3_strategy_group_capacity"
RUNTIME_PROFILE_ID = "tiny-live-v1"
VENUE_ID = "binance-usdm"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_AUTHORIZATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ELIGIBLE = frozenset({"position_protected", "runner_protected"})
_IN_PROGRESS = frozenset(
    {
        "exit_pending",
        "exit_accepted",
        "exit_outcome_unknown",
        "reconciliation_pending",
        "settlement_pending",
        "review_pending",
    }
)
_TERMINAL = frozenset(
    {
        "terminal",
        "leverage_rejected",
        "entry_rejected",
        "entry_reconciled_absent",
    }
)
_UNRESOLVED_COMMAND_STATUSES = frozenset(
    {"prepared", "claimed", "outcome_unknown"}
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-only", action="store_true")
    parser.add_argument("--purpose", choices=("deployment_drain",))
    parser.add_argument("--authorization-id")
    parser.add_argument("--target-commit", required=True)
    parser.add_argument("--source-schema-revision", required=True)
    parser.add_argument("--requested-at-ms", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except Exception:  # noqa: BLE001 - never print DSN or server details.
        print(json.dumps({"status": "failed", "reason": "preflight_failed"}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 2 if result.get("status") == "blocked" else 0


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.source_schema_revision != SOURCE_SCHEMA_REVISION:
        raise ValueError("bridge source schema differs")
    target_commit = str(args.target_commit or "").strip()
    if _COMMIT.fullmatch(target_commit) is None:
        raise ValueError("target commit must be exact")
    if not args.inspect_only:
        if args.purpose != "deployment_drain":
            raise ValueError("bridge purpose differs")
        authorization_id = str(args.authorization_id or "").strip()
        if _AUTHORIZATION_ID.fullmatch(authorization_id) is None:
            raise ValueError("bridge authorization identity differs")
    else:
        authorization_id = ""

    database_url = str(os.getenv("TRADING_KERNEL_DATABASE_URL") or "").strip()
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    runtime_commit = _required_environment("TRADING_KERNEL_RUNTIME_COMMIT")
    runtime_schema = _required_environment("TRADING_KERNEL_SCHEMA_REVISION")
    account_id = _required_environment("TRADING_KERNEL_ACCOUNT_ID")
    if _COMMIT.fullmatch(runtime_commit) is None:
        raise ValueError("source runtime commit must be exact")
    if runtime_schema != SOURCE_SCHEMA_REVISION:
        raise ValueError("source runtime schema differs")
    if _required_environment("TRADING_KERNEL_VENUE_ID") != VENUE_ID:
        raise ValueError("source venue differs")
    if _required_environment("TRADING_KERNEL_ENVIRONMENT") != "live":
        raise ValueError("source environment differs")
    if (
        _required_environment("TRADING_KERNEL_ACCOUNT_POSITION_MODE")
        != "independent_sides"
    ):
        raise ValueError("source position mode differs")

    sys.path.insert(0, CURRENT_RELEASE)
    from src.trading_kernel.application.reconcile_ticket import (
        ExitTicketRequest,
        request_exit,
    )
    from src.trading_kernel.infrastructure.pg_unit_of_work import (
        PostgresKernelUnitOfWork,
    )

    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            context = await _inspect_source_context(
                uow,
                runtime_commit=runtime_commit,
                runtime_schema=runtime_schema,
                account_id=account_id,
            )
        if args.inspect_only or context["status"] == "blocked":
            return context

        requested_ticket_ids: list[str] = []
        in_progress_ticket_ids: list[str] = []
        terminal_ticket_ids: list[str] = []
        blocked_ticket_ids: list[str] = []
        requested_at_ms = (
            int(time.time() * 1_000)
            if args.requested_at_ms is None
            else int(args.requested_at_ms)
        )
        if requested_at_ms <= 0:
            raise ValueError("request time must be positive")
        reason = f"deployment_drain:{authorization_id}:{target_commit}"
        eligible_values = context.get("eligible_ticket_ids")
        if not isinstance(eligible_values, list):
            raise ValueError("bridge eligible Ticket set is invalid")
        for value in eligible_values:
            ticket_id = str(value)
            async with PostgresKernelUnitOfWork(engine) as uow:
                aggregate = await uow.aggregates.get(ticket_id)
                classification = _classify_aggregate(aggregate)
                if classification == "eligible":
                    await request_exit(
                        uow,
                        ExitTicketRequest(
                            ticket_id=ticket_id,
                            reason=reason,
                            requested_at_ms=requested_at_ms,
                        ),
                    )
                    requested_ticket_ids.append(ticket_id)
                elif classification == "in_progress":
                    in_progress_ticket_ids.append(ticket_id)
                elif classification == "terminal":
                    terminal_ticket_ids.append(ticket_id)
                else:
                    blocked_ticket_ids.append(ticket_id)
                    break
        status = (
            "blocked"
            if blocked_ticket_ids
            else "requested"
            if requested_ticket_ids
            else "in_progress"
            if in_progress_ticket_ids
            else "flat"
        )
        return {
            "status": status,
            "requested_ticket_ids": requested_ticket_ids,
            "in_progress_ticket_ids": in_progress_ticket_ids,
            "terminal_ticket_ids": terminal_ticket_ids,
            "blocked_ticket_ids": blocked_ticket_ids,
        }
    finally:
        await engine.dispose()


async def _inspect_source_context(
    uow,
    *,
    runtime_commit: str,
    runtime_schema: str,
    account_id: str,
) -> dict[str, object]:
    connection = uow._require_connection()
    metadata = {
        str(row["metadata_key"]): str(row["metadata_value"])
        for row in (
            await connection.execute(
                text(
                    "SELECT metadata_key, metadata_value "
                    "FROM brc_schema_metadata ORDER BY metadata_key"
                )
            )
        ).mappings()
    }
    if (
        metadata.get("runtime_commit") != runtime_commit
        or metadata.get("schema_revision") != runtime_schema
    ):
        raise ValueError("source metadata identity differs")
    capability = (
        await connection.execute(
            text(
                "SELECT enabled, certified_commit, schema_revision "
                "FROM brc_runtime_capabilities_current "
                "WHERE capability_key = 'exchange_commands'"
            )
        )
    ).mappings().one_or_none()
    if (
        capability is None
        or capability["enabled"] is not True
        or capability["certified_commit"] != runtime_commit
        or capability["schema_revision"] != runtime_schema
    ):
        raise ValueError("source exchange command capability differs")
    profile = (
        await connection.execute(
            text(
                "SELECT venue_id, account_id, environment, position_mode, status "
                "FROM brc_runtime_profiles WHERE runtime_profile_id = :profile_id"
            ),
            {"profile_id": RUNTIME_PROFILE_ID},
        )
    ).mappings().one_or_none()
    if profile is None or any(
        (
            profile["venue_id"] != VENUE_ID,
            profile["account_id"] != account_id,
            profile["environment"] != "live",
            profile["position_mode"] != "independent_sides",
            profile["status"] != "active",
        )
    ):
        raise ValueError("source runtime profile differs")
    policy = (
        await connection.execute(
            text(
                "SELECT enabled, new_entry_submit_enabled, max_concurrent_tickets "
                "FROM brc_owner_policy_current WHERE owner_policy_id = 'policy-main'"
            )
        )
    ).mappings().one_or_none()
    if (
        policy is None
        or policy["enabled"] is not True
        or policy["new_entry_submit_enabled"] is not False
    ):
        raise ValueError("source Owner Policy differs")
    max_active_tickets = min(int(policy["max_concurrent_tickets"]), 3)
    if max_active_tickets <= 0:
        raise ValueError("source Ticket bound is invalid")
    ticket_ids = tuple(
        str(value)
        for value in (
            await connection.execute(
                text(
                    "SELECT aggregate.ticket_id FROM brc_trade_aggregates aggregate "
                    "JOIN brc_trade_tickets ticket ON ticket.ticket_id = aggregate.ticket_id "
                    "WHERE ticket.runtime_profile_id = :profile_id "
                    "AND ticket.venue_id = :venue_id AND ticket.account_id = :account_id "
                    "AND ticket.terminal_at_ms IS NULL "
                    "ORDER BY aggregate.ticket_id LIMIT :row_limit"
                ),
                {
                    "profile_id": RUNTIME_PROFILE_ID,
                    "venue_id": VENUE_ID,
                    "account_id": account_id,
                    "row_limit": max_active_tickets + 1,
                },
            )
        ).scalars()
    )
    if len(ticket_ids) > max_active_tickets:
        raise ValueError("source active Ticket set exceeds bound")

    eligible: list[str] = []
    in_progress: list[str] = []
    terminal: list[str] = []
    blocked: list[str] = []
    for ticket_id in ticket_ids:
        aggregate = await uow.aggregates.get(ticket_id)
        classification = _classify_aggregate(aggregate)
        if classification == "eligible" and aggregate is not None:
            incident = await uow.incidents.get_open_for_ticket(ticket_id)
            commands = await uow.exchange_commands.list_for_ticket(ticket_id)
            unresolved = [
                command
                for command in commands
                if command.status.value in _UNRESOLVED_COMMAND_STATUSES
            ]
            if incident is not None or unresolved or not _protected(aggregate):
                classification = "blocked"
        if classification == "eligible":
            eligible.append(ticket_id)
        elif classification == "in_progress":
            in_progress.append(ticket_id)
        elif classification == "terminal":
            terminal.append(ticket_id)
        else:
            blocked.append(ticket_id)
    status = (
        "blocked"
        if blocked
        else "eligible"
        if eligible
        else "in_progress"
        if in_progress
        else "flat"
    )
    return {
        "status": status,
        "active_ticket_count": len(ticket_ids),
        "eligible_ticket_ids": eligible,
        "in_progress_ticket_ids": in_progress,
        "terminal_ticket_ids": terminal,
        "blocked_ticket_ids": blocked,
    }


def _classify_aggregate(aggregate) -> str:
    if aggregate is None:
        return "terminal"
    status = str(getattr(aggregate.status, "value", aggregate.status))
    if status in _ELIGIBLE:
        return "eligible"
    if status in _IN_PROGRESS:
        return "in_progress"
    if status in _TERMINAL:
        return "terminal"
    return "blocked"


def _protected(aggregate) -> bool:
    return bool(
        Decimal(aggregate.position_qty) > 0
        and Decimal(aggregate.protected_qty) > 0
        and aggregate.active_stop_exchange_order_id is not None
    )


def _required_environment(key: str) -> str:
    value = str(os.getenv(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
