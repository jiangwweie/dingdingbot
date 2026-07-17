"""Evaluate and append one exact active-Ticket exit-policy adoption."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

import sqlalchemy as sa

from src.application.action_time.ticket_exit_execution_binding import (
    build_ticket_exit_execution_snapshot,
)
from src.domain.ticket_exit_policy import TicketExitPolicySnapshot
from src.domain.ticket_exit_policy_adoption import (
    TicketExitPolicyAdoptionEligibilityResult,
    TicketExitPolicyAdoptionEligibilitySnapshot,
    canonical_eligibility_hash,
    evaluate_ticket_exit_policy_adoption_snapshot,
)
from src.application.action_time.ticket_instrument_rule import (
    TicketInstrumentRuleError,
    resolve_ticket_instrument_rule,
)


UNSAFE_COMMAND_STATES = {"prepared", "dispatching", "outcome_unknown"}


class TicketExitPolicyAdoptionError(ValueError):
    """Raised before any write when adoption authority is contradictory."""


def evaluate_ticket_exit_policy_adoption_eligibility(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    exchange_snapshot: dict[str, Any],
    owner_authorization_ref: str,
    runtime_head: str,
    now_ms: int,
) -> TicketExitPolicyAdoptionEligibilityResult:
    """Assemble exact PG/exchange facts into one canonical eligibility result."""

    _require_tables(conn)
    ticket = _one_by_id(conn, "brc_action_time_tickets", "ticket_id", ticket_id)
    if not ticket:
        raise TicketExitPolicyAdoptionError("adoption_ticket_missing")
    policies = _table(conn, "brc_strategy_exit_policies")
    policy_rows = list(
        conn.execute(
            sa.select(policies).where(
                policies.c.strategy_group_id == ticket["strategy_group_id"],
                policies.c.strategy_version
                == ticket["strategy_group_version_id"],
                policies.c.event_spec_id == ticket["event_spec_id"],
                policies.c.side == ticket["side"],
                policies.c.status == "current",
            )
        ).mappings()
    )
    if len(policy_rows) != 1:
        raise TicketExitPolicyAdoptionError(
            "adoption_current_policy_missing"
            if not policy_rows
            else "adoption_multiple_current_policies"
        )
    policy = dict(policy_rows[0])
    policy_payload = _mapping(policy.get("policy_payload"))
    policy_snapshot = TicketExitPolicySnapshot.model_validate(policy_payload)
    if policy_snapshot.payload_hash != str(policy.get("payload_hash") or ""):
        raise TicketExitPolicyAdoptionError("adoption_policy_hash_contradiction")

    lifecycles = _table(conn, "brc_ticket_bound_order_lifecycle_runs")
    lifecycle_rows = list(
        conn.execute(
            sa.select(lifecycles).where(lifecycles.c.ticket_id == ticket_id)
        ).mappings()
    )
    if len(lifecycle_rows) != 1:
        raise TicketExitPolicyAdoptionError("adoption_active_lifecycle_not_unique")
    lifecycle = dict(lifecycle_rows[0])
    protection_set = _one_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        str(lifecycle.get("exit_protection_set_id") or ""),
    )
    if not protection_set:
        raise TicketExitPolicyAdoptionError("adoption_protection_set_missing")
    protection_orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    order_rows = [
        dict(row)
        for row in conn.execute(
            sa.select(protection_orders).where(
                protection_orders.c.exit_protection_set_id
                == protection_set["exit_protection_set_id"]
            )
        ).mappings()
    ]
    sl = _one_role(order_rows, "SL")
    tp1 = _one_role(order_rows, "TP1")
    if not sl or not tp1:
        raise TicketExitPolicyAdoptionError("adoption_protection_orders_missing")

    instrument = _one_by_id(
        conn,
        "brc_exchange_instruments",
        "exchange_instrument_id",
        str(ticket.get("exchange_instrument_id") or ""),
    )
    if not instrument:
        raise TicketExitPolicyAdoptionError("adoption_exchange_instrument_missing")
    try:
        instrument_rule = resolve_ticket_instrument_rule(
            instrument=instrument,
            exchange_snapshot=exchange_snapshot,
        )
    except TicketInstrumentRuleError as exc:
        raise TicketExitPolicyAdoptionError(f"adoption_{exc}") from exc
    price_tick = instrument_rule.price_tick
    quantity_step = instrument_rule.quantity_step

    live_orders = {
        str(item.get("exchange_order_id") or ""): item
        for item in exchange_snapshot.get("open_orders", [])
        if isinstance(item, dict)
    }
    live_sl = live_orders.get(str(sl.get("exchange_order_id") or ""), {})
    live_tp1 = live_orders.get(str(tp1.get("exchange_order_id") or ""), {})
    position = _mapping(exchange_snapshot.get("position"))
    recent_fills = [
        item
        for item in exchange_snapshot.get("recent_fills", [])
        if isinstance(item, dict)
    ]
    entry_fills = [
        item
        for item in recent_fills
        if str(item.get("exchange_order_id") or "")
        == str(protection_set.get("entry_exchange_order_id") or "")
    ]
    entry_fee_amount, entry_fee_asset = _entry_fee_truth(entry_fills)
    tp1_filled_qty = sum(
        (
            _required_decimal(item.get("qty"), "tp1_fill_qty")
            for item in recent_fills
            if str(item.get("exchange_order_id") or "")
            == str(tp1.get("exchange_order_id") or "")
        ),
        Decimal("0"),
    )
    commission_rate = _mapping(exchange_snapshot.get("commission_rate"))
    taker_rate = _required_decimal(
        commission_rate.get("taker_commission_rate"),
        "certified_exit_taker_fee_rate",
    )
    commands = _table(conn, "brc_ticket_bound_exchange_commands")
    unsafe_command_count = int(
        conn.execute(
            sa.select(sa.func.count())
            .select_from(commands)
            .where(
                commands.c.ticket_id == ticket_id,
                commands.c.command_state.in_(UNSAFE_COMMAND_STATES),
            )
        ).scalar_one()
    )
    position_mode = str(exchange_snapshot.get("position_mode") or "")
    expected_position_side = str(
        exchange_snapshot.get("position_side")
        or (str(ticket["side"]).upper() if position_mode == "hedge" else "BOTH")
    ).upper()
    protection_state = (
        "complete_reconciled"
        if bool(protection_set.get("protection_complete"))
        and bool(protection_set.get("reconciled_with_exchange"))
        and live_sl
        and (live_tp1 or str(tp1.get("status") or "") == "filled")
        else "missing"
    )
    event_spec_version = str(policy.get("event_spec_version") or "")
    ticket_event_spec_version_id = str(ticket.get("event_spec_version_id") or "")
    if ticket_event_spec_version_id != f"{ticket['event_spec_id']}:{event_spec_version}":
        event_spec_version = ticket_event_spec_version_id.rsplit(":", 1)[-1]

    snapshot = TicketExitPolicyAdoptionEligibilitySnapshot(
        ticket_id=ticket_id,
        ticket_created_at_ms=int(ticket.get("created_at_ms") or 0),
        ticket_exit_policy_id=str(ticket.get("exit_policy_id") or ""),
        ticket_exit_policy_version=str(ticket.get("exit_policy_version") or ""),
        ticket_exit_policy_hash=str(ticket.get("exit_policy_hash") or ""),
        ticket_status=str(ticket.get("status") or ""),
        lifecycle_state=str(lifecycle.get("status") or ""),
        ticket_strategy_group_id=str(ticket.get("strategy_group_id") or ""),
        ticket_strategy_version=str(
            ticket.get("strategy_group_version_id") or ""
        ),
        ticket_event_spec_id=str(ticket.get("event_spec_id") or ""),
        ticket_event_spec_version=event_spec_version,
        ticket_side=str(ticket.get("side") or ""),
        to_exit_policy_id=str(policy.get("exit_policy_id") or ""),
        to_exit_policy_version=str(policy.get("exit_policy_version") or ""),
        to_exit_policy_hash=str(policy.get("payload_hash") or ""),
        policy_status=str(policy.get("status") or ""),
        policy_approved_at_ms=int(policy.get("approved_at_ms") or 0),
        policy_strategy_group_id=str(policy.get("strategy_group_id") or ""),
        policy_strategy_version=str(policy.get("strategy_version") or ""),
        policy_event_spec_id=str(policy.get("event_spec_id") or ""),
        policy_event_spec_version=str(policy.get("event_spec_version") or ""),
        policy_side=str(policy.get("side") or ""),
        owner_authorization_ref=str(owner_authorization_ref or ""),
        owner_authorization_ticket_id=(
            ticket_id if ticket_id in str(owner_authorization_ref or "") else None
        ),
        runtime_head=str(runtime_head or ""),
        migration_revision=125,
        account_id=str(exchange_snapshot.get("account_id") or ""),
        exchange_id=str(exchange_snapshot.get("exchange_id") or ""),
        exchange_instrument_id=str(
            exchange_snapshot.get("exchange_instrument_id") or ""
        ),
        position_mode=position_mode,
        position_side=expected_position_side,
        pg_position_qty=_required_decimal(
            protection_set.get("entry_filled_qty"), "pg_position_qty"
        ),
        exchange_position_qty=_required_decimal(
            position.get("qty"), "exchange_position_qty"
        ),
        entry_avg_fill_price=_required_decimal(
            protection_set.get("entry_avg_price"), "entry_avg_fill_price"
        ),
        minimum_price_tick=price_tick,
        quantity_step=quantity_step,
        entry_fee_amount=entry_fee_amount,
        entry_fee_asset=entry_fee_asset,
        quote_asset=entry_fee_asset,
        fee_asset_quote_conversion_rate=None,
        certified_exit_taker_fee_rate=taker_rate,
        exit_protection_set_id=str(protection_set["exit_protection_set_id"]),
        protection_state=protection_state,
        sl_order_id=str(sl.get("exchange_order_id") or ""),
        sl_order_type=str(sl.get("order_type") or ""),
        sl_qty=_required_decimal(live_sl.get("qty", sl.get("qty")), "sl_qty"),
        sl_trigger_price=_required_decimal(
            live_sl.get("trigger_price", sl.get("trigger_price")),
            "sl_trigger_price",
        ),
        sl_reduce_only=bool(live_sl.get("reduce_only", sl.get("reduce_only"))),
        sl_side=str(live_sl.get("side", sl.get("side")) or ""),
        sl_position_side=str(
            live_sl.get("position_side") or expected_position_side
        ).upper(),
        tp1_order_id=str(tp1.get("exchange_order_id") or ""),
        tp1_order_type=str(tp1.get("order_type") or ""),
        tp1_qty=_required_decimal(live_tp1.get("qty", tp1.get("qty")), "tp1_qty"),
        tp1_price=_required_decimal(
            live_tp1.get("price", tp1.get("price")), "tp1_price"
        ),
        tp1_filled_qty=tp1_filled_qty,
        tp1_reduce_only=bool(
            live_tp1.get("reduce_only", tp1.get("reduce_only"))
        ),
        tp1_market_fallback_allowed=False,
        tp1_side=str(live_tp1.get("side", tp1.get("side")) or ""),
        tp1_position_side=str(
            live_tp1.get("position_side") or expected_position_side
        ).upper(),
        unsafe_command_count=unsafe_command_count,
        evaluated_at_ms=int(now_ms),
    )
    return evaluate_ticket_exit_policy_adoption_snapshot(snapshot)


def apply_ticket_exit_policy_adoption(
    conn: sa.engine.Connection,
    *,
    eligibility: TicketExitPolicyAdoptionEligibilityResult,
    expected_eligibility_hash: str,
    now_ms: int,
) -> dict[str, Any]:
    """Append the accepted event and initialize its current projection by CAS."""

    if eligibility.status != "eligible":
        raise TicketExitPolicyAdoptionError("adoption_not_eligible")
    actual_hash = canonical_eligibility_hash(eligibility.snapshot)
    if (
        actual_hash != eligibility.eligibility_hash
        or actual_hash != str(expected_eligibility_hash or "")
    ):
        raise TicketExitPolicyAdoptionError("adoption_eligibility_hash_mismatch")
    snapshot = eligibility.snapshot
    events = _table(conn, "brc_ticket_exit_policy_adoption_events")
    projection = _table(conn, "brc_ticket_exit_policy_current")
    event_id = _adoption_event_id(snapshot.ticket_id, actual_hash)
    ticket = _lock_ticket(conn, ticket_id=snapshot.ticket_id)
    if not ticket or (
        str(ticket.get("exit_policy_hash") or "")
        != snapshot.ticket_exit_policy_hash
    ):
        raise TicketExitPolicyAdoptionError("adoption_ticket_cas_changed")
    existing_events = list(
        conn.execute(
            sa.select(events).where(events.c.ticket_id == snapshot.ticket_id)
        ).mappings()
    )
    effective = _effective_accepted_events(existing_events)
    if effective:
        active = effective[0]
        if (
            str(active.get("adoption_event_id") or "") == event_id
            and str(active.get("eligibility_hash") or "") == actual_hash
        ):
            projected = conn.execute(
                sa.select(projection).where(
                    projection.c.ticket_id == snapshot.ticket_id,
                    projection.c.adoption_event_id == event_id,
                    projection.c.exit_policy_hash == snapshot.to_exit_policy_hash,
                )
            ).mappings().first()
            if projected is None or not _projection_mutation_allowed(dict(projected)):
                raise TicketExitPolicyAdoptionError(
                    "adoption_idempotent_projection_missing"
                )
            return {
                "status": "adoption_idempotent",
                "ticket_id": snapshot.ticket_id,
                "adoption_event_id": event_id,
                "exchange_write_called": False,
            }
        raise TicketExitPolicyAdoptionError("adoption_effective_acceptance_exists")
    policies = _table(conn, "brc_strategy_exit_policies")
    policy_row = conn.execute(
        sa.select(policies).where(
            policies.c.exit_policy_id == snapshot.to_exit_policy_id,
            policies.c.exit_policy_version == snapshot.to_exit_policy_version,
            policies.c.payload_hash == snapshot.to_exit_policy_hash,
            policies.c.status == "current",
        )
    ).mappings().first()
    if policy_row is None:
        raise TicketExitPolicyAdoptionError("adoption_policy_cas_changed")
    policy = TicketExitPolicySnapshot.model_validate(
        _mapping(policy_row.get("policy_payload"))
    )
    execution = build_ticket_exit_execution_snapshot(
        ticket_id=snapshot.ticket_id,
        policy=policy,
        side=snapshot.ticket_side,
        entry_avg_fill_price=snapshot.entry_avg_fill_price,
        entry_filled_qty=snapshot.pg_position_qty,
        initial_stop_price=snapshot.sl_trigger_price,
        minimum_price_tick=snapshot.minimum_price_tick,
        quantity_step=snapshot.quantity_step,
        entry_fee_amount=snapshot.entry_fee_amount,
        entry_fee_asset=snapshot.entry_fee_asset,
        quote_asset=snapshot.quote_asset,
        fee_asset_quote_conversion_rate=snapshot.fee_asset_quote_conversion_rate,
        certified_exit_taker_fee_rate=snapshot.certified_exit_taker_fee_rate,
    )
    completion_state = _tp1_completion_state(
        snapshot.tp1_filled_qty,
        execution.resolved_tp1_target_qty,
        snapshot.quantity_step,
    )
    price_difference = abs(snapshot.tp1_price - execution.resolved_tp1_price)
    projection_state = "execution_bound"
    first_blocker = None
    if completion_state == "unfilled" and price_difference > snapshot.minimum_price_tick:
        projection_state = "blocked_tp1_reprice_required"
        first_blocker = "tp1_reprice_required"

    conn.execute(
        events.insert().values(
            adoption_event_id=event_id,
            ticket_id=snapshot.ticket_id,
            from_exit_policy_hash=snapshot.ticket_exit_policy_hash,
            to_exit_policy_id=snapshot.to_exit_policy_id,
            to_exit_policy_version=snapshot.to_exit_policy_version,
            to_exit_policy_hash=snapshot.to_exit_policy_hash,
            owner_authorization_ref=snapshot.owner_authorization_ref,
            eligibility_snapshot=snapshot.model_dump(mode="json", by_alias=True),
            eligibility_hash=actual_hash,
            decision="accepted",
            runtime_head=snapshot.runtime_head,
            supersedes_adoption_event_id=None,
            created_at_ms=int(now_ms),
        )
    )
    existing_projection = conn.execute(
        sa.select(projection).where(projection.c.ticket_id == snapshot.ticket_id)
    ).mappings().first()
    protection_orders = _table(conn, "brc_ticket_bound_exit_protection_orders")
    active_sl = conn.execute(
        sa.select(protection_orders).where(
            protection_orders.c.exit_protection_set_id
            == snapshot.exit_protection_set_id,
            protection_orders.c.exchange_order_id == snapshot.sl_order_id,
        )
    ).mappings().first()
    projection_values = {
        "ticket_id": snapshot.ticket_id,
        "exit_protection_set_id": snapshot.exit_protection_set_id,
        "exit_policy_id": snapshot.to_exit_policy_id,
        "exit_policy_version": snapshot.to_exit_policy_version,
        "exit_policy_hash": snapshot.to_exit_policy_hash,
        "exit_execution_snapshot": execution.model_dump(mode="json"),
        "exit_execution_hash": execution.payload_hash,
        "actual_r_per_unit": execution.actual_r_per_unit,
        "resolved_tp1_price": execution.resolved_tp1_price,
        "resolved_tp1_target_qty": execution.resolved_tp1_target_qty,
        "tp1_cumulative_filled_qty": snapshot.tp1_filled_qty,
        "tp1_completion_state": completion_state,
        "remaining_position_qty": snapshot.exchange_position_qty,
        "state": projection_state,
        "first_blocker": first_blocker,
        "binding_source": "adoption_event",
        "adoption_event_id": event_id,
        "adoption_state": "accepted",
        "mutation_allowed": True,
        "adoption_projection_version": (
            _projection_version(existing_projection) + 1
            if existing_projection is not None
            else 1
        ),
        "updated_at_ms": int(now_ms),
    }
    if active_sl is not None:
        projection_values.update(
            {
                "active_runner_order_id": active_sl.get(
                    "exit_protection_order_id"
                ),
                "active_runner_generation": active_sl.get("generation") or 1,
                "active_runner_stop": active_sl.get("trigger_price"),
            }
        )
    supported_values = {
        key: value
        for key, value in projection_values.items()
        if key in projection.c
    }
    if existing_projection is None:
        conn.execute(projection.insert().values(**supported_values))
    else:
        expected_event_id = str(existing_projection.get("adoption_event_id") or "")
        expected_version = _projection_version(existing_projection)
        if not expected_event_id or not _projection_is_revoked(dict(existing_projection)):
            raise TicketExitPolicyAdoptionError("adoption_projection_replace_not_revoked")
        predicate = [
            projection.c.ticket_id == snapshot.ticket_id,
            projection.c.adoption_event_id == expected_event_id,
        ]
        if "adoption_state" in projection.c:
            predicate.append(projection.c.adoption_state == "revoked")
        if "adoption_projection_version" in projection.c:
            predicate.append(
                projection.c.adoption_projection_version == expected_version
            )
        result = conn.execute(
            projection.update().where(*predicate).values(**supported_values)
        )
        if result.rowcount != 1:
            raise TicketExitPolicyAdoptionError("adoption_projection_cas_changed")
    return {
        "status": "adoption_applied",
        "ticket_id": snapshot.ticket_id,
        "adoption_event_id": event_id,
        "eligibility_hash": actual_hash,
        "exit_execution_hash": execution.payload_hash,
        "state": projection_state,
        "first_blocker": first_blocker,
        "exchange_write_called": False,
    }


def revoke_ticket_exit_policy_adoption(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
    adoption_event_id: str,
    expected_adoption_projection_version: int,
    now_ms: int,
) -> dict[str, Any]:
    """Append one revoke event and CAS the adoption-owned current fields."""

    normalized_ticket_id = str(ticket_id or "").strip()
    normalized_event_id = str(adoption_event_id or "").strip()
    if (
        not normalized_ticket_id
        or not normalized_event_id
        or int(expected_adoption_projection_version) < 1
        or int(now_ms) <= 0
    ):
        raise TicketExitPolicyAdoptionError("adoption_revoke_input_invalid")
    _lock_ticket(conn, ticket_id=normalized_ticket_id)
    events = _table(conn, "brc_ticket_exit_policy_adoption_events")
    projection = _table(conn, "brc_ticket_exit_policy_current")
    accepted = conn.execute(
        sa.select(events).where(
            events.c.ticket_id == normalized_ticket_id,
            events.c.adoption_event_id == normalized_event_id,
            events.c.decision == "accepted",
        )
    ).mappings().first()
    if accepted is None:
        raise TicketExitPolicyAdoptionError("adoption_revoke_target_invalid")
    already_revoked = conn.execute(
        sa.select(events.c.adoption_event_id).where(
            events.c.ticket_id == normalized_ticket_id,
            events.c.decision == "revoked",
            events.c.supersedes_adoption_event_id == normalized_event_id,
        )
    ).first()
    if already_revoked is not None:
        raise TicketExitPolicyAdoptionError("adoption_revoke_already_effective")
    revoke_id = _revoke_event_id(normalized_ticket_id, normalized_event_id, int(now_ms))
    event_values = dict(accepted)
    event_values.update(
        {
            "adoption_event_id": revoke_id,
            "decision": "revoked",
            "supersedes_adoption_event_id": normalized_event_id,
            "created_at_ms": int(now_ms),
        }
    )
    current = conn.execute(
        sa.select(projection).where(projection.c.ticket_id == normalized_ticket_id)
    ).mappings().first()
    if current is None:
        raise TicketExitPolicyAdoptionError("adoption_revoke_projection_missing")
    predicate = [
        projection.c.ticket_id == normalized_ticket_id,
        projection.c.adoption_event_id == normalized_event_id,
    ]
    if "adoption_state" in projection.c:
        predicate.append(projection.c.adoption_state == "accepted")
    if "adoption_projection_version" in projection.c:
        predicate.append(
            projection.c.adoption_projection_version
            == int(expected_adoption_projection_version)
        )
    values = {
        "adoption_state": "revoked",
        "mutation_allowed": False,
        "adoption_projection_version": int(expected_adoption_projection_version) + 1,
        "updated_at_ms": int(now_ms),
    }
    values = {key: value for key, value in values.items() if key in projection.c}
    result = conn.execute(projection.update().where(*predicate).values(**values))
    if result.rowcount != 1:
        raise TicketExitPolicyAdoptionError("adoption_revoke_cas_changed")
    conn.execute(events.insert().values(**event_values))
    return {
        "status": "adoption_revoked",
        "ticket_id": normalized_ticket_id,
        "adoption_event_id": normalized_event_id,
        "revoke_event_id": revoke_id,
        "adoption_projection_version": int(expected_adoption_projection_version) + 1,
        "exchange_write_called": False,
    }


def _entry_fee_truth(fills: list[dict[str, Any]]) -> tuple[Decimal, str]:
    if not fills:
        raise TicketExitPolicyAdoptionError("adoption_entry_fill_fee_missing")
    total = Decimal("0")
    assets: set[str] = set()
    for fill in fills:
        fee = _mapping(fill.get("fee"))
        total += _required_decimal(fee.get("cost"), "entry_fee_amount")
        asset = str(fee.get("currency") or "").strip().upper()
        if not asset:
            raise TicketExitPolicyAdoptionError("adoption_entry_fee_asset_missing")
        assets.add(asset)
    if len(assets) != 1:
        raise TicketExitPolicyAdoptionError("adoption_entry_fee_asset_ambiguous")
    return total, next(iter(assets))


def _tp1_completion_state(
    filled: Decimal,
    target: Decimal,
    quantity_step: Decimal,
) -> str:
    if filled <= 0:
        return "unfilled"
    if filled + quantity_step >= target:
        return "complete"
    return "partial"


def _one_role(rows: list[dict[str, Any]], role: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get("role") or "") == role]
    if len(matches) != 1:
        return {}
    return matches[0]


def _required_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise TicketExitPolicyAdoptionError(
            f"adoption_{field}_invalid"
        ) from exc
    if not result.is_finite():
        raise TicketExitPolicyAdoptionError(f"adoption_{field}_invalid")
    return result


def _adoption_event_id(ticket_id: str, eligibility_hash: str) -> str:
    digest = sha256(f"{ticket_id}|{eligibility_hash}".encode("utf-8")).hexdigest()
    return f"adoption:{digest}"


def _revoke_event_id(ticket_id: str, adoption_event_id: str, now_ms: int) -> str:
    digest = sha256(
        f"revoke|{ticket_id}|{adoption_event_id}|{now_ms}".encode("utf-8")
    ).hexdigest()
    return f"revoke:{digest}"


def _lock_ticket(conn: sa.engine.Connection, *, ticket_id: str) -> dict[str, Any]:
    tickets = _table(conn, "brc_action_time_tickets")
    row = conn.execute(
        sa.select(tickets)
        .where(tickets.c.ticket_id == ticket_id)
        .with_for_update()
    ).mappings().first()
    return dict(row) if row else {}


def _effective_accepted_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    revoked_ids = {
        str(row.get("supersedes_adoption_event_id") or "")
        for row in events
        if str(row.get("decision") or "") == "revoked"
    }
    accepted = [
        dict(row)
        for row in events
        if str(row.get("decision") or "") == "accepted"
        and str(row.get("adoption_event_id") or "") not in revoked_ids
    ]
    if len(accepted) > 1:
        raise TicketExitPolicyAdoptionError("adoption_effective_acceptance_ambiguous")
    return accepted


def _projection_version(row: Any) -> int:
    if not isinstance(row, dict):
        row = dict(row or {})
    try:
        value = int(row.get("adoption_projection_version") or 1)
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


def _projection_is_revoked(row: dict[str, Any]) -> bool:
    return str(row.get("adoption_state") or "") == "revoked" and (
        row.get("mutation_allowed") in {False, 0}
    )


def _projection_mutation_allowed(row: dict[str, Any]) -> bool:
    if "mutation_allowed" not in row:
        return True
    return row.get("mutation_allowed") in {True, 1}


def _require_tables(conn: sa.engine.Connection) -> None:
    required = {
        "brc_action_time_tickets",
        "brc_strategy_exit_policies",
        "brc_ticket_bound_order_lifecycle_runs",
        "brc_ticket_bound_exit_protection_sets",
        "brc_ticket_bound_exit_protection_orders",
        "brc_ticket_bound_exchange_commands",
        "brc_exchange_instruments",
        "brc_ticket_exit_policy_adoption_events",
        "brc_ticket_exit_policy_current",
    }
    missing = sorted(required - set(sa.inspect(conn).get_table_names()))
    if missing:
        raise TicketExitPolicyAdoptionError(
            f"adoption_authority_tables_missing:{','.join(missing)}"
        )


def _one_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    value: str,
) -> dict[str, Any]:
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(getattr(table.c, id_column) == value)
    ).mappings().first()
    return dict(row) if row else {}


def _mapping(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)
