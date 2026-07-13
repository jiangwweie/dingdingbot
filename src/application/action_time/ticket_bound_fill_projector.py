"""Project exchange fills into canonical ticket-bound PG order state."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

import sqlalchemy as sa

from src.application.action_time.lifecycle_safety_core import (
    LifecycleDecision,
    reduce_lifecycle_decision,
)


FINAL_EXIT_ROLES = {"SL", "RUNNER_SL"}


def project_ticket_bound_exchange_fills(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    if not ticket_id or not exchange_snapshot:
        return {
            "status": "no_fill_projection_input",
            "projected_roles": [],
            "projected_count": 0,
        }
    fills = [
        dict(fill)
        for fill in exchange_snapshot.get("recent_fills", [])
        if isinstance(fill, dict)
        and str(fill.get("exchange_order_id") or "").strip()
    ]
    if not fills:
        return {
            "status": "no_new_fills",
            "projected_roles": [],
            "projected_count": 0,
        }
    orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    rows = list(
        conn.execute(
            sa.select(orders).where(orders.c.ticket_id == ticket_id)
        ).mappings()
    )
    fill_by_exchange_id = {
        str(fill["exchange_order_id"]): fill for fill in fills
    }
    projected: list[dict[str, Any]] = []
    for row in rows:
        exchange_order_id = str(row.get("exchange_order_id") or "")
        fill = fill_by_exchange_id.get(exchange_order_id)
        if not fill:
            continue
        if str(row.get("status") or "").lower() == "filled":
            existing_fill = _recorded_fill_for_order(
                conn,
                lifecycle=_lifecycle_for_ticket(conn, ticket_id),
                role=str(row.get("role") or ""),
                exchange_order_id=exchange_order_id,
            )
            if existing_fill and _fill_truth_conflicts(existing_fill, fill):
                return _hard_stop_fill_truth_contradiction(
                    conn,
                    ticket_id=ticket_id,
                    role=str(row.get("role") or ""),
                    exchange_order_id=exchange_order_id,
                    existing_fill=existing_fill,
                    conflicting_fill=fill,
                    now_ms=now_ms,
                )
            continue
        conn.execute(
            orders.update()
            .where(
                orders.c.exit_protection_order_id
                == row["exit_protection_order_id"]
            )
            .values(status="filled", updated_at_ms=now_ms)
        )
        projected.append(
            {
                "role": str(row.get("role") or ""),
                "exchange_order_id": exchange_order_id,
                "fill_qty": str(fill.get("qty") or ""),
                "fill_price": str(fill.get("price") or ""),
                "fill_time_ms": fill.get("timestamp_ms"),
                "fee": fill.get("fee"),
                "realized_pnl": fill.get("realized_pnl"),
                "reference_price": _exit_reference_price(dict(row)),
                "funding_income": (
                    _ticket_attributed_funding_income(
                        exchange_snapshot.get("funding_income", []),
                        ticket_id=ticket_id,
                    )
                    if str(row.get("role") or "") in FINAL_EXIT_ROLES
                    else []
                ),
            }
        )
        if str(row.get("role") or "") == "TP1":
            _insert_fill_event(
                conn,
                lifecycle=_lifecycle_for_ticket(conn, ticket_id),
                event_type="tp1_filled",
                fill=projected[-1],
                now_ms=now_ms,
            )
    final_exit = next(
        (item for item in projected if item["role"] in FINAL_EXIT_ROLES),
        None,
    )
    lifecycle_decision: LifecycleDecision | None = None
    if final_exit:
        lifecycle_decision = _project_final_exit_detected(
            conn,
            ticket_id=ticket_id,
            fill=final_exit,
            now_ms=now_ms,
        )
    payload = {
        "status": "fills_projected" if projected else "no_new_fills",
        "projected_roles": [item["role"] for item in projected],
        "projected_count": len(projected),
        "projected_fills": projected,
    }
    if lifecycle_decision is not None:
        payload["lifecycle_decision"] = lifecycle_decision.to_dict()
    return payload


def _recorded_fill_for_order(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    role: str,
    exchange_order_id: str,
) -> dict[str, Any]:
    if not lifecycle:
        return {}
    event_type = "tp1_filled" if role == "TP1" else "final_exit_detected"
    event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        event_type,
        exchange_order_id,
    )
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    payload = conn.execute(
        sa.select(events.c.event_payload).where(
            events.c.lifecycle_event_id == event_id
        )
    ).scalar_one_or_none()
    mapped = _mapping(payload)
    return _mapping(mapped.get("fill"))


def _fill_truth_conflicts(
    existing_fill: dict[str, Any],
    observed_fill: dict[str, Any],
) -> bool:
    for existing_key, observed_key in (
        ("fill_qty", "qty"),
        ("fill_price", "price"),
    ):
        existing = _normalized_decimal(
            existing_fill.get(existing_key, existing_fill.get(observed_key))
        )
        observed = _normalized_decimal(observed_fill.get(observed_key))
        if existing is not None and observed is not None and existing != observed:
            return True
    return False


def _hard_stop_fill_truth_contradiction(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    role: str,
    exchange_order_id: str,
    existing_fill: dict[str, Any],
    conflicting_fill: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    lifecycle_table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    lifecycle = conn.execute(
        sa.select(lifecycle_table).where(lifecycle_table.c.ticket_id == ticket_id)
    ).mappings().one()
    blocker = f"contradictory_fill_truth:{role}:{exchange_order_id}"
    decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        target_status="blocked",
        event_type="contradictory_fill_truth",
        blockers=[blocker],
        next_action="reconcile_contradictory_exchange_fill_truth",
    )
    conn.execute(
        lifecycle_table.update()
        .where(lifecycle_table.c.lifecycle_run_id == lifecycle["lifecycle_run_id"])
        .values(
            status=decision.status,
            first_blocker=decision.first_blocker,
            blockers=list(decision.blockers),
            updated_at_ms=now_ms,
        )
    )
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        "hard_stopped",
        exchange_order_id,
    )
    if conn.execute(
        sa.select(events.c.lifecycle_event_id).where(
            events.c.lifecycle_event_id == event_id
        )
    ).first() is None:
        conn.execute(
            events.insert().values(
                lifecycle_event_id=event_id,
                lifecycle_run_id=lifecycle["lifecycle_run_id"],
                ticket_id=lifecycle["ticket_id"],
                protected_submit_attempt_id=lifecycle[
                    "protected_submit_attempt_id"
                ],
                event_type="hard_stopped",
                event_payload={
                    "reason": "contradictory_fill_truth",
                    "role": role,
                    "exchange_order_id": exchange_order_id,
                    "existing_fill": existing_fill,
                    "conflicting_fill": conflicting_fill,
                    "first_blocker": blocker,
                },
                created_at_ms=now_ms,
            )
        )
    return {
        "status": "fill_truth_contradiction",
        "projected_roles": [],
        "projected_count": 0,
        "first_blocker": blocker,
        "blockers": [blocker],
        "lifecycle_decision": decision.to_dict(),
    }


def _project_final_exit_detected(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    fill: dict[str, Any],
    now_ms: int,
) -> LifecycleDecision | None:
    lifecycle = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    row = conn.execute(
        sa.select(lifecycle).where(lifecycle.c.ticket_id == ticket_id)
    ).mappings().first()
    if not row:
        return None
    if str(row.get("status") or "") not in {
        "position_protected",
        "runner_protected",
        "tp1_filled",
        "runner_mutation_pending",
    }:
        return None
    decision = reduce_lifecycle_decision(
        current_status=str(row.get("status") or ""),
        target_status="final_exit_detected",
        event_type="final_exit_detected",
    )
    conn.execute(
        lifecycle.update()
        .where(lifecycle.c.lifecycle_run_id == row["lifecycle_run_id"])
        .values(
            status=decision.status,
            first_blocker=decision.first_blocker,
            blockers=list(decision.blockers),
            updated_at_ms=now_ms,
        )
    )
    _insert_fill_event(
        conn,
        lifecycle=dict(row),
        event_type=decision.event_type,
        fill=fill,
        now_ms=now_ms,
    )
    return decision


def _lifecycle_for_ticket(
    conn: sa.engine.Connection,
    ticket_id: str,
) -> dict[str, Any]:
    lifecycle = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    row = conn.execute(
        sa.select(lifecycle).where(lifecycle.c.ticket_id == ticket_id)
    ).mappings().first()
    return dict(row) if row else {}


def _insert_fill_event(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    event_type: str,
    fill: dict[str, Any],
    now_ms: int,
) -> None:
    if not lifecycle:
        return
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        event_type,
        str(fill.get("exchange_order_id") or ""),
    )
    existing = conn.execute(
        sa.select(events.c.lifecycle_event_id).where(
            events.c.lifecycle_event_id == event_id
        )
    ).first()
    if not existing:
        conn.execute(
            events.insert().values(
                lifecycle_event_id=event_id,
                lifecycle_run_id=lifecycle["lifecycle_run_id"],
                ticket_id=lifecycle["ticket_id"],
                protected_submit_attempt_id=lifecycle[
                    "protected_submit_attempt_id"
                ],
                event_type=event_type,
                event_payload={"fill": fill},
                created_at_ms=now_ms,
            )
        )


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]
    return f"{prefix}:{digest}"


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _normalized_decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _exit_reference_price(order: dict[str, Any]) -> str | None:
    role = str(order.get("role") or "")
    value = (
        order.get("trigger_price")
        if role in {"SL", "RUNNER_SL"}
        else order.get("price")
    )
    normalized = str(value or "").strip()
    return normalized or None


def _ticket_attributed_funding_income(
    rows: Any,
    *,
    ticket_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    attributed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("ticket_id", ticket_id)
        item.setdefault(
            "attribution_basis",
            "single_active_position_exact_symbol_time_window",
        )
        attributed.append(item)
    return attributed
