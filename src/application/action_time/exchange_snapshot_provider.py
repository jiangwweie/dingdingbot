#!/usr/bin/env python3
"""Read-only exchange snapshot provider for ticket-bound lifecycle reconciliation."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa


AUTHORITY_BOUNDARY = (
    "ticket_bound_exchange_snapshot_provider; read-only gateway snapshot for "
    "existing ticket-bound exit protection set; no submit, cancel, amend, "
    "FinalGate, Operation Layer, profile, sizing, withdrawal, transfer, or file "
    "authority"
)

ATTEMPT_AUTHORITY_BOUNDARY = (
    "ticket_bound_attempt_exchange_snapshot_provider; read-only gateway "
    "snapshot for existing ticket-bound protected submit attempt; no submit, "
    "cancel, amend, FinalGate, Operation Layer, profile, sizing, withdrawal, "
    "transfer, or file authority"
)


async def fetch_ticket_bound_exchange_snapshot(
    conn: sa.engine.Connection,
    *,
    exit_protection_set_id: str,
    gateway: Any,
    timeout_seconds: float = 8.0,
    recent_fill_limit: int = 50,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    set_id = str(exit_protection_set_id or "").strip()
    if not set_id:
        return _blocked(
            now_ms=now_ms,
            blockers=["exit_protection_set_id_required"],
            protection_set={},
        )
    protection_set = _row_by_id(
        conn,
        "brc_ticket_bound_exit_protection_sets",
        "exit_protection_set_id",
        set_id,
    )
    if not protection_set:
        return _blocked(
            now_ms=now_ms,
            blockers=["exit_protection_set_missing"],
            protection_set={},
        )
    symbol = str(protection_set.get("symbol") or "").strip()
    if not symbol:
        return _blocked(
            now_ms=now_ms,
            blockers=["exit_protection_set_symbol_missing"],
            protection_set=protection_set,
        )
    method_blockers = _gateway_method_blockers(gateway)
    if method_blockers:
        return _blocked(
            now_ms=now_ms,
            blockers=method_blockers,
            protection_set=protection_set,
        )

    try:
        open_orders, recent_fills, positions = await asyncio.wait_for(
            asyncio.gather(
                gateway.fetch_open_orders(symbol),
                gateway.fetch_my_trades(symbol, limit=recent_fill_limit),
                gateway.fetch_positions(symbol),
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return _blocked(
            now_ms=now_ms,
            blockers=["exchange_snapshot_fetch_timeout"],
            protection_set=protection_set,
        )
    except Exception as exc:
        return _blocked(
            now_ms=now_ms,
            blockers=[f"exchange_snapshot_fetch_failed:{type(exc).__name__}"],
            protection_set=protection_set,
        )

    snapshot = {
        "snapshot_id": _snapshot_id(set_id, now_ms),
        "source": "official_runtime_exchange_gateway",
        "exchange_read_called": True,
        "exchange_write_called": False,
        "symbol": symbol,
        "open_orders": [_normalize_open_order(order) for order in open_orders or []],
        "recent_fills": [_normalize_fill(fill) for fill in recent_fills or []],
        "position": _normalize_position(symbol, positions or []),
        "fetched_at_ms": now_ms,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    return {
        "schema": "brc.ticket_bound_exchange_snapshot_provider.v1",
        "status": "snapshot_ready",
        "now_ms": now_ms,
        "ticket_id": protection_set.get("ticket_id"),
        "exit_protection_set_id": set_id,
        "symbol": symbol,
        "first_blocker": None,
        "blockers": [],
        "snapshot": snapshot,
        "exchange_read_called": True,
        "exchange_write_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


async def fetch_ticket_bound_attempt_exchange_snapshot(
    conn: sa.engine.Connection,
    *,
    protected_submit_attempt_id: str,
    gateway: Any,
    timeout_seconds: float = 8.0,
    recent_fill_limit: int = 50,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now_ms = int(now_ms or time.time() * 1000)
    attempt_id = str(protected_submit_attempt_id or "").strip()
    if not attempt_id:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=["protected_submit_attempt_id_required"],
            attempt={},
        )
    attempt = _row_by_id(
        conn,
        "brc_ticket_bound_protected_submit_attempts",
        "protected_submit_attempt_id",
        attempt_id,
    )
    if not attempt:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=["protected_submit_attempt_missing"],
            attempt={},
        )
    symbol = str(attempt.get("symbol") or "").strip()
    if not symbol:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=["protected_submit_attempt_symbol_missing"],
            attempt=attempt,
        )
    method_blockers = _gateway_method_blockers(gateway)
    if method_blockers:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=method_blockers,
            attempt=attempt,
        )

    try:
        open_orders, recent_fills, positions = await asyncio.wait_for(
            asyncio.gather(
                gateway.fetch_open_orders(symbol),
                gateway.fetch_my_trades(symbol, limit=recent_fill_limit),
                gateway.fetch_positions(symbol),
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=["exchange_snapshot_fetch_timeout"],
            attempt=attempt,
        )
    except Exception as exc:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=[f"exchange_snapshot_fetch_failed:{type(exc).__name__}"],
            attempt=attempt,
        )

    snapshot = {
        "snapshot_id": _snapshot_id(attempt_id, now_ms),
        "source": "official_runtime_exchange_gateway",
        "exchange_read_called": True,
        "exchange_write_called": False,
        "symbol": symbol,
        "open_orders": [_normalize_open_order(order) for order in open_orders or []],
        "recent_fills": [_normalize_fill(fill) for fill in recent_fills or []],
        "position": _normalize_position(symbol, positions or []),
        "fetched_at_ms": now_ms,
        "authority_boundary": ATTEMPT_AUTHORITY_BOUNDARY,
    }
    return {
        "schema": "brc.ticket_bound_attempt_exchange_snapshot_provider.v1",
        "status": "snapshot_ready",
        "now_ms": now_ms,
        "ticket_id": attempt.get("ticket_id"),
        "protected_submit_attempt_id": attempt_id,
        "symbol": symbol,
        "first_blocker": None,
        "blockers": [],
        "snapshot": snapshot,
        "exchange_read_called": True,
        "exchange_write_called": False,
        "authority_boundary": ATTEMPT_AUTHORITY_BOUNDARY,
    }


def _gateway_method_blockers(gateway: Any) -> list[str]:
    if gateway is None:
        return ["exchange_snapshot_gateway_required"]
    blockers: list[str] = []
    for name in ("fetch_open_orders", "fetch_my_trades", "fetch_positions"):
        if not callable(getattr(gateway, name, None)):
            blockers.append(f"exchange_snapshot_gateway_missing_{name}")
    return blockers


def _normalize_open_order(order: Any) -> dict[str, Any]:
    raw = _as_dict(order)
    info = _as_dict(raw.get("info"))
    return {
        "exchange_order_id": _first(raw, info, "id", "orderId", "exchange_order_id"),
        "client_order_id": _first(
            raw,
            info,
            "clientOrderId",
            "client_order_id",
            "client_order_id",
        ),
        "symbol": str(raw.get("symbol") or info.get("symbol") or ""),
        "side": str(raw.get("side") or info.get("side") or "").lower(),
        "reduce_only": _as_bool(
            raw.get("reduceOnly")
            if "reduceOnly" in raw
            else raw.get("reduce_only", info.get("reduceOnly"))
        ),
        "qty": str(
            raw.get("amount")
            or raw.get("remaining")
            or info.get("origQty")
            or info.get("quantity")
            or ""
        ),
        "price": str(raw.get("price") or info.get("price") or ""),
        "trigger_price": str(
            raw.get("triggerPrice")
            or raw.get("stopPrice")
            or info.get("stopPrice")
            or ""
        ),
        "status": str(raw.get("status") or info.get("status") or "").lower(),
    }


def _normalize_fill(fill: Any) -> dict[str, Any]:
    raw = _as_dict(fill)
    info = _as_dict(raw.get("info"))
    return {
        "exchange_order_id": _first(raw, info, "order", "orderId", "exchange_order_id"),
        "symbol": str(raw.get("symbol") or info.get("symbol") or ""),
        "side": str(raw.get("side") or info.get("side") or "").lower(),
        "qty": str(raw.get("amount") or info.get("qty") or info.get("quantity") or ""),
        "price": str(raw.get("price") or info.get("price") or ""),
        "fee": raw.get("fee") or info.get("commission"),
        "timestamp_ms": raw.get("timestamp") or info.get("time"),
    }


def _normalize_position(symbol: str, positions: list[Any]) -> dict[str, Any]:
    for position in positions:
        raw = _as_dict(position)
        if raw and str(raw.get("symbol") or "") != symbol:
            continue
        qty = abs(_decimal(raw.get("size") or raw.get("contracts") or raw.get("qty")))
        if qty <= 0:
            continue
        return {
            "symbol": str(raw.get("symbol") or symbol),
            "side": str(raw.get("side") or "").lower(),
            "qty": str(qty),
            "entry_price": str(raw.get("entry_price") or raw.get("entryPrice") or ""),
            "mark_price": str(raw.get("mark_price") or raw.get("markPrice") or ""),
            "unrealized_pnl": str(
                raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or ""
            ),
            "liquidation_price": str(
                raw.get("liquidation_price") or raw.get("liquidationPrice") or ""
            ),
            "position_flat": False,
        }
    return {
        "symbol": symbol,
        "side": "",
        "qty": "0",
        "position_flat": True,
    }


def _blocked(
    *,
    now_ms: int,
    blockers: list[str],
    protection_set: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_exchange_snapshot_provider.v1",
        "status": "blocked",
        "now_ms": now_ms,
        "ticket_id": protection_set.get("ticket_id"),
        "exit_protection_set_id": protection_set.get("exit_protection_set_id"),
        "symbol": protection_set.get("symbol"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "snapshot": {},
        "exchange_read_called": False,
        "exchange_write_called": False,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _attempt_blocked(
    *,
    now_ms: int,
    blockers: list[str],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "brc.ticket_bound_attempt_exchange_snapshot_provider.v1",
        "status": "blocked",
        "now_ms": now_ms,
        "ticket_id": attempt.get("ticket_id"),
        "protected_submit_attempt_id": attempt.get("protected_submit_attempt_id"),
        "symbol": attempt.get("symbol"),
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
        "snapshot": {},
        "exchange_read_called": False,
        "exchange_write_called": False,
        "authority_boundary": ATTEMPT_AUTHORITY_BOUNDARY,
    }


def _row_by_id(
    conn: sa.engine.Connection,
    table_name: str,
    id_column: str,
    id_value: str,
) -> dict[str, Any]:
    table = sa.Table(table_name, sa.MetaData(), autoload_with=conn)
    row = conn.execute(sa.select(table).where(table.c[id_column] == id_value)).mappings().first()
    return dict(row) if row else {}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return dict(value.dict())
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _first(raw: dict[str, Any], info: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value not in {None, ""}:
            return str(value)
        value = info.get(key)
        if value not in {None, ""}:
            return str(value)
    return ""


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _snapshot_id(exit_protection_set_id: str, now_ms: int) -> str:
    return f"ticket_exchange_snapshot:{exit_protection_set_id}:{now_ms}"
