"""Recover local runtime close projection from read-only exchange trade facts."""

from __future__ import annotations

import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Optional, Protocol

from src.domain.models import Direction, Order, OrderRole, OrderStatus, Position
from src.domain.runtime_exchange_close_projection_recovery import (
    RuntimeExchangeCloseProjectionRecoveryRequest,
    RuntimeExchangeCloseProjectionRecoveryResult,
    RuntimeExchangeCloseProjectionRecoveryStatus,
    recovery_id_for_trade,
)


class OrderRepositoryPort(Protocol):
    async def get_order(self, order_id: str) -> Optional[Order]:
        ...

    async def save(self, order: Order) -> None:
        ...


class PositionRepositoryPort(Protocol):
    async def get(self, position_id: str) -> Optional[Position]:
        ...

    async def list_active(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> list[Position]:
        ...


class OrderLifecyclePort(Protocol):
    async def update_order_filled(
        self,
        order_id: str,
        filled_qty: Decimal,
        average_exec_price: Decimal,
    ) -> Order:
        ...


class PositionProjectionPort(Protocol):
    async def project_exit_fill(self, exit_order: Order) -> Any:
        ...


class ExchangeTradeReadPort(Protocol):
    async def fetch_my_trades(self, symbol: str, limit: int = 50) -> list[Any]:
        ...


class RuntimeExchangeCloseProjectionRecoveryService:
    """Apply local close projection from an already-observed exchange trade.

    The service only reads exchange trade facts. It never sends exchange order
    writes; optional apply mode mutates local PG order/position projection.
    """

    def __init__(
        self,
        *,
        exchange_trade_source: ExchangeTradeReadPort | Any,
        order_repository: OrderRepositoryPort,
        position_repository: PositionRepositoryPort,
        order_lifecycle: OrderLifecyclePort,
        position_projection_service: PositionProjectionPort,
    ) -> None:
        self._exchange_trade_source = exchange_trade_source
        self._order_repository = order_repository
        self._position_repository = position_repository
        self._order_lifecycle = order_lifecycle
        self._position_projection_service = position_projection_service

    async def recover(
        self,
        request: RuntimeExchangeCloseProjectionRecoveryRequest,
        *,
        now_ms: int | None = None,
    ) -> RuntimeExchangeCloseProjectionRecoveryResult:
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        blockers: list[str] = []
        warnings: list[str] = []
        order = await self._order_repository.get_order(request.exit_local_order_id)
        if order is None:
            blockers.append("local_exit_order_not_found")
        elif order.symbol != request.symbol:
            blockers.append("local_exit_order_symbol_mismatch")
        elif order.order_role not in _EXIT_ORDER_ROLES:
            blockers.append("local_order_not_exit_or_protection")
        elif request.exit_exchange_order_id and str(order.exchange_order_id or "") not in {
            "",
            request.exit_exchange_order_id,
        }:
            blockers.append("local_exit_order_exchange_id_mismatch")

        position = None
        if order is not None:
            position = await self._position_repository.get(f"pos_{order.signal_id}")
            if position is None:
                active_positions = await self._position_repository.list_active(
                    symbol=request.symbol,
                    limit=10,
                )
                matching = [
                    item
                    for item in active_positions
                    if item.symbol == request.symbol and item.signal_id == order.signal_id
                ]
                if len(matching) == 1:
                    position = matching[0]
                elif len(matching) > 1:
                    blockers.append("multiple_matching_active_positions")
            if position is None:
                if order.status == OrderStatus.FILLED:
                    return self._result(
                        request=request,
                        status=(
                            RuntimeExchangeCloseProjectionRecoveryStatus
                            .ALREADY_PROJECTED
                        ),
                        order=order,
                        position=None,
                        trade=None,
                        blockers=[],
                        warnings=["local_position_already_absent"],
                        local_state_mutated=False,
                        order_status_changed=False,
                        position_projection_changed=False,
                        now_ms=now_ms,
                    )
                blockers.append("local_active_position_not_found")

        trade = await self._find_trade(request)
        if trade is None:
            blockers.append("exchange_close_trade_not_found")

        trade_qty = _trade_qty(trade)
        trade_price = _trade_price(trade)
        trade_side = _trade_side(trade)
        trade_timestamp = _trade_timestamp_ms(trade)

        expected_side = _expected_close_side(position.direction if position else None)
        if trade is not None:
            if _trade_symbol(trade) != request.symbol:
                blockers.append("exchange_trade_symbol_mismatch")
            if trade_qty is None or trade_qty <= Decimal("0"):
                blockers.append("exchange_trade_qty_missing")
            if trade_price is None or trade_price <= Decimal("0"):
                blockers.append("exchange_trade_price_missing")
            if expected_side is not None and trade_side != expected_side:
                blockers.append("exchange_trade_close_side_mismatch")
            if position is not None and trade_qty is not None:
                if trade_qty > position.current_qty:
                    blockers.append("exchange_trade_qty_exceeds_local_position")
                elif trade_qty < position.current_qty:
                    warnings.append("partial_close_projection")

        if blockers:
            return self._result(
                request=request,
                status=RuntimeExchangeCloseProjectionRecoveryStatus.BLOCKED,
                order=order,
                position=position,
                trade=trade,
                blockers=blockers,
                warnings=warnings,
                local_state_mutated=False,
                order_status_changed=False,
                position_projection_changed=False,
                now_ms=now_ms,
            )

        assert order is not None
        assert position is not None
        assert trade_qty is not None
        assert trade_price is not None

        if order.status == OrderStatus.FILLED and position.is_closed:
            return self._result(
                request=request,
                status=RuntimeExchangeCloseProjectionRecoveryStatus.ALREADY_PROJECTED,
                order=order,
                position=position,
                trade=trade,
                blockers=[],
                warnings=warnings,
                local_state_mutated=False,
                order_status_changed=False,
                position_projection_changed=False,
                now_ms=now_ms,
            )

        if not request.apply:
            return self._result(
                request=request,
                status=RuntimeExchangeCloseProjectionRecoveryStatus.READY_TO_APPLY,
                order=order,
                position=position,
                trade=trade,
                blockers=[],
                warnings=warnings,
                local_state_mutated=False,
                order_status_changed=False,
                position_projection_changed=False,
                now_ms=now_ms,
            )

        previous_order_status = order.status
        previous_position_qty = position.current_qty
        updated_order = await self._order_lifecycle.update_order_filled(
            order.id,
            filled_qty=trade_qty,
            average_exec_price=trade_price,
        )
        updated_order.filled_at = trade_timestamp or now_ms
        if updated_order.exit_reason is None:
            updated_order.exit_reason = "EXCHANGE_CLOSE_PROJECTION_RECOVERY"
        await self._order_repository.save(updated_order)
        projection_result = await self._position_projection_service.project_exit_fill(
            updated_order
        )
        projected_position = getattr(projection_result, "position", None)
        return self._result(
            request=request,
            status=RuntimeExchangeCloseProjectionRecoveryStatus.APPLIED,
            order=updated_order,
            position=projected_position or position,
            trade=trade,
            blockers=[],
            warnings=warnings,
            local_state_mutated=True,
            order_status_changed=previous_order_status != updated_order.status,
            position_projection_changed=not bool(
                getattr(projection_result, "was_already_processed", False)
            ),
            realized_pnl_delta=getattr(
                projection_result,
                "delta_realized_pnl",
                Decimal("0"),
            ),
            position_qty_before_override=previous_position_qty,
            now_ms=now_ms,
        )

    async def _find_trade(
        self,
        request: RuntimeExchangeCloseProjectionRecoveryRequest,
    ) -> Any | None:
        trades = await _fetch_my_trades(self._exchange_trade_source, request.symbol)
        for trade in trades:
            if str(_get(trade, "id") or _nested(trade, "info", "id") or "") == request.exit_trade_id:
                return trade
        return None

    def _result(
        self,
        *,
        request: RuntimeExchangeCloseProjectionRecoveryRequest,
        status: RuntimeExchangeCloseProjectionRecoveryStatus,
        order: Order | None,
        position: Position | None,
        trade: Any | None,
        blockers: list[str],
        warnings: list[str],
        local_state_mutated: bool,
        order_status_changed: bool,
        position_projection_changed: bool,
        now_ms: int,
        realized_pnl_delta: Decimal = Decimal("0"),
        position_qty_before_override: Decimal | None = None,
    ) -> RuntimeExchangeCloseProjectionRecoveryResult:
        position_qty_before = (
            position_qty_before_override
            if position_qty_before_override is not None
            else position.current_qty
            if position is not None and not position.is_closed
            else Decimal("0")
        )
        position_qty_after = (
            Decimal("0")
            if position is not None and position.is_closed
            else position_qty_before
        )
        return RuntimeExchangeCloseProjectionRecoveryResult(
            recovery_id=recovery_id_for_trade(
                exit_local_order_id=request.exit_local_order_id,
                exit_trade_id=request.exit_trade_id,
            ),
            status=status,
            symbol=request.symbol,
            exit_local_order_id=request.exit_local_order_id,
            exit_exchange_order_id=request.exit_exchange_order_id,
            exit_trade_id=request.exit_trade_id,
            signal_id=order.signal_id if order is not None else None,
            runtime_instance_id=(
                position.runtime_instance_id
                if position is not None
                else (order.runtime_instance_id if order is not None else None)
            ),
            local_position_id=position.id if position is not None else None,
            position_direction=position.direction.value if position is not None else None,
            expected_close_side=_expected_close_side(
                position.direction if position is not None else None
            ),
            observed_trade_side=_trade_side(trade),
            observed_trade_qty=_trade_qty(trade),
            observed_trade_price=_trade_price(trade),
            observed_trade_timestamp_ms=_trade_timestamp_ms(trade),
            local_position_qty_before=position_qty_before,
            local_position_qty_after=position_qty_after,
            realized_pnl_delta=realized_pnl_delta,
            realized_pnl_after=(
                position.realized_pnl if position is not None else None
            ),
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            local_state_mutated=local_state_mutated,
            order_status_changed=order_status_changed,
            position_projection_changed=position_projection_changed,
            created_at_ms=now_ms,
            metadata={
                "scope": "runtime_exchange_close_projection_recovery",
                "operator_reason": request.operator_reason,
                "dry_run": not request.apply,
                "does_not_submit_cancel_amend_or_close_exchange_orders": True,
                "does_not_create_withdrawal_or_transfer": True,
                "exchange_trade_read_only": True,
            },
        )


_EXIT_ORDER_ROLES = {
    OrderRole.EXIT,
    OrderRole.SL,
    OrderRole.TP1,
    OrderRole.TP2,
    OrderRole.TP3,
    OrderRole.TP4,
    OrderRole.TP5,
}


async def _fetch_my_trades(source: Any, symbol: str) -> list[Any]:
    if hasattr(source, "fetch_my_trades"):
        return list(await source.fetch_my_trades(symbol, limit=50))
    rest_exchange = getattr(source, "rest_exchange", None)
    if rest_exchange is not None and hasattr(rest_exchange, "fetch_my_trades"):
        return list(await rest_exchange.fetch_my_trades(symbol, limit=50))
    raise RuntimeError("exchange_trade_source_missing_fetch_my_trades")


def _expected_close_side(direction: Direction | None) -> str | None:
    if direction == Direction.SHORT:
        return "buy"
    if direction == Direction.LONG:
        return "sell"
    return None


def _trade_symbol(trade: Any | None) -> str | None:
    if trade is None:
        return None
    return _get(trade, "symbol") or _nested(trade, "info", "symbol")


def _trade_side(trade: Any | None) -> str | None:
    if trade is None:
        return None
    side = _get(trade, "side") or _nested(trade, "info", "side")
    return str(side).lower() if side is not None else None


def _trade_qty(trade: Any | None) -> Decimal | None:
    if trade is None:
        return None
    return _decimal_or_none(_get(trade, "amount") or _nested(trade, "info", "qty"))


def _trade_price(trade: Any | None) -> Decimal | None:
    if trade is None:
        return None
    return _decimal_or_none(_get(trade, "price") or _nested(trade, "info", "price"))


def _trade_timestamp_ms(trade: Any | None) -> int | None:
    if trade is None:
        return None
    value = _get(trade, "timestamp") or _nested(trade, "info", "time")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _get(item: Any, key: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _nested(item: Any, *keys: str) -> Any:
    current = item
    for key in keys:
        current = _get(current, key)
        if current is None:
            return None
    return current


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item not in out:
            out.append(item)
    return out
