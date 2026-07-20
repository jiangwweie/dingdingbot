"""Typed local Order construction for one durable ticket-bound command."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType


class TicketBoundLocalOrderIdentityError(ValueError):
    """The persisted Command/Ticket identity cannot form a safe local order."""


def build_ticket_bound_local_order(
    *,
    command: dict[str, Any],
    signal_event_id: str,
    now_ms: int,
    order_type: OrderType,
) -> Order:
    """Build a local Order without collapsing Ticket identity into signal fields."""

    required = (
        "local_order_id",
        "exchange_command_id",
        "ticket_id",
        "account_id",
        "exchange_id",
        "exchange_instrument_id",
        "runtime_profile_id",
        "strategy_group_id",
        "exposure_episode_id",
        "gateway_symbol",
        "side",
        "order_role",
        "amount",
    )
    missing = [name for name in required if not str(command.get(name) or "").strip()]
    if missing or not str(signal_event_id or "").strip():
        raise TicketBoundLocalOrderIdentityError(
            "ticket_bound_local_order_identity_missing:"
            + ",".join([*missing, *([] if signal_event_id else ["signal_event_id"])])
        )
    direction = Direction.LONG if str(command["side"]) == "long" else Direction.SHORT
    return Order(
        id=str(command["local_order_id"]),
        signal_id=str(signal_event_id),
        symbol=str(command["gateway_symbol"]),
        direction=direction,
        order_type=order_type,
        order_role=OrderRole(str(command["order_role"])),
        price=_optional_decimal(command.get("price")),
        trigger_price=_optional_decimal(command.get("stop_price")),
        requested_qty=Decimal(str(command["amount"])),
        status=OrderStatus.CREATED,
        created_at=now_ms,
        updated_at=now_ms,
        reduce_only=command.get("reduce_only") is True,
        parent_order_id=command.get("parent_order_id"),
        signal_evaluation_id=None,
        ticket_id=str(command["ticket_id"]),
        exchange_command_id=str(command["exchange_command_id"]),
        account_id=str(command["account_id"]),
        exchange_id=str(command["exchange_id"]),
        exchange_instrument_id=str(command["exchange_instrument_id"]),
        runtime_profile_id=str(command["runtime_profile_id"]),
        strategy_group_id=str(command["strategy_group_id"]),
        exposure_episode_id=str(command["exposure_episode_id"]),
    )


def assert_ticket_bound_local_order_identity(
    *, order: Order, command: dict[str, Any], signal_event_id: str
) -> None:
    """Fail closed before dispatch if repository round-trip changed identity."""

    expected = {
        "id": str(command["local_order_id"]),
        "signal_id": str(signal_event_id),
        "ticket_id": str(command["ticket_id"]),
        "exchange_command_id": str(command["exchange_command_id"]),
        "account_id": str(command["account_id"]),
        "exchange_id": str(command["exchange_id"]),
        "exchange_instrument_id": str(command["exchange_instrument_id"]),
        "runtime_profile_id": str(command["runtime_profile_id"]),
        "strategy_group_id": str(command["strategy_group_id"]),
        "exposure_episode_id": str(command["exposure_episode_id"]),
    }
    mismatched = [name for name, value in expected.items() if getattr(order, name) != value]
    if order.signal_evaluation_id is not None:
        mismatched.append("signal_evaluation_id")
    if mismatched:
        raise TicketBoundLocalOrderIdentityError(
            "ticket_bound_local_order_roundtrip_mismatch:" + ",".join(mismatched)
        )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
