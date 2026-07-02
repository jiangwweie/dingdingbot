"""Recover local runtime order/position projection from accepted exchange facts.

This service is intentionally narrow: it reads exchange order/position facts for
an already-submitted runtime order chain and repairs local PG projection. It
must not submit, cancel, amend, close, withdraw, or transfer anything.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.application.order_lifecycle_service import OrderLifecycleService
from src.application.position_projection_service import PositionProjectionService
from src.domain.models import Direction, Order, OrderPlacementResult, OrderRole, OrderStatus


class RuntimeExchangeSubmitProjectionRecoveryStatus(str, Enum):
    BLOCKED = "blocked"
    DRY_RUN_READY = "dry_run_ready"
    APPLIED = "applied"


class RuntimeExchangeSubmitProjectionRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=128)
    entry_local_order_id: str = Field(min_length=1, max_length=260)
    entry_exchange_order_id: str = Field(min_length=1, max_length=128)
    protection_local_order_id: str = Field(min_length=1, max_length=260)
    protection_exchange_order_id: str = Field(min_length=1, max_length=128)
    apply: bool = False
    operator_reason: str = Field(
        default="runtime_exchange_submit_projection_recovery",
        min_length=1,
        max_length=220,
    )


class RuntimeExchangeSubmitProjectionRecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RuntimeExchangeSubmitProjectionRecoveryStatus
    symbol: str
    entry_local_order_id: str
    entry_exchange_order_id: str
    protection_local_order_id: str
    protection_exchange_order_id: str
    entry_filled_qty: Optional[Decimal] = None
    entry_average_exec_price: Optional[Decimal] = None
    protection_qty: Optional[Decimal] = None
    protection_trigger_price: Optional[Decimal] = None
    position_size: Optional[Decimal] = None
    position_side: Optional[str] = None
    projected_position_id: Optional[str] = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    local_state_mutated: bool = False
    exchange_read_only: bool = True
    exchange_write_called: bool = False
    order_created: bool = False
    order_cancelled: bool = False
    order_amended: bool = False
    position_closed: bool = False
    withdrawal_or_transfer_created: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeExchangeSubmitProjectionGatewayPort(Protocol):
    async def fetch_order(self, exchange_order_id: str, symbol: str) -> OrderPlacementResult:
        ...

    async def fetch_open_orders(
        self,
        symbol: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        ...

    async def fetch_positions(self, symbol: Optional[str] = None) -> list[Any]:
        ...


class RuntimeExchangeSubmitProjectionOrderRepositoryPort(Protocol):
    async def save(self, order: Order) -> None:
        ...


class RuntimeExchangeSubmitProjectionRecoveryService:
    """Repair local projection for an already accepted runtime submit."""

    def __init__(
        self,
        *,
        gateway: RuntimeExchangeSubmitProjectionGatewayPort,
        order_repository: RuntimeExchangeSubmitProjectionOrderRepositoryPort,
        lifecycle: OrderLifecycleService,
        position_projection_service: PositionProjectionService,
    ) -> None:
        self._gateway = gateway
        self._order_repository = order_repository
        self._lifecycle = lifecycle
        self._position_projection_service = position_projection_service

    async def recover(
        self,
        request: RuntimeExchangeSubmitProjectionRecoveryRequest,
    ) -> RuntimeExchangeSubmitProjectionRecoveryResult:
        blockers: list[str] = []
        warnings: list[str] = []

        entry_order = await self._lifecycle.get_order(request.entry_local_order_id)
        protection_order = await self._lifecycle.get_order(
            request.protection_local_order_id
        )
        if entry_order is None:
            blockers.append("entry_local_order_missing")
        if protection_order is None:
            blockers.append("protection_local_order_missing")

        entry_result: OrderPlacementResult | None = None
        protection_fact: dict[str, Any] | None = None
        matching_position: Any | None = None

        if entry_order is not None:
            _validate_local_entry_order(
                entry_order,
                request=request,
                blockers=blockers,
            )
        if protection_order is not None:
            _validate_local_protection_order(
                protection_order,
                request=request,
                blockers=blockers,
            )

        try:
            entry_result = await self._gateway.fetch_order(
                request.entry_exchange_order_id,
                request.symbol,
            )
        except Exception as exc:  # pragma: no cover - exact gateway exception is adapter-specific
            blockers.append(f"entry_exchange_order_fetch_failed:{type(exc).__name__}")

        if entry_result is not None:
            _validate_entry_exchange_result(
                entry_result,
                request=request,
                blockers=blockers,
            )

        try:
            stop_orders = await self._gateway.fetch_open_orders(
                request.symbol,
                params={"stop": True},
            )
            protection_fact = _find_exchange_order(
                stop_orders,
                exchange_order_id=request.protection_exchange_order_id,
                client_order_id=request.protection_local_order_id,
            )
            if protection_fact is None:
                blockers.append("protection_exchange_open_order_missing")
        except Exception as exc:  # pragma: no cover - exact gateway exception is adapter-specific
            blockers.append(
                f"protection_exchange_open_order_fetch_failed:{type(exc).__name__}"
            )

        try:
            positions = await self._gateway.fetch_positions(request.symbol)
            if entry_order is not None:
                matching_position = _find_matching_position(
                    positions,
                    symbol=request.symbol,
                    direction=entry_order.direction,
                )
            if matching_position is None:
                blockers.append("exchange_position_missing")
        except Exception as exc:  # pragma: no cover - exact gateway exception is adapter-specific
            blockers.append(f"exchange_position_fetch_failed:{type(exc).__name__}")

        entry_filled_qty = _entry_filled_qty(entry_result)
        entry_average_exec_price = (
            entry_result.average_exec_price if entry_result is not None else None
        )
        protection_qty = _order_amount(protection_fact)
        protection_trigger_price = _order_trigger_price(protection_fact)
        position_size = _position_size(matching_position)
        position_side = _position_side(matching_position)

        if entry_filled_qty is not None and protection_qty is not None:
            if protection_qty < entry_filled_qty:
                blockers.append("protection_qty_less_than_entry_fill")
            elif protection_qty > entry_filled_qty:
                warnings.append("protection_qty_exceeds_entry_fill")
        if position_size is not None and entry_filled_qty is not None:
            if position_size != entry_filled_qty:
                blockers.append("exchange_position_size_mismatch_entry_fill")
        if protection_fact is not None and not _order_reduce_only(protection_fact):
            blockers.append("protection_exchange_order_not_reduce_only")
        if protection_fact is not None and _order_status(protection_fact) != "open":
            blockers.append("protection_exchange_order_not_open")

        if blockers:
            return self._result(
                request=request,
                status=RuntimeExchangeSubmitProjectionRecoveryStatus.BLOCKED,
                entry_filled_qty=entry_filled_qty,
                entry_average_exec_price=entry_average_exec_price,
                protection_qty=protection_qty,
                protection_trigger_price=protection_trigger_price,
                position_size=position_size,
                position_side=position_side,
                blockers=blockers,
                warnings=warnings,
            )

        if not request.apply:
            return self._result(
                request=request,
                status=RuntimeExchangeSubmitProjectionRecoveryStatus.DRY_RUN_READY,
                entry_filled_qty=entry_filled_qty,
                entry_average_exec_price=entry_average_exec_price,
                protection_qty=protection_qty,
                protection_trigger_price=protection_trigger_price,
                position_size=position_size,
                position_side=position_side,
                blockers=[],
                warnings=warnings,
            )

        assert entry_order is not None
        assert protection_order is not None
        assert entry_filled_qty is not None
        assert entry_average_exec_price is not None
        assert protection_qty is not None

        updated_entry = await self._apply_entry_recovery(
            entry_order,
            exchange_order_id=request.entry_exchange_order_id,
            requested_qty=entry_filled_qty,
            filled_qty=entry_filled_qty,
            average_exec_price=entry_average_exec_price,
            price=entry_result.price if entry_result is not None else None,
        )
        updated_protection = await self._apply_protection_recovery(
            protection_order,
            exchange_order_id=request.protection_exchange_order_id,
            requested_qty=protection_qty,
            trigger_price=protection_trigger_price,
        )
        position = await self._position_projection_service.project_entry_fill(
            updated_entry
        )

        return self._result(
            request=request,
            status=RuntimeExchangeSubmitProjectionRecoveryStatus.APPLIED,
            entry_filled_qty=updated_entry.filled_qty,
            entry_average_exec_price=updated_entry.average_exec_price,
            protection_qty=updated_protection.requested_qty,
            protection_trigger_price=updated_protection.trigger_price,
            position_size=position.current_qty if position is not None else position_size,
            position_side=position_side,
            projected_position_id=position.id if position is not None else None,
            blockers=[],
            warnings=warnings,
            local_state_mutated=True,
        )

    async def _apply_entry_recovery(
        self,
        order: Order,
        *,
        exchange_order_id: str,
        requested_qty: Decimal,
        filled_qty: Decimal,
        average_exec_price: Decimal,
        price: Optional[Decimal],
    ) -> Order:
        order.exchange_order_id = exchange_order_id
        order.requested_qty = requested_qty
        order.price = price
        await self._order_repository.save(order)
        await _ensure_order_open_for_fill(self._lifecycle, order.id, exchange_order_id)
        updated = await self._lifecycle.update_order_filled(
            order.id,
            filled_qty=filled_qty,
            average_exec_price=average_exec_price,
        )
        updated.requested_qty = requested_qty
        updated.price = price
        updated.exchange_order_id = exchange_order_id
        await self._order_repository.save(updated)
        return updated

    async def _apply_protection_recovery(
        self,
        order: Order,
        *,
        exchange_order_id: str,
        requested_qty: Decimal,
        trigger_price: Optional[Decimal],
    ) -> Order:
        order.exchange_order_id = exchange_order_id
        order.requested_qty = requested_qty
        if trigger_price is not None:
            order.trigger_price = trigger_price
        order.reduce_only = True
        await self._order_repository.save(order)
        updated = await _ensure_order_open(
            self._lifecycle,
            order.id,
            exchange_order_id,
        )
        updated.requested_qty = requested_qty
        if trigger_price is not None:
            updated.trigger_price = trigger_price
        updated.reduce_only = True
        await self._order_repository.save(updated)
        return updated

    @staticmethod
    def _result(
        *,
        request: RuntimeExchangeSubmitProjectionRecoveryRequest,
        status: RuntimeExchangeSubmitProjectionRecoveryStatus,
        entry_filled_qty: Optional[Decimal],
        entry_average_exec_price: Optional[Decimal],
        protection_qty: Optional[Decimal],
        protection_trigger_price: Optional[Decimal],
        position_size: Optional[Decimal],
        position_side: Optional[str],
        blockers: list[str],
        warnings: list[str],
        projected_position_id: Optional[str] = None,
        local_state_mutated: bool = False,
    ) -> RuntimeExchangeSubmitProjectionRecoveryResult:
        return RuntimeExchangeSubmitProjectionRecoveryResult(
            status=status,
            symbol=request.symbol,
            entry_local_order_id=request.entry_local_order_id,
            entry_exchange_order_id=request.entry_exchange_order_id,
            protection_local_order_id=request.protection_local_order_id,
            protection_exchange_order_id=request.protection_exchange_order_id,
            entry_filled_qty=entry_filled_qty,
            entry_average_exec_price=entry_average_exec_price,
            protection_qty=protection_qty,
            protection_trigger_price=protection_trigger_price,
            position_size=position_size,
            position_side=position_side,
            projected_position_id=projected_position_id,
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            local_state_mutated=local_state_mutated,
            metadata={
                "scope": "runtime_exchange_submit_projection_recovery",
                "operator_reason": request.operator_reason,
                "dry_run": not request.apply,
                "repairs_local_projection_only": True,
                "does_not_submit_cancel_amend_or_close_orders": True,
                "does_not_create_withdrawal_or_transfer": True,
            },
        )


async def _ensure_order_open_for_fill(
    lifecycle: OrderLifecycleService,
    order_id: str,
    exchange_order_id: str,
) -> Order:
    order = await _ensure_order_open(lifecycle, order_id, exchange_order_id)
    if order.status == OrderStatus.PARTIALLY_FILLED:
        return order
    if order.status != OrderStatus.OPEN:
        raise RuntimeError(f"order_not_fill_ready:{order.status.value}")
    return order


async def _ensure_order_open(
    lifecycle: OrderLifecycleService,
    order_id: str,
    exchange_order_id: str,
) -> Order:
    order = await lifecycle.get_order(order_id)
    if order is None:
        raise ValueError(f"order_missing:{order_id}")
    if order.status == OrderStatus.FILLED:
        return order
    if order.status in {OrderStatus.CANCELED, OrderStatus.REJECTED, OrderStatus.EXPIRED}:
        raise RuntimeError(f"terminal_order_cannot_be_recovered:{order.status.value}")
    if order.status in {OrderStatus.CREATED, OrderStatus.PENDING}:
        order = await lifecycle.submit_order(order_id, exchange_order_id=exchange_order_id)
    if order.status == OrderStatus.SUBMITTED:
        order = await lifecycle.confirm_order(order_id, exchange_order_id=exchange_order_id)
    return order


def _validate_local_entry_order(
    order: Order,
    *,
    request: RuntimeExchangeSubmitProjectionRecoveryRequest,
    blockers: list[str],
) -> None:
    if order.symbol != request.symbol:
        blockers.append("entry_local_symbol_mismatch")
    if order.order_role != OrderRole.ENTRY:
        blockers.append("entry_local_role_mismatch")
    if order.exchange_order_id and order.exchange_order_id != request.entry_exchange_order_id:
        blockers.append("entry_local_exchange_id_mismatch")


def _validate_local_protection_order(
    order: Order,
    *,
    request: RuntimeExchangeSubmitProjectionRecoveryRequest,
    blockers: list[str],
) -> None:
    if order.symbol != request.symbol:
        blockers.append("protection_local_symbol_mismatch")
    if order.order_role != OrderRole.SL:
        blockers.append("protection_local_role_mismatch")
    if (
        order.exchange_order_id
        and order.exchange_order_id != request.protection_exchange_order_id
    ):
        blockers.append("protection_local_exchange_id_mismatch")


def _validate_entry_exchange_result(
    result: OrderPlacementResult,
    *,
    request: RuntimeExchangeSubmitProjectionRecoveryRequest,
    blockers: list[str],
) -> None:
    if result.symbol != request.symbol:
        blockers.append("entry_exchange_symbol_mismatch")
    if result.exchange_order_id != request.entry_exchange_order_id:
        blockers.append("entry_exchange_id_mismatch")
    if result.status != OrderStatus.FILLED:
        blockers.append("entry_exchange_order_not_filled")
    if _entry_filled_qty(result) is None:
        blockers.append("entry_exchange_filled_qty_missing")
    if result.average_exec_price is None:
        blockers.append("entry_exchange_average_exec_price_missing")


def _entry_filled_qty(result: OrderPlacementResult | None) -> Optional[Decimal]:
    if result is None:
        return None
    if result.filled_qty is not None and result.filled_qty > Decimal("0"):
        return result.filled_qty
    if result.status == OrderStatus.FILLED and result.amount > Decimal("0"):
        return result.amount
    return None


def _find_exchange_order(
    orders: list[dict[str, Any]],
    *,
    exchange_order_id: str,
    client_order_id: str,
) -> dict[str, Any] | None:
    for order in orders:
        if str(order.get("id") or "") == exchange_order_id:
            return order
        if str(order.get("clientOrderId") or "") == client_order_id:
            return order
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        if str(info.get("orderId") or "") == exchange_order_id:
            return order
        if str(info.get("clientOrderId") or "") == client_order_id:
            return order
    return None


def _find_matching_position(
    positions: list[Any],
    *,
    symbol: str,
    direction: Direction,
) -> Any | None:
    expected_side = "long" if direction == Direction.LONG else "short"
    for position in positions:
        if getattr(position, "symbol", None) != symbol:
            continue
        if str(getattr(position, "side", "")).lower() != expected_side:
            continue
        if _position_size(position) and _position_size(position) > Decimal("0"):
            return position
    return None


def _order_amount(order: dict[str, Any] | None) -> Optional[Decimal]:
    if order is None:
        return None
    raw = order.get("amount")
    if raw is None:
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        raw = info.get("origQty")
    return _decimal_or_none(raw)


def _order_trigger_price(order: dict[str, Any] | None) -> Optional[Decimal]:
    if order is None:
        return None
    raw = order.get("triggerPrice") or order.get("stopPrice")
    if raw is None:
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        raw = info.get("stopPrice")
    value = _decimal_or_none(raw)
    if value == Decimal("0"):
        return None
    return value


def _order_reduce_only(order: dict[str, Any]) -> bool:
    raw = order.get("reduceOnly")
    if raw is None:
        info = order.get("info") if isinstance(order.get("info"), dict) else {}
        raw = info.get("reduceOnly")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _order_status(order: dict[str, Any]) -> str:
    return str(order.get("status") or "").strip().lower()


def _position_size(position: Any | None) -> Optional[Decimal]:
    if position is None:
        return None
    return _decimal_or_none(getattr(position, "size", None))


def _position_side(position: Any | None) -> Optional[str]:
    if position is None:
        return None
    value = getattr(position, "side", None)
    return str(value).lower() if value is not None else None


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
