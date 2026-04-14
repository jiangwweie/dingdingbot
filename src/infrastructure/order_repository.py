"""
Order Repository - SQLite persistence for trading orders.

P5-011: 订单清理机制
- 所有订单都要有迹可循，本地都要入库
- 支持订单的保存、查询、更新状态
- 支持订单链追踪（ENTRY -> TP/SL）
"""
import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple, Set

import aiosqlite

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction,
    OrderResponse, OrderResponseFull,
)

logger = logging.getLogger(__name__)


class OrderRepository:
    """
    SQLite repository for persisting trading orders.

    核心职责:
    1. 订单持久化 - 所有系统生成的订单都必须入库
    2. 订单状态追踪 - 记录订单从创建到终结的全生命周期
    3. 订单链管理 - 通过 parent_order_id 和 oco_group_id 追踪关联订单
    4. 查询服务 - 支持按信号、币种、状态、角色等多维度查询

    依赖注入:
    - ExchangeGateway: 交易所网关（可选）
    - OrderAuditLogger: 审计日志器（可选）
    """

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
        exchange_gateway: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
    ):
        """
        Initialize OrderRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
            exchange_gateway: ExchangeGateway instance for canceling orders (dependency injection)
            audit_logger: OrderAuditLogger instance for audit logging (dependency injection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        # ✅ 修复：使用字典存储每个事件循环专用的 Lock
        self._locks: Dict[int, asyncio.Lock] = {}
        self._global_lock = threading.Lock()  # 保护 _locks 字典
        self._sync_lock = threading.Lock()  # 用于同步调用场景
        self._exchange_gateway = exchange_gateway  # 依赖注入：交易所网关
        self._audit_logger = audit_logger  # 依赖注入：审计日志器
        logger.info(f"订单仓库初始化完成：{db_path}")

    def set_exchange_gateway(self, gateway: Any) -> None:
        """设置交易所网关（依赖注入）"""
        self._exchange_gateway = gateway

    def set_audit_logger(self, logger_instance: Any) -> None:
        """设置审计日志器（依赖注入）"""
        self._audit_logger = logger_instance

    def _ensure_lock(self) -> asyncio.Lock:
        """
        获取当前事件循环专用的 Lock。

        使用双重检查锁定模式确保线程安全。
        每个事件循环有独立的 Lock，避免跨事件循环共享导致的竞态条件。

        Returns:
            asyncio.Lock: 当前事件循环专用的锁实例
        """
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            # 同步调用场景：返回同步锁
            # 注意：这种情况下获得的锁无法在异步代码中使用
            return self._sync_lock

        # 双重检查锁定模式
        if loop_id not in self._locks:
            with self._global_lock:
                # 再次检查，避免多个线程同时创建 Lock
                if loop_id not in self._locks:
                    self._locks[loop_id] = asyncio.Lock()

        return self._locks[loop_id]

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.

        This method is idempotent - calling it multiple times has no effect after first initialization.
        """
        # 幂等性检查：如果已经初始化，直接返回
        if self._db is not None:
            return

        async with self._ensure_lock():
            # Create connection if not injected
            if self._owns_connection and self._db is None:
                # Create data directory if not exists
                db_dir = os.path.dirname(self.db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)

                # Open database connection via connection pool (shared across repos)
                from src.infrastructure.connection_pool import get_connection as pool_get_connection
                self._db = await pool_get_connection(self.db_path)
                # PRAGMAs are set centrally in connection_pool, no need to repeat here

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
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            async with self._ensure_lock():
                await self._db.commit()
                self._db = None
                logger.info("订单仓库本地引用已清除")

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
        async with self._ensure_lock():
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
                    -- IMP-001 修复：直接更新为 excluded 值，支持将字段更新为 NULL
                    filled_at = excluded.filled_at,
                    exchange_order_id = excluded.exchange_order_id,
                    exit_reason = excluded.exit_reason,
                    parent_order_id = excluded.parent_order_id,
                    oco_group_id = excluded.oco_group_id,
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
        async with self._ensure_lock():
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
                            -- IMP-001 修复：直接更新为 excluded 值，支持将字段更新为 NULL
                            filled_at = excluded.filled_at,
                            exchange_order_id = excluded.exchange_order_id,
                            exit_reason = excluded.exit_reason,
                            parent_order_id = excluded.parent_order_id,
                            oco_group_id = excluded.oco_group_id,
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
        async with self._ensure_lock():
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
        async with self._ensure_lock():
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
        async with self._ensure_lock():
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
        async with self._ensure_lock():
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE signal_id = ? ORDER BY created_at ASC",
                (signal_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def get_by_signal_id(self, signal_id: str) -> List[Order]:
        """
        Get all orders for a specific signal - alias for get_orders_by_signal.

        Args:
            signal_id: Signal ID to query

        Returns:
            List of Order objects
        """
        return await self.get_orders_by_signal(signal_id)

    async def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        order_role: Optional[OrderRole] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Get orders with pagination and optional filters.

        Args:
            symbol: Optional symbol to filter
            status: Optional status to filter
            order_role: Optional order role to filter
            limit: Maximum number of orders to return (1-200)
            offset: Pagination offset (default 0)

        Returns:
            Dict with:
                - items: List of Order objects
                - total: Total count matching filters
                - limit: Requested limit
                - offset: Requested offset
        """
        async with self._ensure_lock():
            # Build WHERE clause
            where_conditions = []
            params: List[Any] = []

            if symbol:
                where_conditions.append("symbol = ?")
                params.append(symbol)

            if status:
                where_conditions.append("status = ?")
                params.append(status.value)

            if order_role:
                where_conditions.append("order_role = ?")
                params.append(order_role.value)

            # Build final WHERE clause
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)
            else:
                where_clause = ""

            # Get total count
            count_query = f"SELECT COUNT(*) FROM orders {where_clause}" if where_clause else "SELECT COUNT(*) FROM orders"
            count_cursor = await self._db.execute(count_query, tuple(params))
            total = (await count_cursor.fetchone())[0]
            await count_cursor.close()

            # Get paginated results
            params.append(limit)
            params.append(offset)

            query = f"""
                SELECT * FROM orders
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = await self._db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            await cursor.close()

            return {
                'items': [self._row_to_order(row) for row in rows],
                'total': total,
                'limit': limit,
                'offset': offset,
            }

    async def get_orders_by_signal_ids(
        self,
        signal_ids: List[str],
        page: int = 1,
        page_size: int = 20,
        order_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get orders by multiple signal IDs (for backtest report orders).

        Args:
            signal_ids: List of signal IDs to query
            page: Page number (1-based)
            page_size: Page size (1-100)
            order_role: Optional order role filter (ENTRY/TP1/SL/etc)

        Returns:
            Dict with:
                - orders: List of Order objects
                - total: Total count
                - page: Current page
                - page_size: Page size
        """
        async with self._ensure_lock():
            # Build WHERE clause
            placeholders = ','.join('?' * len(signal_ids))
            where_clause = f"signal_id IN ({placeholders})"
            params = list(signal_ids)

            # Add order_role filter if provided
            if order_role:
                where_clause += " AND order_role = ?"
                params.append(order_role)

            # Get total count
            count_cursor = await self._db.execute(
                f"SELECT COUNT(*) FROM orders WHERE {where_clause}",
                tuple(params)
            )
            total = (await count_cursor.fetchone())[0]
            await count_cursor.close()

            # Get paginated results
            offset = (page - 1) * page_size
            params.append(page_size)
            params.append(offset)

            cursor = await self._db.execute(
                f"""
                SELECT * FROM orders
                WHERE {where_clause}
                ORDER BY created_at ASC
                LIMIT ? OFFSET ?
                """,
                tuple(params)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return {
                'orders': [self._row_to_order(row) for row in rows],
                'total': total,
                'page': page,
                'page_size': page_size,
            }

    async def get_orders_by_symbol(self, symbol: str, limit: int = 100) -> List[Order]:
        """
        Get orders for a specific symbol.

        Args:
            symbol: Trading symbol to query
            limit: Maximum number of orders to return

        Returns:
            List of Order objects
        """
        async with self._ensure_lock():
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
        async with self._ensure_lock():
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
        async with self._ensure_lock():
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

    async def get_by_status(self, status: str) -> List[Order]:
        """
        Get all orders by status.

        Args:
            status: Order status to filter

        Returns:
            List of Order objects
        """
        async with self._ensure_lock():
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC",
                (status,)
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
        async with self._ensure_lock():
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

    async def get_order_chain_by_order_id(self, order_id: str) -> List[Order]:
        """
        Get the complete order chain by order ID (ENTRY or child order).

        This method retrieves:
        - If order_id is an ENTRY order: all child orders (TP/SL) with this parent_order_id
        - If order_id is a child order: the parent ENTRY order + all sibling orders

        Args:
            order_id: Order ID

        Returns:
            List of Order objects in the chain (ENTRY first, then TP/SL orders)
        """
        async with self._ensure_lock():
            # First, get the target order
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE id = ? ORDER BY created_at ASC",
                (order_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()

            if not row:
                return []

            target_order = self._row_to_order(row)

            # Determine the parent_order_id and oco_group_id
            if target_order.order_role == OrderRole.ENTRY:
                # This is an ENTRY order, get all children
                parent_id = target_order.id
                oco_group_id = target_order.oco_group_id
            else:
                # This is a child order, get the parent and siblings
                parent_id = target_order.parent_order_id
                oco_group_id = target_order.oco_group_id

            orders = []

            # Get parent ENTRY order if exists
            if parent_id:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE id = ? ORDER BY created_at ASC",
                    (parent_id,)
                )
                parent_row = await cursor.fetchone()
                await cursor.close()

                if parent_row:
                    orders.append(self._row_to_order(parent_row))

            # Get all child orders (TP/SL)
            if parent_id or target_order.order_role == OrderRole.ENTRY:
                search_parent_id = parent_id if parent_id else target_order.id
                cursor = await self._db.execute(
                    """
                    SELECT * FROM orders
                    WHERE parent_order_id = ?
                    ORDER BY
                        CASE order_role
                            WHEN 'TP1' THEN 1
                            WHEN 'TP2' THEN 2
                            WHEN 'TP3' THEN 3
                            WHEN 'TP4' THEN 4
                            WHEN 'TP5' THEN 5
                            WHEN 'SL' THEN 6
                            ELSE 7
                        END,
                        created_at ASC
                    """,
                    (search_parent_id,)
                )
                child_rows = await cursor.fetchall()
                await cursor.close()

                for child_row in child_rows:
                    orders.append(self._row_to_order(child_row))

            return orders

    async def get_oco_group(self, oco_group_id: str) -> List[Order]:
        """
        Get all orders in an OCO group.

        Args:
            oco_group_id: OCO group ID

        Returns:
            List of Order objects
        """
        async with self._ensure_lock():
            cursor = await self._db.execute(
                "SELECT * FROM orders WHERE oco_group_id = ? ORDER BY created_at ASC",
                (oco_group_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    # ============================================================
    # Order Tree Methods (订单管理级联展示功能)
    # ============================================================
    async def get_order_tree(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = 7,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        获取订单树形结构（分页加载）

        实现思路:
        1. 查询所有 ENTRY 订单（根节点）- 分页
        2. 批量查询这些 ENTRY 的子订单（通过 parent_order_id IN (...)）
        3. 在内存中组装树形结构

        Args:
            symbol: 币种对过滤（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            days: 最近 N 天（可选，默认 7 天）
            page: 页码（从 1 开始）
            page_size: 每页数量（默认 50，最大 200）

        Returns:
            {
                "items": List[Dict[str, Any]],  # 树形结构列表
                "total": int,                    # 当前页根订单数
                "total_count": int,              # 总根订单数（用于分页）
                "page": int,                     # 当前页码
                "page_size": int,                # 每页数量
                "metadata": Dict[str, Any],      # 元数据
            }
        """
        lock = self._ensure_lock()
        async with lock:
            # Step 1: 获取根订单列表（ENTRY 角色）- 分页
            root_orders, total_count = await self._get_entry_orders(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                days=days,
                page=page,
                page_size=page_size,
            )

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
                    }
                }

            # Step 2: 批量获取所有子订单
            entry_ids = [o.id for o in root_orders]
            child_orders = await self._get_child_orders(entry_ids)

            # Step 3: 内存组装树形结构
            order_map = {}
            for order in root_orders:
                order_map[order.id] = {
                    "order": self._order_to_response(order),
                    "children": [],
                    "level": 0,
                    "has_children": False,  # 先设为 False，后面会更新
                }

            # 将子订单添加到父节点的 children 中
            for child in child_orders:
                parent_id = child.parent_order_id
                if parent_id in order_map:
                    order_map[parent_id]["children"].append({
                        "order": self._order_to_response(child),
                        "children": [],
                        "level": 1,
                        "has_children": False,
                    })
                    order_map[parent_id]["has_children"] = True

            return {
                "items": list(order_map.values()),
                "total": len(root_orders),
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "metadata": {
                    "symbol_filter": symbol,
                    "days_filter": days,
                    "loaded_at": int(datetime.now(timezone.utc).timestamp() * 1000),
                }
            }

    async def _get_entry_orders(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        days: Optional[int] = 7,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Order], int]:
        """
        获取 ENTRY 订单列表（根节点）- 分页

        Args:
            symbol: 币种对过滤
            start_date: 开始日期
            end_date: 结束日期
            days: 最近 N 天
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            Tuple of (List of Order objects, total_count)
        """
        # Build WHERE clause
        where_conditions = ["order_role = ?"]
        params: List[Any] = [OrderRole.ENTRY.value]

        if symbol:
            where_conditions.append("symbol = ?")
            params.append(symbol)

        # Handle date filtering
        if start_date:
            where_conditions.append("created_at >= ?")
            params.append(int(start_date.timestamp() * 1000))
        elif end_date:
            where_conditions.append("created_at <= ?")
            params.append(int(end_date.timestamp() * 1000))
        elif days:
            from datetime import timedelta
            start_ts = datetime.now(timezone.utc) - timedelta(days=days)
            where_conditions.append("created_at >= ?")
            params.append(int(start_ts.timestamp() * 1000))

        where_clause = "WHERE " + " AND ".join(where_conditions)

        # 注意：不使用锁，因为调用方（get_order_tree）已经持有锁
        # Get total count
        count_cursor = await self._db.execute(
            f"SELECT COUNT(*) FROM orders {where_clause}",
            tuple(params)
        )
        total_count = (await count_cursor.fetchone())[0]
        await count_cursor.close()

        # Get paginated results with LIMIT and OFFSET
        offset = (page - 1) * page_size
        params.append(page_size)
        params.append(offset)
        cursor = await self._db.execute(
            f"""
            SELECT * FROM orders
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        return [self._row_to_order(row) for row in rows], total_count

    async def _get_child_orders(self, parent_ids: List[str]) -> List[Order]:
        """
        批量获取子订单列表

        Args:
            parent_ids: 父订单 ID 列表

        Returns:
            List of child Order objects
        """
        if not parent_ids:
            return []

        placeholders = ','.join('?' * len(parent_ids))

        # 注意：不使用锁，因为调用方（get_order_tree）已经持有锁
        cursor = await self._db.execute(
            f"""
            SELECT * FROM orders
            WHERE parent_order_id IN ({placeholders})
            ORDER BY
                CASE order_role
                    WHEN 'TP1' THEN 1
                    WHEN 'TP2' THEN 2
                    WHEN 'TP3' THEN 3
                    WHEN 'TP4' THEN 4
                    WHEN 'TP5' THEN 5
                    WHEN 'SL' THEN 6
                    ELSE 7
                END,
                created_at ASC
            """,
            tuple(parent_ids)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        return [self._row_to_order(row) for row in rows]

    def _order_to_response(self, order: Order) -> Dict[str, Any]:
        """
        Convert Order to OrderResponseFull dictionary

        Args:
            order: Order object

        Returns:
            Dictionary with OrderResponseFull fields
        """
        from decimal import Decimal

        # 计算剩余数量
        remaining_qty = order.requested_qty - order.filled_qty

        return {
            "order_id": order.id,
            "exchange_order_id": order.exchange_order_id,
            "symbol": order.symbol,
            "order_type": order.order_type.value,
            "order_role": order.order_role.value,
            "direction": order.direction.value,
            "status": order.status.value,
            "quantity": str(order.requested_qty),
            "filled_qty": str(order.filled_qty),
            "remaining_qty": str(remaining_qty),
            "price": str(order.price) if order.price else None,
            "trigger_price": str(order.trigger_price) if order.trigger_price else None,
            "average_exec_price": str(order.average_exec_price) if order.average_exec_price else None,
            "reduce_only": order.reduce_only,
            "signal_id": order.signal_id,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
            "filled_at": order.filled_at,
        }

    async def _get_all_related_order_ids(self, order_ids: List[str]) -> Set[str]:
        """
        递归获取所有关联订单 ID（包括子订单和父订单）

        Args:
            order_ids: 初始订单 ID 列表

        Returns:
            所有关联订单 ID 集合
        """
        all_ids = set(order_ids)
        queue = list(order_ids)

        while queue:
            current_id = queue.pop(0)

            # 获取子订单
            cursor = await self._db.execute(
                "SELECT id FROM orders WHERE parent_order_id = ?",
                (current_id,)
            )
            child_rows = await cursor.fetchall()
            await cursor.close()

            for child_row in child_rows:
                child_id = child_row[0]
                if child_id not in all_ids:
                    all_ids.add(child_id)
                    queue.append(child_id)

            # 获取父订单
            cursor = await self._db.execute(
                "SELECT parent_order_id FROM orders WHERE id = ?",
                (current_id,)
            )
            parent_row = await cursor.fetchone()
            await cursor.close()

            if parent_row and parent_row[0] and parent_row[0] not in all_ids:
                all_ids.add(parent_row[0])
                queue.append(parent_row[0])

        return all_ids

    async def delete_orders_batch(
        self,
        order_ids: List[str],
        cancel_on_exchange: bool = True,
        audit_info: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        批量删除订单（带事务保护）

        Args:
            order_ids: 订单 ID 列表
            cancel_on_exchange: 是否调用交易所取消接口
            audit_info: 审计信息（operator_id, ip_address, user_agent）

        Returns:
            {
                "deleted_count": int,
                "cancelled_on_exchange": List[str],
                "failed_to_cancel": List[Dict[str, str]],
                "deleted_from_db": List[str],
                "failed_to_delete": List[Dict[str, str]],
                "audit_log_id": Optional[str],
            }
        """
        import json
        import uuid

        result = {
            "deleted_count": 0,
            "cancelled_on_exchange": [],
            "failed_to_cancel": [],
            "deleted_from_db": [],
            "failed_to_delete": [],
            "audit_log_id": None,
        }

        # 验证参数
        if not order_ids:
            raise ValueError("订单 ID 列表不能为空")

        if len(order_ids) > 100:
            raise ValueError("批量删除最多支持 100 个订单")

        # 注意：移除外层锁，避免锁嵌套死锁
        # 数据库事务操作在单独的锁上下文中执行
        try:
            # Step 1: 收集所有需要删除的订单 ID（包括级联子订单）
            # FIX-004: 使用递归方法获取完整订单链
            all_order_ids = await self._get_all_related_order_ids(order_ids)

            # Step 2: 获取订单详情
            orders_to_delete = []
            for oid in all_order_ids:
                cursor = await self._db.execute(
                    "SELECT * FROM orders WHERE id = ?",
                    (oid,)
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row:
                    orders_to_delete.append(self._row_to_order(row))

            # Step 3: 取消 OPEN 状态的订单（调用交易所 API）
            # FIX-001: 使用注入的 ExchangeGateway 实例
            if cancel_on_exchange:
                for order in orders_to_delete:
                        if order.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
                            if order.exchange_order_id and self._exchange_gateway:
                                try:
                                    result_cancel = await self._exchange_gateway.cancel_order(
                                        exchange_order_id=order.exchange_order_id,
                                        symbol=order.symbol,
                                    )
                                    if result_cancel.is_success:
                                        result["cancelled_on_exchange"].append(order.id)
                                    else:
                                        result["failed_to_cancel"].append({
                                            "order_id": order.id,
                                            "reason": result_cancel.error_message or "Unknown error",
                                        })
                                except Exception as e:
                                    # FIX-009: 取消失败记录为 warning（业务异常）
                                    logger.warning(f"取消订单失败 {order.id}: {e}")
                                    result["failed_to_cancel"].append({
                                        "order_id": order.id,
                                        "reason": str(e),
                                    })
                            elif not self._exchange_gateway:
                                # FIX-009: 预期行为降级为 info
                                logger.info(f"跳过交易所取消：ExchangeGateway 未注入")
                                result["failed_to_cancel"].append({
                                    "order_id": order.id,
                                    "reason": "ExchangeGateway not initialized",
                                })
                            else:
                                # 没有 exchange_order_id，无法调用交易所
                                result["failed_to_cancel"].append({
                                    "order_id": order.id,
                                    "reason": "No exchange_order_id",
                                })

            # Step 4: 批量删除数据库记录（事务保护）
            # FIX-005: 分批删除，避免单次操作过大
            BATCH_SIZE = 50
            await self._db.execute("BEGIN")
            try:
                for i in range(0, len(orders_to_delete), BATCH_SIZE):
                    batch = orders_to_delete[i:i + BATCH_SIZE]
                    placeholders = ','.join('?' * len(batch))
                    await self._db.execute(
                        f"DELETE FROM orders WHERE id IN ({placeholders})",
                        tuple(o.id for o in batch)
                    )
                await self._db.commit()
                result["deleted_from_db"] = [o.id for o in orders_to_delete]
                result["deleted_count"] = len(result["deleted_from_db"])
            except Exception as db_error:
                await self._db.rollback()
                raise db_error

            # Step 5: 记录审计日志
            # FIX-002: 使用注入的审计日志器（全局单例）
            audit_log_id = str(uuid.uuid4())
            result["audit_log_id"] = audit_log_id

            try:
                from src.domain.models import OrderAuditEventType, OrderAuditTriggerSource

                if self._audit_logger:
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
                            # FIX-010: 增加失败详情
                            "failed_to_cancel": result["failed_to_cancel"],
                            "failed_to_delete": result.get("failed_to_delete", []),
                            "operator_id": audit_info.get("operator_id") if audit_info else None,
                            "ip_address": audit_info.get("ip_address") if audit_info else None,
                        },
                    )
                    logger.info(f"审计日志已记录：{audit_log_id}")
                else:
                    # FIX-009: 预期行为降级为 info
                    logger.info("审计日志器未注入，跳过日志记录")
            except Exception as audit_error:
                # FIX-009: 审计日志失败记录为 error（系统错误）
                logger.error(f"记录审计日志失败：{audit_error}")

            return result


        except Exception as e:
            logger.error(f"批量删除订单失败：{str(e)}")
            raise e

    async def get_order_count(self, signal_id: str) -> int:
        """
        Get total order count for a signal.

        Args:
            signal_id: Signal ID

        Returns:
            Order count
        """
        async with self._ensure_lock():
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
        async with self._ensure_lock():
            cursor = await self._db.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [self._row_to_order(row) for row in rows]

    async def delete_order(self, order_id: str, cascade: bool = True) -> None:
        """
        Delete an order from the database.

        P1-005: 支持级联清理
        - 如果删除的是 ENTRY 订单，默认级联删除关联的 TP/SL 订单
        - 删除子订单（TP/SL）时，不级联删除父订单

        Args:
            order_id: Order ID to delete
            cascade: If True and order is ENTRY, cascade delete child TP/SL orders
        """
        async with self._ensure_lock():
            # 获取订单信息以判断是否需要级联删除
            order = await self.get_order(order_id)
            if not order:
                logger.warning(f"尝试删除不存在的订单：{order_id}")
                return

            # 如果是 ENTRY 订单且启用级联删除，先删除关联的 TP/SL 订单
            if cascade and order.order_role == OrderRole.ENTRY:
                # 删除子订单（通过 parent_order_id 关联）
                await self._db.execute(
                    "DELETE FROM orders WHERE parent_order_id = ?",
                    (order_id,)
                )
                logger.debug(f"级联删除子订单 (parent={order_id})")

                # 删除 OCO 组中的订单（通过 oco_group_id 关联）
                if order.oco_group_id:
                    await self._db.execute(
                        "DELETE FROM orders WHERE oco_group_id = ? AND id != ?",
                        (order.oco_group_id, order_id)
                    )
                    logger.debug(f"级联删除 OCO 组订单 (group={order.oco_group_id})")

            # 删除主订单
            await self._db.execute(
                "DELETE FROM orders WHERE id = ?",
                (order_id,)
            )
            await self._db.commit()
            logger.info(f"订单已删除：{order_id} (cascade={cascade})")

    async def clear_orders(self, signal_id: Optional[str] = None, symbol: Optional[str] = None) -> int:
        """
        Clear orders by signal or symbol.

        Args:
            signal_id: Optional signal ID to filter
            symbol: Optional symbol to filter

        Returns:
            Number of orders deleted
        """
        async with self._ensure_lock():
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

    async def delete_orders_by_signal_id(self, signal_id: str, cascade: bool = True) -> int:
        """
        Delete all orders for a signal (P1-005: 级联清理).

        Args:
            signal_id: Signal ID to delete orders for
            cascade: If True, also delete related child orders

        Returns:
            Number of orders deleted
        """
        async with self._ensure_lock():
            # 先获取所有关联订单
            orders = await self.get_orders_by_signal(signal_id)
            order_ids = [o.id for o in orders]

            # 收集所有需要删除的订单 ID（包括级联的）
            all_to_delete = set(order_ids)

            if cascade:
                # 找到所有 ENTRY 订单
                entry_ids = [o.id for o in orders if o.order_role == OrderRole.ENTRY]

                # 找到所有 ENTRY 的子订单 ID
                for entry_id in entry_ids:
                    # 通过 parent_order_id 查找子订单
                    cursor = await self._db.execute(
                        "SELECT id FROM orders WHERE parent_order_id = ?",
                        (entry_id,)
                    )
                    child_rows = await cursor.fetchall()
                    await cursor.close()
                    all_to_delete.update(row[0] for row in child_rows)

                    # 通过 oco_group_id 查找 OCO 组订单
                    entry_order = next((o for o in orders if o.id == entry_id), None)
                    if entry_order and entry_order.oco_group_id:
                        cursor = await self._db.execute(
                            "SELECT id FROM orders WHERE oco_group_id = ?",
                            (entry_order.oco_group_id,)
                        )
                        oco_rows = await cursor.fetchall()
                        await cursor.close()
                        all_to_delete.update(row[0] for row in oco_rows)

            # 批量删除
            placeholders = ','.join('?' * len(all_to_delete))
            cursor = await self._db.execute(
                f"DELETE FROM orders WHERE id IN ({placeholders})",
                tuple(all_to_delete)
            )
            deleted_count = cursor.rowcount
            await self._db.commit()
            await cursor.close()

            logger.info(f"信号 {signal_id} 的订单已清理：{deleted_count} 个 (cascade={cascade})")
            return deleted_count
