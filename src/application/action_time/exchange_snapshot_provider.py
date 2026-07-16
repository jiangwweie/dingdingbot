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
ACCOUNT_EXPOSURE_MAX_AGE_MS = 30_000

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
    funding_start_time_ms = _ticket_entry_fill_time_ms(
        conn,
        str(protection_set.get("ticket_id") or ""),
    )
    core = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=scope,
        snapshot_identity=set_id,
        gateway=gateway,
        timeout_seconds=timeout_seconds,
        recent_fill_limit=recent_fill_limit,
        now_ms=now_ms,
        funding_start_time_ms=funding_start_time_ms,
        funding_end_time_ms=now_ms if funding_start_time_ms is not None else None,
        conditional_parent_order_ids=load_ticket_conditional_parent_order_ids(
            conn,
            ticket_id=str(protection_set.get("ticket_id") or ""),
        ),
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
    funding_start_time_ms = _ticket_entry_fill_time_ms(
        conn,
        str(attempt.get("ticket_id") or ""),
    )
    core = await fetch_resolved_ticket_bound_exchange_snapshot(
        scope=scope,
        snapshot_identity=attempt_id,
        gateway=gateway,
        timeout_seconds=timeout_seconds,
        recent_fill_limit=recent_fill_limit,
        now_ms=now_ms,
        funding_start_time_ms=funding_start_time_ms,
        funding_end_time_ms=now_ms if funding_start_time_ms is not None else None,
        conditional_parent_order_ids=load_ticket_conditional_parent_order_ids(
            conn,
            ticket_id=str(attempt.get("ticket_id") or ""),
        ),
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
    funding_start_time_ms: int | None = None,
    funding_end_time_ms: int | None = None,
    conditional_parent_order_ids: list[str] | None = None,
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
    exchange_request_count = 0
    try:
        narrow_fetch = getattr(gateway, "fetch_ticket_lifecycle_snapshot", None)
        funding_fetch = getattr(gateway, "fetch_funding_income", None)
        should_fetch_funding = (
            (callable(narrow_fetch) or callable(funding_fetch))
            and funding_start_time_ms is not None
            and funding_end_time_ms is not None
            and funding_end_time_ms >= funding_start_time_ms
        )
        conditional_fetch = getattr(gateway, "fetch_conditional_order_lineage", None)
        should_fetch_conditional_lineage = bool(
            (callable(narrow_fetch) or callable(conditional_fetch))
            and conditional_parent_order_ids
        )
        account_exposure_fetch = getattr(
            gateway, "fetch_account_exposure_snapshot", None
        )
        should_fetch_account_exposure = callable(narrow_fetch) or callable(
            account_exposure_fetch
        )
        if callable(narrow_fetch):
            narrow_result = await asyncio.wait_for(
                narrow_fetch(
                    exchange_symbol=scope.exchange_symbol,
                    exchange_market_id=scope.canonical_symbol,
                    recent_fill_limit=recent_fill_limit,
                    funding_start_time_ms=(
                        int(funding_start_time_ms)
                        if should_fetch_funding
                        else None
                    ),
                    funding_end_time_ms=(
                        int(funding_end_time_ms) if should_fetch_funding else None
                    ),
                    conditional_parent_order_ids=list(
                        conditional_parent_order_ids or []
                    ),
                ),
                timeout=timeout_seconds,
            )
            if not isinstance(narrow_result, dict):
                raise RuntimeError("ticket_lifecycle_snapshot_root_not_object")
            open_orders = list(narrow_result.get("open_orders") or [])
            recent_fills = list(narrow_result.get("recent_fills") or [])
            positions = list(narrow_result.get("positions") or [])
            funding_result = dict(
                narrow_result.get("funding_result")
                or {"rows": [], "error": None}
            )
            conditional_result = dict(
                narrow_result.get("conditional_result")
                or {"rows": [], "error": None}
            )
            account_exposure_result = dict(
                narrow_result.get("account_exposure_result") or {}
            )
            commission_rate = dict(narrow_result.get("commission_rate") or {})
            market_rule = dict(narrow_result.get("market_rule") or {})
            exchange_request_count = int(
                narrow_result.get("exchange_request_count") or 0
            )
            should_fetch_funding = funding_start_time_ms is not None
            should_fetch_conditional_lineage = bool(
                conditional_parent_order_ids
            )
            should_fetch_account_exposure = True
        else:
            (
                open_orders,
                recent_fills,
                positions,
                funding_result,
                conditional_result,
                account_exposure_result,
            ) = await asyncio.wait_for(
                asyncio.gather(
                    gateway.fetch_all_open_orders(scope.exchange_symbol),
                    gateway.fetch_my_trades(
                        scope.exchange_symbol,
                        limit=recent_fill_limit,
                    ),
                    gateway.fetch_position_rows(scope.exchange_symbol),
                    _fetch_optional_funding_income(
                        funding_fetch=funding_fetch,
                        symbol=scope.exchange_symbol,
                        start_time_ms=int(funding_start_time_ms or 0),
                        end_time_ms=int(funding_end_time_ms or 0),
                    )
                    if should_fetch_funding
                    else asyncio.sleep(0, result={"rows": [], "error": None}),
                    _fetch_optional_conditional_order_lineage(
                        conditional_fetch=conditional_fetch,
                        symbol=scope.exchange_symbol,
                        parent_exchange_order_ids=list(
                            conditional_parent_order_ids or []
                        ),
                    )
                    if should_fetch_conditional_lineage
                    else asyncio.sleep(0, result={"rows": [], "error": None}),
                    account_exposure_fetch()
                    if should_fetch_account_exposure
                    else asyncio.sleep(0, result={}),
                ),
                timeout=timeout_seconds,
            )
            exchange_request_count = (
                3
                + int(should_fetch_funding)
                + int(should_fetch_conditional_lineage)
                + int(should_fetch_account_exposure)
            )
            commission_rate = {}
            market_rule = {}
    except TimeoutError:
        blockers = ["exchange_snapshot_fetch_timeout"]
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "snapshot": {},
            "exchange_read_called": True,
            "exchange_request_count": exchange_request_count,
        }
    except Exception as exc:
        blockers = [f"exchange_snapshot_fetch_failed:{type(exc).__name__}"]
        return {
            "status": "blocked",
            "first_blocker": blockers[0],
            "blockers": blockers,
            "snapshot": {},
            "exchange_read_called": True,
            "exchange_request_count": exchange_request_count,
        }
    position, position_blockers = _normalize_position(scope, positions or [])
    funding_income = list(funding_result.get("rows") or [])
    funding_error = funding_result.get("error")
    conditional_order_lineage = _normalize_conditional_order_lineage(
        list(conditional_result.get("rows") or [])
    )
    normalized_fills = [_normalize_fill(fill) for fill in recent_fills or []]
    _bind_conditional_parent_ids(
        normalized_fills,
        conditional_order_lineage=conditional_order_lineage,
    )
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
        "recent_fills": normalized_fills,
        "conditional_order_lineage": conditional_order_lineage,
        "conditional_order_lineage_available": (
            should_fetch_conditional_lineage
            and conditional_result.get("error") is None
        ),
        "conditional_order_lineage_error": conditional_result.get("error"),
        "funding_income": _normalize_funding_income(
            funding_income or [],
            ticket_id=scope.ticket_id,
            canonical_symbol=scope.canonical_symbol,
            start_time_ms=funding_start_time_ms,
            end_time_ms=funding_end_time_ms,
        ),
        "funding_income_available": should_fetch_funding and funding_error is None,
        "funding_income_error": funding_error,
        "account_exposure": _normalize_account_exposure(
            scope=scope,
            payload=(
                dict(account_exposure_result)
                if isinstance(account_exposure_result, dict)
                else {}
            ),
            now_ms=now_ms,
        ),
        "commission_rate": commission_rate,
        "market_rule": {
            **market_rule,
            "exchange_instrument_id": scope.exchange_instrument_id,
            "exchange_id": scope.exchange_id,
        }
        if market_rule
        else {},
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
        "exchange_request_count": exchange_request_count,
    }


def _normalize_account_exposure(
    *,
    scope: TicketBoundExchangeScope,
    payload: dict[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    if not payload:
        return {}
    normalized = dict(payload)
    blockers = [str(item) for item in payload.get("blockers", []) if item]
    if str(payload.get("account_id") or "") != scope.account_id:
        blockers.append("account_exposure_account_mismatch")
    if str(payload.get("exchange_id") or "") != scope.exchange_id:
        blockers.append("account_exposure_exchange_mismatch")
    observed_at_ms = int(payload.get("observed_at_ms") or 0)
    age_ms = now_ms - observed_at_ms
    if observed_at_ms <= 0 or age_ms < 0 or age_ms > ACCOUNT_EXPOSURE_MAX_AGE_MS:
        blockers.append("account_exposure_snapshot_stale")
    if blockers:
        normalized["status"] = "invalid"
        normalized["effective_account_exposure_leverage"] = None
    normalized["blockers"] = _dedupe(blockers)
    return normalized


async def _fetch_optional_funding_income(
    *,
    funding_fetch: Any,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
) -> dict[str, Any]:
    try:
        rows = await funding_fetch(
            symbol,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
    except Exception as exc:
        return {"rows": [], "error": type(exc).__name__}
    return {"rows": list(rows or []), "error": None}


async def _fetch_optional_conditional_order_lineage(
    *,
    conditional_fetch: Any,
    symbol: str,
    parent_exchange_order_ids: list[str],
) -> dict[str, Any]:
    try:
        rows = await conditional_fetch(symbol, parent_exchange_order_ids)
    except Exception as exc:
        return {"rows": [], "error": type(exc).__name__}
    return {"rows": list(rows or []), "error": None}


def load_ticket_conditional_parent_order_ids(
    conn: sa.engine.Connection,
    *,
    ticket_id: str,
) -> list[str]:
    if not ticket_id:
        return []
    ids: list[str] = []
    inspector = sa.inspect(conn)
    if inspector.has_table("brc_ticket_bound_exit_protection_orders"):
        table = _table(conn, "brc_ticket_bound_exit_protection_orders")
        rows = conn.execute(
            sa.select(table.c.exchange_order_id).where(
                table.c.ticket_id == ticket_id,
                table.c.role.in_(("SL", "RUNNER_SL")),
            )
        ).scalars()
        ids.extend(str(value).strip() for value in rows if str(value or "").strip())
    if ids or not inspector.has_table("brc_ticket_bound_protected_submit_attempts"):
        return list(dict.fromkeys(ids))
    attempts = _table(conn, "brc_ticket_bound_protected_submit_attempts")
    raw_submit_result = conn.execute(
        sa.select(attempts.c.submit_result)
        .where(attempts.c.ticket_id == ticket_id)
        .order_by(attempts.c.updated_at_ms.desc())
        .limit(1)
    ).scalar_one_or_none()
    submit_result = _as_dict(raw_submit_result)
    for order in submit_result.get("submitted_orders", []):
        if not isinstance(order, dict):
            continue
        if str(order.get("order_role") or "").upper() not in {"SL", "RUNNER_SL"}:
            continue
        exchange_order_id = str(order.get("exchange_order_id") or "").strip()
        if exchange_order_id:
            ids.append(exchange_order_id)
    return list(dict.fromkeys(ids))


def _gateway_method_blockers(gateway: Any) -> list[str]:
    if gateway is None:
        return ["exchange_snapshot_gateway_required"]
    if callable(getattr(gateway, "fetch_ticket_lifecycle_snapshot", None)):
        return []
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
    side = str(raw.get("side") or info.get("side") or "").lower()
    fee = raw.get("fee")
    if not isinstance(fee, dict):
        commission = raw.get("commission") or info.get("commission")
        commission_asset = (
            raw.get("commissionAsset") or info.get("commissionAsset")
        )
        fee = (
            {
                "cost": str(commission),
                "currency": str(commission_asset or "") or None,
            }
            if commission not in (None, "")
            else None
        )
    return {
        "exchange_trade_id": _first(
            raw,
            info,
            "id",
            "tradeId",
            "trade_id",
            "exchange_trade_id",
        ),
        "exchange_order_id": _first(raw, info, "order", "orderId", "exchange_order_id"),
        "symbol": str(raw.get("symbol") or info.get("symbol") or ""),
        "side": side,
        "position_side": str(
            raw.get("positionSide")
            or raw.get("position_side")
            or info.get("positionSide")
            or ""
        ).upper(),
        "qty": str(
            raw.get("amount")
            or raw.get("qty")
            or info.get("qty")
            or info.get("quantity")
            or ""
        ),
        "price": str(raw.get("price") or info.get("price") or ""),
        "fee": fee,
        "liquidity_role": normalize_liquidity_role(
            raw.get("takerOrMaker") or info.get("takerOrMaker"),
            raw.get("maker") if raw.get("maker") is not None else info.get("maker"),
            (
                raw.get("buyerMaker")
                if raw.get("buyerMaker") is not None
                else info.get("buyerMaker")
            ),
            trade_side=side,
        ),
        "realized_pnl": (
            raw.get("realizedPnl")
            or raw.get("realized_pnl")
            or info.get("realizedPnl")
        ),
        "timestamp_ms": (
            raw.get("timestamp") or raw.get("timestamp_ms") or info.get("time")
        ),
    }


def normalize_liquidity_role(
    taker_or_maker: Any,
    maker: Any,
    buyer_maker: Any,
    *,
    trade_side: str,
) -> str | None:
    direct = str(taker_or_maker or "").strip().lower()
    if direct in {"maker", "taker"}:
        return direct
    maker_flag = _optional_bool(maker)
    if maker_flag is not None:
        return "maker" if maker_flag else "taker"
    buyer_maker_flag = _optional_bool(buyer_maker)
    normalized_side = str(trade_side or "").strip().lower()
    if buyer_maker_flag is None or normalized_side not in {"buy", "sell"}:
        return None
    owner_is_maker = (
        buyer_maker_flag if normalized_side == "buy" else not buyer_maker_flag
    )
    return "maker" if owner_is_maker else "taker"


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _normalize_conditional_order_lineage(rows: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = _as_dict(row)
        parent_id = str(item.get("parent_exchange_order_id") or "").strip()
        actual_id = str(item.get("actual_exchange_order_id") or "").strip()
        if not parent_id or not actual_id:
            continue
        normalized.append(
            {
                "parent_exchange_order_id": parent_id,
                "actual_exchange_order_id": actual_id,
                "client_order_id": str(item.get("client_order_id") or "").strip(),
                "status": str(item.get("status") or "").lower(),
            }
        )
    return normalized


def _bind_conditional_parent_ids(
    fills: list[dict[str, Any]],
    *,
    conditional_order_lineage: list[dict[str, Any]],
) -> None:
    parent_by_actual_id = {
        str(item["actual_exchange_order_id"]): str(
            item["parent_exchange_order_id"]
        )
        for item in conditional_order_lineage
    }
    client_by_actual_id = {
        str(item["actual_exchange_order_id"]): str(item.get("client_order_id") or "")
        for item in conditional_order_lineage
    }
    for fill in fills:
        actual_id = str(fill.get("exchange_order_id") or "").strip()
        parent_id = parent_by_actual_id.get(actual_id)
        if not parent_id:
            continue
        fill["parent_exchange_order_id"] = parent_id
        client_order_id = client_by_actual_id.get(actual_id)
        if client_order_id:
            fill["client_order_id"] = client_order_id


def _normalize_funding_income(
    rows: list[Any],
    *,
    ticket_id: str,
    canonical_symbol: str,
    start_time_ms: int | None,
    end_time_ms: int | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        raw = _as_dict(row)
        income_type = str(
            raw.get("incomeType") or raw.get("income_type") or ""
        ).upper()
        symbol = str(raw.get("symbol") or "").replace("/", "").split(":")[0]
        timestamp_ms = _int_optional(raw.get("time") or raw.get("timestamp"))
        if income_type != "FUNDING_FEE" or symbol != canonical_symbol:
            continue
        if timestamp_ms is None:
            continue
        if start_time_ms is not None and timestamp_ms < start_time_ms:
            continue
        if end_time_ms is not None and timestamp_ms > end_time_ms:
            continue
        normalized.append(
            {
                "income_id": str(
                    raw.get("tranId") or raw.get("id") or raw.get("income_id") or ""
                ),
                "ticket_id": ticket_id,
                "symbol": symbol,
                "income_type": income_type,
                "amount": str(raw.get("income") or raw.get("amount") or ""),
                "asset": str(raw.get("asset") or raw.get("currency") or "").upper(),
                "timestamp_ms": timestamp_ms,
                "attribution_basis": (
                    "single_active_position_exact_symbol_time_window"
                ),
            }
        )
    return sorted(
        normalized,
        key=lambda item: (item["timestamp_ms"], item["income_id"]),
    )


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


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _ticket_entry_fill_time_ms(
    conn: sa.engine.Connection,
    ticket_id: str,
) -> int | None:
    if not ticket_id:
        return None
    events = sa.Table(
        "brc_ticket_bound_lifecycle_events",
        sa.MetaData(),
        autoload_with=conn,
    )
    row = conn.execute(
        sa.select(events.c.event_payload)
        .where(
            events.c.ticket_id == ticket_id,
            events.c.event_type == "entry_filled",
        )
        .order_by(events.c.created_at_ms.asc())
        .limit(1)
    ).mappings().first()
    if not row:
        return None
    payload = _as_dict(row.get("event_payload"))
    fill = _as_dict(payload.get("entry_fill") or payload.get("fill"))
    return _int_optional(fill.get("fill_time_ms") or fill.get("timestamp_ms"))


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


def _int_optional(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _snapshot_id(exit_protection_set_id: str, now_ms: int) -> str:
    return f"ticket_exchange_snapshot:{exit_protection_set_id}:{now_ms}"
