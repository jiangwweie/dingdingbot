#!/usr/bin/env python3
"""Read-only exchange snapshot provider for ticket-bound lifecycle reconciliation."""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa

from src.application.action_time.exchange_scope import (
    TicketBoundExchangeScope,
    resolve_ticket_bound_exchange_scope,
    validate_gateway_identity_for_scope,
)


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
    scope_resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=str(protection_set.get("ticket_id") or ""),
        now_ms=now_ms,
    )
    if scope_resolution.status != "resolved" or scope_resolution.scope is None:
        return _blocked(
            now_ms=now_ms,
            blockers=list(scope_resolution.blockers),
            protection_set=protection_set,
        )
    scope = scope_resolution.scope
    core = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=scope,
        snapshot_identity=set_id,
        gateway=gateway,
        timeout_seconds=timeout_seconds,
        recent_fill_limit=recent_fill_limit,
        now_ms=now_ms,
        authority_boundary=AUTHORITY_BOUNDARY,
    )
    return {
        "schema": "brc.ticket_bound_exchange_snapshot_provider.v1",
        "status": core["status"],
        "now_ms": now_ms,
        "ticket_id": protection_set.get("ticket_id"),
        "exit_protection_set_id": set_id,
        "symbol": scope.canonical_symbol,
        "first_blocker": core["first_blocker"],
        "blockers": core["blockers"],
        "snapshot": core["snapshot"],
        "exchange_read_called": core["exchange_read_called"],
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
    scope_resolution = resolve_ticket_bound_exchange_scope(
        conn,
        ticket_id=str(attempt.get("ticket_id") or ""),
        now_ms=now_ms,
    )
    if scope_resolution.status != "resolved" or scope_resolution.scope is None:
        return _attempt_blocked(
            now_ms=now_ms,
            blockers=list(scope_resolution.blockers),
            attempt=attempt,
        )
    scope = scope_resolution.scope
    core = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=scope,
        snapshot_identity=attempt_id,
        gateway=gateway,
        timeout_seconds=timeout_seconds,
        recent_fill_limit=recent_fill_limit,
        now_ms=now_ms,
        authority_boundary=ATTEMPT_AUTHORITY_BOUNDARY,
    )
    return {
        "schema": "brc.ticket_bound_attempt_exchange_snapshot_provider.v1",
        "status": core["status"],
        "now_ms": now_ms,
        "ticket_id": attempt.get("ticket_id"),
        "protected_submit_attempt_id": attempt_id,
        "symbol": scope.canonical_symbol,
        "first_blocker": core["first_blocker"],
        "blockers": core["blockers"],
        "snapshot": core["snapshot"],
        "exchange_read_called": core["exchange_read_called"],
        "exchange_write_called": False,
        "authority_boundary": ATTEMPT_AUTHORITY_BOUNDARY,
    }


async def fetch_resolved_ticket_bound_exchange_snapshot(
    *,
    scope: TicketBoundExchangeScope,
    snapshot_identity: str,
    gateway: Any,
    timeout_seconds: float,
    recent_fill_limit: int,
    now_ms: int,
    authority_boundary: str = AUTHORITY_BOUNDARY,
) -> dict[str, Any]:
    """Perform exchange reads without any PG connection or transaction."""

    blockers = _gateway_method_blockers(gateway)
    blockers.extend(_gateway_scope_blockers(gateway, scope))
    if blockers:
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "snapshot": {},
            "exchange_read_called": False,
        }
    try:
        open_orders, recent_fills, positions = await asyncio.wait_for(
            asyncio.gather(
                gateway.fetch_all_open_orders(scope.exchange_symbol),
                gateway.fetch_my_trades(
                    scope.exchange_symbol,
                    limit=recent_fill_limit,
                ),
                gateway.fetch_position_rows(scope.exchange_symbol),
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        blockers = ["exchange_snapshot_fetch_timeout"]
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "snapshot": {},
            "exchange_read_called": True,
        }
    except Exception as exc:
        blockers = [f"exchange_snapshot_fetch_failed:{type(exc).__name__}"]
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "snapshot": {},
            "exchange_read_called": True,
        }
    position, position_blockers = _normalize_position(scope, positions or [])
    snapshot = {
        "snapshot_id": _snapshot_id(snapshot_identity, now_ms),
        "source": "official_runtime_exchange_gateway",
        "exchange_read_called": True,
        "exchange_write_called": False,
        "account_id": scope.account_id,
        "symbol": scope.canonical_symbol,
        "exchange_instrument_id": scope.exchange_instrument_id,
        "exchange_id": scope.exchange_id,
        "exchange_symbol": scope.exchange_symbol,
        "position_mode": scope.position_mode,
        "position_side": scope.position_side,
        "netting_domain_key": scope.netting_domain_key,
        "open_orders": [_normalize_open_order(order) for order in open_orders or []],
        "recent_fills": [_normalize_fill(fill) for fill in recent_fills or []],
        "position": position,
        "fetched_at_ms": now_ms,
        "authority_boundary": authority_boundary,
    }
    return {
        "status": "blocked" if position_blockers else "snapshot_ready",
        "first_blocker": position_blockers[0] if position_blockers else None,
        "blockers": position_blockers,
        "snapshot": snapshot,
        "exchange_read_called": True,
    }


def _gateway_method_blockers(gateway: Any) -> list[str]:
    if gateway is None:
        return ["exchange_snapshot_gateway_required"]
    blockers: list[str] = []
    for name in (
        "fetch_all_open_orders",
        "fetch_my_trades",
        "fetch_position_rows",
    ):
        if not callable(getattr(gateway, name, None)):
            blockers.append(f"exchange_snapshot_gateway_missing_{name}")
    return blockers


def _gateway_scope_blockers(
    gateway: Any,
    scope: TicketBoundExchangeScope,
) -> list[str]:
    return validate_gateway_identity_for_scope(
        scope,
        gateway_account_id=getattr(gateway, "runtime_account_id", None),
        gateway_exchange_id=getattr(gateway, "runtime_exchange_id", None),
    )


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
        "position_side": str(
            raw.get("positionSide")
            or raw.get("position_side")
            or info.get("positionSide")
            or ""
        ).upper(),
        "reduce_only": _as_bool(
            raw.get("reduceOnly")
            if "reduceOnly" in raw
            else raw.get("reduce_only", info.get("reduceOnly"))
        ),
        "close_position": _as_bool(
            raw.get("closePosition")
            if "closePosition" in raw
            else raw.get("close_position", info.get("closePosition"))
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
        "position_side": str(
            raw.get("positionSide")
            or raw.get("position_side")
            or info.get("positionSide")
            or ""
        ).upper(),
        "qty": str(raw.get("amount") or info.get("qty") or info.get("quantity") or ""),
        "price": str(raw.get("price") or info.get("price") or ""),
        "fee": raw.get("fee") or info.get("commission"),
        "realized_pnl": (
            raw.get("realizedPnl")
            or raw.get("realized_pnl")
            or info.get("realizedPnl")
        ),
        "timestamp_ms": raw.get("timestamp") or info.get("time"),
    }


def _normalize_position(
    scope: TicketBoundExchangeScope,
    positions: list[Any],
) -> tuple[dict[str, Any], list[str]]:
    matching: list[dict[str, Any]] = []
    malformed = False
    for position in positions:
        raw = _as_dict(position)
        if not raw:
            malformed = True
            continue
        raw_symbol = str(raw.get("symbol") or "").strip()
        if not raw_symbol:
            malformed = True
            continue
        if raw_symbol != scope.exchange_symbol:
            continue
        qty = _decimal_optional(
            raw.get("size")
            if raw.get("size") is not None
            else raw.get("contracts", raw.get("qty"))
        )
        if qty is None:
            malformed = True
            continue
        info = _as_dict(raw.get("info"))
        position_side = str(
            raw.get("position_side")
            or raw.get("positionSide")
            or info.get("positionSide")
            or ""
        ).upper()
        matching.append(
            {
                **raw,
                "_qty": abs(qty),
                "_position_side": position_side,
            }
        )

    if malformed:
        return _unknown_position(scope), ["exchange_position_snapshot_malformed"]

    if scope.position_mode == "hedge":
        ambiguous = [
            row
            for row in matching
            if row["_qty"] > 0 and row["_position_side"] not in {"LONG", "SHORT"}
        ]
        if ambiguous:
            return _unknown_position(scope), ["exchange_position_side_missing"]
        target = [
            row
            for row in matching
            if row["_position_side"] == scope.position_side and row["_qty"] > 0
        ]
    else:
        invalid_bucket = [
            row
            for row in matching
            if row["_qty"] > 0 and row["_position_side"] not in {"", "BOTH"}
        ]
        if invalid_bucket:
            return _unknown_position(scope), ["exchange_position_mode_mismatch"]
        target = [row for row in matching if row["_qty"] > 0]

    if len(target) > 1:
        return _unknown_position(scope), ["exchange_position_target_ambiguous"]
    if not target:
        return {
            "symbol": scope.canonical_symbol,
            "exchange_symbol": scope.exchange_symbol,
            "side": scope.side,
            "position_side": scope.position_side or "BOTH",
            "position_bucket": scope.position_bucket,
            "qty": "0",
            "position_flat": True,
            "truth_state": "flat",
        }, []

    raw = target[0]
    observed_side = str(raw.get("side") or "").lower()
    if observed_side and observed_side != scope.side:
        return _unknown_position(scope), ["exchange_position_direction_conflict"]
    return {
        "symbol": scope.canonical_symbol,
        "exchange_symbol": scope.exchange_symbol,
        "side": scope.side,
        "position_side": scope.position_side or "BOTH",
        "position_bucket": scope.position_bucket,
        "qty": str(raw["_qty"]),
        "entry_price": str(raw.get("entry_price") or raw.get("entryPrice") or ""),
        "mark_price": str(raw.get("mark_price") or raw.get("markPrice") or ""),
        "unrealized_pnl": str(
            raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or ""
        ),
        "liquidation_price": str(
            raw.get("liquidation_price") or raw.get("liquidationPrice") or ""
        ),
        "position_flat": False,
        "truth_state": "active",
    }, []


def _unknown_position(scope: TicketBoundExchangeScope) -> dict[str, Any]:
    return {
        "symbol": scope.canonical_symbol,
        "exchange_symbol": scope.exchange_symbol,
        "side": scope.side,
        "position_side": scope.position_side or "BOTH",
        "position_bucket": scope.position_bucket,
        "qty": "",
        "position_flat": False,
        "truth_state": "unknown",
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


def _decimal_optional(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _snapshot_id(exit_protection_set_id: str, now_ms: int) -> str:
    return f"ticket_exchange_snapshot:{exit_protection_set_id}:{now_ms}"
