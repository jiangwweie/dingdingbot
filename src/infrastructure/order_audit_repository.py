"""
Order Audit Log Repository - 订单审计日志数据访问层

ORD-5: 订单审计日志表

职责：
1. 审计日志的持久化
2. 按订单 ID/信号 ID/时间范围查询审计日志
3. 支持异步队列写入

与 ORD-1 集成点：
- OrderLifecycleService._transition() 调用 log_status_change()
- 订单删除时调用 log_delete()
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import uuid
import asyncio

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.models import (
    OrderAuditLog,
    OrderAuditLogCreate,
    OrderAuditLogQuery,
    OrderAuditEventType,
    OrderAuditTriggerSource,
)


class OrderAuditLogRepository:
    """
    订单审计日志数据访问层

    提供审计日志的 CRUD 操作和查询接口
    """

    def __init__(self, db_session_factory=None):
        """
        初始化审计日志仓库

        Args:
            db_session_factory: 数据库 Session 工厂
        """
        self._db_session_factory = db_session_factory
        self._queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None

    async def initialize(self, queue_size: int = 1000) -> None:
        """
        初始化异步队列

        Args:
            queue_size: 队列最大容量
        """
        self._queue = asyncio.Queue(maxsize=queue_size)
        self._worker_task = asyncio.create_task(self._worker())

    async def close(self) -> None:
        """关闭异步写入 Worker"""
        if self._worker_task:
            await self._queue.join()
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """后台 Worker 异步写入审计日志"""
        while True:
            try:
                log_entry = await self._queue.get()
                await self._save_log_entry(log_entry)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # 记录错误但不中断 Worker
                self._queue.task_done()

    async def _save_log_entry(self, log_entry: Dict[str, Any]) -> None:
        """
        保存审计日志到数据库

        Args:
            log_entry: 审计日志字典
        """
        if self._db_session_factory is None:
            return

        async with self._db_session_factory() as session:
            # 使用原始 SQL 插入
            await session.execute(
                """
                INSERT INTO order_audit_logs (
                    id, order_id, signal_id, old_status, new_status,
                    event_type, triggered_by, metadata, created_at
                ) VALUES (
                    :id, :order_id, :signal_id, :old_status, :new_status,
                    :event_type, :triggered_by, :metadata, :created_at
                )
                """,
                log_entry,
            )
            await session.commit()

    async def log(
        self,
        order_id: str,
        new_status: str,
        event_type: OrderAuditEventType,
        triggered_by: OrderAuditTriggerSource,
        signal_id: Optional[str] = None,
        old_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        use_queue: bool = True,
    ) -> str:
        """
        记录审计日志

        Args:
            order_id: 订单 ID
            new_status: 新状态
            event_type: 事件类型
            triggered_by: 触发来源
            signal_id: 信号 ID（可选）
            old_status: 旧状态（可选）
            metadata: 元数据（可选）
            use_queue: 是否使用异步队列（默认 True）

        Returns:
            审计日志 ID
        """
        log_id = f"audit_{uuid.uuid4().hex[:8]}"
        created_at = int(datetime.now(timezone.utc).timestamp() * 1000)

        log_entry = {
            "id": log_id,
            "order_id": order_id,
            "signal_id": signal_id,
            "old_status": old_status,
            "new_status": new_status,
            "event_type": event_type.value if isinstance(event_type, OrderAuditEventType) else event_type,
            "triggered_by": triggered_by.value if isinstance(triggered_by, OrderAuditTriggerSource) else triggered_by,
            "metadata": json.dumps(metadata) if metadata else None,
            "created_at": created_at,
        }

        if use_queue and self._queue is not None:
            # 异步队列写入
            try:
                await self._queue.put(log_entry)
            except asyncio.QueueFull:
                # 队列满时降级为同步写入
                await self._save_log_entry(log_entry)
        else:
            # 同步写入
            await self._save_log_entry(log_entry)

        return log_id

    async def log_status_change(
        self,
        order_id: str,
        signal_id: Optional[str],
        old_status: Optional[str],
        new_status: str,
        triggered_by: OrderAuditTriggerSource,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        便捷方法：记录订单状态变更

        Args:
            order_id: 订单 ID
            signal_id: 信号 ID
            old_status: 旧状态
            new_status: 新状态
            triggered_by: 触发来源
            metadata: 元数据

        Returns:
            审计日志 ID
        """
        # 根据状态变更确定事件类型
        event_type = self._determine_event_type(old_status, new_status)

        return await self.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            event_type=event_type,
            triggered_by=triggered_by,
            metadata=metadata,
        )

    def _determine_event_type(
        self,
        old_status: Optional[str],
        new_status: str,
    ) -> OrderAuditEventType:
        """
        根据状态变更确定事件类型

        Args:
            old_status: 旧状态
            new_status: 新状态

        Returns:
            事件类型
        """
        # 首次创建
        if old_status is None:
            return OrderAuditEventType.ORDER_CREATED

        # 状态转换映射
        event_mapping = {
            (None, "CREATED"): OrderAuditEventType.ORDER_CREATED,
            ("CREATED", "SUBMITTED"): OrderAuditEventType.ORDER_SUBMITTED,
            ("SUBMITTED", "OPEN"): OrderAuditEventType.ORDER_CONFIRMED,
            ("OPEN", "PARTIALLY_FILLED"): OrderAuditEventType.ORDER_PARTIAL_FILLED,
            ("PARTIALLY_FILLED", "FILLED"): OrderAuditEventType.ORDER_FILLED,
            ("OPEN", "FILLED"): OrderAuditEventType.ORDER_FILLED,
            ("*", "CANCELED"): OrderAuditEventType.ORDER_CANCELED,
            ("*", "REJECTED"): OrderAuditEventType.ORDER_REJECTED,
            ("OPEN", "EXPIRED"): OrderAuditEventType.ORDER_EXPIRED,
        }

        # 通配符匹配
        if new_status == "CANCELED":
            return OrderAuditEventType.ORDER_CANCELED
        if new_status == "REJECTED":
            return OrderAuditEventType.ORDER_REJECTED

        # 精确匹配
        key = (old_status, new_status)
        if key in event_mapping:
            return event_mapping[key]

        # 默认为更新事件
        return OrderAuditEventType.ORDER_UPDATED

    async def get_by_order_id(
        self,
        order_id: str,
        limit: int = 100,
    ) -> List[OrderAuditLog]:
        """
        按订单 ID 查询审计日志

        Args:
            order_id: 订单 ID
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        if self._db_session_factory is None:
            return []

        async with self._db_session_factory() as session:
            result = await session.execute(
                """
                SELECT id, order_id, signal_id, old_status, new_status,
                       event_type, triggered_by, metadata, created_at
                FROM order_audit_logs
                WHERE order_id = :order_id
                ORDER BY created_at ASC
                LIMIT :limit
                """,
                {"order_id": order_id, "limit": limit},
            )
            rows = result.fetchall()
            return [self._row_to_model(row) for row in rows]

    async def get_by_signal_id(
        self,
        signal_id: str,
        limit: int = 1000,
    ) -> List[OrderAuditLog]:
        """
        按信号 ID 查询审计日志（用于追踪订单链）

        Args:
            signal_id: 信号 ID
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        if self._db_session_factory is None:
            return []

        async with self._db_session_factory() as session:
            result = await session.execute(
                """
                SELECT id, order_id, signal_id, old_status, new_status,
                       event_type, triggered_by, metadata, created_at
                FROM order_audit_logs
                WHERE signal_id = :signal_id
                ORDER BY created_at ASC
                LIMIT :limit
                """,
                {"signal_id": signal_id, "limit": limit},
            )
            rows = result.fetchall()
            return [self._row_to_model(row) for row in rows]

    async def query(self, query_params: OrderAuditLogQuery) -> List[OrderAuditLog]:
        """
        通用查询接口

        Args:
            query_params: 查询参数

        Returns:
            审计日志列表
        """
        if self._db_session_factory is None:
            return []

        # 构建 SQL 查询
        sql = """
            SELECT id, order_id, signal_id, old_status, new_status,
                   event_type, triggered_by, metadata, created_at
            FROM order_audit_logs
            WHERE 1=1
        """
        params = {}

        if query_params.order_id:
            sql += " AND order_id = :order_id"
            params["order_id"] = query_params.order_id

        if query_params.signal_id:
            sql += " AND signal_id = :signal_id"
            params["signal_id"] = query_params.signal_id

        if query_params.event_type:
            sql += " AND event_type = :event_type"
            params["event_type"] = (
                query_params.event_type.value
                if isinstance(query_params.event_type, OrderAuditEventType)
                else query_params.event_type
            )

        if query_params.triggered_by:
            sql += " AND triggered_by = :triggered_by"
            params["triggered_by"] = (
                query_params.triggered_by.value
                if isinstance(query_params.triggered_by, OrderAuditTriggerSource)
                else query_params.triggered_by
            )

        if query_params.start_time:
            sql += " AND created_at >= :start_time"
            params["start_time"] = query_params.start_time

        if query_params.end_time:
            sql += " AND created_at <= :end_time"
            params["end_time"] = query_params.end_time

        sql += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = query_params.limit
        params["offset"] = query_params.offset

        async with self._db_session_factory() as session:
            result = await session.execute(sql, params)
            rows = result.fetchall()
            return [self._row_to_model(row) for row in rows]

    async def get_by_time_range(
        self,
        start_time: int,
        end_time: int,
        limit: int = 1000,
    ) -> List[OrderAuditLog]:
        """
        按时间范围查询审计日志

        Args:
            start_time: 开始时间（毫秒时间戳）
            end_time: 结束时间（毫秒时间戳）
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        if self._db_session_factory is None:
            return []

        async with self._db_session_factory() as session:
            result = await session.execute(
                """
                SELECT id, order_id, signal_id, old_status, new_status,
                       event_type, triggered_by, metadata, created_at
                FROM order_audit_logs
                WHERE created_at BETWEEN :start_time AND :end_time
                ORDER BY created_at DESC
                LIMIT :limit
                """,
                {"start_time": start_time, "end_time": end_time, "limit": limit},
            )
            rows = result.fetchall()
            return [self._row_to_model(row) for row in rows]

    async def get_by_operation_type(
        self,
        event_type: OrderAuditEventType,
        limit: int = 100,
    ) -> List[OrderAuditLog]:
        """
        按操作类型查询审计日志

        Args:
            event_type: 事件类型
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        if self._db_session_factory is None:
            return []

        async with self._db_session_factory() as session:
            result = await session.execute(
                """
                SELECT id, order_id, signal_id, old_status, new_status,
                       event_type, triggered_by, metadata, created_at
                FROM order_audit_logs
                WHERE event_type = :event_type
                ORDER BY created_at DESC
                LIMIT :limit
                """,
                {"event_type": event_type.value if isinstance(event_type, OrderAuditEventType) else event_type, "limit": limit},
            )
            rows = result.fetchall()
            return [self._row_to_model(row) for row in rows]

    def _row_to_model(self, row) -> OrderAuditLog:
        """
        将数据库行转换为 Pydantic 模型

        Args:
            row: 数据库行

        Returns:
            OrderAuditLog 模型
        """
        return OrderAuditLog(
            id=row.id,
            order_id=row.order_id,
            signal_id=row.signal_id,
            old_status=row.old_status,
            new_status=row.new_status,
            event_type=row.event_type,
            triggered_by=row.triggered_by,
            metadata=json.loads(row.metadata) if row.metadata else None,
            created_at=row.created_at,
        )
