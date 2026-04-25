"""Position Projection Service - execution 主链仓位投影骨架。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from src.domain.models import Direction
from src.domain.models import Order, Position
from src.infrastructure.repository_ports import PositionRepositoryPort


class PositionProjectionService:
    """把成交订单投影为本地 PG positions 执行态。"""

    def __init__(self, repository: Optional[PositionRepositoryPort]) -> None:
        self._repository = repository

    async def project_entry_fill(self, entry_order: Order) -> Optional[Position]:
        """根据 ENTRY 成交构建当前仓位投影。"""
        if self._repository is None:
            return None

        entry_price = entry_order.average_exec_price or entry_order.price or Decimal("0")
        existing = await self._repository.get(f"pos_{entry_order.signal_id}")
        current_qty = entry_order.filled_qty
        realized_pnl = Decimal("0")
        total_fees_paid = Decimal("0")
        total_funding_paid = Decimal("0")
        watermark_price = entry_price
        is_closed = False
        opened_at = int(datetime.now(timezone.utc).timestamp() * 1000)
        closed_at = None

        if existing is not None:
            current_qty = max(existing.current_qty, entry_order.filled_qty)
            realized_pnl = existing.realized_pnl
            total_fees_paid = existing.total_fees_paid
            total_funding_paid = existing.total_funding_paid
            watermark_price = existing.watermark_price or entry_price
            is_closed = existing.is_closed and current_qty <= Decimal("0")
            opened_at = existing.opened_at or opened_at
            closed_at = existing.closed_at

        position = Position(
            id=f"pos_{entry_order.signal_id}",
            signal_id=entry_order.signal_id,
            symbol=entry_order.symbol,
            direction=entry_order.direction,
            entry_price=entry_price,
            current_qty=current_qty,
            watermark_price=watermark_price,
            realized_pnl=realized_pnl,
            total_fees_paid=total_fees_paid,
            total_funding_paid=total_funding_paid,
            opened_at=opened_at,
            closed_at=closed_at,
            is_closed=is_closed,
        )
        await self._repository.save(position)
        return position

    async def project_exit_fill(self, exit_order: Order) -> Optional[Position]:
        """根据 TP/SL 成交更新当前仓位投影。"""
        if self._repository is None:
            return None

        position_id = f"pos_{exit_order.signal_id}"
        position = await self._repository.get(position_id)
        if position is None:
            return None

        exit_qty = exit_order.filled_qty or Decimal("0")
        exit_price = exit_order.average_exec_price or exit_order.price
        if exit_qty <= Decimal("0") or exit_price is None:
            return position

        fee_paid = getattr(exit_order, "close_fee", None)
        if fee_paid is None:
            fee_paid = getattr(exit_order, "fee_paid", Decimal("0"))

        gross_pnl = self._calculate_gross_pnl(
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=exit_qty,
        )
        net_pnl = gross_pnl - fee_paid

        remaining_qty = position.current_qty - exit_qty
        if remaining_qty <= Decimal("0"):
            remaining_qty = Decimal("0")
            position.is_closed = True
            position.closed_at = int(datetime.now(timezone.utc).timestamp() * 1000)

        position.current_qty = remaining_qty
        position.realized_pnl += net_pnl
        position.total_fees_paid += fee_paid
        position.watermark_price = self._update_watermark(
            direction=position.direction,
            current_watermark=position.watermark_price,
            exec_price=exit_price,
            entry_price=position.entry_price,
        )

        await self._repository.save(position)
        return position

    @staticmethod
    def _calculate_gross_pnl(
        *,
        direction: Direction,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        if direction == Direction.LONG:
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity

    @staticmethod
    def _update_watermark(
        *,
        direction: Direction,
        current_watermark: Optional[Decimal],
        exec_price: Decimal,
        entry_price: Decimal,
    ) -> Decimal:
        watermark = current_watermark or entry_price
        if direction == Direction.LONG:
            return max(watermark, exec_price)
        return min(watermark, exec_price)
