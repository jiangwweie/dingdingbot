"""
Order Repository - SQLite persistence for trading orders.

P5-011: 订单清理机制
- 所有订单都要有迹可循，本地都要入库
- 支持订单的保存、查询、更新状态
- 支持订单链追踪（ENTRY -> TP/SL）
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

import aiosqlite

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
    OrderResponse, OrderResponseFull,
)
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class OrderRepository:
    """
    SQLite repository for persisting trading orders.

    核心职责:
    1. 订单持久化 - 所有系统生成的订单都必须入库
    2. 订单状态追踪 - 记录订单从创建到终结的全生命周期
    3. 订单链管理 - 通过 parent_order_id 和 oco_group_id 追踪关联订单
    4. 查询服务 - 支持按信号、币种、状态、角色等多维度查询
    """

    def __init__(self, db_path: str = "data/orders.db"):
        """
        Initialize OrderRepository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        logger.info(f"订单仓库初始化完成：{db_path}")

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        async with self._lock:
            # Create data directory if not exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row

            # Enable WAL mode for high concurrency write support (P0-001)
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.execute("PRAGMA wal_autocheckpoint=1000")
            await self._db.execute("PRAGMA cache_size=-64000")  # 64MB cache

            # Create orders table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id                  TEXT PRIMARY KEY,
                    signal_id           TEXT NOT NULL,
                    symbol              TEXT NOT NULL,
                    direction           TEXT NOT NULL,
                    order_type          TEXT NOT NULL,
                    order_role          TEXT NOT NULL,
                    price               TEXT,
                    trigger_price       TEXT,
                    requested_qty       TEXT NOT NULL,
                    filled_qty          TEXT NOT NULL DEFAULT '0',
                    average_exec_price  TEXT,
                    status              TEXT NOT NULL DEFAULT 'PENDING',
                    reduce_only         INTEGER NOT NULL DEFAULT 0,
                    parent_order_id     TEXT,
                    oco_group_id        TEXT,
                    exit_reason         TEXT,
                    exchange_order_id   TEXT,
                    filled_at           INTEGER,
                    created_at          INTEGER NOT NULL,
                    updated_at          INTEGER NOT NULL
                )
            """)

            # Create indexes for performance
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_signal_id ON orders(signal_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_order_role ON orders(order_role)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_parent_order_id ON orders(parent_order_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_oco_group_id ON orders(oco_group_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_orders_filled_at ON orders(filled_at)
            """)

            await self._db.commit()
            logger.info("订单仓库表创建完成")

    async def close(self) -> None:
        """Close database connection"""
        async with self._lock:
            if self._db:
                await self._db.commit()
                await self._db.close()
                self._db = None
                logger.info("订单仓库连接已关闭")

    # ============================================================
    # Write Operations
    # ============================================================
    async def save(self, order: Order) -> None:
        """
        Save or update an order to the database.

        使用 SQLite ON CONFLICT DO UPDATE 语法（真·UPSERT）避免 INSERT OR REPLACE 的数据擦除问题：
        - INSERT OR REPLACE 会用 NULL 覆盖已存在的字段
        - ON CONFLICT DO UPDATE 只更新指定的字段

        Args:
            order: Order object to save
        """
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO orders (
                    id, signal_id, symbol, direction, order_type, order_role,
                    price, trigger_price, requested_qty, filled_qty,
                    average_exec_price, status, reduce_only, parent_order_id,
                    oco_group_id, exit_reason, exchange_order_id, filled_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    filled_qty = excluded.filled_qty,
                    average_exec_price = excluded.average_exec_price,
                    filled_at = COALESCE(excluded.filled_at, orders.filled_at),
                    exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),
                    exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),
                    parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),
                    oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),
                    updated_at = excluded.updated_at
                """,
                (
                    order.id,
                    order.signal_id,
                    order.symbol,
                    order.direction.value,
                    order.order_type.value,
                    order.order_role.value,
                    str(order.price) if order.price else None,
                    str(order.trigger_price) if order.trigger_price else None,
                    str(order.requested_qty),
                    str(order.filled_qty),
                    str(order.average_exec_price) if order.average_exec_price else None,
                    order.status.value,
                    1 if order.reduce_only else 0,
                    order.parent_order_id,
                    order.oco_group_id,
                    order.exit_reason,
                    order.exchange_order_id,
                    order.filled_at,
                    order.created_at,
                    order.updated_at,
                )
            )
            await self._db.commit()
            logger.debug(f"订单已保存：{order.id}, status={order.status.value}, role={order.order_role.value}")

    async def save_batch(self, orders: List[Order]) -> None:
        """
        Save multiple orders in a single transaction.

        Args:
            orders: List of Order objects to save
        """
        async with self._lock:
            # 使用 BEGIN 显式开启事务
            await self._db.execute("BEGIN")
            try:
                for order in orders:
                    await self._db.execute(
                        """
                        INSERT INTO orders (
                            id, signal_id, symbol, direction, order_type, order_role,
                            price, trigger_price, requested_qty, filled_qty,
                            average_exec_price, status, reduce_only, parent_order_id,
                            oco_group_id, exit_reason, exchange_order_id, filled_at,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            status = excluded.status,
                            filled_qty = excluded.filled_qty,
                            average_exec_price = excluded.average_exec_price,
                            filled_at = COALESCE(excluded.filled_at, orders.filled_at),
                            exchange_order_id = COALESCE(excluded.exchange_order_id, orders.exchange_order_id),
                            exit_reason = COALESCE(excluded.exit_reason, orders.exit_reason),
                            parent_order_id = COALESCE(excluded.parent_order_id, orders.parent_order_id),
                            oco_group_id = COALESCE(excluded.oco_group_id, orders.oco_group_id),
                            updated_at = excluded.updated_at
                        """,
                        (
                            order.id,
                            order.signal_id,
                            order.symbol,
                            order.direction.value,
                            order.order_type.value,
                            order.order_role.value,
                            str(order.price) if order.price else None,
                            str(order.trigger_price) if order.trigger_price else None,
                            str(order.requested_qty),
                            str(order.filled_qty),
                            str(order.average_exec_price) if order.average_exec_price else None,
                            order.status.value,
                            1 if order.reduce_only else 0,
                            order.parent_order_id,
                            order.oco_group_id,
                            order.exit_reason,
                            order.exchange_order_id,
                            order.filled_at,
                            order.created_at,
                            order.updated_at,
                        )
                    )
                await self._db.commit()
            except Exception as e:
                await self._db.rollback()
                raise e
            logger.info(f"批量保存订单：{len(orders)} 个")

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
        Update order status and optional fields.

        Args:
            order_id: Order ID to update
            status: New order status
            filled_qty: Updated filled quantity (optional)
            average_exec_price: Updated average execution price (optional)
            filled_at: Filled timestamp (optional)
            exchange_order_id: Exchange order ID (optional)
            exit_reason: Exit reason for SL/TP orders (optional)
        """
        async with self._lock:
            update_fields = ["status = ?", "updated_at = ?"]
            params = [status.value, int(datetime.now(timezone.utc).timestamp() * 1000)]

            if filled_qty is not None:
                update_fields.append("filled_qty = ?")
                params.append(str(filled_qty))

            if average_exec_price is not None:
                update_fields.append("average_exec_price = ?")
                params.append(str(average_exec_price))

            if exchange_order_id is not None:
                update_fields.append("exchange_order_id = ?")
                params.append(exchange_order_id)

            if exit_reason is not None:
                update_fields.append("exit_reason = ?")
                params.append(exit_reason)

            params.append(order_id)

            await self._db.execute(
                f"""
                UPDATE orders
                SET {", ".join(update_fields)}
                WHERE id = ?
                """,
                tuple(params)
            )
            await self._db.commit()
            logger.debug(f"订单状态已更新：{order_id}, status={status.value}")

    async def mark_order_filled(self, order_id: str, filled_at: int) -> None:
        """
        标记订单已成交（T4 专用接口）。

        Args:
            order_id: Order ID to update
            filled_at: Filled timestamp in milliseconds
        """
        async with self._lock:
            await self._db.execute(
                """
                UPDATE orders
                SET status = 'FILLED',
                    filled_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    filled_at,
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                    order_id
                )
            )
            await self._db.commit()
            logger.debug(f"订单已标记为成交：{order_id}, filled_at={filled_at}")

    async def save_order(self, order: Order) -> None:
        """
        保存订单（创建或更新）- T4 标准接口别名。

        Args:
            order: Order object to save
        """
        await self.save(order)

    async def get_order_detail(self, order_id: str) -> Optional[Order]:
        """
        获取订单详情 - T4 标准接口别名。

        Args:
            order_id: Order ID to query

        Returns:
            Order object or None if not found
        """
        return await self.get_order(order_id)

    # ============================================================
    # Read Operations
    # ============================================================
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get a single order by ID.

        Args:
            order_id: Order ID to query

        Returns:
            Order object or None if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE id = ?",
                (order_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row:
                return self._row_to_order(row)
            return None

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        """
        Get all orders for a specific signal.

        Args:
            signal_id: Signal ID to query

        Returns:
            List of Order objects
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE signal_id = ? ORDER BY created_at ASC",
                (signal_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]:
        """
        Get orders for a specific symbol.

        Args:
            symbol: Trading symbol to query
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol, limit)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_orders_by_status(self, status: OrderStatus, symbol: Optional[str] = None) -> List[Order]:
        """
        Get orders by status.

        Args:
            status: Order status to filter
            symbol: Optional symbol to filter

        Returns:
            List of Order objects
        """
        async with self._lock:
            if symbol:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE status = ? AND symbol = ? ORDER BY created_at DESC",
                    (status.value, symbol)
                )
            else:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
                    (status.value,)
                )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders (status = OPEN or PARTIALLY_FILLED).

        Args:
            symbol: Optional symbol to filter

        Returns:
            List of Order objects
        """
        async with self._lock:
            if symbol:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE status IN ('OPEN', 'PARTIALLY_FILLED') AND symbol = ? ORDER BY created_at DESC",
                    (symbol,)
                )
            else:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE status IN ('OPEN', 'PARTIALLY_FILLED') ORDER BY created_at DESC"
                )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_orders_by_role(
        self,
        role: OrderRole,
        signal_id: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        """
        Get orders by role.

        Args:
            role: Order role to filter
            signal_id: Optional signal ID to filter
            symbol: Optional symbol to filter

        Returns:
            List of Order objects
        """
        async with self._lock:
            query = "SELECT * FROM orders WHERE order_role = ?"
            params = [role.value]

            if signal_id:
                query += " AND signal_id = ?"
                params.append(signal_id)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)

            query += " ORDER BY created_at DESC"

            cursor = await self._db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_order_chain(self, signal_id: str) -> Dict[str, List[Order]]:
        """
        Get the complete order chain for a signal.

        Args:
            signal_id: Signal ID

        Returns:
            Dictionary with order lists by role:
            {
                "entry": [Order],
                "tps": [Order],
                "sl": [Order]
            }
        """
        orders = await self.get_orders_by_signal(signal_id)

        entry_orders = []
        tp_orders = []
        sl_orders = []

        for order in orders:
            if order.order_role == OrderRole.ENTRY:
                entry_orders.append(order)
            elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]:
                tp_orders.append(order)
            elif order.order_role == OrderRole.SL:
                sl_orders.append(order)

        return {
            "entry": entry_orders,
            "tps": tp_orders,
            "sl": sl_orders,
        }

    async def get_oco_group(self, oco_group_id: str) -> List[Order]:
        """
        Get all orders in an OCO group.

        Args:
            oco_group_id: OCO group ID

        Returns:
            List of Order objects
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE oco_group_id = ? ORDER BY created_at ASC",
                (oco_group_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_order_count(self, signal_id: str) -> int:
        """
        Get total order count for a signal.

        Args:
            signal_id: Signal ID

        Returns:
            Order count
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM orders WHERE signal_id = ?",
                (signal_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()

            return row[0] if row else 0

    # ============================================================
    # Utility Methods
    # ============================================================
    def _row_to_order(self, row: aiosqlite.Row) -> Order:
        """
        Convert a database row to an Order object.

        Args:
            row: Database row

        Returns:
            Order object
        """
        return Order(
            id=row["id"],
            signal_id=row["signal_id"],
            symbol=row["symbol"],
            direction=Direction(row["direction"]),
            order_type=OrderType(row["order_type"]),
            order_role=OrderRole(row["order_role"]),
            price=Decimal(row["price"]) if row["price"] else None,
            trigger_price=Decimal(row["trigger_price"]) if row["trigger_price"] else None,
            requested_qty=Decimal(row["requested_qty"]),
            filled_qty=Decimal(row["filled_qty"]),
            average_exec_price=Decimal(row["average_exec_price"]) if row["average_exec_price"] else None,
            status=OrderStatus(row["status"]),
            reduce_only=bool(row["reduce_only"]),
            parent_order_id=row["parent_order_id"],
            oco_group_id=row["oco_group_id"],
            exit_reason=row["exit_reason"],
            exchange_order_id=row["exchange_order_id"],
            filled_at=row["filled_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_all_orders(self, limit: int = 1000) -> List[Order]:
        """
        Get all orders with pagination.

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def delete_order(self, order_id: str) -> None:
        """
        Delete an order from the database.

        Args:
            order_id: Order ID to delete
        """
        async with self._lock:
            await self._db.execute(
                "DELETE FROM orders WHERE id = ?",
                (order_id,)
            )
            await self._db.commit()
            logger.debug(f"订单已删除：{order_id}")

    async def clear_orders(self, signal_id: Optional[str] = None, symbol: Optional[str] = None) -> int:
        """
        Clear orders by signal or symbol.

        Args:
            signal_id: Optional signal ID to filter
            symbol: Optional symbol to filter

        Returns:
            Number of orders deleted
        """
        async with self._lock:
            if signal_id:
                cursor = await self._db.execute(
                    "DELETE FROM orders WHERE signal_id = ?",
                    (signal_id,)
                )
            elif symbol:
                cursor = await self._db.execute(
                    "DELETE FROM orders WHERE symbol = ?",
                    (symbol,)
                )
            else:
                cursor = await self._db.execute("DELETE FROM orders")

            deleted_count = cursor.rowcount
            await self._db.commit()
            await cursor.close()

            logger.info(f"订单已清理：{deleted_count} 个")
            return deleted_count
