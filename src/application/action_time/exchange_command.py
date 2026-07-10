"""Persist and transition ticket-bound exchange commands in PostgreSQL."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

import sqlalchemy as sa

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
        fingerprint = command_request_fingerprint(order)
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
                request.get("exchange_instrument_id")
                or request.get("exchange_symbol")
                or ""
            ),
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
            reduce_only=order.get("reduce_only") is True,
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
                "order_role",
                "side",
                "gateway_side",
                "local_order_id",
                "parent_order_id",
                "client_order_id",
                "command_generation",
                "authority_source_ref",
            ):
                if existing_row.get(key) != row.get(key):
                    raise ValueError(f"exchange_command_identity_mismatch:{key}")
            materialized.append(_json_safe(existing_row))
            continue
        conn.execute(table.insert().values(**row))
        materialized.append(row)
    return materialized


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
