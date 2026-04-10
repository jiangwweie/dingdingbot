"""
Reconciliation Repository - SQLite persistence for reconciliation reports.

P0-003: 完善重启对账流程
- 对账报告持久化到数据库，用于审计和历史查询
- 支持按币种、对账类型、时间范围查询
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

import aiosqlite

from src.domain.models import (
    ReconciliationReport,
    ReconciliationType,
    DiscrepancyType,
    PositionMismatch,
    OrderMismatch,
    GhostOrder,
    ImportedOrder,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    PositionInfo,
    OrderResponse,
)
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class ReconciliationRepository:
    """
    SQLite repository for persisting reconciliation reports.

    核心职责:
    1. 对账报告持久化 - 记录每次对账的摘要和详情
    2. 差异详情追踪 - 存储每个差异项的详细信息
    3. 查询服务 - 支持按币种、类型、时间范围查询
    """

    def __init__(
        self,
        db_path: str = "data/reconciliation.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize ReconciliationRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        self._lock = asyncio.Lock()
        logger.info(f"对账仓库初始化完成：db_path={db_path}")

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create connection if not injected
        if self._owns_connection and self._db is None:
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

            # Create reconciliation_reports table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS reconciliation_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- 基本信息
                    report_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    reconciliation_type TEXT NOT NULL,

                    -- 时间信息
                    started_at INTEGER NOT NULL,
                    completed_at INTEGER,
                    grace_period_seconds INTEGER DEFAULT 10,

                    -- 对账结果摘要
                    is_consistent INTEGER NOT NULL DEFAULT 1,
                    total_discrepancies INTEGER DEFAULT 0,

                    -- 差异统计
                    ghost_orders_count INTEGER DEFAULT 0,
                    orphan_orders_count INTEGER DEFAULT 0,
                    position_mismatch_count INTEGER DEFAULT 0,

                    -- 处理结果
                    actions_taken TEXT,

                    -- 错误信息
                    error_code TEXT,
                    error_message TEXT,

                    -- 元数据
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
                )
            """)

            # Create reconciliation_details table
            await self._db.execute("""
                CREATE TABLE IF NOT EXISTS reconciliation_details (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- 关联信息
                    report_id TEXT NOT NULL,

                    -- 差异类型
                    discrepancy_type TEXT NOT NULL,

                    -- 差异详情（JSON 格式存储完整信息）
                    local_data TEXT,
                    exchange_data TEXT NOT NULL,

                    -- 处理结果
                    action_taken TEXT,
                    action_result TEXT,
                    resolved INTEGER DEFAULT 0,

                    -- 时间戳
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
                )
            """)

            # Create indexes for performance
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_symbol ON reconciliation_reports(symbol)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_type ON reconciliation_reports(reconciliation_type)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_time ON reconciliation_reports(started_at)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_reports_consistency ON reconciliation_reports(is_consistent)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_details_report ON reconciliation_details(report_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_details_type ON reconciliation_details(discrepancy_type)
            """)

            await self._db.commit()
            logger.info("对账仓库表创建完成")

    async def close(self) -> None:
        """Close database connection (only if self-owned)"""
        if self._db and self._owns_connection:
            async with self._lock:
                await self._db.commit()
                await self._db.close()
                self._db = None
                logger.info("对账仓库连接已关闭")

    # ============================================================
    # Write Operations
    # ============================================================

    async def save_report(self, report: ReconciliationReport, reconciliation_type: ReconciliationType = ReconciliationType.STARTUP) -> str:
        """
        Save a reconciliation report to the database.

        Args:
            report: ReconciliationReport object
            reconciliation_type: Type of reconciliation (startup/daily/manual)

        Returns:
            report_id: The ID of the saved report
        """
        async with self._lock:
            current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

            # Prepare actions_taken JSON
            actions_taken = []
            for ghost in report.ghost_orders:
                actions_taken.append({
                    "action": "mark_cancelled",
                    "order_id": ghost.order_id,
                    "symbol": ghost.symbol,
                })
            for imported in report.imported_orders:
                actions_taken.append({
                    "action": "import_order",
                    "order_id": imported.order_id,
                    "symbol": imported.symbol,
                })
            for canceled in report.canceled_orphan_orders:
                actions_taken.append({
                    "action": "cancel_order",
                    "order_id": canceled.order_id,
                    "symbol": canceled.symbol,
                })

            await self._db.execute(
                """
                INSERT INTO reconciliation_reports (
                    report_id, symbol, reconciliation_type,
                    started_at, completed_at, grace_period_seconds,
                    is_consistent, total_discrepancies,
                    ghost_orders_count, orphan_orders_count, position_mismatch_count,
                    actions_taken, error_code, error_message,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.reconciliation_time,  # Use reconciliation_time as report_id for simplicity
                    report.symbol,
                    reconciliation_type.value,
                    report.reconciliation_time,
                    current_time,
                    report.grace_period_seconds,
                    1 if report.is_consistent else 0,
                    report.total_discrepancies,
                    len(report.ghost_orders),
                    len(report.orphan_orders) + len(report.canceled_orphan_orders),
                    len(report.position_mismatches) + len(report.missing_positions),
                    json.dumps(actions_taken),
                    None,  # error_code
                    None,  # error_message
                    current_time,
                    current_time,
                )
            )

            # Save details for each discrepancy
            # Ghost orders
            for ghost in report.ghost_orders:
                await self._save_detail(
                    report_id=str(report.reconciliation_time),
                    discrepancy_type=DiscrepancyType.GHOST_ORDER,
                    local_data={
                        "order_id": ghost.order_id,
                        "symbol": ghost.symbol,
                        "local_status": ghost.local_status.value,
                    },
                    exchange_data={},
                    action_taken="MARKED_CANCELLED",
                    action_result={"action": ghost.action_taken},
                    resolved=1,
                )

            # Orphan orders
            for orphan in report.orphan_orders:
                await self._save_detail(
                    report_id=str(report.reconciliation_time),
                    discrepancy_type=DiscrepancyType.ORPHAN_ORDER,
                    local_data=None,
                    exchange_data=self._order_to_dict(orphan),
                    action_taken="PENDING",
                    action_result=None,
                    resolved=0,
                )

            # Imported orders
            for imported in report.imported_orders:
                await self._save_detail(
                    report_id=str(report.reconciliation_time),
                    discrepancy_type=DiscrepancyType.ORPHAN_ORDER,
                    local_data=None,
                    exchange_data=self._imported_order_to_dict(imported),
                    action_taken="IMPORTED_TO_DB",
                    action_result={"action": imported.action_taken},
                    resolved=1,
                )

            # Canceled orphan orders
            for canceled in report.canceled_orphan_orders:
                await self._save_detail(
                    report_id=str(report.reconciliation_time),
                    discrepancy_type=DiscrepancyType.ORPHAN_ORDER,
                    local_data=None,
                    exchange_data=self._imported_order_to_dict(canceled),
                    action_taken="CANCELLED",
                    action_result={"action": canceled.action_taken},
                    resolved=1,
                )

            await self._db.commit()
            logger.info(f"对账报告已保存：report_id={report.reconciliation_time}, symbol={report.symbol}, discrepancies={report.total_discrepancies}")
            return str(report.reconciliation_time)

    async def _save_detail(
        self,
        report_id: str,
        discrepancy_type: DiscrepancyType,
        local_data: Optional[Dict[str, Any]],
        exchange_data: Dict[str, Any],
        action_taken: Optional[str],
        action_result: Optional[Dict[str, Any]],
        resolved: int,
    ) -> None:
        """Save a reconciliation detail record"""
        await self._db.execute(
            """
            INSERT INTO reconciliation_details (
                report_id, discrepancy_type,
                local_data, exchange_data,
                action_taken, action_result, resolved,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now') * 1000)
            """,
            (
                report_id,
                discrepancy_type.value,
                json.dumps(local_data) if local_data else None,
                json.dumps(exchange_data),
                action_taken,
                json.dumps(action_result) if action_result else None,
                resolved,
            )
        )

    def _order_to_dict(self, order: OrderResponse) -> Dict[str, Any]:
        """Convert OrderResponse to dictionary"""
        return {
            "order_id": order.order_id,
            "exchange_order_id": order.exchange_order_id,
            "symbol": order.symbol,
            "order_type": order.order_type.value,
            "direction": order.direction.value,
            "order_role": order.order_role.value,
            "status": order.status.value,
            "amount": str(order.amount),
            "filled_amount": str(order.filled_amount),
            "price": str(order.price) if order.price else None,
            "trigger_price": str(order.trigger_price) if order.trigger_price else None,
            "reduce_only": order.reduce_only,
        }

    def _imported_order_to_dict(self, order: ImportedOrder) -> Dict[str, Any]:
        """Convert ImportedOrder to dictionary"""
        return {
            "order_id": order.order_id,
            "exchange_order_id": order.exchange_order_id,
            "symbol": order.symbol,
            "order_type": order.order_type.value,
            "direction": order.direction.value,
            "order_role": order.order_role.value,
            "status": order.status.value,
            "amount": str(order.amount),
            "price": str(order.price) if order.price else None,
            "trigger_price": str(order.trigger_price) if order.trigger_price else None,
            "reduce_only": order.reduce_only,
            "imported_at": order.imported_at,
            "action_taken": order.action_taken,
        }

    # ============================================================
    # Read Operations
    # ============================================================

    async def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a reconciliation report by ID.

        Args:
            report_id: Report ID

        Returns:
            Report dictionary or None if not found
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_reports WHERE report_id = ?",
                (report_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()

            if row:
                return dict(row)
            return None

    async def get_reports_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get reconciliation reports for a specific symbol.

        Args:
            symbol: Trading symbol
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_reports WHERE symbol = ? ORDER BY started_at DESC LIMIT ?",
                (symbol, limit)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows]

    async def get_reports_by_type(
        self,
        reconciliation_type: ReconciliationType,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get reconciliation reports by type.

        Args:
            reconciliation_type: Type of reconciliation
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_reports WHERE reconciliation_type = ? ORDER BY started_at DESC LIMIT ?",
                (reconciliation_type.value, limit)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows]

    async def get_recent_reports(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent reconciliation reports.

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_reports ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows]

    async def get_report_details(self, report_id: str) -> List[Dict[str, Any]]:
        """
        Get reconciliation details for a specific report.

        Args:
            report_id: Report ID

        Returns:
            List of detail dictionaries
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_details WHERE report_id = ? ORDER BY created_at ASC",
                (report_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows]

    async def get_inconsistent_reports(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get reports with inconsistencies (discrepancies found).

        Args:
            limit: Maximum number of reports to return

        Returns:
            List of report dictionaries
        """
        async with self._lock:
            cursor = await self._db.execute(
                "SELECT * FROM reconciliation_reports WHERE is_consistent = 0 ORDER BY started_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()

            return [dict(row) for row in rows]

    # ============================================================
    # Utility Methods
    # ============================================================

    async def clear_reports(self, symbol: Optional[str] = None) -> int:
        """
        Clear reconciliation reports.

        Args:
            symbol: Optional symbol to filter

        Returns:
            Number of reports deleted
        """
        async with self._lock:
            if symbol:
                # Delete details first (cascade)
                await self._db.execute(
                    "DELETE FROM reconciliation_details WHERE report_id IN (SELECT report_id FROM reconciliation_reports WHERE symbol = ?)",
                    (symbol,)
                )
                cursor = await self._db.execute(
                    "DELETE FROM reconciliation_reports WHERE symbol = ?",
                    (symbol,)
                )
            else:
                cursor = await self._db.execute("DELETE FROM reconciliation_reports")

            deleted_count = cursor.rowcount
            await self._db.commit()
            await cursor.close()

            logger.info(f"对账报告已清理：{deleted_count} 个")
            return deleted_count
