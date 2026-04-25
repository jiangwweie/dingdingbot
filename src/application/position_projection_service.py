"""Position Projection Service - execution 主链仓位投影骨架。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Optional

from src.domain.models import Direction
from src.domain.models import Order, Position
from src.infrastructure.repository_ports import PositionRepositoryPort


class PositionProjectionService:
    """把成交订单投影为本地 PG positions 执行态。"""

    def __init__(self, repository: Optional[PositionRepositoryPort]) -> None:
        self._repository = repository
        self._projection_locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, position_id: str) -> asyncio.Lock:
        lock = self._projection_locks.get(position_id)
        if lock is None:
            lock = asyncio.Lock()
            self._projection_locks[position_id] = lock
        return lock

    async def project_entry_fill(self, entry_order: Order) -> Optional[Position]:
        """根据 ENTRY 成交构建当前仓位投影。"""
        if self._repository is None:
            return None

        position_id = f"pos_{entry_order.signal_id}"
        async with self._get_lock(position_id):
            entry_price = entry_order.average_exec_price or entry_order.price or Decimal("0")
            existing = await self._repository.get(position_id)
            current_qty = entry_order.filled_qty
            realized_pnl = Decimal("0")
            total_fees_paid = Decimal("0")
            total_funding_paid = Decimal("0")
            watermark_price = entry_price
            is_closed = False
            opened_at = int(datetime.now(timezone.utc).timestamp() * 1000)
            closed_at = None
            projected_exit_fills = {}
            projected_exit_fees = {}

            if existing is not None:
                current_qty = max(existing.current_qty, entry_order.filled_qty)
                realized_pnl = existing.realized_pnl
                total_fees_paid = existing.total_fees_paid
                total_funding_paid = existing.total_funding_paid
                watermark_price = existing.watermark_price or entry_price
                is_closed = existing.is_closed and current_qty <= Decimal("0")
                opened_at = existing.opened_at or opened_at
                closed_at = existing.closed_at
                projected_exit_fills = dict(existing.projected_exit_fills)
                projected_exit_fees = dict(existing.projected_exit_fees)

            position = Position(
                id=position_id,
                signal_id=entry_order.signal_id,
                symbol=entry_order.symbol,
                direction=entry_order.direction,
                entry_price=entry_price,
                current_qty=current_qty,
                watermark_price=watermark_price,
                realized_pnl=realized_pnl,
                total_fees_paid=total_fees_paid,
                total_funding_paid=total_funding_paid,
                projected_exit_fills=projected_exit_fills,
                projected_exit_fees=projected_exit_fees,
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
        async with self._get_lock(position_id):
            position = await self._repository.get(position_id)
            if position is None:
                return None

            cumulative_exit_qty = exit_order.filled_qty or Decimal("0")
            exit_price = exit_order.average_exec_price or exit_order.price
            if cumulative_exit_qty <= Decimal("0") or exit_price is None:
                return position

            previous_projected_qty = position.projected_exit_fills.get(
                exit_order.id, Decimal("0")
            )
            delta_exit_qty = cumulative_exit_qty - previous_projected_qty
            if delta_exit_qty <= Decimal("0"):
                return position

            fee_total = getattr(exit_order, "close_fee", None)
            if fee_total is None:
                fee_total = getattr(exit_order, "fee_paid", Decimal("0"))
            previous_projected_fee = position.projected_exit_fees.get(
                exit_order.id, Decimal("0")
            )
            delta_fee = fee_total - previous_projected_fee
            if delta_fee < Decimal("0"):
                delta_fee = Decimal("0")

            gross_pnl = self._calculate_gross_pnl(
                direction=position.direction,
                entry_price=position.entry_price,
                exit_price=exit_price,
                quantity=delta_exit_qty,
            )
            net_pnl = gross_pnl - delta_fee

            remaining_qty = position.current_qty - delta_exit_qty
            if remaining_qty <= Decimal("0"):
                remaining_qty = Decimal("0")
                position.is_closed = True
                position.closed_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            position.current_qty = remaining_qty
            position.realized_pnl += net_pnl
            position.total_fees_paid += delta_fee
            position.projected_exit_fills[exit_order.id] = cumulative_exit_qty
            position.projected_exit_fees[exit_order.id] = fee_total
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
