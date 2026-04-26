"""
PostgreSQL Order Repository - PG 核心订单仓储

这是双轨迁移阶段新增的 PG 实现，不替换现有 SQLite OrderRepository。
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.models import Direction, Order, OrderRole, OrderStatus, OrderType
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import PGOrderORM


class PgOrderRepository:
    """PG 版订单仓储。"""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._exchange_gateway: Optional[Any] = None  # 依赖注入：交易所网关
        self._audit_logger: Optional[Any] = None  # 依赖注入：审计日志器

    def set_exchange_gateway(self, gateway: Any) -> None:
        """设置交易所网关（依赖注入）。"""
        self._exchange_gateway = gateway

    def set_audit_logger(self, logger_instance: Any) -> None:
        """设置审计日志器（依赖注入）。"""
        self._audit_logger = logger_instance

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def close(self) -> None:
        return None

    async def save(self, order: Order) -> None:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(order))
            await session.commit()

    async def save_batch(self, orders: List[Order]) -> None:
        async with self._session_maker() as session:
            for order in orders:
                await session.merge(self._to_orm(order))
            await session.commit()

    async def get_order(self, order_id: str) -> Optional[Order]:
        async with self._session_maker() as session:
            orm = await session.get(PGOrderORM, order_id)
            return self._to_domain(orm) if orm else None

    async def get_order_by_exchange_id(self, exchange_order_id: str) -> Optional[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(PGOrderORM.exchange_order_id == exchange_order_id)
            result = await session.execute(stmt)
            orm = result.scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        async with self._session_maker() as session:
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.signal_id == signal_id)
                .order_by(PGOrderORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]:
        async with self._session_maker() as session:
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.symbol == symbol)
                .order_by(PGOrderORM.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        order_role: Optional[OrderRole] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        async with self._session_maker() as session:
            filters = []
            if symbol:
                filters.append(PGOrderORM.symbol == symbol)
            if status:
                filters.append(PGOrderORM.status == status.value)
            if order_role:
                filters.append(PGOrderORM.order_role == order_role.value)

            count_stmt = select(func.count()).select_from(PGOrderORM)
            if filters:
                count_stmt = count_stmt.where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()

            stmt = select(PGOrderORM)
            if filters:
                stmt = stmt.where(*filters)
            stmt = stmt.order_by(PGOrderORM.created_at.desc()).limit(limit).offset(offset)
            result = await session.execute(stmt)
            items = [self._to_domain(orm) for orm in result.scalars().all()]

            return {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    async def get_orders_by_signal_ids(
        self,
        signal_ids: List[str],
        page: int = 1,
        page_size: int = 20,
        order_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not signal_ids:
            return {"orders": [], "total": 0, "page": page, "page_size": page_size}

        async with self._session_maker() as session:
            filters = [PGOrderORM.signal_id.in_(signal_ids)]
            if order_role:
                filters.append(PGOrderORM.order_role == order_role)

            count_stmt = select(func.count()).select_from(PGOrderORM).where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()

            offset = max(page - 1, 0) * page_size
            stmt = (
                select(PGOrderORM)
                .where(*filters)
                .order_by(PGOrderORM.created_at.asc())
                .limit(page_size)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return {
                "orders": [self._to_domain(orm) for orm in result.scalars().all()],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    async def get_orders_by_status(
        self,
        status: OrderStatus,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(PGOrderORM.status == status.value)
            if symbol:
                stmt = stmt.where(PGOrderORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderORM.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_orders_by_role(
        self,
        role: OrderRole,
        signal_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(PGOrderORM.order_role == role.value)
            if signal_id:
                stmt = stmt.where(PGOrderORM.signal_id == signal_id)
            if symbol:
                stmt = stmt.where(PGOrderORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderORM.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        async with self._session_maker() as session:
            stmt = select(PGOrderORM).where(
                PGOrderORM.status.in_(
                    [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]
                )
            )
            if symbol:
                stmt = stmt.where(PGOrderORM.symbol == symbol)
            stmt = stmt.order_by(PGOrderORM.created_at.desc())
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_order_chain(self, signal_id: str) -> Dict[str, List[Order]]:
        orders = await self.get_orders_by_signal(signal_id)
        entry_orders: List[Order] = []
        tp_orders: List[Order] = []
        sl_orders: List[Order] = []
        for order in orders:
            if order.order_role == OrderRole.ENTRY:
                entry_orders.append(order)
            elif order.order_role in {
                OrderRole.TP1,
                OrderRole.TP2,
                OrderRole.TP3,
                OrderRole.TP4,
                OrderRole.TP5,
            }:
                tp_orders.append(order)
            elif order.order_role == OrderRole.SL:
                sl_orders.append(order)
        return {"entry": entry_orders, "tps": tp_orders, "sl": sl_orders}

    async def get_order_chain_by_order_id(self, order_id: str) -> List[Order]:
        target_order = await self.get_order(order_id)
        if target_order is None:
            return []

        parent_id = (
            target_order.id
            if target_order.order_role == OrderRole.ENTRY
            else target_order.parent_order_id
        )

        orders: List[Order] = []
        if parent_id and parent_id != target_order.id:
            parent_order = await self.get_order(parent_id)
            if parent_order is not None:
                orders.append(parent_order)
        elif target_order.order_role == OrderRole.ENTRY:
            orders.append(target_order)

        search_parent_id = parent_id or target_order.id
        async with self._session_maker() as session:
            role_rank = case(
                (PGOrderORM.order_role == "TP1", 1),
                (PGOrderORM.order_role == "TP2", 2),
                (PGOrderORM.order_role == "TP3", 3),
                (PGOrderORM.order_role == "TP4", 4),
                (PGOrderORM.order_role == "TP5", 5),
                (PGOrderORM.order_role == "SL", 6),
                else_=7,
            )
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.parent_order_id == search_parent_id)
                .order_by(role_rank, PGOrderORM.created_at.asc())
            )
            result = await session.execute(stmt)
            orders.extend(self._to_domain(orm) for orm in result.scalars().all())
        return orders

    async def get_oco_group(self, oco_group_id: str) -> List[Order]:
        async with self._session_maker() as session:
            stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.oco_group_id == oco_group_id)
                .order_by(PGOrderORM.created_at.asc())
            )
            result = await session.execute(stmt)
            return [self._to_domain(orm) for orm in result.scalars().all()]

    async def get_order_tree(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = 7,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        async with self._session_maker() as session:
            filters = [PGOrderORM.order_role == OrderRole.ENTRY.value]
            if symbol:
                filters.append(PGOrderORM.symbol == symbol)

            if start_date is not None:
                filters.append(PGOrderORM.created_at >= int(start_date.timestamp() * 1000))
            elif days is not None:
                since = datetime.now(timezone.utc) - timedelta(days=days)
                filters.append(PGOrderORM.created_at >= int(since.timestamp() * 1000))
            if end_date is not None:
                filters.append(PGOrderORM.created_at <= int(end_date.timestamp() * 1000))

            count_stmt = select(func.count()).select_from(PGOrderORM).where(*filters)
            total_count = (await session.execute(count_stmt)).scalar_one()

            offset = max(page - 1, 0) * page_size
            root_stmt = (
                select(PGOrderORM)
                .where(*filters)
                .order_by(PGOrderORM.created_at.desc())
                .limit(page_size)
                .offset(offset)
            )
            root_result = await session.execute(root_stmt)
            root_orders = root_result.scalars().all()

            if not root_orders:
                return {
                    "items": [],
                    "total": 0,
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "metadata": {
                        "symbol_filter": symbol,
                        "days_filter": days,
                        "loaded_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                    },
                }

            entry_ids = [order.id for order in root_orders]
            child_stmt = (
                select(PGOrderORM)
                .where(PGOrderORM.parent_order_id.in_(entry_ids))
                .order_by(PGOrderORM.created_at.asc())
            )
            child_result = await session.execute(child_stmt)
            child_rows = child_result.scalars().all()

            children_by_parent: Dict[str, List[Order]] = {}
            for child in child_rows:
                children_by_parent.setdefault(child.parent_order_id or "", []).append(
                    self._to_domain(child)
                )

            items = []
            for root in root_orders:
                root_domain = self._to_domain(root)
                child_orders = children_by_parent.get(root.id, [])
                items.append(
                    {
                        "order": self._order_to_response(root_domain),
                        "children": [
                            {
                                "order": self._order_to_response(child),
                                "children": [],
                                "level": 1,
                                "has_children": False,
                            }
                            for child in child_orders
                        ],
                        "level": 0,
                        "has_children": bool(child_orders),
                    }
                )

            return {
                "items": items,
                "total": len(root_orders),
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "metadata": {
                    "symbol_filter": symbol,
                    "days_filter": days,
                    "loaded_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                },
            }

    async def delete_orders_batch(
        self,
        order_ids: List[str],
        cancel_on_exchange: bool = True,
        audit_info: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        result = {
            "deleted_count": 0,
            "cancelled_on_exchange": [],
            "failed_to_cancel": [],
            "deleted_from_db": [],
            "failed_to_delete": [],
            "audit_log_id": None,
        }

        if not order_ids:
            raise ValueError("订单 ID 列表不能为空")
        if len(order_ids) > 100:
            raise ValueError("批量删除最多支持 100 个订单")

        all_order_ids = await self._get_all_related_order_ids(order_ids)
        orders_to_delete: List[Order] = []
        for oid in all_order_ids:
            order = await self.get_order(oid)
            if order is not None:
                orders_to_delete.append(order)

        if cancel_on_exchange:
            for order in orders_to_delete:
                if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                    if order.exchange_order_id and self._exchange_gateway is not None:
                        try:
                            cancel_result = await self._exchange_gateway.cancel_order(
                                exchange_order_id=order.exchange_order_id,
                                symbol=order.symbol,
                            )
                            if cancel_result.is_success:
                                result["cancelled_on_exchange"].append(order.id)
                            else:
                                result["failed_to_cancel"].append(
                                    {
                                        "order_id": order.id,
                                        "reason": cancel_result.error_message
                                        or "Unknown error",
                                    }
                                )
                        except Exception as exc:
                            result["failed_to_cancel"].append(
                                {"order_id": order.id, "reason": str(exc)}
                            )
                    elif self._exchange_gateway is None:
                        result["failed_to_cancel"].append(
                            {
                                "order_id": order.id,
                                "reason": "ExchangeGateway not initialized",
                            }
                        )
                    else:
                        result["failed_to_cancel"].append(
                            {"order_id": order.id, "reason": "No exchange_order_id"}
                        )

        deleted_ids = [order.id for order in orders_to_delete]
        if deleted_ids:
            async with self._session_maker() as session:
                await session.execute(delete(PGOrderORM).where(PGOrderORM.id.in_(deleted_ids)))
                await session.commit()
            result["deleted_from_db"] = deleted_ids
            result["deleted_count"] = len(deleted_ids)

        audit_log_id = f"audit_{datetime.now(timezone.utc).timestamp()}"
        result["audit_log_id"] = audit_log_id
        if self._audit_logger is not None:
            try:
                from src.domain.models import OrderAuditEventType, OrderAuditTriggerSource

                await self._audit_logger.log(
                    order_id="BATCH_DELETE",
                    signal_id=None,
                    old_status=None,
                    new_status="DELETED",
                    event_type=OrderAuditEventType.ORDER_CANCELED,
                    triggered_by=OrderAuditTriggerSource.USER,
                    metadata={
                        "operation": "DELETE_BATCH",
                        "order_ids": order_ids,
                        "cancelled_on_exchange": result["cancelled_on_exchange"],
                        "deleted_from_db": result["deleted_from_db"],
                        "failed_to_cancel": result["failed_to_cancel"],
                        "failed_to_delete": result["failed_to_delete"],
                        "operator_id": audit_info.get("operator_id") if audit_info else None,
                        "ip_address": audit_info.get("ip_address") if audit_info else None,
                    },
                )
            except Exception:
                pass
        return result

    async def update_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_qty: Optional[Decimal] = None,
        average_exec_price: Optional[Decimal] = None,
        filled_at: Optional[int] = None,
        exchange_order_id: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ) -> None:
        """
        更新订单状态和可选字段。

        Args:
            order_id: 订单 ID
            status: 新状态
            filled_qty: 成交数量（可选）
            average_exec_price: 平均成交价（可选）
            filled_at: 成交时间戳（可选）
            exchange_order_id: 交易所订单 ID（可选）
            exit_reason: 退出原因（可选）
        """
        async with self._session_maker() as session:
            orm = await session.get(PGOrderORM, order_id)
            if orm is None:
                return

            orm.status = status.value
            orm.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

            if filled_qty is not None:
                orm.filled_qty = filled_qty
            if average_exec_price is not None:
                orm.average_exec_price = average_exec_price
            if filled_at is not None:
                orm.filled_at = filled_at
            if exchange_order_id is not None:
                orm.exchange_order_id = exchange_order_id
            if exit_reason is not None:
                orm.exit_reason = exit_reason

            await session.commit()

    async def _get_all_related_order_ids(self, order_ids: List[str]) -> Set[str]:
        all_ids: Set[str] = set(order_ids)
        queue: List[str] = list(order_ids)

        async with self._session_maker() as session:
            while queue:
                current_id = queue.pop(0)

                child_stmt = select(PGOrderORM.id).where(
                    PGOrderORM.parent_order_id == current_id
                )
                child_result = await session.execute(child_stmt)
                for child_id in child_result.scalars().all():
                    if child_id not in all_ids:
                        all_ids.add(child_id)
                        queue.append(child_id)

                parent_stmt = select(PGOrderORM.parent_order_id).where(
                    PGOrderORM.id == current_id
                )
                parent_result = await session.execute(parent_stmt)
                parent_id = parent_result.scalar_one_or_none()
                if parent_id and parent_id not in all_ids:
                    all_ids.add(parent_id)
                    queue.append(parent_id)

        return all_ids

    @staticmethod
    def _order_to_response(order: Order) -> Dict[str, Any]:
        remaining_qty = order.requested_qty - order.filled_qty
        return {
            "order_id": order.id,
            "exchange_order_id": order.exchange_order_id,
            "symbol": order.symbol,
            "order_type": order.order_type,
            "order_role": order.order_role,
            "direction": order.direction,
            "status": order.status,
            "quantity": order.requested_qty,
            "filled_qty": order.filled_qty,
            "remaining_qty": remaining_qty,
            "price": order.price,
            "trigger_price": order.trigger_price,
            "average_exec_price": order.average_exec_price,
            "reduce_only": order.reduce_only,
            "client_order_id": None,
            "strategy_name": None,
            "signal_id": order.signal_id,
            "stop_loss": None,
            "take_profit": None,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "filled_at": order.filled_at,
            "fee_paid": Decimal("0"),
            "fee_currency": None,
            "tags": [],
        }

    @staticmethod
    def _to_orm(order: Order) -> PGOrderORM:
        return PGOrderORM(
            id=order.id,
            signal_id=order.signal_id,
            exchange_order_id=order.exchange_order_id,
            symbol=order.symbol,
            direction=order.direction.value,
            order_type=order.order_type.value,
            order_role=order.order_role.value,
            price=order.price,
            trigger_price=order.trigger_price,
            requested_qty=order.requested_qty,
            filled_qty=order.filled_qty,
            average_exec_price=order.average_exec_price,
            status=order.status.value,
            reduce_only=order.reduce_only,
            parent_order_id=order.parent_order_id,
            oco_group_id=order.oco_group_id,
            exit_reason=order.exit_reason,
            filled_at=order.filled_at,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _to_domain(orm: PGOrderORM) -> Order:
        return Order(
            id=orm.id,
            signal_id=orm.signal_id,
            exchange_order_id=orm.exchange_order_id,
            symbol=orm.symbol,
            direction=Direction(orm.direction),
            order_type=OrderType(orm.order_type),
            order_role=OrderRole(orm.order_role),
            price=orm.price,
            trigger_price=orm.trigger_price,
            requested_qty=orm.requested_qty,
            filled_qty=orm.filled_qty,
            average_exec_price=orm.average_exec_price,
            status=OrderStatus(orm.status),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            exit_reason=orm.exit_reason,
            reduce_only=orm.reduce_only,
            parent_order_id=orm.parent_order_id,
            oco_group_id=orm.oco_group_id,
            filled_at=orm.filled_at,
        )
