"""Persist and transition ticket-bound exchange commands in PostgreSQL."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_scope import (
    resolve_ticket_bound_exchange_scope,
)

from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    TicketBoundExchangeCommand,
    command_transition_blockers,
    deterministic_client_order_id,
)


TABLE_NAME = "brc_ticket_bound_exchange_commands"


def list_exchange_commands_for_attempt(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
) -> list[dict[str, Any]]:
    table = _table(conn)
    role_order = sa.case(
        (table.c.order_role == "ENTRY", 1),
        (table.c.order_role == "SL", 2),
        (table.c.order_role == "TP1", 3),
        else_=4,
    )
    rows = conn.execute(
        sa.select(table)
        .where(
            table.c.protected_submit_attempt_id == protected_submit_attempt_id
        )
        .order_by(role_order, table.c.command_generation)
    ).mappings()
    return [_json_safe(dict(row)) for row in rows]


def materialize_ticket_bound_exchange_commands(
    conn: sa.engine.Connection,
    *,
    attempt: dict[str, Any],
    now_ms: int,
) -> list[dict[str, Any]]:
    """Insert immutable prepared commands or verify an identical replay."""

    if str(attempt.get("status") or "") != "submit_prepared":
        raise ValueError("exchange_commands_require_submit_prepared_attempt")
    if str(attempt.get("submit_mode") or "") != "real_gateway_action":
        raise ValueError("exchange_commands_require_real_gateway_action")
    request = _mapping(attempt.get("submit_request"))
    orders = request.get("orders")
    if not isinstance(orders, list) or not orders:
        raise ValueError("exchange_command_orders_required")

    table = _table(conn)
    scope_resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=str(attempt.get("ticket_id") or ""),
        now_ms=now_ms,
    )
    if scope_resolution.status != "resolved" or scope_resolution.scope is None:
        raise ValueError(
            ",".join(scope_resolution.blockers)
            or "ticket_exchange_scope_unresolved"
        )
    scope = scope_resolution.scope
    if not scope.current_entry_eligible:
        raise ValueError(",".join(scope.current_entry_blockers))
    if str(request.get("account_id") or "") != scope.account_id:
        raise ValueError("exchange_command_account_scope_mismatch")
    requested_gateway_symbol = str(request.get("exchange_symbol") or "")
    if requested_gateway_symbol != scope.exchange_symbol:
        raise ValueError("exchange_command_gateway_symbol_scope_mismatch")
    materialized: list[dict[str, Any]] = []
    for raw_order in orders:
        order = _mapping(raw_order)
        role = str(order.get("order_role") or "").upper()
        generation = 1
        command_id = _stable_id(
            "exchange_command",
            str(attempt.get("ticket_id") or ""),
            role,
            str(generation),
        )
        reduce_intent = "open_position" if role == "ENTRY" else "reduce_position"
        fingerprint = command_request_fingerprint(
            {
                **order,
                "exchange_id": scope.exchange_id,
                "exchange_instrument_id": scope.exchange_instrument_id,
                "gateway_symbol": scope.exchange_symbol,
                "position_mode": scope.position_mode,
                "position_side": scope.position_side,
                "netting_domain_key": scope.netting_domain_key,
                "reduce_intent": reduce_intent,
                "command_kind": "place_order",
                "command_source": "protected_submit",
            }
        )
        command = TicketBoundExchangeCommand(
            exchange_command_id=command_id,
            protected_submit_attempt_id=str(
                attempt.get("protected_submit_attempt_id") or ""
            ),
            ticket_id=str(attempt.get("ticket_id") or ""),
            operation_submit_command_id=str(
                attempt.get("operation_submit_command_id") or ""
            ),
            account_id=str(request.get("account_id") or ""),
            strategy_group_id=str(attempt.get("strategy_group_id") or ""),
            runtime_profile_id=str(attempt.get("runtime_profile_id") or ""),
            exchange_instrument_id=str(
                scope.exchange_instrument_id
            ),
            exchange_id=scope.exchange_id,
            gateway_symbol=scope.exchange_symbol,
            symbol=str(attempt.get("symbol") or ""),
            order_role=role,
            side=str(attempt.get("side") or ""),
            gateway_side=str(order.get("gateway_side") or ""),
            local_order_id=str(order.get("local_order_id") or ""),
            parent_order_id=_optional_text(order.get("parent_order_id")),
            client_order_id=deterministic_client_order_id(
                str(attempt.get("ticket_id") or ""),
                str(attempt.get("operation_submit_command_id") or ""),
                role,
                generation,
            ),
            command_generation=generation,
            request_fingerprint=fingerprint,
            order_type=str(order.get("gateway_order_type") or ""),
            amount=_required_decimal(order.get("amount"), "amount"),
            price=_optional_decimal(order.get("price")),
            stop_price=_optional_decimal(order.get("trigger_price")),
            desired_leverage=(
                int(order["desired_leverage"])
                if order.get("desired_leverage") is not None
                else None
            ),
            reduce_only=order.get("reduce_only") is True,
            reduce_intent=reduce_intent,
            position_mode=scope.position_mode,
            position_side=scope.position_side,
            position_bucket=scope.position_bucket,
            netting_domain_key=scope.netting_domain_key,
            command_kind="place_order",
            command_source="protected_submit",
            source_command_id=str(
                attempt.get("protected_submit_attempt_id") or ""
            ),
            authority_source_ref=str(
                attempt.get("authority_source_ref")
                or "protected-submit:missing-authority-source"
            ),
            command_state=ExchangeCommandState.PREPARED,
            outcome_class=ExchangeCommandOutcomeClass.PENDING,
            prepared_at_ms=now_ms,
            updated_at_ms=now_ms,
        )
        row = command.model_dump(mode="json")
        existing = conn.execute(
            sa.select(table).where(table.c.exchange_command_id == command_id)
        ).mappings().first()
        if existing is not None:
            existing_row = dict(existing)
            if str(existing_row.get("request_fingerprint") or "") != fingerprint:
                raise ValueError("exchange_command_request_fingerprint_mismatch")
            for key in (
                "protected_submit_attempt_id",
                "ticket_id",
                "operation_submit_command_id",
                "account_id",
                "strategy_group_id",
                "runtime_profile_id",
                "exchange_instrument_id",
                "exchange_id",
                "gateway_symbol",
                "symbol",
                "order_role",
                "side",
                "gateway_side",
                "local_order_id",
                "parent_order_id",
                "client_order_id",
                "command_generation",
                "authority_source_ref",
                "reduce_intent",
                "position_mode",
                "position_side",
                "position_bucket",
                "netting_domain_key",
                "command_kind",
                "desired_leverage",
                "command_source",
                "source_command_id",
            ):
                if existing_row.get(key) != row.get(key):
                    raise ValueError(f"exchange_command_identity_mismatch:{key}")
            materialized.append(_json_safe(existing_row))
            continue
        conn.execute(table.insert().values(**row))
        materialized.append(row)
    return materialized


def resize_prepared_protection_command_to_entry_fill(
    conn: sa.engine.Connection,
    *,
    exchange_command_id: str,
    now_ms: int,
) -> dict[str, Any]:
    """Bind SL/TP1 quantity to confirmed actual ENTRY fill before dispatch."""

    table = _table(conn)
    command = _row(conn, exchange_command_id)
    role = str(command.get("order_role") or "")
    if role not in {"SL", "TP1"}:
        return command
    if str(command.get("command_state") or "") != "prepared":
        raise ValueError("protection_command_not_prepared_for_fill_resize")
    entry = conn.execute(
        sa.select(table).where(
            table.c.protected_submit_attempt_id
            == command.get("protected_submit_attempt_id"),
            table.c.order_role == "ENTRY",
        )
    ).mappings().first()
    if not entry or str(entry.get("command_state") or "") not in {
        "confirmed_submitted",
        "reconciled_submitted",
    }:
        raise ValueError("entry_fill_not_confirmed_before_protection")
    entry_result = _mapping(entry.get("exchange_result"))
    filled_qty = _required_decimal(
        entry_result.get("filled_qty"),
        "entry_filled_qty",
    )
    requested_qty = _required_decimal(entry.get("amount"), "entry_requested_qty")
    if filled_qty > requested_qty:
        raise ValueError("entry_filled_qty_exceeds_requested_qty")
    if filled_qty == requested_qty:
        return command
    instrument = _row_by_column(
        conn,
        "brc_exchange_instruments",
        "exchange_instrument_id",
        str(command.get("exchange_instrument_id") or ""),
    )
    quantity_step = _required_decimal(
        instrument.get("quantity_step"),
        "exchange_quantity_step",
    )
    target = filled_qty
    if role == "TP1":
        original_ratio = _required_decimal(command.get("amount"), "amount") / requested_qty
        target = filled_qty * original_ratio
    target = (target // quantity_step) * quantity_step
    if target <= 0 or target > filled_qty:
        raise ValueError(f"{role.lower()}_quantity_invalid_after_entry_fill")
    if target == _required_decimal(command.get("amount"), "amount"):
        return command
    updated = {**command, "amount": target}
    updated["request_fingerprint"] = command_request_fingerprint(
        {
            **updated,
            "gateway_order_type": updated.get("order_type"),
            "trigger_price": updated.get("stop_price"),
        }
    )
    updated["authority_source_ref"] = (
        f"{str(command.get('authority_source_ref') or '')}"
        f"|actual-entry-fill:{str(entry.get('exchange_command_id') or '')}"
    )
    updated["updated_at_ms"] = now_ms
    conn.execute(
        table.update()
        .where(table.c.exchange_command_id == exchange_command_id)
        .values(
            amount=target,
            request_fingerprint=updated["request_fingerprint"],
            authority_source_ref=updated["authority_source_ref"],
            updated_at_ms=now_ms,
        )
    )
    return _json_safe(updated)


def mark_exchange_command_dispatching(
    conn: sa.engine.Connection,
    *,
    exchange_command_id: str,
    now_ms: int,
) -> dict[str, Any]:
    return _transition(
        conn,
        exchange_command_id=exchange_command_id,
        target=ExchangeCommandState.DISPATCHING,
        outcome_class=ExchangeCommandOutcomeClass.PENDING,
        updates={"dispatch_started_at_ms": now_ms, "updated_at_ms": now_ms},
    )


def claim_next_exchange_command(
    conn: sa.engine.Connection,
    *,
    claim_owner: str,
    now_ms: int,
    lease_ms: int = 15_000,
    command_sources: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Claim at most one prepared command inside a short PG transaction."""

    owner = str(claim_owner or "").strip()
    if not owner:
        raise ValueError("exchange_command_claim_owner_required")
    if lease_ms <= 0:
        raise ValueError("exchange_command_claim_lease_invalid")
    table = _table(conn)
    if conn.dialect.name == "postgresql":
        conn.execute(
            sa.text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('brc_ticket_bound_exchange_command_claim'))"
            )
        )
    dispatching = conn.execute(
        sa.select(table.c.exchange_command_id).where(
            table.c.command_state == ExchangeCommandState.DISPATCHING.value
        ).limit(1)
    ).first()
    if dispatching is not None:
        return {}
    role_order = sa.case(
        (table.c.order_role == "ENTRY", 1),
        (table.c.order_role == "SL", 2),
        (table.c.order_role == "TP1", 3),
        (table.c.order_role == "RUNNER_SL", 4),
        else_=5,
    )
    query = sa.select(table).where(
        table.c.command_state == ExchangeCommandState.PREPARED.value
    )
    blocking = table.alias("blocking_exchange_command")
    query = query.where(
        ~sa.exists(
            sa.select(sa.literal(1)).where(
                blocking.c.netting_domain_key == table.c.netting_domain_key,
                blocking.c.command_state.in_(
                    (
                        ExchangeCommandState.OUTCOME_UNKNOWN.value,
                        ExchangeCommandState.HARD_STOPPED.value,
                        ExchangeCommandState.CONFIRMED_REJECTED.value,
                    )
                ),
            )
        )
    )
    if command_sources is not None:
        if not command_sources:
            return {}
        query = query.where(table.c.command_source.in_(command_sources))
    query = (
        query
        .order_by(
            table.c.prepared_at_ms.asc(),
            table.c.command_generation.asc(),
            role_order,
            table.c.exchange_command_id.asc(),
        )
        .limit(1)
    )
    if conn.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    row = conn.execute(query).mappings().first()
    if row is None:
        return {}
    command_id = str(row["exchange_command_id"])
    claim_token = _stable_id(
        "exchange_command_claim",
        command_id,
        owner,
        str(now_ms),
    )
    return _transition(
        conn,
        exchange_command_id=command_id,
        target=ExchangeCommandState.DISPATCHING,
        outcome_class=ExchangeCommandOutcomeClass.PENDING,
        updates={
            "dispatch_started_at_ms": now_ms,
            "claim_owner": owner,
            "claim_token": claim_token,
            "claim_started_at_ms": now_ms,
            "claim_expires_at_ms": now_ms + lease_ms,
            "execution_attempt_count": int(
                row.get("execution_attempt_count") or 0
            )
            + 1,
            "updated_at_ms": now_ms,
        },
    )


def expire_stale_exchange_command_claims(
    conn: sa.engine.Connection,
    *,
    now_ms: int,
) -> list[dict[str, Any]]:
    """Persist ambiguous outcome before any command can be reconsidered."""

    table = _table(conn)
    rows = conn.execute(
        sa.select(table).where(
            table.c.command_state == ExchangeCommandState.DISPATCHING.value,
            table.c.claim_expires_at_ms.is_not(None),
            table.c.claim_expires_at_ms <= now_ms,
        )
    ).mappings().all()
    return [
        record_exchange_command_outcome(
            conn,
            exchange_command_id=str(row["exchange_command_id"]),
            target_state=ExchangeCommandState.OUTCOME_UNKNOWN,
            outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
            exchange_result={
                "error_code": "dispatch_lease_expired",
                "error_message": (
                    "worker lease expired before a committed exchange outcome"
                ),
            },
            now_ms=now_ms,
        )
        for row in rows
    ]


def record_claimed_exchange_command_outcome(
    conn: sa.engine.Connection,
    *,
    exchange_command_id: str,
    claim_token: str,
    target_state: ExchangeCommandState,
    outcome_class: ExchangeCommandOutcomeClass,
    exchange_result: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    row = _row(conn, exchange_command_id)
    if str(row.get("claim_token") or "") != str(claim_token or ""):
        raise ValueError("exchange_command_claim_token_mismatch")
    if str(row.get("command_state") or "") != "dispatching":
        raise ValueError("exchange_command_claim_not_dispatching")
    return record_exchange_command_outcome(
        conn,
        exchange_command_id=exchange_command_id,
        target_state=target_state,
        outcome_class=outcome_class,
        exchange_result=exchange_result,
        now_ms=now_ms,
    )


def record_exchange_command_outcome(
    conn: sa.engine.Connection,
    *,
    exchange_command_id: str,
    target_state: ExchangeCommandState,
    outcome_class: ExchangeCommandOutcomeClass,
    exchange_result: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    updates = {
        "exchange_result": _json_safe(exchange_result),
        "exchange_order_id": _optional_text(
            exchange_result.get("exchange_order_id")
        ),
        "exchange_error_code": _optional_text(exchange_result.get("error_code")),
        "exchange_error_message": _optional_text(
            exchange_result.get("error_message")
        ),
        "resolved_at_ms": now_ms
        if target_state
        not in {ExchangeCommandState.OUTCOME_UNKNOWN}
        else None,
        "updated_at_ms": now_ms,
    }
    return _transition(
        conn,
        exchange_command_id=exchange_command_id,
        target=target_state,
        outcome_class=outcome_class,
        updates=updates,
    )


def command_request_fingerprint(order: dict[str, Any]) -> str:
    canonical = {
        "local_order_id": str(order.get("local_order_id") or ""),
        "parent_order_id": str(order.get("parent_order_id") or ""),
        "order_role": str(order.get("order_role") or "").upper(),
        "symbol": str(order.get("symbol") or ""),
        "gateway_order_type": str(order.get("gateway_order_type") or ""),
        "gateway_side": str(order.get("gateway_side") or ""),
        "amount": str(_required_decimal(order.get("amount"), "amount")),
        "price": _decimal_text(order.get("price")),
        "trigger_price": _decimal_text(order.get("trigger_price")),
        "reduce_only": order.get("reduce_only") is True,
        "exchange_id": str(order.get("exchange_id") or ""),
        "exchange_instrument_id": str(
            order.get("exchange_instrument_id") or ""
        ),
        "gateway_symbol": str(order.get("gateway_symbol") or ""),
        "position_mode": str(order.get("position_mode") or ""),
        "position_side": str(order.get("position_side") or ""),
        "netting_domain_key": str(order.get("netting_domain_key") or ""),
        "reduce_intent": str(order.get("reduce_intent") or ""),
        "command_kind": str(order.get("command_kind") or ""),
        "command_source": str(order.get("command_source") or ""),
        "desired_leverage": (
            int(order["desired_leverage"])
            if order.get("desired_leverage") is not None
            else None
        ),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def _transition(
    conn: sa.engine.Connection,
    *,
    exchange_command_id: str,
    target: ExchangeCommandState,
    outcome_class: ExchangeCommandOutcomeClass,
    updates: dict[str, Any],
) -> dict[str, Any]:
    table = _table(conn)
    existing = conn.execute(
        sa.select(table).where(
            table.c.exchange_command_id == exchange_command_id
        )
    ).mappings().first()
    if existing is None:
        raise ValueError("exchange_command_missing")
    current = ExchangeCommandState(str(existing["command_state"]))
    blockers = command_transition_blockers(
        current=current,
        target=target,
        outcome_class=outcome_class,
    )
    if blockers:
        raise ValueError(",".join(blockers))
    values = {
        **updates,
        "command_state": target.value,
        "outcome_class": outcome_class.value,
    }
    conn.execute(
        table.update()
        .where(table.c.exchange_command_id == exchange_command_id)
        .values(**values)
    )
    return _row(conn, exchange_command_id)


def _row(conn: sa.engine.Connection, exchange_command_id: str) -> dict[str, Any]:
    table = _table(conn)
    row = conn.execute(
        sa.select(table).where(
            table.c.exchange_command_id == exchange_command_id
        )
    ).mappings().one()
    return _json_safe(dict(row))


def _row_by_column(
    conn: sa.engine.Connection,
    table_name: str,
    column_name: str,
    value: str,
) -> dict[str, Any]:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=conn)
    row = conn.execute(
        sa.select(table).where(table.c[column_name] == value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection) -> sa.Table:
    return sa.Table(TABLE_NAME, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _required_decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"exchange_command_{name}_invalid") from exc
    if parsed <= 0:
        raise ValueError(f"exchange_command_{name}_invalid")
    return parsed


def _optional_decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    return _required_decimal(value, "optional_decimal")


def _decimal_text(value: Any) -> str:
    parsed = _optional_decimal(value)
    return str(parsed) if parsed is not None else ""


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value
