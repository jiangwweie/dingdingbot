"""
Order Audit Logger - 订单审计日志服务

ORD-5: 订单审计日志

职责：
1. 提供审计日志写入接口
2. 异步队列处理，不阻塞主流程
3. 与 ORD-1 OrderLifecycleService 集成

使用示例:
    audit_logger = OrderAuditLogger(repository)
    await audit_logger.start()

    # 在订单状态变更时记录
    await audit_logger.log_status_change(
        order_id="ord_xxx",
        signal_id="sig_xxx",
        old_status="OPEN",
        new_status="FILLED",
        triggered_by=OrderAuditTriggerSource.EXCHANGE,
        metadata={"filled_qty": "0.5", "price": "50000"},
    )
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging

from src.domain.models import (
    OrderAuditLog,
    OrderAuditLogCreate,
    OrderAuditLogQuery,
    OrderAuditEventType,
    OrderAuditTriggerSource,
)
from src.infrastructure.order_audit_repository import OrderAuditLogRepository

logger = logging.getLogger(__name__)


class OrderAuditLogger:
    """
    订单审计日志服务

    提供审计日志的写入和查询接口，支持异步队列处理
    """

    def __init__(self, repository: OrderAuditLogRepository):
        """
        初始化审计日志服务

        Args:
            repository: 审计日志数据仓库
        """
        self._repository = repository
        self._started = False

    def _validate_event_type(self, event_type) -> OrderAuditEventType:
        """
        验证并转换 event_type 为枚举类型

        Args:
            event_type: 事件类型（可以是枚举或字符串）

        Returns:
            OrderAuditEventType 枚举值

        Raises:
            ValueError: 当传入无效的 event_type 时
        """
        if isinstance(event_type, OrderAuditEventType):
            return event_type
        try:
            return OrderAuditEventType(event_type)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid event_type: {event_type}")

    def _validate_trigger_source(self, triggered_by) -> OrderAuditTriggerSource:
        """
        验证并转换 triggered_by 为枚举类型

        Args:
            triggered_by: 触发来源（可以是枚举或字符串）

        Returns:
            OrderAuditTriggerSource 枚举值

        Raises:
            ValueError: 当传入无效的 triggered_by 时
        """
        if isinstance(triggered_by, OrderAuditTriggerSource):
            return triggered_by
        try:
            return OrderAuditTriggerSource(triggered_by)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid triggered_by: {triggered_by}")

    async def start(self, queue_size: int = 1000) -> None:
        """
        启动审计日志服务

        Args:
            queue_size: 异步队列最大容量
        """
        if not self._started:
            await self._repository.initialize(queue_size)
            self._started = True
            logger.info(f"OrderAuditLogger 已启动（队列容量：{queue_size}）")

    async def stop(self) -> None:
        """停止审计日志服务"""
        if self._started:
            await self._repository.close()
            self._started = False
            logger.info("OrderAuditLogger 已停止")

    async def log(
        self,
        order_id: str,
        new_status: str,
        event_type: OrderAuditEventType,
        triggered_by: OrderAuditTriggerSource,
        signal_id: Optional[str] = None,
        old_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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

        Returns:
            审计日志 ID

        Raises:
            ValueError: 当 event_type 或 triggered_by 参数无效时
        """
        # 类型校验
        validated_event_type = self._validate_event_type(event_type)
        validated_triggered_by = self._validate_trigger_source(triggered_by)

        return await self._repository.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            event_type=validated_event_type,
            triggered_by=validated_triggered_by,
            metadata=metadata,
            use_queue=True,
        )

    async def log_status_change(
        self,
        order_id: str,
        signal_id: Optional[str],
        old_status: Optional[str],
        new_status: str,
        event_type: OrderAuditEventType,
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
            event_type: 事件类型
            triggered_by: 触发来源
            metadata: 元数据

        Returns:
            审计日志 ID

        Raises:
            ValueError: 当 event_type 或 triggered_by 参数无效时
        """
        # 类型校验
        validated_event_type = self._validate_event_type(event_type)
        validated_triggered_by = self._validate_trigger_source(triggered_by)

        return await self._repository.log_status_change(
            order_id=order_id,
            signal_id=signal_id,
            old_status=old_status,
            new_status=new_status,
            triggered_by=validated_triggered_by,
            metadata=metadata,
        )

    async def log_order_created(
        self,
        order_id: str,
        signal_id: Optional[str],
        triggered_by: OrderAuditTriggerSource = OrderAuditTriggerSource.USER,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录订单创建事件"""
        return await self.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=None,
            new_status="CREATED",
            event_type=OrderAuditEventType.ORDER_CREATED,
            triggered_by=triggered_by,
            metadata=metadata,
        )

    async def log_order_submitted(
        self,
        order_id: str,
        signal_id: Optional[str],
        exchange_order_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录订单提交事件"""
        meta = metadata or {}
        if exchange_order_id:
            meta["exchange_order_id"] = exchange_order_id
        return await self.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status="CREATED",
            new_status="SUBMITTED",
            event_type=OrderAuditEventType.ORDER_SUBMITTED,
            triggered_by=OrderAuditTriggerSource.SYSTEM,
            metadata=meta,
        )

    async def log_order_filled(
        self,
        order_id: str,
        signal_id: Optional[str],
        filled_qty: str,
        average_exec_price: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录订单成交事件"""
        meta = metadata or {}
        meta["filled_qty"] = filled_qty
        meta["average_exec_price"] = average_exec_price
        return await self.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=None,  # 可能是 OPEN 或 PARTIALLY_FILLED
            new_status="FILLED",
            event_type=OrderAuditEventType.ORDER_FILLED,
            triggered_by=OrderAuditTriggerSource.EXCHANGE,
            metadata=meta,
        )

    async def log_order_canceled(
        self,
        order_id: str,
        signal_id: Optional[str],
        cancel_reason: Optional[str] = None,
        oco_triggered: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录订单取消事件"""
        meta = metadata or {}
        if cancel_reason:
            meta["cancel_reason"] = cancel_reason
        meta["oco_triggered"] = oco_triggered
        return await self.log(
            order_id=order_id,
            signal_id=signal_id,
            old_status=None,  # 可能是 OPEN、SUBMITTED 等
            new_status="CANCELED",
            event_type=OrderAuditEventType.ORDER_CANCELED,
            triggered_by=OrderAuditTriggerSource.SYSTEM if oco_triggered else OrderAuditTriggerSource.USER,
            metadata=meta,
        )

    async def get_audit_history(self, order_id: str, limit: int = 100) -> List[OrderAuditLog]:
        """
        获取订单审计历史

        Args:
            order_id: 订单 ID
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        return await self._repository.get_by_order_id(order_id, limit)

    async def get_signal_audit_history(self, signal_id: str, limit: int = 1000) -> List[OrderAuditLog]:
        """
        获取信号关联的所有订单审计历史

        Args:
            signal_id: 信号 ID
            limit: 返回数量限制

        Returns:
            审计日志列表
        """
        return await self._repository.get_by_signal_id(signal_id, limit)

    async def query(self, query_params: OrderAuditLogQuery) -> List[OrderAuditLog]:
        """
        通用查询接口

        Args:
            query_params: 查询参数

        Returns:
            审计日志列表
        """
        return await self._repository.query(query_params)
