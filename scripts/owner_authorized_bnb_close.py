#!/usr/bin/env python3
"""Owner-authorized BNB close / residual-protection cleanup.

This script is intentionally narrower than a product action API. It supports
only the explicit Owner-approved scope for the current BNB live acceptance:
BNB/USDT:USDT LONG, max 0.01 BNB. Default mode is dry-run.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.position_projection_service import PositionProjectionService
from src.domain.models import Order, OrderAuditEventType, OrderAuditTriggerSource, OrderRole, OrderStatus
from src.infrastructure.database import get_pg_session_maker
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.pg_order_repository import PgOrderRepository
from src.infrastructure.pg_position_repository import PgPositionRepository


SYMBOL = "BNB/USDT:USDT"
SIDE = "LONG"
MAX_AMOUNT = Decimal("0.01")
APPROVAL_ENV = "OWNER_APPROVED_BNB_CLOSE_SCOPE"
APPROVAL_VALUE = "BNB/USDT:USDT:LONG:0.01:close_or_cancel_residual_protection:2026-06-04"
MODE_ENV = "OWNER_BNB_CLOSE_MODE"
DEFAULT_SIGNAL_PREFIX = "owner-live-auth-"
PROTECTION_ROLES = {OrderRole.SL, OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}
ACTIVE_ORDER_STATUSES = {OrderStatus.SUBMITTED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}


class _NoopCapitalProtection:
    async def record_exit_projection(self, **_kwargs: Any) -> None:
        return None


@dataclass
class CloseContext:
    signal_id: str | None
    pg_active_positions: list[Any]
    exchange_positions: list[Any]
    chain_orders: list[Order]
    open_protection_orders: list[Order]


def _mode() -> str:
    return (os.environ.get(MODE_ENV) or "dry_run").strip().lower()


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {
            str(k): _json_value(v)
            for k, v in value.__dict__.items()
            if not str(k).startswith("_")
        }
    return value


def _order_json(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "signal_id": order.signal_id,
        "exchange_order_id": order.exchange_order_id,
        "symbol": order.symbol,
        "direction": _json_value(order.direction),
        "order_role": _json_value(order.order_role),
        "order_type": _json_value(order.order_type),
        "status": _json_value(order.status),
        "requested_qty": _json_value(order.requested_qty),
        "filled_qty": _json_value(order.filled_qty),
        "average_exec_price": _json_value(order.average_exec_price),
        "price": _json_value(order.price),
        "trigger_price": _json_value(order.trigger_price),
        "reduce_only": order.reduce_only,
        "parent_order_id": order.parent_order_id,
        "exit_reason": order.exit_reason,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _position_qty(position: Any) -> Decimal:
    for name in ("current_qty", "quantity", "size"):
        value = getattr(position, name, None)
        if value is not None:
            return Decimal(str(value))
    return Decimal("0")


def _position_side(position: Any) -> str:
    for name in ("direction", "side"):
        value = getattr(position, name, None)
        if value is not None:
            if hasattr(value, "value"):
                return str(value.value).upper()
            return str(value).upper()
    return ""


def _assert_static_env_guard() -> None:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
    }
    failures: list[str] = []
    for key, expected_value in expected.items():
        actual = (os.environ.get(key) or "").strip().lower()
        if actual != expected_value:
            failures.append(f"{key}={actual!r}, expected {expected_value!r}")
    if not os.environ.get("EXCHANGE_API_KEY") or not os.environ.get("EXCHANGE_API_SECRET"):
        failures.append("exchange credentials unavailable")
    if _mode() == "apply" and (os.environ.get(APPROVAL_ENV) or "").strip() != APPROVAL_VALUE:
        failures.append(f"{APPROVAL_ENV} must equal {APPROVAL_VALUE}")
    if failures:
        raise RuntimeError("BNB close guard failed: " + "; ".join(failures))


async def _write_audit(
    session_maker,
    *,
    order: Order,
    old_status: str | None,
    new_status: str,
    event_type: OrderAuditEventType,
    metadata: dict[str, Any],
) -> str:
    audit_id = f"audit_{uuid.uuid4().hex[:8]}"
    async with session_maker() as session:
        await session.execute(
            text(
                """
                INSERT INTO order_audit_logs (
                    id, order_id, signal_id, old_status, new_status,
                    event_type, triggered_by, metadata, created_at
                ) VALUES (
                    :id, :order_id, :signal_id, :old_status, :new_status,
                    :event_type, :triggered_by, :metadata, :created_at
                )
                """
            ),
            {
                "id": audit_id,
                "order_id": order.id,
                "signal_id": order.signal_id,
                "old_status": old_status,
                "new_status": new_status,
                "event_type": event_type.value,
                "triggered_by": OrderAuditTriggerSource.USER.value,
                "metadata": json.dumps(metadata, ensure_ascii=False, default=str),
                "created_at": int(time.time() * 1000),
            },
        )
        await session.commit()
    return audit_id


def _choose_signal_id(pg_active_positions: list[Any], orders: list[Order]) -> str | None:
    active_signal_ids = [getattr(pos, "signal_id", None) for pos in pg_active_positions if getattr(pos, "signal_id", None)]
    if len(set(active_signal_ids)) == 1:
        return str(active_signal_ids[0])
    candidates: dict[str, int] = {}
    for order in orders:
        if order.symbol != SYMBOL or not order.signal_id:
            continue
        if not str(order.signal_id).startswith(DEFAULT_SIGNAL_PREFIX):
            continue
        if order.order_role in {OrderRole.ENTRY, OrderRole.TP1, OrderRole.SL}:
            candidates[str(order.signal_id)] = max(candidates.get(str(order.signal_id), 0), int(order.created_at or 0))
    if not candidates:
        return None
    return sorted(candidates.items(), key=lambda item: item[1], reverse=True)[0][0]


async def _load_context(position_repo, order_repo, gateway) -> CloseContext:
    pg_active = await position_repo.list_active(symbol=SYMBOL, limit=10)
    exchange_positions = await gateway.fetch_positions(SYMBOL)
    symbol_orders = await order_repo.get_orders_by_symbol(SYMBOL, limit=200)
    signal_id = _choose_signal_id(pg_active, symbol_orders)
    chain_orders = [order for order in symbol_orders if signal_id and order.signal_id == signal_id]
    open_protection = [
        order for order in chain_orders
        if order.order_role in PROTECTION_ROLES and order.status in ACTIVE_ORDER_STATUSES
    ]
    return CloseContext(
        signal_id=signal_id,
        pg_active_positions=pg_active,
        exchange_positions=exchange_positions,
        chain_orders=chain_orders,
        open_protection_orders=open_protection,
    )


def _validate_context(context: CloseContext) -> None:
    if len(context.pg_active_positions) > 1:
        raise RuntimeError(f"expected at most one active PG BNB position; found {len(context.pg_active_positions)}")
    if len(context.exchange_positions) > 1:
        raise RuntimeError(f"expected at most one active exchange BNB position; found {len(context.exchange_positions)}")
    if bool(context.pg_active_positions) != bool(context.exchange_positions):
        raise RuntimeError(
            "PG/exchange active BNB position presence mismatch; refusing live close "
            f"pg={len(context.pg_active_positions)} exchange={len(context.exchange_positions)}"
        )
    for position in [*context.pg_active_positions, *context.exchange_positions]:
        symbol = getattr(position, "symbol", SYMBOL)
        qty = _position_qty(position)
        side = _position_side(position)
        if symbol != SYMBOL:
            raise RuntimeError(f"unexpected symbol in BNB close scope: {symbol}")
        if qty <= Decimal("0") or qty > MAX_AMOUNT:
            raise RuntimeError(f"unexpected BNB close quantity: {qty}")
        if side not in {SIDE, "LONG"}:
            raise RuntimeError(f"unexpected BNB close side: {side}")
    if context.pg_active_positions and context.exchange_positions:
        pg_qty = _position_qty(context.pg_active_positions[0])
        exchange_qty = _position_qty(context.exchange_positions[0])
        if pg_qty != exchange_qty:
            raise RuntimeError(f"PG/exchange BNB quantity mismatch: {pg_qty} != {exchange_qty}")
    if not context.signal_id and (context.pg_active_positions or context.open_protection_orders):
        raise RuntimeError("unable to resolve current BNB signal scope")
    for order in context.open_protection_orders:
        if order.symbol != SYMBOL:
            raise RuntimeError(f"unexpected protection symbol: {order.symbol}")
        if order.requested_qty > MAX_AMOUNT:
            raise RuntimeError(f"unexpected protection quantity: {order.requested_qty}")


def _planned_action(context: CloseContext) -> str:
    if context.pg_active_positions or context.exchange_positions:
        return "close_position_then_cancel_protection"
    if context.open_protection_orders:
        return "cancel_residual_protection_only"
    return "noop_already_flat"


async def _cancel_residual_protection(
    *,
    context: CloseContext,
    order_repo,
    gateway,
    session_maker,
    reason: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for order in context.open_protection_orders:
        old_status = order.status.value if hasattr(order.status, "value") else str(order.status)
        exchange_result: dict[str, Any] = {"attempted": False}
        if order.exchange_order_id:
            try:
                result = await gateway.cancel_order(order.exchange_order_id, order.symbol)
                exchange_result = {
                    "attempted": True,
                    "status": _json_value(result.status),
                    "exchange_order_id": result.exchange_order_id,
                    "message": result.message,
                }
            except Exception as exc:
                exchange_result = {
                    "attempted": True,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
        order.status = OrderStatus.CANCELED
        order.exit_reason = reason
        order.updated_at = int(time.time() * 1000)
        await order_repo.save(order)
        audit_id = await _write_audit(
            session_maker,
            order=order,
            old_status=old_status,
            new_status=OrderStatus.CANCELED.value,
            event_type=OrderAuditEventType.ORDER_CANCELED,
            metadata={
                "source": "owner_authorized_bnb_close",
                "reason": reason,
                "scope": APPROVAL_VALUE,
                "exchange_cancel": exchange_result,
            },
        )
        actions.append(
            {
                "action": "cancel_residual_protection",
                "order": _order_json(order),
                "old_status": old_status,
                "exchange_result": exchange_result,
                "audit_id": audit_id,
            }
        )
    return actions


async def _close_active_position(
    *,
    context: CloseContext,
    order_repo,
    position_repo,
    gateway,
    session_maker,
    reason: str,
) -> list[dict[str, Any]]:
    lifecycle = OrderLifecycleService(order_repo)
    orchestrator = ExecutionOrchestrator(
        capital_protection=_NoopCapitalProtection(),
        order_lifecycle=lifecycle,
        gateway=gateway,
        position_projection_service=PositionProjectionService(position_repo),
    )
    position = context.pg_active_positions[0] if context.pg_active_positions else context.exchange_positions[0]
    result = await orchestrator.execute_controlled_close(
        position=position,
        reason=reason,
        max_amount=MAX_AMOUNT,
    )
    close_order = result["close_order"]
    close_audit_id = await _write_audit(
        session_maker,
        order=close_order,
        old_status=None,
        new_status=close_order.status.value if hasattr(close_order.status, "value") else str(close_order.status),
        event_type=OrderAuditEventType.ORDER_FILLED,
        metadata={
            "source": "owner_authorized_bnb_close",
            "reason": reason,
            "scope": APPROVAL_VALUE,
            "terminalized_protection_orders": [
                getattr(order, "id", None)
                for order in result.get("terminalized_protection_orders") or []
            ],
        },
    )
    return [
        {
            "action": "close_position_then_cancel_protection",
            "close_order": _order_json(close_order),
            "terminalized_protection_orders": [
                _order_json(order) for order in result.get("terminalized_protection_orders") or []
            ],
            "audit_id": close_audit_id,
        }
    ]


async def _run() -> dict[str, Any]:
    _assert_static_env_guard()
    mode = _mode()
    if mode not in {"dry_run", "apply"}:
        raise RuntimeError(f"unsupported mode: {mode}")

    session_maker = get_pg_session_maker()
    order_repo = PgOrderRepository(session_maker)
    position_repo = PgPositionRepository(session_maker)
    gateway = ExchangeGateway(
        os.environ.get("EXCHANGE_NAME", "binance"),
        os.environ["EXCHANGE_API_KEY"],
        os.environ["EXCHANGE_API_SECRET"],
        testnet=False,
    )
    await gateway.initialize()
    try:
        before = await _load_context(position_repo, order_repo, gateway)
        _validate_context(before)
        action = _planned_action(before)
        actions: list[dict[str, Any]] = []
        reason = "owner_authorized_bnb_position_close_2026_06_04"
        if mode == "apply":
            if action == "close_position_then_cancel_protection":
                actions = await _close_active_position(
                    context=before,
                    order_repo=order_repo,
                    position_repo=position_repo,
                    gateway=gateway,
                    session_maker=session_maker,
                    reason=reason,
                )
            elif action == "cancel_residual_protection_only":
                actions = await _cancel_residual_protection(
                    context=before,
                    order_repo=order_repo,
                    gateway=gateway,
                    session_maker=session_maker,
                    reason=reason,
                )

        after = await _load_context(position_repo, order_repo, gateway)
        return {
            "mode": mode,
            "scope": {
                "symbol": SYMBOL,
                "side": SIDE,
                "max_amount": str(MAX_AMOUNT),
                "approval_value": APPROVAL_VALUE if mode == "apply" else "required_for_apply",
            },
            "planned_action": action,
            "before": {
                "signal_id": before.signal_id,
                "pg_active_positions": _json_value(before.pg_active_positions),
                "exchange_positions": _json_value(before.exchange_positions),
                "chain_orders": [_order_json(order) for order in before.chain_orders],
                "open_protection_orders": [_order_json(order) for order in before.open_protection_orders],
            },
            "actions": actions,
            "after": {
                "signal_id": after.signal_id,
                "pg_active_positions": _json_value(after.pg_active_positions),
                "exchange_positions": _json_value(after.exchange_positions),
                "chain_orders": [_order_json(order) for order in after.chain_orders],
                "open_protection_orders": [_order_json(order) for order in after.open_protection_orders],
            },
            "safety": {
                "places_market_close": action == "close_position_then_cancel_protection" and mode == "apply",
                "cancels_residual_protection": action in {
                    "close_position_then_cancel_protection",
                    "cancel_residual_protection_only",
                } and mode == "apply",
                "other_symbol_allowed": False,
                "other_side_allowed": False,
                "max_attempts": 1,
            },
        }
    finally:
        await gateway.close()


def main() -> None:
    result = asyncio.run(_run())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
