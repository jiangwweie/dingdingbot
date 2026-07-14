"""Production reconciliation -> settlement -> review -> closure projection."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

import sqlalchemy as sa

from src.application.action_time.lifecycle_safety_core import (
    lifecycle_decision_for_status,
    reduce_lifecycle_decision,
)

from src.application.action_time.live_outcome_ledger import (
    materialize_live_outcome_ledger,
)
from src.application.action_time.post_submit_closure import (
    materialize_ticket_bound_lifecycle_closure,
)
from src.application.action_time.ticket_bound_budget_settlement import (
    settle_ticket_bound_budget,
)


FINAL_ROLES = {"SL", "RUNNER_SL"}
LIVE_PROTECTION_ORDER_STATUSES = {
    "planned",
    "submitted",
    "open",
    "partially_filled",
    "cancel_pending",
    "replace_pending",
}


def finalize_ticket_bound_lifecycle_if_ready(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    now_ms: int,
) -> dict[str, Any]:
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        ticket_id,
    )
    if not lifecycle:
        return _result("not_ready_lifecycle_missing", [], False)
    if str(lifecycle.get("status") or "") == "lifecycle_closed":
        _close_action_time_ticket(conn, ticket_id=ticket_id)
        outcome = materialize_live_outcome_ledger(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )
        return {
            **_result(
                "lifecycle_closed",
                [],
                False,
                lifecycle_status="lifecycle_closed",
            ),
            "live_outcome_status": outcome.get("status"),
        }
    if str(lifecycle.get("status") or "") not in {
        "reconciliation_matched",
        "budget_settled",
        "review_recorded",
    }:
        return _result(
            "not_ready_lifecycle_active",
            [],
            False,
            lifecycle_status=str(lifecycle.get("status") or "blocked"),
        )

    final_order = _final_exit_evidence(conn, ticket_id)
    flat_tick = _latest_flat_reconciliation_tick(conn, ticket_id)
    blockers: list[str] = []
    if not final_order:
        blockers.append("final_exit_filled_order_missing")
    if not flat_tick:
        blockers.append("final_position_flat_reconciliation_tick_missing")
    if (
        final_order
        and final_order.get("external_close") is not True
        and final_order.get("reduce_only") is not True
    ):
        blockers.append("final_exit_order_reduce_only_missing")
    blockers.extend(
        _residual_live_protection_blockers(
            conn,
            ticket_id=ticket_id,
            final_order=final_order,
        )
    )
    if blockers:
        lifecycle_status = (
            "position_closed_protection_live"
            if any(
                blocker.startswith("position_closed_protection_live:")
                for blocker in blockers
            )
            else "final_exit_unknown"
        )
        return _result(
            "finalization_blocked",
            blockers,
            False,
            lifecycle_status=lifecycle_status,
        )

    attempt_id = str(lifecycle.get("protected_submit_attempt_id") or "")
    reconciliation_evidence_id = str(flat_tick["reconciliation_tick_id"])
    settlement_evidence_id = _stable_id(
        "budget_settlement",
        ticket_id,
        str(final_order["exchange_order_id"]),
    )
    review_evidence_id = _stable_id(
        "lifecycle_review",
        ticket_id,
        reconciliation_evidence_id,
    )
    reconciliation_payload = {
        "reconciliation_evidence_id": reconciliation_evidence_id,
        "final_exit_exchange_order_id": str(final_order["exchange_order_id"]),
        "final_exit_role": str(final_order["role"]),
        "final_position_flat_confirmed": True,
        "reconciliation_tick_id": reconciliation_evidence_id,
    }
    _upsert_event(
        conn,
        lifecycle=lifecycle,
        event_type="reconciliation_matched",
        evidence_id=reconciliation_evidence_id,
        payload=reconciliation_payload,
        now_ms=now_ms,
    )

    settlement = settle_ticket_bound_budget(
        conn,
        ticket_id=ticket_id,
        settlement_evidence_id=settlement_evidence_id,
        now_ms=now_ms,
    )
    if settlement.get("status") != "released":
        return _result(
            "finalization_blocked",
            list(settlement.get("blockers") or []),
            False,
            lifecycle_status="settlement_blocked",
        )
    budget_mutated = settlement.get("runtime_budget_mutated") is True
    lifecycle = _set_lifecycle_status(
        conn,
        lifecycle=lifecycle,
        status="budget_settled",
        now_ms=now_ms,
    )
    _upsert_event(
        conn,
        lifecycle=lifecycle,
        event_type="budget_settled",
        evidence_id=settlement_evidence_id,
        payload={
            "settlement_evidence_id": settlement_evidence_id,
            "budget_status": "released",
            "budget_mutated": budget_mutated,
        },
        now_ms=now_ms,
    )
    lifecycle = _set_lifecycle_status(
        conn,
        lifecycle=lifecycle,
        status="review_recorded",
        now_ms=now_ms,
    )
    _upsert_event(
        conn,
        lifecycle=lifecycle,
        event_type="review_recorded",
        evidence_id=review_evidence_id,
        payload={
            "review_evidence_id": review_evidence_id,
            "review_scope": "mechanical_lifecycle_completion",
            "strategy_quality_decision": "pending_live_outcome_governance_review",
        },
        now_ms=now_ms,
    )
    closure = materialize_ticket_bound_lifecycle_closure(
        conn,
        protected_submit_attempt_id=attempt_id,
        final_exit_exchange_order_id=str(final_order["exchange_order_id"]),
        final_exit_role=str(final_order["role"]),
        final_position_flat_confirmed=True,
        reconciliation_evidence_id=reconciliation_evidence_id,
        settlement_evidence_id=settlement_evidence_id,
        review_evidence_id=review_evidence_id,
        realized_pnl=None,
        now_ms=now_ms,
    )
    if closure.get("status") != "closed":
        return {
            **_result(
                "finalization_blocked",
                list(closure.get("blockers") or []),
                budget_mutated,
                lifecycle_status="review_blocked",
            ),
            "closure_status": closure.get("status"),
        }
    _close_action_time_ticket(conn, ticket_id=ticket_id)
    outcome = materialize_live_outcome_ledger(
        conn,
        ticket_id=ticket_id,
        now_ms=now_ms,
    )
    return {
        **_result(
            "lifecycle_closed",
            [],
            budget_mutated,
            lifecycle_status="lifecycle_closed",
        ),
        "closure_status": closure.get("status"),
        "live_outcome_status": outcome.get("status"),
        "reconciliation_evidence_id": reconciliation_evidence_id,
        "settlement_evidence_id": settlement_evidence_id,
        "review_evidence_id": review_evidence_id,
    }


def _final_filled_order(
    conn: sa.engine.Connection,
    ticket_id: str,
) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    rows = conn.execute(
        sa.select(table).where(
            table.c.ticket_id == ticket_id,
            table.c.role.in_(tuple(FINAL_ROLES)),
            table.c.status == "filled",
        )
        .order_by(table.c.updated_at_ms.desc())
        .limit(1)
    ).mappings().first()
    return dict(rows) if rows else {}


def _final_exit_evidence(
    conn: sa.engine.Connection,
    ticket_id: str,
) -> dict[str, Any]:
    tracked = _final_filled_order(conn, ticket_id)
    if tracked:
        return {**tracked, "external_close": False}
    lifecycle = _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "ticket_id",
        ticket_id,
    )
    if not lifecycle:
        return {}
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    rows = conn.execute(
        sa.select(events)
        .where(
            events.c.lifecycle_run_id == lifecycle["lifecycle_run_id"],
            events.c.event_type == "final_exit_detected",
        )
        .order_by(events.c.created_at_ms.desc())
    ).mappings()
    for row in rows:
        payload = _json_dict(row.get("event_payload"))
        fill = _json_dict(payload.get("fill"))
        if str(fill.get("role") or "").upper() != "EXTERNAL_CLOSE":
            continue
        exchange_order_id = str(fill.get("exchange_order_id") or "").strip()
        if not exchange_order_id:
            continue
        return {
            "exchange_order_id": exchange_order_id,
            "role": "EXTERNAL_CLOSE",
            "reduce_only": None,
            "external_close": True,
            "lifecycle_event_id": row.get("lifecycle_event_id"),
        }
    return {}


def _latest_flat_reconciliation_tick(
    conn: sa.engine.Connection,
    ticket_id: str,
) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_reconciliation_ticks")
    row = conn.execute(
        sa.select(table).where(
            table.c.ticket_id == ticket_id,
            table.c.position_state == "flat",
            table.c.status == "matched",
        )
        .order_by(table.c.updated_at_ms.desc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else {}


def _residual_live_protection_blockers(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    final_order: dict[str, Any],
) -> list[str]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    final_order_id = str(final_order.get("exit_protection_order_id") or "")
    rows = conn.execute(
        sa.select(table).where(
            table.c.ticket_id == ticket_id,
            table.c.status.in_(tuple(LIVE_PROTECTION_ORDER_STATUSES)),
        )
    ).mappings()
    return [
        f"position_closed_protection_live:{str(row.get('role') or 'UNKNOWN')}"
        for row in rows
        if str(row.get("exit_protection_order_id") or "") != final_order_id
    ]


def _set_lifecycle_status(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    status: str,
    now_ms: int,
) -> dict[str, Any]:
    decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        target_status=status,
    )
    table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    conn.execute(
        table.update()
        .where(table.c.lifecycle_run_id == lifecycle["lifecycle_run_id"])
        .values(
            status=decision.status,
            first_blocker=decision.first_blocker,
            blockers=list(decision.blockers),
            updated_at_ms=now_ms,
        )
    )
    return _row_by_id(
        conn,
        "brc_ticket_bound_order_lifecycle_runs",
        "lifecycle_run_id",
        str(lifecycle["lifecycle_run_id"]),
    )


def _close_action_time_ticket(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
) -> None:
    tickets = _table(conn, "brc_action_time_tickets")
    conn.execute(
        tickets.update()
        .where(tickets.c.ticket_id == ticket_id)
        .where(tickets.c.status != "closed")
        .values(status="closed")
    )


def _upsert_event(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    event_type: str,
    evidence_id: str,
    payload: dict[str, Any],
    now_ms: int,
) -> None:
    table = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        event_type,
        evidence_id,
    )
    existing_payload = conn.execute(
        sa.select(table.c.event_payload).where(
            table.c.lifecycle_event_id == event_id
        )
    ).scalar_one_or_none()
    if existing_payload is not None:
        existing = _json_dict(existing_payload)
        if all(existing.get(key) == value for key, value in payload.items()):
            return
        event_id = _stable_id(
            "ticket_lifecycle_event",
            str(lifecycle["lifecycle_run_id"]),
            event_type,
            evidence_id,
            "fact_repair",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
        )
        if conn.execute(
            sa.select(table.c.lifecycle_event_id).where(
                table.c.lifecycle_event_id == event_id
            )
        ).first():
            return
    conn.execute(
        table.insert().values(
            lifecycle_event_id=event_id,
            lifecycle_run_id=lifecycle["lifecycle_run_id"],
            ticket_id=lifecycle["ticket_id"],
            protected_submit_attempt_id=lifecycle[
                "protected_submit_attempt_id"
            ],
            event_type=event_type,
            event_payload=payload,
            created_at_ms=now_ms,
        )
    )


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:40]
    return f"{prefix}:{digest}"


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _result(
    status: str,
    blockers: list[str],
    budget_mutated: bool,
    *,
    lifecycle_status: str | None = None,
) -> dict[str, Any]:
    decision = lifecycle_decision_for_status(
        lifecycle_status or ("blocked" if blockers else "blocked"),
        blockers=blockers,
    )
    return {
        "status": status,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "runtime_budget_mutated": budget_mutated,
        "exchange_write_called": False,
        "lifecycle_decision": decision.to_dict(),
    }
