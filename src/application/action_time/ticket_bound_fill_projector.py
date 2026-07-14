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
    projected: list[dict[str, Any]] = []
    for row in rows:
        exchange_order_id = str(row.get("exchange_order_id") or "")
        if str(row.get("role") or "") == "TP1" and _versioned_exit_projection_exists(
            conn,
            ticket_id=ticket_id,
        ):
            versioned = _project_versioned_tp1_fills(
                conn,
                ticket_id=ticket_id,
                order=dict(row),
                fills=fills,
                exchange_snapshot=exchange_snapshot,
                now_ms=now_ms,
            )
            if versioned.get("status") == "blocked":
                return versioned
            projected.extend(versioned.get("projected_fills") or [])
            continue
        fill = _fill_for_order(fills, exchange_order_id=exchange_order_id)
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
            if existing_fill:
                continue
        else:
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
                "exchange_trade_id": str(fill.get("exchange_trade_id") or "") or None,
                "exchange_order_id": str(fill.get("exchange_order_id") or ""),
                "parent_exchange_order_id": (
                    str(fill.get("parent_exchange_order_id") or "") or None
                ),
                "fill_qty": str(fill.get("qty") or ""),
                "fill_price": str(fill.get("price") or ""),
                "fill_time_ms": fill.get("timestamp_ms"),
                "fee": fill.get("fee"),
                "liquidity_role": fill.get("liquidity_role"),
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
                "funding_income_available": (
                    exchange_snapshot.get("funding_income_available") is True
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
            if _tp1_gtx_taker_contradiction(
                conn,
                ticket_id=ticket_id,
                fill=projected[-1],
            ):
                return _hard_stop_tp1_gtx_taker_contradiction(
                    conn,
                    ticket_id=ticket_id,
                    fill=projected[-1],
                    now_ms=now_ms,
                )
    _review_closed_external_exit_lineage(
        conn,
        ticket_id=ticket_id,
        exchange_snapshot=exchange_snapshot,
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


def _versioned_exit_projection_exists(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
) -> bool:
    if not sa.inspect(conn).has_table("brc_ticket_exit_policy_current"):
        return False
    table = _table(conn, "brc_ticket_exit_policy_current")
    return conn.execute(
        sa.select(table.c.ticket_id).where(table.c.ticket_id == ticket_id)
    ).first() is not None


def _project_versioned_tp1_fills(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    order: dict[str, Any],
    fills: list[dict[str, Any]],
    exchange_snapshot: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    exchange_order_id = str(order.get("exchange_order_id") or "")
    matching = _fills_for_order(fills, exchange_order_id=exchange_order_id)
    if not matching:
        return {"status": "no_new_fills", "projected_fills": []}
    lifecycle = _lifecycle_for_ticket(conn, ticket_id)
    newly_projected: list[dict[str, Any]] = []
    for fill in matching:
        projected_fill = {
            "role": "TP1",
            "exchange_trade_id": str(fill.get("exchange_trade_id") or "") or None,
            "exchange_order_id": str(fill.get("exchange_order_id") or ""),
            "parent_exchange_order_id": (
                str(fill.get("parent_exchange_order_id") or "") or None
            ),
            "fill_qty": str(fill.get("qty") or ""),
            "fill_price": str(fill.get("price") or ""),
            "fill_time_ms": fill.get("timestamp_ms"),
            "fee": fill.get("fee"),
            "liquidity_role": fill.get("liquidity_role"),
            "realized_pnl": fill.get("realized_pnl"),
            "reference_price": _exit_reference_price(order),
            "funding_income": [],
            "funding_income_available": (
                exchange_snapshot.get("funding_income_available") is True
            ),
        }
        existing = _recorded_tp1_trade(
            conn,
            lifecycle=lifecycle,
            projected_fill=projected_fill,
        )
        if existing:
            if _fill_truth_conflicts(existing, projected_fill):
                return _hard_stop_fill_truth_contradiction(
                    conn,
                    ticket_id=ticket_id,
                    role="TP1",
                    exchange_order_id=exchange_order_id,
                    existing_fill=existing,
                    conflicting_fill=projected_fill,
                    now_ms=now_ms,
                )
            continue
        inserted = _insert_fill_event(
            conn,
            lifecycle=lifecycle,
            event_type="tp1_filled",
            fill=projected_fill,
            now_ms=now_ms,
        )
        if inserted:
            newly_projected.append(projected_fill)
        if _tp1_gtx_taker_contradiction(
            conn,
            ticket_id=ticket_id,
            fill=projected_fill,
        ):
            return _hard_stop_tp1_gtx_taker_contradiction(
                conn,
                ticket_id=ticket_id,
                fill=projected_fill,
                now_ms=now_ms,
            )

    cumulative = _recorded_tp1_cumulative_qty(
        conn,
        lifecycle=lifecycle,
        exchange_order_id=exchange_order_id,
    )
    projections = _table(conn, "brc_ticket_exit_policy_current")
    current = conn.execute(
        sa.select(projections).where(projections.c.ticket_id == ticket_id)
    ).mappings().one()
    target = _normalized_decimal(current.get("resolved_tp1_target_qty"))
    if target is None or target <= 0:
        target = _normalized_decimal(order.get("qty"))
    position = _mapping(exchange_snapshot.get("position"))
    remaining = _normalized_decimal(position.get("qty"))
    if target is None or target <= 0 or remaining is None or remaining < 0:
        blocker = "tp1_fill_projection_required_fact_missing"
        conn.execute(
            projections.update()
            .where(projections.c.ticket_id == ticket_id)
            .values(first_blocker=blocker, updated_at_ms=now_ms)
        )
        return {
            "status": "blocked",
            "projected_roles": [],
            "projected_count": 0,
            "projected_fills": [],
            "first_blocker": blocker,
            "blockers": [blocker],
        }
    tolerance = _tp1_completion_tolerance(
        conn,
        ticket_id=ticket_id,
        current=dict(current),
    )
    if cumulative > target + tolerance:
        completion = "contradictory"
        blocker = "tp1_cumulative_fill_exceeds_frozen_target"
    elif target - cumulative <= tolerance:
        completion = "complete"
        blocker = None
    elif cumulative > 0:
        completion = "partial"
        blocker = None
    else:
        completion = "unfilled"
        blocker = None
    conn.execute(
        projections.update()
        .where(projections.c.ticket_id == ticket_id)
        .values(
            tp1_cumulative_filled_qty=cumulative,
            tp1_completion_state=completion,
            remaining_position_qty=remaining,
            state=(
                "tp1_complete"
                if completion == "complete"
                else "tp1_partial" if completion == "partial" else "blocked"
            ),
            first_blocker=blocker,
            updated_at_ms=now_ms,
        )
    )
    orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    conn.execute(
        orders.update()
        .where(
            orders.c.exit_protection_order_id
            == order["exit_protection_order_id"]
        )
        .values(
            status=(
                "filled"
                if completion == "complete"
                else "partially_filled" if completion == "partial" else order["status"]
            ),
            updated_at_ms=now_ms,
        )
    )
    if blocker:
        return {
            "status": "blocked",
            "projected_roles": ["TP1"] if newly_projected else [],
            "projected_count": len(newly_projected),
            "projected_fills": newly_projected,
            "first_blocker": blocker,
            "blockers": [blocker],
        }
    return {
        "status": "fills_projected" if newly_projected else "no_new_fills",
        "projected_fills": newly_projected,
    }


def _tp1_completion_tolerance(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    current: dict[str, Any],
) -> Decimal:
    tickets = _table(conn, "brc_action_time_tickets")
    ticket = conn.execute(
        sa.select(tickets).where(tickets.c.ticket_id == ticket_id)
    ).mappings().one()
    policy = _mapping(ticket.get("exit_policy_snapshot"))
    steps = int(policy.get("tp_completion_tolerance_qty_steps") or 0)
    instruments = _table(conn, "brc_exchange_instruments")
    instrument = conn.execute(
        sa.select(instruments).where(
            instruments.c.exchange_instrument_id
            == ticket["exchange_instrument_id"]
        )
    ).mappings().one()
    quantity_step = _normalized_decimal(instrument.get("quantity_step"))
    if quantity_step is None or quantity_step <= 0:
        return Decimal("0")
    return Decimal(steps) * quantity_step


def _recorded_tp1_trade(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    projected_fill: dict[str, Any],
) -> dict[str, Any]:
    if not lifecycle:
        return {}
    identity = _fill_event_identity(projected_fill)
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    rows = conn.execute(
        sa.select(events.c.event_payload).where(
            events.c.lifecycle_run_id == lifecycle["lifecycle_run_id"],
            events.c.event_type == "tp1_filled",
        )
    ).scalars()
    for payload in rows:
        fill = _mapping(_mapping(payload).get("fill"))
        if _fill_event_identity(fill) == identity:
            return fill
    return {}


def _recorded_tp1_cumulative_qty(
    conn: sa.engine.Connection,
    *,
    lifecycle: dict[str, Any],
    exchange_order_id: str,
) -> Decimal:
    if not lifecycle:
        return Decimal("0")
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    total = Decimal("0")
    for payload in conn.execute(
        sa.select(events.c.event_payload).where(
            events.c.lifecycle_run_id == lifecycle["lifecycle_run_id"],
            events.c.event_type == "tp1_filled",
        )
    ).scalars():
        fill = _mapping(_mapping(payload).get("fill"))
        if exchange_order_id not in {
            str(fill.get("exchange_order_id") or ""),
            str(fill.get("parent_exchange_order_id") or ""),
        }:
            continue
        qty = _normalized_decimal(fill.get("fill_qty", fill.get("qty")))
        if qty is not None and qty > 0:
            total += qty
    return total


def _tp1_gtx_taker_contradiction(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    fill: dict[str, Any],
) -> bool:
    if str(fill.get("liquidity_role") or "").lower() != "taker":
        return False
    if not sa.inspect(conn).has_table("brc_ticket_bound_exchange_commands"):
        return False
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    command = conn.execute(
        sa.select(commands).where(
            commands.c.ticket_id == ticket_id,
            commands.c.order_role == "TP1",
            commands.c.command_kind == "place_order",
        )
    ).mappings().first()
    if not command:
        return False
    return (
        str(command.get("execution_style") or "") == "passive_limit_gtx"
        or str(command.get("time_in_force") or "").upper() == "GTX"
        or command.get("post_only") is True
    )


def _hard_stop_tp1_gtx_taker_contradiction(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    fill: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    blocker = "tp1_gtx_taker_contradiction"
    lifecycle_table = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    lifecycle = conn.execute(
        sa.select(lifecycle_table).where(lifecycle_table.c.ticket_id == ticket_id)
    ).mappings().one()
    decision = reduce_lifecycle_decision(
        current_status=str(lifecycle.get("status") or ""),
        target_status="blocked",
        event_type="hard_stopped",
        blockers=[blocker],
        next_action="reconcile_tp1_execution_adapter_truth",
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
    _insert_fill_event(
        conn,
        lifecycle=dict(lifecycle),
        event_type=decision.event_type,
        fill={**fill, "first_blocker": blocker},
        now_ms=now_ms,
    )
    return {
        "status": "blocked",
        "projected_roles": ["TP1"],
        "projected_count": 1,
        "projected_fills": [fill],
        "first_blocker": blocker,
        "blockers": [blocker],
        "lifecycle_decision": decision.to_dict(),
    }


def _review_closed_external_exit_lineage(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any],
    now_ms: int,
) -> None:
    if exchange_snapshot.get("conditional_order_lineage_available") is not True:
        return
    if not sa.inspect(conn).has_table("brc_ticket_bound_post_submit_closures"):
        return
    closures = _table(conn, "brc_ticket_bound_post_submit_closures")
    closure = conn.execute(
        sa.select(closures).where(closures.c.ticket_id == ticket_id)
    ).mappings().first()
    if not closure:
        return
    evidence = _mapping(closure.get("reconciliation_evidence"))
    if str(evidence.get("final_exit_role") or "").upper() != "EXTERNAL_CLOSE":
        return
    final_exit_id = str(
        evidence.get("final_exit_exchange_order_id") or ""
    ).strip()
    lineage_actual_ids = {
        str(item.get("actual_exchange_order_id") or "").strip()
        for item in exchange_snapshot.get("conditional_order_lineage", [])
        if isinstance(item, dict)
    }
    if final_exit_id and final_exit_id in lineage_actual_ids:
        return
    if evidence.get("conditional_lineage_reviewed_at_ms") is not None:
        return
    conn.execute(
        closures.update()
        .where(
            closures.c.post_submit_closure_id
            == closure["post_submit_closure_id"]
        )
        .values(
            reconciliation_evidence={
                **evidence,
                "conditional_lineage_reviewed_at_ms": now_ms,
                "conditional_lineage_review_result": (
                    "external_close_confirmed_no_conditional_parent_match"
                ),
            },
            updated_at_ms=now_ms,
        )
    )


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
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    payloads = conn.execute(
        sa.select(events.c.event_payload).where(
            events.c.lifecycle_run_id == lifecycle["lifecycle_run_id"],
            events.c.event_type == event_type,
        )
    ).scalars()
    for payload in payloads:
        fill = _mapping(_mapping(payload).get("fill"))
        if exchange_order_id in {
            str(fill.get("exchange_order_id") or ""),
            str(fill.get("parent_exchange_order_id") or ""),
        }:
            return fill
    return {}


def _fill_for_order(
    fills: list[dict[str, Any]],
    *,
    exchange_order_id: str,
) -> dict[str, Any]:
    for fill in fills:
        if exchange_order_id in {
            str(fill.get("exchange_order_id") or ""),
            str(fill.get("parent_exchange_order_id") or ""),
        }:
            return dict(fill)
    return {}


def _fills_for_order(
    fills: list[dict[str, Any]],
    *,
    exchange_order_id: str,
) -> list[dict[str, Any]]:
    return [
        dict(fill)
        for fill in fills
        if exchange_order_id
        in {
            str(fill.get("exchange_order_id") or ""),
            str(fill.get("parent_exchange_order_id") or ""),
        }
    ]


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
        observed = _normalized_decimal(
            observed_fill.get(observed_key, observed_fill.get(existing_key))
        )
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
    if str(row.get("status") or "") == "lifecycle_closed":
        _insert_fill_event(
            conn,
            lifecycle=dict(row),
            event_type="final_exit_detected",
            fill=fill,
            now_ms=now_ms,
        )
        _correct_closed_lifecycle_final_exit_lineage(
            conn,
            ticket_id=ticket_id,
            fill=fill,
            now_ms=now_ms,
        )
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


def _correct_closed_lifecycle_final_exit_lineage(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    fill: dict[str, Any],
    now_ms: int,
) -> None:
    if not sa.inspect(conn).has_table("brc_ticket_bound_post_submit_closures"):
        return
    role = str(fill.get("role") or "").upper()
    exchange_order_id = str(fill.get("exchange_order_id") or "").strip()
    if role not in FINAL_EXIT_ROLES or not exchange_order_id:
        return
    closures = _table(conn, "brc_ticket_bound_post_submit_closures")
    closure = conn.execute(
        sa.select(closures).where(closures.c.ticket_id == ticket_id)
    ).mappings().first()
    if not closure:
        return
    evidence = _mapping(closure.get("reconciliation_evidence"))
    if (
        str(evidence.get("final_exit_role") or "").upper() == role
        and str(evidence.get("final_exit_exchange_order_id") or "")
        == exchange_order_id
    ):
        return
    warnings = _string_list(closure.get("warnings"))
    correction = "final_exit_lineage_corrected_from_exchange_fact"
    if correction not in warnings:
        warnings.append(correction)
    conn.execute(
        closures.update()
        .where(
            closures.c.post_submit_closure_id
            == closure["post_submit_closure_id"]
        )
        .values(
            reconciliation_evidence={
                **evidence,
                "final_exit_exchange_order_id": exchange_order_id,
                "final_exit_parent_exchange_order_id": (
                    str(fill.get("parent_exchange_order_id") or "") or None
                ),
                "final_exit_role": role,
                "lineage_correction_source": "exact_conditional_order_lineage",
            },
            warnings=warnings,
            updated_at_ms=now_ms,
        )
    )


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
) -> bool:
    if not lifecycle:
        return False
    events = _table(conn, "brc_ticket_bound_lifecycle_events")
    event_id = _stable_id(
        "ticket_lifecycle_event",
        str(lifecycle["lifecycle_run_id"]),
        event_type,
        _fill_event_identity(fill),
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
        return True
    return False


def _fill_event_identity(fill: dict[str, Any]) -> str:
    trade_id = str(fill.get("exchange_trade_id") or "").strip()
    if trade_id:
        return f"trade:{trade_id}"
    return "fill:" + sha256(
        "|".join(
            (
                str(fill.get("exchange_order_id") or ""),
                str(fill.get("parent_exchange_order_id") or ""),
                str(fill.get("fill_time_ms", fill.get("timestamp_ms")) or ""),
                str(fill.get("fill_qty", fill.get("qty")) or ""),
                str(fill.get("fill_price", fill.get("price")) or ""),
            )
        ).encode("utf-8")
    ).hexdigest()


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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


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
