"""Converge terminal ticket-bound protection truth into the core order projection.

The core ``orders`` projection is still consumed by legacy read-only next-attempt
views.  It must therefore be updated from an already-proven terminal
ticket-bound lifecycle result; this module never calls an exchange and never
creates, deletes, or reopens an order.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa


_SOURCE_TO_CORE_STATUS = {
    "filled": "FILLED",
    "cancelled": "CANCELED",
    "replaced": "CANCELED",
    "expired": "EXPIRED",
    "rejected": "REJECTED",
}
_TERMINAL_CORE_STATUSES = set(_SOURCE_TO_CORE_STATUS.values())


def project_terminal_ticket_bound_orders_to_core(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    symbol: str,
    protection_orders: list[dict[str, Any]],
    lifecycle_status: str,
    now_ms: int,
) -> list[dict[str, str]]:
    """Project exact terminal protection rows to matching core orders.

    A mismatch is intentionally a no-op.  The ticket-bound row remains the
    evidence and the caller's reconciler will retain the inconsistency instead
    of guessing at an order identity.
    """

    inspector = sa.inspect(conn)
    if not inspector.has_table("orders"):
        return []
    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    required = {"id", "symbol", "order_role", "status", "exchange_order_id"}
    if not required.issubset(order_columns):
        return []

    core_orders = sa.table(
        "orders",
        *[sa.column(name) for name in order_columns],
    )
    projected: list[dict[str, str]] = []
    for protection_order in protection_orders:
        source_status = str(protection_order.get("status") or "").lower()
        target_status = _SOURCE_TO_CORE_STATUS.get(source_status)
        local_order_id = str(protection_order.get("local_order_id") or "").strip()
        exchange_order_id = str(protection_order.get("exchange_order_id") or "").strip()
        role = str(protection_order.get("role") or "").upper()
        order_symbol = str(protection_order.get("symbol") or symbol or "").strip()
        if not target_status or not local_order_id or not exchange_order_id or not role or not order_symbol:
            continue
        core = conn.execute(
            sa.select(core_orders).where(core_orders.c.id == local_order_id)
        ).mappings().first()
        if not core:
            continue
        if (
            str(core.get("exchange_order_id") or "").strip() != exchange_order_id
            or str(core.get("symbol") or "").strip() != order_symbol
            or str(core.get("order_role") or "").upper() != role
        ):
            continue
        old_status = str(core.get("status") or "").upper()
        if old_status in _TERMINAL_CORE_STATUSES:
            continue
        values: dict[str, Any] = {"status": target_status}
        if "updated_at" in order_columns:
            values["updated_at"] = now_ms
        if target_status == "FILLED" and "filled_at" in order_columns:
            values["filled_at"] = now_ms
        conn.execute(
            core_orders.update().where(
                core_orders.c.id == local_order_id,
                core_orders.c.status == core.get("status"),
            ).values(**values)
        )
        _append_audit_event_if_available(
            conn,
            ticket_id=ticket_id,
            local_order_id=local_order_id,
            old_status=old_status,
            new_status=target_status,
            source_status=source_status,
            lifecycle_status=lifecycle_status,
            now_ms=now_ms,
        )
        projected.append(
            {
                "local_order_id": local_order_id,
                "old_status": old_status,
                "new_status": target_status,
            }
        )
    return projected


def _append_audit_event_if_available(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    local_order_id: str,
    old_status: str,
    new_status: str,
    source_status: str,
    lifecycle_status: str,
    now_ms: int,
) -> None:
    inspector = sa.inspect(conn)
    if not inspector.has_table("order_audit_logs"):
        return
    columns = {column["name"] for column in inspector.get_columns("order_audit_logs")}
    required = {"id", "order_id", "new_status", "event_type", "triggered_by", "created_at"}
    if not required.issubset(columns):
        return
    digest = hashlib.sha256(
        f"terminal-core-order-projection:{ticket_id}:{local_order_id}:{new_status}".encode()
    ).hexdigest()[:48]
    values: dict[str, Any] = {
        "id": f"core-projection-{digest}",
        "order_id": local_order_id,
        "new_status": new_status,
        "event_type": "ticket_bound_terminal_projection",
        "triggered_by": "ticket_bound_lifecycle",
        "created_at": now_ms,
    }
    if "old_status" in columns:
        values["old_status"] = old_status
    if "metadata" in columns:
        values["metadata"] = json.dumps(
            {
                "ticket_id": ticket_id,
                "source_status": source_status,
                "lifecycle_status": lifecycle_status,
                "exchange_write_called": False,
            },
            sort_keys=True,
        )
    audit = sa.table("order_audit_logs", *[sa.column(name) for name in columns])
    exists = conn.execute(sa.select(audit.c.id).where(audit.c.id == values["id"])).first()
    if not exists:
        conn.execute(audit.insert().values(**values))
