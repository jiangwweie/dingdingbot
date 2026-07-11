#!/usr/bin/env python3
"""Retired compatibility surface for direct runner exchange mutation.

Runner mutation is executed only through committed
``brc_ticket_bound_exchange_commands`` and the short-transaction worker.
"""

from __future__ import annotations

import time
from typing import Any

import sqlalchemy as sa


AUTHORITY_BOUNDARY = (
    "legacy_direct_runner_mutation_executor_retired; durable PG exchange "
    "command authority required; no exchange write"
)


async def execute_ticket_bound_runner_mutation_command(
    conn: sa.engine.Connection,
    *,
    runner_mutation_command_id: str,
    gateway: Any,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Fail closed; retained only to make old callers explicit."""

    del conn, runner_mutation_command_id, gateway
    now_ms = int(now_ms or time.time() * 1000)
    return {
        "schema": "brc.ticket_bound_runner_mutation_execution.v1",
        "status": "blocked",
        "now_ms": now_ms,
        "runner_mutation_command_id": None,
        "ticket_id": None,
        "strategy_group_id": None,
        "symbol": None,
        "side": None,
        "result_payload": {},
        "first_blocker": "legacy_direct_runner_executor_retired",
        "blockers": ["legacy_direct_runner_executor_retired"],
        "next_action": "materialize_durable_runner_exchange_commands",
        "exchange_write_called": False,
        "order_created": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
