"""Maintain one versioned Ticket exit policy through the durable command authority.

The service owns policy projection and command preparation only.  It never calls
an exchange gateway.  The existing ticket-bound command worker remains the only
exchange-write authority.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from hashlib import sha256
import json
from typing import Any, Callable

import sqlalchemy as sa

from src.application.action_time.exchange_scope import (
    TicketBoundExchangeScope,
    resolve_ticket_bound_exchange_scope,
)
from src.application.action_time.ticket_exit_market_fact_service import (
    ClosedCandle,
    ClosedCandleSource,
    TIMEFRAME_MS,
    materialize_due_ticket_exit_market_facts,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    TicketBoundExchangeCommand,
    deterministic_client_order_id,
)
from src.domain.ticket_exit_policy import (
    ExitDecision,
    ExitDecisionKind,
    ExitEvaluationInput,
    ExitMarketFact,
    ReferenceTrailRunnerRule,
    StructuralAtrRunnerRule,
    TicketExitExecutionSnapshot,
    TicketExitPolicySnapshot,
    calculate_runner_break_even_floor,
    evaluate_exit_policy,
)
from src.application.action_time.ticket_exit_policy_binding import (
    resolve_effective_ticket_exit_policy_binding,
)
from src.application.action_time.ticket_instrument_rule import (
    TicketInstrumentRuleError,
    resolve_ticket_instrument_rule,
)


CAPABILITY_ID = "ticket_exit_policy_v1"
COMMAND_TABLE = "brc_ticket_bound_exchange_commands"
CONFIRMED_COMMAND_STATES = {"confirmed_submitted", "reconciled_submitted"}
TERMINAL_FAILURE_STATES = {"confirmed_rejected", "hard_stopped"}
PENDING_COMMAND_STATES = {"prepared", "dispatching"}
AUTHORITY_BOUNDARY = (
    "ticket_exit_policy_service; exact frozen Ticket policy and PG projection to "
    "existing durable exchange command only; no direct exchange call, signal, "
    "FinalGate, Operation Layer, profile, sizing, withdrawal, or transfer authority"
)


def maintain_ticket_exit_policy_in_transaction(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any] | None = None,
    now_ms: int,
) -> dict[str, Any]:
    """Evaluate already-persisted facts and prepare at most one next command."""

    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_ticket_id or now_ms <= 0:
        raise ValueError("ticket_exit_policy_maintenance_input_invalid")
    if not _capability_enabled(conn):
        return _result("exit_policy_capability_disabled", normalized_ticket_id)
    early_projection = _row_by_id(
        conn,
        "brc_ticket_exit_policy_current",
        "ticket_id",
        normalized_ticket_id,
    )
    if (
        early_projection
        and _decimal_or_none(early_projection.get("remaining_position_qty"))
        == Decimal("0")
    ):
        return _result("position_terminal", normalized_ticket_id)

    loaded = _load_state(
        conn,
        ticket_id=normalized_ticket_id,
        exchange_snapshot=exchange_snapshot,
        now_ms=now_ms,
    )
    if loaded.get("blockers"):
        return _block_projection(
            conn,
            projection=loaded.get("projection") or {},
            ticket_id=normalized_ticket_id,
            blocker=str(loaded["blockers"][0]),
            now_ms=now_ms,
        )
    projection = loaded["projection"]
    policy = loaded["policy"]
    execution = loaded["execution"]
    active = loaded["active_order"]
    instrument_rule = loaded["instrument_rule"]
    scope = loaded["scope"]

    close_pending = _existing_close_state(conn, projection=projection)
    if close_pending:
        return close_pending
    pending = _advance_pending_runner_replacement(
        conn,
        loaded=loaded,
        now_ms=now_ms,
    )
    if pending is not None:
        return pending

    completion = str(projection.get("tp1_completion_state") or "")
    remaining_qty = _decimal_or_none(projection.get("remaining_position_qty"))
    if remaining_qty is None or remaining_qty < 0:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker="remaining_position_quantity_invalid",
            now_ms=now_ms,
        )
    if remaining_qty == 0:
        return _result("position_terminal", normalized_ticket_id)
    if completion == "contradictory":
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker="tp1_completion_truth_contradictory",
            now_ms=now_ms,
        )
    reprice = _advance_tp1_reprice(
        conn,
        loaded=loaded,
        completion=completion,
        now_ms=now_ms,
    )
    if reprice is not None:
        return reprice
    if completion == "unfilled":
        return _record_decision(
            conn,
            projection=projection,
            kind="noop",
            reason="tp1_unfilled",
            state="execution_bound",
            now_ms=now_ms,
        )
    if completion == "partial":
        active_qty = _required_decimal(active.get("qty"), "active_runner_quantity")
        if active_qty == remaining_qty:
            return _record_decision(
                conn,
                projection=projection,
                kind="noop",
                reason="protection_quantity_synchronized",
                state="tp1_partial",
                now_ms=now_ms,
            )
        return _prepare_runner_replacement(
            conn,
            loaded=loaded,
            proposed_stop=_required_decimal(
                active.get("trigger_price"), "active_runner_stop"
            ),
            amount=remaining_qty,
            reason="tp1_partial_protection_resize",
            source_watermark=_fill_watermark(projection),
            now_ms=now_ms,
        )
    if completion != "complete":
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker="tp1_completion_state_invalid",
            now_ms=now_ms,
        )

    price_tick = instrument_rule.price_tick
    quantity_step = instrument_rule.quantity_step
    tolerance = Decimal(policy.tp_completion_tolerance_qty_steps) * quantity_step
    if abs(remaining_qty - execution.runner_target_qty) > tolerance:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker="runner_quantity_contradicts_execution_snapshot",
            now_ms=now_ms,
        )
    try:
        floor = calculate_runner_break_even_floor(
            side=scope.side,
            entry_avg_fill_price=execution.entry_avg_fill_price,
            runner_qty=remaining_qty,
            allocated_entry_fee_quote=execution.entry_fee_quote,
            certified_exit_taker_fee_rate=execution.certified_exit_taker_fee_rate,
            slippage_buffer_quote=execution.slippage_buffer_quote,
            minimum_price_tick=price_tick,
        )
    except ValueError as exc:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker=f"runner_floor_invalid:{exc}",
            now_ms=now_ms,
        )
    _update_projection(
        conn,
        ticket_id=normalized_ticket_id,
        values={"runner_break_even_floor": floor, "updated_at_ms": now_ms},
    )
    projection = {**projection, "runner_break_even_floor": floor}

    market_fact, fact_blocker = _load_latest_exit_market_fact(
        conn,
        loaded=loaded,
        now_ms=now_ms,
    )
    if fact_blocker:
        # The TP1 floor is immediate and independent of public-candle availability.
        market_fact = None
    evaluation = ExitEvaluationInput(
        policy=policy,
        ticket_id=normalized_ticket_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        venue_id=scope.exchange_id,
        side=scope.side,
        position_qty=remaining_qty,
        current_runner_stop=_required_decimal(
            active.get("trigger_price"), "active_runner_stop"
        ),
        active_runner_generation=int(active.get("generation") or 1),
        protection_identity_exact=True,
        tp1_completion_state="complete",
        immediate_runner_floor=floor,
        minimum_price_tick=price_tick,
        market_fact=market_fact,
        evaluated_watermark_ms=(
            market_fact.watermark_ms if market_fact is not None else _fill_watermark(projection)
        ),
    )
    decision = evaluate_exit_policy(evaluation)
    if decision.kind is ExitDecisionKind.CLOSE_RUNNER:
        return _prepare_runner_close(
            conn,
            loaded=loaded,
            decision=decision,
            now_ms=now_ms,
        )
    if decision.kind is ExitDecisionKind.MOVE_RUNNER_STOP:
        return _prepare_runner_replacement(
            conn,
            loaded=loaded,
            proposed_stop=_required_decimal(
                decision.proposed_stop, "proposed_runner_stop"
            ),
            amount=remaining_qty,
            reason=decision.reason_code,
            source_watermark=decision.source_watermark_ms,
            now_ms=now_ms,
        )
    if decision.kind is ExitDecisionKind.BLOCKED:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=normalized_ticket_id,
            blocker=decision.reason_code,
            now_ms=now_ms,
        )
    return _record_decision(
        conn,
        projection=projection,
        kind=decision.kind.value,
        reason=decision.reason_code,
        state="runner_protected",
        now_ms=now_ms,
    )


async def maintain_ticket_exit_policy(
    *,
    conn_factory: Callable[[], AbstractContextManager[sa.engine.Connection]],
    ticket_id: str,
    now_ms: int,
    closed_candle_source: ClosedCandleSource,
) -> dict[str, Any]:
    """Run immediate maintenance, then one bounded due-fact pass when needed."""

    with conn_factory() as conn:
        immediate = maintain_ticket_exit_policy_in_transaction(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )
        engine = conn.engine
    if immediate["status"] not in {
        "runner_stop_not_improved",
        "runner_protected",
        "no_due_market_fact",
    }:
        return immediate
    await materialize_due_ticket_exit_market_facts(
        engine,
        ticket_ids=[ticket_id],
        now_ms=now_ms,
        source=closed_candle_source,
    )
    with conn_factory() as conn:
        return maintain_ticket_exit_policy_in_transaction(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )


def _load_state(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any] | None,
    now_ms: int,
) -> dict[str, Any]:
    required_tables = (
        "brc_action_time_tickets",
        "brc_ticket_exit_policy_current",
        "brc_ticket_bound_exit_protection_sets",
        "brc_ticket_bound_exit_protection_orders",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_protected_submit_attempts",
        "brc_exchange_instruments",
    )
    missing = [name for name in required_tables if not sa.inspect(conn).has_table(name)]
    if missing:
        return {"blockers": [f"ticket_exit_policy_table_missing:{missing[0]}"]}
    ticket = _row_by_id(conn, "brc_action_time_tickets", "ticket_id", ticket_id)
    projection = _row_by_id(
        conn, "brc_ticket_exit_policy_current", "ticket_id", ticket_id
    )
    if not ticket or not projection:
        return {
            "projection": projection,
            "blockers": ["ticket_exit_policy_state_missing"],
        }
    try:
        binding = resolve_effective_ticket_exit_policy_binding(
            conn,
            ticket_id=ticket_id,
            now_ms=now_ms,
        )
        if binding.snapshot is None:
            return {
                "projection": projection,
                "blockers": ["legacy_ticket_exit_policy_unbound"],
            }
        policy = binding.snapshot
        execution = TicketExitExecutionSnapshot.model_validate(
            _mapping(projection.get("exit_execution_snapshot"))
        )
    except Exception as exc:
        return {
            "projection": projection,
            "blockers": [f"ticket_exit_policy_snapshot_invalid:{type(exc).__name__}"],
        }
    if (
        str(projection.get("exit_policy_hash") or "") != policy.payload_hash
        or str(projection.get("exit_execution_hash") or "") != execution.payload_hash
        or execution.ticket_id != ticket_id
        or execution.exit_policy_id != policy.exit_policy_id
        or execution.exit_policy_version != policy.exit_policy_version
    ):
        return {
            "projection": projection,
            "blockers": ["ticket_exit_policy_identity_contradiction"],
        }
    resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=ticket_id,
        now_ms=now_ms,
    )
    if resolution.status != "resolved" or resolution.scope is None:
        return {
            "projection": projection,
            "blockers": list(resolution.blockers) or ["ticket_exchange_scope_unresolved"],
        }
    set_id = str(projection.get("exit_protection_set_id") or "").strip()
    if not set_id:
        lifecycle = _row_by_id(
            conn, "brc_ticket_bound_order_lifecycle_runs", "ticket_id", ticket_id
        )
        set_id = str(lifecycle.get("exit_protection_set_id") or "").strip()
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    orders = _rows_by_value(
        conn,
        "brc_ticket_bound_exit_protection_orders",
        "exit_protection_set_id",
        set_id,
    )
    active, active_blocker = _resolve_active_order(
        orders=orders,
        projection=projection,
    )
    if active_blocker:
        return {
            "projection": projection,
            "blockers": [active_blocker],
        }
    instrument = _row_by_id(
        conn,
        "brc_exchange_instruments",
        "exchange_instrument_id",
        resolution.scope.exchange_instrument_id,
    )
    lifecycle = _row_by_id(
        conn, "brc_ticket_bound_order_lifecycle_runs", "ticket_id", ticket_id
    )
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(lifecycle.get("protected_submit_attempt_id") or ""),
    )
    if not protection_set or not instrument or not lifecycle or not attempt:
        return {
            "projection": projection,
            "blockers": ["ticket_exit_policy_lifecycle_identity_incomplete"],
        }
    try:
        instrument_rule = resolve_ticket_instrument_rule(
            instrument=instrument,
            exchange_snapshot=exchange_snapshot,
        )
    except TicketInstrumentRuleError as exc:
        return {
            "projection": projection,
            "blockers": [f"ticket_instrument_rule_{exc}"],
        }
    active_generation = int(active.get("generation") or 1)
    active_stop = _required_decimal(active.get("trigger_price"), "active_runner_stop")
    if (
        str(projection.get("active_runner_order_id") or "")
        != str(active.get("exit_protection_order_id") or "")
        or int(projection.get("active_runner_generation") or 0) != active_generation
        or _decimal_or_none(projection.get("active_runner_stop")) != active_stop
        or str(projection.get("exit_protection_set_id") or "") != set_id
    ):
        _update_projection(
            conn,
            ticket_id=ticket_id,
            values={
                "exit_protection_set_id": set_id,
                "active_runner_order_id": active["exit_protection_order_id"],
                "active_runner_generation": active_generation,
                "active_runner_stop": active_stop,
                "updated_at_ms": now_ms,
            },
        )
        projection = {
            **projection,
            "exit_protection_set_id": set_id,
            "active_runner_order_id": active["exit_protection_order_id"],
            "active_runner_generation": active_generation,
            "active_runner_stop": active_stop,
        }
    return {
        "ticket": ticket,
        "projection": projection,
        "policy": policy,
        "execution": execution,
        "scope": resolution.scope,
        "protection_set": protection_set,
        "orders": orders,
        "active_order": active,
        "instrument": instrument,
        "instrument_rule": instrument_rule,
        "lifecycle": lifecycle,
        "attempt": attempt,
        "blockers": [],
    }


def _resolve_active_order(
    *,
    orders: list[dict[str, Any]],
    projection: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    active_statuses = {"planned", "submitted", "open", "partially_filled"}
    candidates = [
        row
        for row in orders
        if str(row.get("role") or "") in {"SL", "RUNNER_SL"}
        and str(row.get("status") or "") in active_statuses
    ]
    projected_id = str(projection.get("active_runner_order_id") or "")
    if projected_id:
        projected = next(
            (
                row
                for row in candidates
                if str(row.get("exit_protection_order_id") or "") == projected_id
            ),
            None,
        )
        if projected is not None:
            return dict(projected), None
    if not candidates:
        return {}, "active_runner_protection_missing"
    highest_generation = max(int(row.get("generation") or 1) for row in candidates)
    highest = [
        row for row in candidates if int(row.get("generation") or 1) == highest_generation
    ]
    if len(highest) != 1:
        return {}, "active_runner_protection_ambiguous"
    return dict(highest[0]), None


def _advance_pending_runner_replacement(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    now_ms: int,
) -> dict[str, Any] | None:
    projection = loaded["projection"]
    pending_command_id = str(projection.get("pending_runner_order_id") or "")
    if not pending_command_id:
        return None
    ticket_id = str(projection["ticket_id"])
    place = _row_by_id(
        conn, COMMAND_TABLE, "exchange_command_id", pending_command_id
    )
    if not place or str(place.get("command_source") or "") != "exit_policy_runner":
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="pending_runner_command_missing",
            now_ms=now_ms,
        )
    state = str(place.get("command_state") or "")
    if state in PENDING_COMMAND_STATES:
        return _result("runner_place_pending", ticket_id)
    if state == "outcome_unknown":
        return _result(
            "runner_place_outcome_unknown",
            ticket_id,
            blockers=["exchange_command_outcome_unknown"],
        )
    if state in TERMINAL_FAILURE_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker=f"runner_place_{state}",
            now_ms=now_ms,
        )
    if state not in CONFIRMED_COMMAND_STATES or not str(
        place.get("exchange_order_id") or ""
    ):
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="runner_place_confirmation_invalid",
            now_ms=now_ms,
        )

    old_id = str(projection.get("replaced_runner_order_id") or "")
    old = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_orders",
        "exit_protection_order_id",
        old_id,
    )
    if not old:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="runner_replacement_prior_order_missing",
            now_ms=now_ms,
        )
    if str(old.get("status") or "") == "filled":
        return _result("position_terminal_during_runner_replacement", ticket_id)
    new_order = _ensure_pending_protection_order(
        conn,
        loaded=loaded,
        place=place,
        old=old,
        now_ms=now_ms,
    )
    cancel = _command_by_source_kind(
        conn,
        source_command_id=str(place["source_command_id"]),
        command_kind="cancel_order",
    )
    if not cancel:
        cancel = _materialize_policy_command(
            conn,
            loaded=loaded,
            command_source="exit_policy_runner",
            source_command_id=str(place["source_command_id"]),
            command_kind="cancel_order",
            order_role=str(old.get("role") or "RUNNER_SL"),
            order_type="cancel",
            amount=_required_decimal(place.get("amount"), "runner_replacement_amount"),
            stop_price=None,
            target_exchange_order_id=str(old.get("exchange_order_id") or ""),
            local_order_id=f"{place['source_command_id']}:cancel-old",
            parent_order_id=str(old["exit_protection_order_id"]),
            generation=int(place.get("command_generation") or 1),
            now_ms=now_ms,
        )
        _update_order(
            conn,
            order_id=str(old["exit_protection_order_id"]),
            values={"status": "cancel_pending", "updated_at_ms": now_ms},
        )
        return _result(
            "runner_cancel_prepared",
            ticket_id,
            command_id=str(cancel["exchange_command_id"]),
        )
    cancel_state = str(cancel.get("command_state") or "")
    if cancel_state in PENDING_COMMAND_STATES:
        return _result("runner_cancel_pending", ticket_id)
    if cancel_state == "outcome_unknown":
        return _result(
            "runner_cancel_outcome_unknown",
            ticket_id,
            blockers=["exchange_command_outcome_unknown"],
        )
    if cancel_state in TERMINAL_FAILURE_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker=f"runner_cancel_{cancel_state}",
            now_ms=now_ms,
        )
    if cancel_state not in CONFIRMED_COMMAND_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="runner_cancel_confirmation_invalid",
            now_ms=now_ms,
        )
    _update_order(
        conn,
        order_id=str(old["exit_protection_order_id"]),
        values={"status": "replaced", "updated_at_ms": now_ms},
    )
    _update_projection(
        conn,
        ticket_id=ticket_id,
        values={
            "active_runner_order_id": new_order["exit_protection_order_id"],
            "active_runner_generation": new_order["generation"],
            "active_runner_stop": new_order["trigger_price"],
            "pending_runner_order_id": None,
            "pending_generation": None,
            "replaced_runner_order_id": None,
            "runner_floor_applied_at_ms": (
                now_ms
                if str(projection.get("last_reason_code") or "")
                == "tp1_completion_runner_floor"
                else projection.get("runner_floor_applied_at_ms")
            ),
            "state": "runner_protected",
            "first_blocker": None,
            "updated_at_ms": now_ms,
        },
    )
    return _result("runner_replacement_completed", ticket_id)


def _advance_tp1_reprice(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    completion: str,
    now_ms: int,
) -> dict[str, Any] | None:
    projection = loaded["projection"]
    ticket_id = str(projection["ticket_id"])
    existing_commands = _rows_by_value(
        conn,
        COMMAND_TABLE,
        "ticket_id",
        ticket_id,
    )
    reprice_commands = [
        row
        for row in existing_commands
        if str(row.get("command_source") or "")
        == "exit_policy_tp1_reprice"
    ]
    if (
        str(projection.get("state") or "")
        != "blocked_tp1_reprice_required"
        and not reprice_commands
    ):
        return None
    tp1_candidates = [
        row
        for row in loaded["orders"]
        if str(row.get("role") or "") == "TP1"
        and str(row.get("status") or "")
        not in {"replaced", "failed"}
    ]
    if not tp1_candidates:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="tp1_reprice_order_missing",
            now_ms=now_ms,
        )
    old = min(
        tp1_candidates,
        key=lambda row: int(row.get("generation") or 1),
    )
    execution: TicketExitExecutionSnapshot = loaded["execution"]
    source_id = _stable_id(
        "exit-policy-tp1-reprice",
        ticket_id,
        str(loaded["policy"].payload_hash),
        str(execution.resolved_tp1_price),
        str(execution.resolved_tp1_target_qty),
    )
    cancel = _command_by_source_kind(
        conn,
        source_command_id=source_id,
        command_kind="cancel_order",
    )
    if not cancel:
        cancel = _materialize_policy_command(
            conn,
            loaded=loaded,
            command_source="exit_policy_tp1_reprice",
            source_command_id=source_id,
            command_kind="cancel_order",
            order_role="TP1",
            order_type="cancel",
            amount=_required_decimal(old.get("qty"), "tp1_reprice_old_qty"),
            stop_price=None,
            target_exchange_order_id=str(old.get("exchange_order_id") or ""),
            local_order_id=f"{source_id}:cancel-old-tp1",
            parent_order_id=str(old["exit_protection_order_id"]),
            generation=int(old.get("generation") or 1),
            now_ms=now_ms,
        )
        _update_order(
            conn,
            order_id=str(old["exit_protection_order_id"]),
            values={"status": "cancel_pending", "updated_at_ms": now_ms},
        )
        return _result(
            "tp1_reprice_cancel_prepared",
            ticket_id,
            command_id=str(cancel["exchange_command_id"]),
        )
    cancel_state = str(cancel.get("command_state") or "")
    if cancel_state in PENDING_COMMAND_STATES:
        return _result("tp1_reprice_cancel_pending", ticket_id)
    if cancel_state == "outcome_unknown":
        return _result(
            "tp1_reprice_cancel_outcome_unknown",
            ticket_id,
            blockers=["exchange_command_outcome_unknown"],
        )
    if cancel_state in TERMINAL_FAILURE_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker=f"tp1_reprice_cancel_{cancel_state}",
            now_ms=now_ms,
        )
    if cancel_state not in CONFIRMED_COMMAND_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="tp1_reprice_cancel_confirmation_invalid",
            now_ms=now_ms,
        )
    if completion != "unfilled":
        _update_projection(
            conn,
            ticket_id=ticket_id,
            values={
                "state": "execution_bound",
                "first_blocker": None,
                "updated_at_ms": now_ms,
            },
        )
        return _result("tp1_reprice_superseded_by_fill", ticket_id)

    _update_order(
        conn,
        order_id=str(old["exit_protection_order_id"]),
        values={"status": "cancelled", "updated_at_ms": now_ms},
    )
    place = _command_by_source_kind(
        conn,
        source_command_id=source_id,
        command_kind="place_order",
    )
    if not place:
        remaining_qty = _required_decimal(
            projection.get("remaining_position_qty"),
            "tp1_reprice_remaining_qty",
        )
        if remaining_qty < execution.resolved_tp1_target_qty:
            return _block_projection(
                conn,
                projection=projection,
                ticket_id=ticket_id,
                blocker="tp1_reprice_quantity_exceeds_remaining_position",
                now_ms=now_ms,
            )
        place = _materialize_policy_command(
            conn,
            loaded=loaded,
            command_source="exit_policy_tp1_reprice",
            source_command_id=source_id,
            command_kind="place_order",
            order_role="TP1",
            order_type="limit",
            amount=execution.resolved_tp1_target_qty,
            stop_price=None,
            target_exchange_order_id=None,
            local_order_id=f"{source_id}:tp1",
            parent_order_id=str(old["exit_protection_order_id"]),
            generation=int(old.get("generation") or 1) + 1,
            now_ms=now_ms,
            price=execution.resolved_tp1_price,
            execution_style="limit_gtc",
            time_in_force="GTC",
        )
        return _result(
            "tp1_reprice_place_prepared",
            ticket_id,
            command_id=str(place["exchange_command_id"]),
        )
    place_state = str(place.get("command_state") or "")
    if place_state in PENDING_COMMAND_STATES:
        return _result("tp1_reprice_place_pending", ticket_id)
    if place_state == "outcome_unknown":
        return _result(
            "tp1_reprice_place_outcome_unknown",
            ticket_id,
            blockers=["exchange_command_outcome_unknown"],
        )
    if place_state in TERMINAL_FAILURE_STATES:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker=f"tp1_reprice_place_{place_state}",
            now_ms=now_ms,
        )
    if place_state not in CONFIRMED_COMMAND_STATES or not str(
        place.get("exchange_order_id") or ""
    ):
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=ticket_id,
            blocker="tp1_reprice_place_confirmation_invalid",
            now_ms=now_ms,
        )
    new_order = _ensure_tp1_reprice_order(
        conn,
        place=place,
        old=old,
        now_ms=now_ms,
    )
    _update_order(
        conn,
        order_id=str(old["exit_protection_order_id"]),
        values={"status": "replaced", "updated_at_ms": now_ms},
    )
    protection_sets = _table(conn, "brc_ticket_bound_exit_protection_sets")
    conn.execute(
        protection_sets.update()
        .where(
            protection_sets.c.exit_protection_set_id
            == str(old["exit_protection_set_id"])
        )
        .values(tp1_order_id=new_order["exit_protection_order_id"], updated_at_ms=now_ms)
    )
    _update_projection(
        conn,
        ticket_id=ticket_id,
        values={
            "state": "execution_bound",
            "first_blocker": None,
            "updated_at_ms": now_ms,
        },
    )
    return _result("tp1_reprice_completed", ticket_id)


def _prepare_runner_replacement(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    proposed_stop: Decimal,
    amount: Decimal,
    reason: str,
    source_watermark: int,
    now_ms: int,
) -> dict[str, Any]:
    projection = loaded["projection"]
    active = loaded["active_order"]
    scope: TicketBoundExchangeScope = loaded["scope"]
    tick = loaded["instrument_rule"].price_tick
    if proposed_stop <= 0 or proposed_stop % tick != 0:
        return _block_projection(
            conn,
            projection=projection,
            ticket_id=scope.ticket_id,
            blocker="proposed_stop_not_tick_aligned",
            now_ms=now_ms,
        )
    active_stop = _required_decimal(active.get("trigger_price"), "active_runner_stop")
    if reason != "tp1_partial_protection_resize":
        improved = proposed_stop > active_stop if scope.side == "long" else proposed_stop < active_stop
        if not improved:
            return _record_decision(
                conn,
                projection=projection,
                kind="noop",
                reason="runner_stop_not_improved",
                state="runner_protected",
                now_ms=now_ms,
            )
    generation = int(active.get("generation") or 1) + 1
    source_id = _stable_id(
        "exit-policy-runner",
        scope.ticket_id,
        str(loaded["policy"].payload_hash),
        str(source_watermark),
        reason,
        str(generation),
    )
    place = _materialize_policy_command(
        conn,
        loaded=loaded,
        command_source="exit_policy_runner",
        source_command_id=source_id,
        command_kind="place_order",
        order_role="RUNNER_SL",
        order_type="stop_market",
        amount=amount,
        stop_price=proposed_stop,
        target_exchange_order_id=None,
        local_order_id=f"{source_id}:runner",
        parent_order_id=str(active["exit_protection_order_id"]),
        generation=generation,
        now_ms=now_ms,
    )
    _update_projection(
        conn,
        ticket_id=scope.ticket_id,
        values={
            "pending_runner_order_id": place["exchange_command_id"],
            "pending_generation": generation,
            "replaced_runner_order_id": active["exit_protection_order_id"],
            "last_decision_kind": "move_runner_stop",
            "last_reason_code": reason,
            "state": "runner_replacement_pending",
            "first_blocker": None,
            "updated_at_ms": now_ms,
        },
    )
    return _result(
        "runner_replacement_prepared",
        scope.ticket_id,
        command_id=str(place["exchange_command_id"]),
    )


def _prepare_runner_close(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    decision: ExitDecision,
    now_ms: int,
) -> dict[str, Any]:
    scope: TicketBoundExchangeScope = loaded["scope"]
    projection = loaded["projection"]
    qty = _required_decimal(decision.close_qty, "runner_close_quantity")
    source_id = _stable_id(
        "exit-policy-close",
        scope.ticket_id,
        str(loaded["policy"].payload_hash),
        str(decision.source_watermark_ms),
        decision.reason_code,
    )
    command = _materialize_policy_command(
        conn,
        loaded=loaded,
        command_source="exit_policy_close",
        source_command_id=source_id,
        command_kind="place_order",
        order_role="RUNNER_SL",
        order_type="market",
        amount=qty,
        stop_price=None,
        target_exchange_order_id=None,
        local_order_id=f"{source_id}:close",
        parent_order_id=str(loaded["active_order"]["exit_protection_order_id"]),
        generation=int(loaded["active_order"].get("generation") or 1),
        now_ms=now_ms,
    )
    _update_projection(
        conn,
        ticket_id=scope.ticket_id,
        values={
            "last_decision_kind": "close_runner",
            "last_reason_code": decision.reason_code,
            "state": "runner_close_pending",
            "first_blocker": None,
            "updated_at_ms": now_ms,
        },
    )
    return _result(
        "runner_close_prepared",
        scope.ticket_id,
        command_id=str(command["exchange_command_id"]),
    )


def _existing_close_state(
    conn: sa.engine.Connection,
    *,
    projection: dict[str, Any],
) -> dict[str, Any] | None:
    if str(projection.get("state") or "") != "runner_close_pending":
        return None
    commands = _rows_by_value(
        conn, COMMAND_TABLE, "ticket_id", str(projection["ticket_id"])
    )
    close = next(
        (row for row in commands if row.get("command_source") == "exit_policy_close"),
        None,
    )
    if close is None:
        return _result(
            "runner_close_command_missing",
            str(projection["ticket_id"]),
            blockers=["runner_close_command_missing"],
        )
    state = str(close.get("command_state") or "")
    if state == "outcome_unknown":
        return _result(
            "runner_close_outcome_unknown",
            str(projection["ticket_id"]),
            blockers=["exchange_command_outcome_unknown"],
        )
    if state in TERMINAL_FAILURE_STATES:
        return _result(
            f"runner_close_{state}",
            str(projection["ticket_id"]),
            blockers=[f"runner_close_{state}"],
        )
    return _result("runner_close_pending", str(projection["ticket_id"]))


def _materialize_policy_command(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    command_source: str,
    source_command_id: str,
    command_kind: str,
    order_role: str,
    order_type: str,
    amount: Decimal,
    stop_price: Decimal | None,
    target_exchange_order_id: str | None,
    local_order_id: str,
    parent_order_id: str,
    generation: int,
    now_ms: int,
    price: Decimal | None = None,
    execution_style: str | None = None,
    time_in_force: str | None = None,
    post_only: bool = False,
) -> dict[str, Any]:
    scope: TicketBoundExchangeScope = loaded["scope"]
    attempt = loaded["attempt"]
    gateway_side = "sell" if scope.side == "long" else "buy"
    command_id = _stable_id(
        "ticket-exchange-command",
        command_source,
        source_command_id,
        command_kind,
        order_role,
        str(generation),
    )
    client_order_id = deterministic_client_order_id(
        scope.ticket_id,
        source_command_id,
        f"{command_kind}:{order_role}",
        generation,
    )
    fingerprint_payload = {
        "command_source": command_source,
        "source_command_id": source_command_id,
        "command_kind": command_kind,
        "order_role": order_role,
        "account_id": scope.account_id,
        "exchange_instrument_id": scope.exchange_instrument_id,
        "position_bucket": scope.position_bucket,
        "gateway_side": gateway_side,
        "amount": str(amount),
        "price": str(price) if price is not None else None,
        "stop_price": str(stop_price) if stop_price is not None else None,
        "target_exchange_order_id": target_exchange_order_id,
        "policy_hash": loaded["policy"].payload_hash,
        "generation": generation,
    }
    fingerprint = "sha256:" + sha256(
        json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    command = TicketBoundExchangeCommand(
        exchange_command_id=command_id,
        protected_submit_attempt_id=str(attempt["protected_submit_attempt_id"]),
        ticket_id=scope.ticket_id,
        operation_submit_command_id=str(attempt["operation_submit_command_id"]),
        account_id=scope.account_id,
        strategy_group_id=scope.strategy_group_id,
        runtime_profile_id=scope.runtime_profile_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        exchange_id=scope.exchange_id,
        gateway_symbol=scope.exchange_symbol,
        symbol=scope.canonical_symbol,
        order_role=order_role,
        side=scope.side,
        gateway_side=gateway_side,
        local_order_id=local_order_id,
        parent_order_id=parent_order_id,
        client_order_id=client_order_id,
        command_generation=generation,
        request_fingerprint=fingerprint,
        order_type=order_type,
        execution_style=execution_style,
        time_in_force=time_in_force,
        post_only=post_only,
        market_fallback_allowed=False,
        amount=amount,
        price=price,
        stop_price=stop_price,
        reduce_only=True,
        reduce_intent="reduce_position",
        position_mode=scope.position_mode,
        position_side=scope.position_side,
        position_bucket=scope.position_bucket,
        netting_domain_key=scope.netting_domain_key,
        command_kind=command_kind,
        command_source=command_source,
        source_command_id=source_command_id,
        target_exchange_order_id=target_exchange_order_id,
        authority_source_ref=(
            f"ticket-exit-policy:{loaded['policy'].payload_hash}:"
            f"{source_command_id}"
        )[:256],
        command_state=ExchangeCommandState.PREPARED,
        outcome_class=ExchangeCommandOutcomeClass.PENDING,
        prepared_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    row = command.model_dump(mode="json")
    table = _table(conn, COMMAND_TABLE)
    existing = conn.execute(
        sa.select(table).where(table.c.exchange_command_id == command_id)
    ).mappings().first()
    if existing:
        if str(existing.get("request_fingerprint") or "") != fingerprint:
            raise ValueError("exit_policy_command_fingerprint_mismatch")
        return dict(existing)
    conn.execute(table.insert().values(**row))
    return row


def _ensure_tp1_reprice_order(
    conn: sa.engine.Connection,
    *,
    place: dict[str, Any],
    old: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    existing = conn.execute(
        sa.select(table).where(table.c.local_order_id == place["local_order_id"])
    ).mappings().first()
    if existing:
        if (
            str(existing.get("exchange_order_id") or "")
            != str(place.get("exchange_order_id") or "")
            or int(existing.get("generation") or 0)
            != int(place.get("command_generation") or 0)
        ):
            raise ValueError("tp1_reprice_order_identity_contradiction")
        return dict(existing)
    row = {
        "exit_protection_order_id": _stable_id(
            "ticket-exit-protection-order", str(place["exchange_command_id"])
        ),
        "exit_protection_set_id": str(old["exit_protection_set_id"]),
        "ticket_id": str(old["ticket_id"]),
        "role": "TP1",
        "local_order_id": str(place["local_order_id"]),
        "exchange_order_id": str(place["exchange_order_id"]),
        "status": "submitted",
        "order_type": "LIMIT",
        "side": str(place["gateway_side"]),
        "qty": _required_decimal(place["amount"], "tp1_reprice_amount"),
        "price": _required_decimal(place["price"], "tp1_reprice_price"),
        "trigger_price": None,
        "reduce_only": True,
        "replaces_exit_protection_order_id": str(old["exit_protection_order_id"]),
        "generation": int(place["command_generation"]),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    conn.execute(table.insert().values(**row))
    return row


def _ensure_pending_protection_order(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    place: dict[str, Any],
    old: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    existing = conn.execute(
        sa.select(table).where(table.c.local_order_id == place["local_order_id"])
    ).mappings().first()
    if existing:
        if (
            str(existing.get("exchange_order_id") or "")
            != str(place.get("exchange_order_id") or "")
            or int(existing.get("generation") or 0)
            != int(place.get("command_generation") or 0)
        ):
            raise ValueError("pending_runner_protection_identity_contradiction")
        return dict(existing)
    row = {
        "exit_protection_order_id": _stable_id(
            "ticket-exit-protection-order", str(place["exchange_command_id"])
        ),
        "exit_protection_set_id": str(old["exit_protection_set_id"]),
        "ticket_id": str(old["ticket_id"]),
        "role": "RUNNER_SL",
        "local_order_id": str(place["local_order_id"]),
        "exchange_order_id": str(place["exchange_order_id"]),
        "status": "submitted",
        "order_type": "stop_market",
        "side": str(place["gateway_side"]),
        "qty": _required_decimal(place["amount"], "runner_amount"),
        "price": None,
        "trigger_price": _required_decimal(place["stop_price"], "runner_stop"),
        "reduce_only": True,
        "replaces_exit_protection_order_id": str(old["exit_protection_order_id"]),
        "generation": int(place["command_generation"]),
        "created_at_ms": now_ms,
        "updated_at_ms": now_ms,
    }
    conn.execute(table.insert().values(**row))
    return row


def _load_latest_exit_market_fact(
    conn: sa.engine.Connection,
    *,
    loaded: dict[str, Any],
    now_ms: int,
) -> tuple[ExitMarketFact | None, str | None]:
    projection = loaded["projection"]
    fact_id = str(projection.get("last_reason_code") or "")
    watermark = projection.get("last_evaluated_watermark_ms")
    if not fact_id.startswith("fact_ticket_exit_market:") and not fact_id.startswith(
        "fact-exit-"
    ):
        return None, None
    fact = _row_by_id(
        conn, "brc_runtime_fact_snapshots", "fact_snapshot_id", fact_id
    )
    if not fact:
        return None, "ticket_exit_market_fact_missing"
    if int(fact.get("valid_until_ms") or 0) <= now_ms:
        return None, "ticket_exit_market_fact_stale"
    values = _mapping(fact.get("fact_values"))
    if (
        str(values.get("ticket_id") or "") != str(projection["ticket_id"])
        or int(values.get("watermark_ms") or 0) != int(watermark or 0)
    ):
        return None, "ticket_exit_market_fact_identity_mismatch"
    try:
        candles = [ClosedCandle.model_validate(item) for item in values.get("candles", [])]
    except Exception:
        return None, "ticket_exit_market_candles_invalid"
    if not candles:
        return None, "ticket_exit_market_candles_missing"
    policy: TicketExitPolicySnapshot = loaded["policy"]
    missing_reference_keys = {
        rule.reference_key for rule in policy.invalidation_rules
    } - set(_mapping(values.get("references")))
    explicit_hits = tuple(str(item) for item in values.get("invalidation_rule_ids_hit", []))
    if missing_reference_keys and not explicit_hits:
        return None, f"ticket_exit_reference_fact_missing:{sorted(missing_reference_keys)[0]}"
    market_fact = _derive_exit_market_fact(
        policy=policy,
        side=loaded["scope"].side,
        candles=candles,
        references=_mapping(values.get("references")),
        explicit_invalidation_hits=explicit_hits,
        entry_time_ms=_entry_fill_time_ms(conn, loaded["lifecycle"]),
        minimum_price_tick=loaded["instrument_rule"].price_tick,
    )
    return market_fact, None


def _derive_exit_market_fact(
    *,
    policy: TicketExitPolicySnapshot,
    side: str,
    candles: list[ClosedCandle],
    references: dict[str, Any],
    explicit_invalidation_hits: tuple[str, ...],
    entry_time_ms: int,
    minimum_price_tick: Decimal,
) -> ExitMarketFact:
    latest = candles[-1]
    hits = set(explicit_invalidation_hits)
    for rule in policy.invalidation_rules:
        reference = _decimal_or_none(references.get(rule.reference_key))
        if reference is None:
            continue
        if rule.trigger == "close_below_or_equal" and latest.close <= reference:
            hits.add(rule.rule_id)
        if rule.trigger == "close_above_or_equal" and latest.close >= reference:
            hits.add(rule.rule_id)
    structural: Decimal | None = None
    reference_candidate: Decimal | None = None
    if isinstance(policy.runner_rule, StructuralAtrRunnerRule):
        rule = policy.runner_rule
        atr = _average_true_range(candles, period=rule.atr_period)
        window = candles[-rule.structure_window_bars :]
        if atr is not None and len(window) == rule.structure_window_bars:
            raw = (
                min(item.low for item in window) - atr * rule.atr_buffer_multiple
                if side == "long"
                else max(item.high for item in window) + atr * rule.atr_buffer_multiple
            )
            structural = _round_price(
                raw,
                minimum_price_tick,
                rounding=ROUND_FLOOR if side == "long" else ROUND_CEILING,
            )
    elif isinstance(policy.runner_rule, ReferenceTrailRunnerRule):
        reference = _decimal_or_none(references.get(policy.runner_rule.reference_key))
        if reference is not None:
            offset = minimum_price_tick * policy.runner_rule.buffer_ticks
            reference_candidate = _round_price(
                reference - offset if side == "long" else reference + offset,
                minimum_price_tick,
                rounding=ROUND_FLOOR if side == "long" else ROUND_CEILING,
            )
    interval = TIMEFRAME_MS[getattr(policy.runner_rule, "timeframe")]
    holding_bars = max(0, (latest.close_time_ms - entry_time_ms) // interval)
    return ExitMarketFact(
        watermark_ms=latest.close_time_ms,
        is_final_closed_candle=latest.is_final_closed_candle,
        close_price=latest.close,
        holding_bars=int(holding_bars),
        invalidation_rule_ids_hit=tuple(sorted(hits)),
        structural_stop_candidate=structural,
        reference_stop_candidate=reference_candidate,
    )


def _average_true_range(
    candles: list[ClosedCandle],
    *,
    period: int,
) -> Decimal | None:
    if period < 1 or len(candles) < period + 1:
        return None
    true_ranges: list[Decimal] = []
    for previous, current in zip(candles[-period - 1 : -1], candles[-period:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return sum(true_ranges, Decimal("0")) / Decimal(period)


def _entry_fill_time_ms(conn: sa.engine.Connection, lifecycle: dict[str, Any]) -> int:
    events = _rows_by_value(
        conn,
        "brc_ticket_bound_lifecycle_events",
        "lifecycle_run_id",
        str(lifecycle["lifecycle_run_id"]),
    )
    candidates: list[int] = []
    for event in events:
        if str(event.get("event_type") or "") != "entry_filled":
            continue
        fill = _mapping(_mapping(event.get("event_payload")).get("fill"))
        candidates.append(int(fill.get("fill_time_ms") or event.get("created_at_ms") or 0))
    return min(candidates) if candidates else int(lifecycle.get("created_at_ms") or 0)


def _record_decision(
    conn: sa.engine.Connection,
    *,
    projection: dict[str, Any],
    kind: str,
    reason: str,
    state: str,
    now_ms: int,
) -> dict[str, Any]:
    _update_projection(
        conn,
        ticket_id=str(projection["ticket_id"]),
        values={
            "last_decision_kind": kind,
            "last_reason_code": reason,
            "state": state,
            "first_blocker": None,
            "updated_at_ms": now_ms,
        },
    )
    return _result(reason, str(projection["ticket_id"]))


def _block_projection(
    conn: sa.engine.Connection,
    *,
    projection: dict[str, Any],
    ticket_id: str,
    blocker: str,
    now_ms: int,
) -> dict[str, Any]:
    if projection:
        _update_projection(
            conn,
            ticket_id=ticket_id,
            values={
                "last_decision_kind": "blocked",
                "last_reason_code": blocker,
                "first_blocker": blocker,
                "updated_at_ms": now_ms,
            },
        )
    return _result("exit_policy_blocked", ticket_id, blockers=[blocker])


def _capability_enabled(conn: sa.engine.Connection) -> bool:
    if not sa.inspect(conn).has_table("brc_runtime_capabilities_current"):
        return False
    row = _row_by_id(
        conn,
        "brc_runtime_capabilities_current",
        "capability_id",
        CAPABILITY_ID,
    )
    return str(row.get("status") or "") == "enabled"


def _fill_watermark(projection: dict[str, Any]) -> int:
    quantity = str(projection.get("tp1_cumulative_filled_qty") or "0")
    digest = sha256(quantity.encode("utf-8")).hexdigest()[:12]
    return int(digest, 16)


def _command_by_source_kind(
    conn: sa.engine.Connection,
    *,
    source_command_id: str,
    command_kind: str,
) -> dict[str, Any]:
    table = _table(conn, COMMAND_TABLE)
    row = conn.execute(
        sa.select(table).where(
            table.c.source_command_id == source_command_id,
            table.c.command_kind == command_kind,
        )
    ).mappings().first()
    return dict(row) if row else {}


def _update_projection(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    values: dict[str, Any],
) -> None:
    table = _table(conn, "brc_ticket_exit_policy_current")
    updated = conn.execute(
        table.update().where(table.c.ticket_id == ticket_id).values(**values)
    )
    if updated.rowcount != 1:
        raise ValueError("ticket_exit_policy_projection_missing")


def _update_order(
    conn: sa.engine.Connection,
    *,
    order_id: str,
    values: dict[str, Any],
) -> None:
    table = _table(conn, "brc_ticket_bound_exit_protection_orders")
    updated = conn.execute(
        table.update()
        .where(table.c.exit_protection_order_id == order_id)
        .values(**values)
    )
    if updated.rowcount != 1:
        raise ValueError("ticket_exit_protection_order_missing")


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value or not sa.inspect(conn).has_table(table_name):
        return {}
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _rows_by_value(
    conn: sa.engine.Connection,
    table_name: str,
    column: str,
    value: str,
) -> list[dict[str, Any]]:
    if not value or not sa.inspect(conn).has_table(table_name):
        return []
    table = _table(conn, table_name)
    return [
        dict(row)
        for row in conn.execute(
            sa.select(table).where(table.c[column] == value)
        ).mappings()
    ]


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _required_decimal(value: Any, field: str) -> Decimal:
    parsed = _decimal_or_none(value)
    if parsed is None or parsed <= 0:
        raise ValueError(f"{field}_invalid")
    return parsed


def _round_price(value: Decimal, tick: Decimal, *, rounding: str) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"


def _result(
    status: str,
    ticket_id: str,
    *,
    blockers: list[str] | None = None,
    command_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "brc.ticket_exit_policy_maintenance.v1",
        "status": status,
        "ticket_id": ticket_id,
        "blockers": list(blockers or []),
        "exchange_write_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    if command_id:
        payload["exchange_command_id"] = command_id
    return payload
