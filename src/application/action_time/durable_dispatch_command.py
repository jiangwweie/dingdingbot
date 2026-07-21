"""Persist and claim the post-Runtime-Safety Action-Time dispatch boundary.

The command is intentionally narrower than an exchange command.  It is the
single durable bridge from the typed Action-Time coordinator to the typed
protected-submit preparation port.  The command worker never re-selects a
Ticket and never replays FinalGate, Operation Layer, or Runtime Safety.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import sqlalchemy as sa


TABLE_NAME = "brc_action_time_dispatch_commands"
PENDING = "pending"
CLAIMED = "claimed"
PREPARED = "submit_prepared"
BLOCKED = "blocked"
TERMINAL_STATES = {PREPARED, BLOCKED}


def materialize_action_time_dispatch_command(
    conn: sa.Connection,
    *,
    action_time_invocation_id: str,
    ticket_id: str,
    operation_layer_handoff_id: str,
    runtime_safety_snapshot: dict[str, Any],
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Commit an immutable dispatch identity after Runtime Safety is ready."""

    now_ms = int(now_ms or time.time() * 1000)
    invocation_id = str(action_time_invocation_id or "").strip()
    ticket_id = str(ticket_id or "").strip()
    handoff_id = str(operation_layer_handoff_id or "").strip()
    safety = dict(runtime_safety_snapshot or {})
    blockers = _materialization_blockers(
        invocation_id=invocation_id,
        ticket_id=ticket_id,
        handoff_id=handoff_id,
        safety=safety,
        now_ms=now_ms,
    )
    if blockers:
        return _result("blocked", {}, blockers=blockers)

    operation_submit_command_id = _safety_text(
        safety,
        "operation_submit_command_id",
    )
    command_id = _stable_id(
        "action_time_dispatch_command",
        operation_submit_command_id,
    )
    table = _table(conn)
    existing = conn.execute(
        sa.select(table).where(table.c.operation_submit_command_id == operation_submit_command_id)
    ).mappings().first()
    if existing:
        row = dict(existing)
        identity_blockers = _identity_blockers(
            row,
            invocation_id=invocation_id,
            ticket_id=ticket_id,
            handoff_id=handoff_id,
            safety=safety,
        )
        if identity_blockers:
            return _result("blocked", row, blockers=identity_blockers)
        return _result("already_materialized", row, blockers=[])

    row = {
        "dispatch_command_id": command_id,
        "action_time_invocation_id": invocation_id,
        "ticket_id": ticket_id,
        "operation_layer_handoff_id": handoff_id,
        "operation_submit_command_id": operation_submit_command_id,
        "runtime_safety_snapshot_id": _safety_text(
            safety,
            "runtime_safety_snapshot_id",
        ),
        "strategy_group_id": str(safety.get("strategy_group_id") or ""),
        "symbol": str(safety.get("symbol") or ""),
        "side": str(safety.get("side") or ""),
        "runtime_profile_id": str(safety.get("runtime_profile_id") or ""),
        "state": PENDING,
        "protected_submit_attempt_id": None,
        "first_blocker": None,
        "claim_owner": None,
        "claim_token": None,
        "claim_expires_at_ms": None,
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    conn.execute(table.insert().values(**row))
    return _result("materialized", row, blockers=[])


def claim_next_action_time_dispatch_command(
    conn: sa.Connection,
    *,
    worker_id: str,
    now_ms: int | None = None,
    lease_ms: int = 15_000,
) -> dict[str, Any]:
    """Claim one pending command under a short transaction and lease."""

    now_ms = int(now_ms or time.time() * 1000)
    owner = str(worker_id or "").strip()
    if not owner:
        raise ValueError("action_time_dispatch_worker_id_required")
    if lease_ms <= 0:
        raise ValueError("action_time_dispatch_lease_invalid")
    table = _table(conn)
    if conn.dialect.name == "postgresql":
        conn.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('brc_action_time_dispatch_command_claim'))"
            )
        )
    conn.execute(
        table.update()
        .where(table.c.state == CLAIMED, table.c.claim_expires_at_ms <= now_ms)
        .values(
            state=PENDING,
            claim_owner=None,
            claim_token=None,
            claim_expires_at_ms=None,
            updated_at_ms=now_ms,
        )
    )
    query = (
        sa.select(table)
        .where(table.c.state == PENDING)
        .order_by(table.c.created_at_ms.asc(), table.c.dispatch_command_id.asc())
        .limit(1)
    )
    if conn.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    selected = conn.execute(query).mappings().first()
    if not selected:
        return _result("no_pending_command", {}, blockers=[])
    row = dict(selected)
    token = _stable_id("action_time_dispatch_claim", row["dispatch_command_id"], owner, str(now_ms))
    conn.execute(
        table.update()
        .where(table.c.dispatch_command_id == row["dispatch_command_id"], table.c.state == PENDING)
        .values(
            state=CLAIMED,
            claim_owner=owner,
            claim_token=token,
            claim_expires_at_ms=now_ms + lease_ms,
            updated_at_ms=now_ms,
        )
    )
    return _result(
        "claimed",
        {
            **row,
            "state": CLAIMED,
            "claim_owner": owner,
            "claim_token": token,
            "claim_expires_at_ms": now_ms + lease_ms,
            "updated_at_ms": now_ms,
        },
        blockers=[],
    )


def complete_claimed_action_time_dispatch_command(
    conn: sa.Connection,
    *,
    dispatch_command_id: str,
    claim_token: str,
    protected_submit_attempt_id: str = "",
    blockers: list[str] | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Commit preparation outcome; exchange I/O belongs to its own worker."""

    now_ms = int(now_ms or time.time() * 1000)
    blockers = _dedupe(blockers or [])
    table = _table(conn)
    row = conn.execute(
        sa.select(table).where(table.c.dispatch_command_id == str(dispatch_command_id))
    ).mappings().first()
    if not row:
        return _result("blocked", {}, blockers=["action_time_dispatch_command_missing"])
    current = dict(row)
    if current.get("state") in TERMINAL_STATES:
        return _result("already_terminal", current, blockers=[])
    if current.get("state") != CLAIMED or str(current.get("claim_token") or "") != str(claim_token or ""):
        return _result("blocked", current, blockers=["action_time_dispatch_claim_lost"])
    state = BLOCKED if blockers else PREPARED
    conn.execute(
        table.update()
        .where(table.c.dispatch_command_id == str(dispatch_command_id), table.c.claim_token == str(claim_token))
        .values(
            state=state,
            protected_submit_attempt_id=(str(protected_submit_attempt_id).strip() or None),
            first_blocker=(blockers[0] if blockers else None),
            claim_expires_at_ms=None,
            updated_at_ms=now_ms,
        )
    )
    return _result(
        state,
        {
            **current,
            "state": state,
            "protected_submit_attempt_id": str(protected_submit_attempt_id).strip() or None,
            "first_blocker": blockers[0] if blockers else None,
            "claim_expires_at_ms": None,
            "updated_at_ms": now_ms,
        },
        blockers=blockers,
    )


def _materialization_blockers(
    *,
    invocation_id: str,
    ticket_id: str,
    handoff_id: str,
    safety: dict[str, Any],
    now_ms: int,
) -> list[str]:
    blockers: list[str] = []
    for key, value in (
        ("action_time_invocation_id", invocation_id),
        ("ticket_id", ticket_id),
        ("operation_layer_handoff_id", handoff_id),
        ("runtime_safety_snapshot_id", _safety_text(safety, "runtime_safety_snapshot_id")),
        ("operation_submit_command_id", _safety_text(safety, "operation_submit_command_id")),
        ("strategy_group_id", safety.get("strategy_group_id")),
        ("symbol", safety.get("symbol")),
        ("side", safety.get("side")),
        ("runtime_profile_id", safety.get("runtime_profile_id")),
    ):
        if not str(value or "").strip():
            blockers.append(f"dispatch_command_missing:{key}")
    for key, expected in (
        ("ticket_id", ticket_id),
        ("operation_layer_handoff_id", handoff_id),
    ):
        actual = _safety_text(safety, key)
        if actual and actual != expected:
            blockers.append(f"dispatch_command_runtime_safety_mismatch:{key}")
    if safety.get("submit_allowed") is not True:
        blockers.append("dispatch_command_runtime_safety_not_submit_allowed")
    if str(safety.get("safety_state") or "") != "live_submit_ready":
        blockers.append("dispatch_command_runtime_safety_not_live_submit_ready")
    valid_until_ms = int(safety.get("valid_until_ms") or 0)
    if valid_until_ms and valid_until_ms <= now_ms:
        blockers.append("dispatch_command_runtime_safety_expired")
    return _dedupe(blockers)


def _identity_blockers(
    row: dict[str, Any],
    *,
    invocation_id: str,
    ticket_id: str,
    handoff_id: str,
    safety: dict[str, Any],
) -> list[str]:
    expected = {
        "action_time_invocation_id": invocation_id,
        "ticket_id": ticket_id,
        "operation_layer_handoff_id": handoff_id,
        "runtime_safety_snapshot_id": _safety_text(safety, "runtime_safety_snapshot_id"),
        "operation_submit_command_id": _safety_text(safety, "operation_submit_command_id"),
        "strategy_group_id": str(safety.get("strategy_group_id") or ""),
        "symbol": str(safety.get("symbol") or ""),
        "side": str(safety.get("side") or ""),
        "runtime_profile_id": str(safety.get("runtime_profile_id") or ""),
    }
    return [
        f"dispatch_command_identity_mismatch:{key}"
        for key, value in expected.items()
        if str(row.get(key) or "") != value
    ]


def _table(conn: sa.Connection) -> sa.Table:
    return sa.Table(TABLE_NAME, sa.MetaData(), autoload_with=conn)


def _safety_text(safety: dict[str, Any], key: str) -> str:
    value = safety.get(key)
    if value is None:
        refs = safety.get("trusted_fact_refs")
        if isinstance(refs, dict):
            value = refs.get(key)
    return str(value or "").strip()


def _result(status: str, row: dict[str, Any], *, blockers: list[str]) -> dict[str, Any]:
    return {
        "schema": "brc.action_time_dispatch_command.v1",
        "status": status,
        "dispatch_command_id": row.get("dispatch_command_id"),
        "operation_submit_command_id": row.get("operation_submit_command_id"),
        "ticket_id": row.get("ticket_id"),
        "runtime_safety_snapshot_id": row.get("runtime_safety_snapshot_id"),
        "protected_submit_attempt_id": row.get("protected_submit_attempt_id"),
        "claim_owner": row.get("claim_owner"),
        "claim_token": row.get("claim_token"),
        "claim_expires_at_ms": row.get("claim_expires_at_ms"),
        "state": row.get("state"),
        "first_blocker": blockers[0] if blockers else row.get("first_blocker"),
        "blockers": blockers,
    }


def _stable_id(*parts: str) -> str:
    material = "|".join(parts)
    return "action_time_dispatch:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))
