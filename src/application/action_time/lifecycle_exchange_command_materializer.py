"""Materialize lifecycle plan rows into the one durable exchange authority."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Literal

import sqlalchemy as sa

from src.application.action_time.exchange_scope import (
    TicketBoundExchangeScope,
    resolve_ticket_bound_exchange_scope,
)
from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    TicketBoundExchangeCommand,
    deterministic_client_order_id,
)


TABLE = "brc_ticket_bound_exchange_commands"


def materialize_lifecycle_exchange_commands(
    conn: sa.engine.Connection,
    *,
    command_source: Literal[
        "protection_recovery",
        "runner_mutation",
        "orphan_cleanup",
    ],
    source_command_id: str,
    now_ms: int,
) -> list[dict[str, Any]]:
    """Persist exact place/cancel intents; never call the exchange."""

    source_table, source_id_column = {
        "protection_recovery": (
            "brc_ticket_bound_protection_recovery_commands",
            "protection_recovery_command_id",
        ),
        "runner_mutation": (
            "brc_ticket_bound_runner_mutation_commands",
            "runner_mutation_command_id",
        ),
        "orphan_cleanup": (
            "brc_ticket_bound_orphan_protection_cleanup_commands",
            "orphan_protection_cleanup_command_id",
        ),
    }[command_source]
    source = _row_by_id(conn, source_table, source_id_column, source_command_id)
    if not source:
        raise ValueError(f"lifecycle_exchange_source_missing:{command_source}")
    if str(source.get("status") or "") != "prepared":
        raise ValueError(f"lifecycle_exchange_source_not_prepared:{command_source}")
    ticket_id = str(source.get("ticket_id") or "")
    resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=ticket_id,
        now_ms=now_ms,
    )
    if resolution.status != "resolved" or resolution.scope is None:
        raise ValueError(
            ",".join(resolution.blockers) or "ticket_exchange_scope_unresolved"
        )
    scope = resolution.scope
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        str(source.get("protected_submit_attempt_id") or ""),
    )
    if not attempt:
        raise ValueError("lifecycle_exchange_attempt_missing")
    intents = _source_intents(
        command_source=command_source,
        source=source,
    )
    if not intents:
        raise ValueError("lifecycle_exchange_intents_empty")
    return [
        _insert_or_verify(
            conn,
            scope=scope,
            attempt=attempt,
            source=source,
            command_source=command_source,
            source_command_id=source_command_id,
            intent=intent,
            generation=index,
            now_ms=now_ms,
        )
        for index, intent in enumerate(intents, start=1)
    ]


def _source_intents(
    *,
    command_source: str,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    plan = _json_object(source.get("command_plan"))
    if command_source == "protection_recovery":
        return [
            {
                **dict(order),
                "command_kind": "place_order",
                "order_role": str(order.get("order_role") or "").upper(),
                "parent_order_id": order.get("local_order_id"),
                "local_order_id": (
                    f"{source['protection_recovery_command_id']}:"
                    f"{str(order.get('order_role') or '').upper()}"
                ),
            }
            for order in plan.get("submit_missing_orders", [])
            if isinstance(order, dict)
        ]
    if command_source == "runner_mutation":
        submit = _json_object(plan.get("submit_runner_sl"))
        cancel = _json_object(plan.get("cancel_old_sl"))
        return [
            {
                "command_kind": "place_order",
                "order_role": "RUNNER_SL",
                "gateway_order_type": "stop_market",
                "gateway_side": submit.get("side"),
                "amount": submit.get("qty"),
                "trigger_price": submit.get("trigger_price"),
                "price": None,
                "reduce_only": True,
                "local_order_id": f"{source['runner_mutation_command_id']}:runner-sl",
                "parent_order_id": cancel.get("local_order_id"),
            },
            {
                "command_kind": "cancel_order",
                "order_role": "SL",
                "gateway_order_type": "cancel",
                "gateway_side": submit.get("side"),
                "amount": submit.get("qty"),
                "price": None,
                "trigger_price": None,
                "reduce_only": True,
                "local_order_id": f"{source['runner_mutation_command_id']}:cancel-old-sl",
                "parent_order_id": cancel.get("local_order_id"),
                "target_exchange_order_id": cancel.get("exchange_order_id"),
            },
        ]
    intents: list[dict[str, Any]] = []
    for order in plan.get("cancel_orders", []):
        if not isinstance(order, dict):
            continue
        intents.append(
            {
                "command_kind": "cancel_order",
                "order_role": str(order.get("role") or "").upper(),
                "gateway_order_type": "cancel",
                "gateway_side": order.get("side"),
                "amount": order.get("qty"),
                "price": None,
                "trigger_price": None,
                "reduce_only": True,
                "local_order_id": (
                    f"{source['orphan_protection_cleanup_command_id']}:"
                    f"cancel:{order.get('role')}"
                ),
                "parent_order_id": order.get("exit_protection_order_id"),
                "target_exchange_order_id": order.get("exchange_order_id"),
            }
        )
    return intents


def _insert_or_verify(
    conn: sa.engine.Connection,
    *,
    scope: TicketBoundExchangeScope,
    attempt: dict[str, Any],
    source: dict[str, Any],
    command_source: str,
    source_command_id: str,
    intent: dict[str, Any],
    generation: int,
    now_ms: int,
) -> dict[str, Any]:
    role = str(intent.get("order_role") or "").upper()
    kind = str(intent.get("command_kind") or "")
    if role not in {"SL", "TP1", "RUNNER_SL"}:
        raise ValueError(f"lifecycle_exchange_role_invalid:{role}")
    if kind not in {"place_order", "cancel_order"}:
        raise ValueError(f"lifecycle_exchange_kind_invalid:{kind}")
    amount = Decimal(str(intent.get("amount") or "0"))
    if amount <= 0:
        raise ValueError(f"lifecycle_exchange_amount_invalid:{role}")
    local_order_id = str(intent.get("local_order_id") or "").strip()
    if not local_order_id:
        local_order_id = f"{source_command_id}:{kind}:{role}:{generation}"
    command_id = _stable_id(
        "lifecycle_exchange_command",
        command_source,
        source_command_id,
        kind,
        role,
        str(generation),
    )
    client_order_id = deterministic_client_order_id(
        scope.ticket_id,
        source_command_id,
        f"{kind}:{role}",
        generation,
    )
    fingerprint_values = {
        "command_source": command_source,
        "source_command_id": source_command_id,
        "command_kind": kind,
        "order_role": role,
        "account_id": scope.account_id,
        "exchange_id": scope.exchange_id,
        "exchange_instrument_id": scope.exchange_instrument_id,
        "gateway_symbol": scope.exchange_symbol,
        "position_mode": scope.position_mode,
        "position_side": scope.position_side,
        "netting_domain_key": scope.netting_domain_key,
        "gateway_side": str(intent.get("gateway_side") or ""),
        "amount": str(amount),
        "price": _decimal_text(intent.get("price")),
        "trigger_price": _decimal_text(intent.get("trigger_price")),
        "target_exchange_order_id": str(
            intent.get("target_exchange_order_id") or ""
        ),
    }
    fingerprint = "sha256:" + sha256(
        json.dumps(
            fingerprint_values,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    command = TicketBoundExchangeCommand(
        exchange_command_id=command_id,
        protected_submit_attempt_id=str(
            source.get("protected_submit_attempt_id") or ""
        ),
        ticket_id=scope.ticket_id,
        operation_submit_command_id=str(
            attempt.get("operation_submit_command_id") or ""
        ),
        account_id=scope.account_id,
        strategy_group_id=scope.strategy_group_id,
        runtime_profile_id=scope.runtime_profile_id,
        exchange_instrument_id=scope.exchange_instrument_id,
        exchange_id=scope.exchange_id,
        gateway_symbol=scope.exchange_symbol,
        symbol=scope.canonical_symbol,
        order_role=role,
        side=scope.side,
        gateway_side=str(intent.get("gateway_side") or ""),
        local_order_id=local_order_id,
        parent_order_id=str(intent.get("parent_order_id") or "") or None,
        client_order_id=client_order_id,
        command_generation=generation,
        request_fingerprint=fingerprint,
        order_type=str(intent.get("gateway_order_type") or ""),
        amount=amount,
        price=_decimal_or_none(intent.get("price")),
        stop_price=_decimal_or_none(intent.get("trigger_price")),
        reduce_only=True,
        reduce_intent="reduce_position",
        position_mode=scope.position_mode,
        position_side=scope.position_side,
        position_bucket=scope.position_bucket,
        netting_domain_key=scope.netting_domain_key,
        command_kind=kind,
        command_source=command_source,
        source_command_id=source_command_id,
        target_exchange_order_id=(
            str(intent.get("target_exchange_order_id") or "") or None
        ),
        authority_source_ref=(
            f"{command_source}:{source_command_id}"
        ),
        command_state=ExchangeCommandState.PREPARED,
        outcome_class=ExchangeCommandOutcomeClass.PENDING,
        prepared_at_ms=now_ms,
        updated_at_ms=now_ms,
    )
    row = command.model_dump(mode="json")
    table = _table(conn, TABLE)
    existing = conn.execute(
        sa.select(table).where(table.c.exchange_command_id == command_id)
    ).mappings().first()
    if existing:
        if str(existing.get("request_fingerprint") or "") != fingerprint:
            raise ValueError("lifecycle_exchange_command_fingerprint_mismatch")
        return dict(existing)
    conn.execute(table.insert().values(**row))
    return row


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    if not id_value:
        return {}
    table = _table(conn, table_name)
    row = conn.execute(
        sa.select(table).where(table.c[id_column] == id_value)
    ).mappings().first()
    return dict(row) if row else {}


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _json_object(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    return Decimal(str(value))


def _decimal_text(value: Any) -> str:
    parsed = _decimal_or_none(value)
    return str(parsed) if parsed is not None else ""


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"
