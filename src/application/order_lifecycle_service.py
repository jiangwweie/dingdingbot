"""
Order Lifecycle Service - 订单全生命周期服务层

ORD-1: 订单状态机系统性重构 - T2 任务

核心职责:
1. 统一管理订单从创建到终结的完整生命周期
2. 封装状态机转换逻辑
3. 提供订单操作的统一接口
4. 集成审计日志记录
5. 触发订单变更回调（用于 WebSocket 推送）

依赖:
- OrderStateMachine: 状态转换核心
- OrderRepository: 订单持久化
- OrderAuditLogger: 审计日志记录
"""
import asyncio
from typing import Optional, Dict, Any, List, Callable, Awaitable
from decimal import Decimal
import logging
from datetime import datetime, timezone

from src.domain.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    OrderStrategy,
    Position,
)
from src.domain.order_state_machine import OrderStateMachine, OrderTransitionError
from src.domain.exceptions import InvalidOrderStateTransition
from src.infrastructure.repository_ports import OrderRepositoryPort
from src.application.order_audit_logger import OrderAuditLogger, OrderAuditEventType, OrderAuditTriggerSource

logger = logging.getLogger(__name__)

TERMINAL_ORDER_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
}
ORDER_STATUS_RANK = {
    OrderStatus.CREATED: 0,
    OrderStatus.PENDING: 0,
    OrderStatus.SUBMITTED: 1,
    OrderStatus.OPEN: 2,
    OrderStatus.PARTIALLY_FILLED: 3,
    OrderStatus.FILLED: 4,
    OrderStatus.CANCELED: 4,
    OrderStatus.REJECTED: 4,
    OrderStatus.EXPIRED: 4,
}


class OrderLifecycleService:
    """
    订单全生命周期服务

    核心职责:
    1. 统一管理订单从创建到终结的完整生命周期
    2. 封装状态机转换逻辑
    3. 提供订单操作的统一接口
    4. 集成审计日志记录
    5. 触发订单变更回调（用于 WebSocket 推送）

    使用示例:
        service = OrderLifecycleService(repository, audit_logger)
        await service.start()

        # 创建订单
        order = await service.create_order(
            strategy=strategy,
            signal_id="sig_123",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            total_qty=Decimal('1.0'),
            initial_sl_rr=Decimal('-1.0'),
            tp_targets=[Decimal('1.5'), Decimal('2.0'), Decimal('3.0')]
        )

        # 提交订单
        await service.submit_order(order.id, exchange_order_id="binance_123")

        # 确认挂单
        await service.confirm_order(order.id)

        # 更新成交
        await service.update_order_filled(
            order.id,
            filled_qty=Decimal('1.0'),
            average_exec_price=Decimal('65000')
        )

        # 取消订单
        await service.cancel_order(order.id, reason="User requested")
    """

    def __init__(
        self,
        repository: OrderRepositoryPort,
        audit_logger: Optional[OrderAuditLogger] = None,
        pending_update_retry_interval_seconds: float = 0.1,
        pending_update_max_retries: int = 5,
    ):
        """
        初始化订单生命周期服务

        Args:
            repository: 订单仓库
            audit_logger: 审计日志服务（可选）
        """
        self._repository = repository
        self._audit_logger = audit_logger
        self._on_order_changed: Optional[Callable[[Order], Awaitable[None]]] = None
        self._state_machines: Dict[str, OrderStateMachine] = {}

        # MVP-Protected-Position-Step2: ENTRY 部分成交后的保护单挂载回调
        self._on_entry_partially_filled: Optional[Callable[[Order], Awaitable[None]]] = None
        self._on_entry_filled: Optional[Callable[[Order], Awaitable[None]]] = None
        self._on_exit_progressed: Optional[Callable[[Order], Awaitable[None]]] = None
        self._on_exit_filled: Optional[Callable[[Order], Awaitable[None]]] = None
        self._pending_exchange_updates: Dict[str, Dict[str, Any]] = {}
        self._pending_update_tasks: Dict[str, asyncio.Task] = {}
        self._pending_update_retry_interval_seconds = pending_update_retry_interval_seconds
        self._pending_update_max_retries = pending_update_max_retries

    async def start(self) -> None:
        """启动服务"""
        await self._repository.initialize()
        if self._audit_logger:
            await self._audit_logger.start(queue_size=1000)  # 显式传入队列容量参数，增强可读性
        logger.info("OrderLifecycleService 已启动")

    async def stop(self) -> None:
        """停止服务"""
        await self._cancel_pending_update_tasks()
        if self._audit_logger:
            await self._audit_logger.stop()
        self._state_machines.clear()
        logger.info("OrderLifecycleService 已停止")

    async def _cancel_pending_update_tasks(self) -> None:
        """Cancel in-memory retry tasks for early exchange updates."""
        tasks = list(self._pending_update_tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Pending exchange update retry task shutdown error: %s",
                    exc,
                    exc_info=True,
                )
        self._pending_update_tasks.clear()
        self._pending_exchange_updates.clear()

    def list_pending_exchange_updates(self) -> Dict[str, Dict[str, Any]]:
        """Return a shallow diagnostic snapshot of buffered exchange updates."""
        return {
            exchange_order_id: {
                "first_seen_at": item.get("first_seen_at"),
                "last_seen_at": item.get("last_seen_at"),
                "retry_count": item.get("retry_count", 0),
                "order_status": getattr(item.get("order"), "status", None).value
                if getattr(item.get("order"), "status", None) is not None
                else None,
            }
            for exchange_order_id, item in self._pending_exchange_updates.items()
        }

    def set_order_changed_callback(
        self,
        callback: Callable[[Order], Awaitable[None]]
    ) -> None:
        """
        设置订单变更回调（用于 WebSocket 推送）

        Args:
            callback: 异步回调函数，接收 Order 对象
        """
        self._on_order_changed = callback

    def set_entry_partially_filled_callback(
        self,
        callback: Callable[[Order], Awaitable[None]]
    ) -> None:
        """
        设置 ENTRY 部分成交回调（用于挂载保护单）

        MVP-Protected-Position-Step2: ENTRY 部分成交后挂载最小保护单

        Args:
            callback: 异步回调函数，接收 Order 对象
        """
        self._on_entry_partially_filled = callback

    def set_entry_filled_callback(
        self,
        callback: Callable[[Order], Awaitable[None]]
    ) -> None:
        """设置 ENTRY 完全成交回调（用于挂载保护单与更新投影）。"""
        self._on_entry_filled = callback

    def set_exit_filled_callback(
        self,
        callback: Callable[[Order], Awaitable[None]]
    ) -> None:
        """设置 TP/SL 完全成交回调（用于更新 position projection）。"""
        self._on_exit_filled = callback

    def set_exit_progressed_callback(
        self,
        callback: Callable[[Order], Awaitable[None]]
    ) -> None:
        """设置 TP/SL 成交推进回调（部分成交/完全成交均可触发，用于增量投影）。"""
        self._on_exit_progressed = callback

    async def _notify_order_changed(self, order: Order) -> None:
        """通知订单已变更"""
        if self._on_order_changed:
            try:
                await self._on_order_changed(order)
            except Exception as e:
                logger.error(f"订单变更回调失败：{e}", exc_info=True)

    async def _log_audit(
        self,
        order: Order,
        event_type: OrderAuditEventType,
        triggered_by: OrderAuditTriggerSource,
        old_status: Optional[str] = None,
        new_status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录审计日志"""
        if self._audit_logger:
            try:
                await self._audit_logger.log(
                    order_id=order.id,
                    signal_id=order.signal_id,
                    old_status=old_status,
                    new_status=new_status or order.status.value,
                    event_type=event_type,
                    triggered_by=triggered_by,
                    metadata=metadata,
                )
            except Exception as e:
                logger.error(f"审计日志记录失败：{e}", exc_info=True)

    def _get_or_create_state_machine(self, order: Order) -> OrderStateMachine:
        """获取或创建状态机"""
        if order.id not in self._state_machines:
            state_machine = OrderStateMachine(order)

            async def on_transition(o: Order, old: OrderStatus, new: OrderStatus):
                """状态转换回调"""
                # 触发订单变更通知
                await self._notify_order_changed(o)

                # 记录审计日志
                await self._log_audit(
                    order=o,
                    event_type=self._map_status_to_event(old, new),
                    triggered_by=OrderAuditTriggerSource.SYSTEM,
                    old_status=old.value,
                    new_status=new.value,
                )

            state_machine.set_transition_callback(on_transition)
            self._state_machines[order.id] = state_machine
        else:
            # 更新状态机持有的订单对象引用，确保状态转换反映到正确的对象上
            self._state_machines[order.id]._order = order
        return self._state_machines[order.id]

    @staticmethod
    def _map_status_to_event(old_status: OrderStatus, new_status: OrderStatus) -> OrderAuditEventType:
        """将状态转换映射到审计事件类型"""
        event_map = {
            (OrderStatus.CREATED, OrderStatus.SUBMITTED): OrderAuditEventType.ORDER_SUBMITTED,
            (OrderStatus.CREATED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
            (OrderStatus.SUBMITTED, OrderStatus.OPEN): OrderAuditEventType.ORDER_CONFIRMED,
            (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED): OrderAuditEventType.ORDER_PARTIAL_FILLED,
            (OrderStatus.SUBMITTED, OrderStatus.FILLED): OrderAuditEventType.ORDER_FILLED,
            (OrderStatus.SUBMITTED, OrderStatus.REJECTED): OrderAuditEventType.ORDER_REJECTED,
            (OrderStatus.SUBMITTED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
            (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED): OrderAuditEventType.ORDER_PARTIAL_FILLED,
            (OrderStatus.OPEN, OrderStatus.FILLED): OrderAuditEventType.ORDER_FILLED,
            (OrderStatus.OPEN, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
            (OrderStatus.OPEN, OrderStatus.REJECTED): OrderAuditEventType.ORDER_REJECTED,
            (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED): OrderAuditEventType.ORDER_FILLED,
            (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELED): OrderAuditEventType.ORDER_CANCELED,
        }
        return event_map.get((old_status, new_status), OrderAuditEventType.ORDER_UPDATED)

    # ============================================================
    # 核心方法 - 订单生命周期管理
    # ============================================================

    async def create_order(
        self,
        strategy: OrderStrategy,
        signal_id: str,
        symbol: str,
        direction: Direction,
        total_qty: Decimal,
        initial_sl_rr: Decimal,
        tp_targets: List[Decimal],
    ) -> Order:
        """
        创建订单 - 订单生命周期的起点

        Args:
            strategy: 订单策略
            signal_id: 信号 ID
            symbol: 交易对
            direction: 方向
            total_qty: 总数量
            initial_sl_rr: 初始止损 RR 倍数
            tp_targets: TP 目标价格列表

        Returns:
            创建的订单对象
        """
        from src.domain.order_manager import OrderManager
        import uuid

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 使用 OrderManager 创建 ENTRY 订单
        order_manager = OrderManager()
        orders = order_manager.create_order_chain(
            strategy=strategy,
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            total_qty=total_qty,
            initial_sl_rr=initial_sl_rr,
            tp_targets=tp_targets,
        )

        if not orders:
            raise ValueError("创建订单失败：OrderManager 返回空列表")

        order = orders[0]
        order.status = OrderStatus.CREATED  # 确保初始状态为 CREATED

        # 保存到仓库
        await self._repository.save(order)

        # 创建状态机（自动记录 CREATED 事件）
        state_machine = self._get_or_create_state_machine(order)

        # 记录订单创建审计日志
        await self._log_audit(
            order=order,
            event_type=OrderAuditEventType.ORDER_CREATED,
            triggered_by=OrderAuditTriggerSource.USER,
            new_status=OrderStatus.CREATED.value,
            metadata={
                "strategy_name": strategy.name if strategy else None,
                "symbol": symbol,
                "direction": direction.value,
                "quantity": str(total_qty),
            }
        )

        # 触发变更通知
        await self._notify_order_changed(order)

        logger.info(f"订单创建成功：{order.id} (策略：{strategy.name if strategy else 'N/A'}, 币种：{symbol})")
        return order

    async def register_created_order(
        self,
        order: Order,
        *,
        triggered_by: OrderAuditTriggerSource = OrderAuditTriggerSource.SYSTEM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Order:
        """注册一个已生成但尚未提交的订单。"""
        order.status = OrderStatus.CREATED
        await self._repository.save(order)
        self._get_or_create_state_machine(order)
        await self._log_audit(
            order=order,
            event_type=OrderAuditEventType.ORDER_CREATED,
            triggered_by=triggered_by,
            new_status=OrderStatus.CREATED.value,
            metadata=metadata,
        )
        await self._notify_order_changed(order)
        return order

    async def submit_order(
        self,
        order_id: str,
        exchange_order_id: Optional[str] = None
    ) -> Order:
        """
        提交订单到交易所

        Args:
            order_id: 订单 ID
            exchange_order_id: 交易所订单 ID（可选）

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        # 获取订单
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        # 获取状态机并执行转换
        state_machine = self._get_or_create_state_machine(order)

        if exchange_order_id:
            order.exchange_order_id = exchange_order_id

        await state_machine.transition_to(
            OrderStatus.SUBMITTED,
            trigger_source="SYSTEM",
            metadata={"action": "submit_to_exchange", "exchange_order_id": exchange_order_id}
        )

        # 保存到仓库
        await self._repository.save(order)

        logger.info(f"订单已提交：{order_id} -> 交易所 ID: {exchange_order_id or 'N/A'}")
        return order

    async def confirm_order(
        self,
        order_id: str,
        exchange_order_id: Optional[str] = None
    ) -> Order:
        """
        确认订单挂单（交易所已接受）

        Args:
            order_id: 订单 ID
            exchange_order_id: 交易所订单 ID（可选）

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)

        if exchange_order_id:
            order.exchange_order_id = exchange_order_id

        await state_machine.transition_to(
            OrderStatus.OPEN,
            trigger_source="EXCHANGE",
            metadata={"action": "confirm_open"}
        )

        await self._repository.save(order)
        logger.info(f"订单已确认挂单：{order_id}")
        return order

    async def update_order_partially_filled(
        self,
        order_id: str,
        filled_qty: Decimal,
        average_exec_price: Decimal,
    ) -> Order:
        """
        更新订单为部分成交

        Args:
            order_id: 订单 ID
            filled_qty: 已成交数量
            average_exec_price: 平均成交价

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)
        order.filled_qty = filled_qty
        order.average_exec_price = average_exec_price

        await state_machine.mark_partially_filled(
            filled_qty=str(filled_qty),
            average_exec_price=str(average_exec_price)
        )

        await self._repository.save(order)
        logger.info(f"订单部分成交：{order_id} (数量：{filled_qty}, 价格：{average_exec_price})")
        return order

    async def update_order_filled(
        self,
        order_id: str,
        filled_qty: Decimal,
        average_exec_price: Decimal,
    ) -> Order:
        """
        更新订单为完全成交

        Args:
            order_id: 订单 ID
            filled_qty: 已成交数量
            average_exec_price: 平均成交价

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)
        order.filled_qty = filled_qty
        order.average_exec_price = average_exec_price

        await state_machine.mark_filled(
            filled_qty=str(filled_qty),
            average_exec_price=str(average_exec_price)
        )

        await self._repository.save(order)
        logger.info(f"订单完全成交：{order_id} (数量：{filled_qty}, 价格：{average_exec_price})")
        return order

    async def update_order_requested_qty(
        self,
        order_id: str,
        new_requested_qty: Decimal,
    ) -> Order:
        """
        更新订单的请求数量（P1-6：用于调整 SL 订单覆盖全仓）

        注意：此方法只更新本地事实（requested_qty + updated_at），不调用交易所改单接口。
        适用场景：partial-fill 增量补挂时，调整已有 SL 的数量以覆盖全部已成交仓位。

        Args:
            order_id: 订单 ID
            new_requested_qty: 新的请求数量

        Returns:
            更新后的订单对象

        Raises:
            ValueError: 订单不存在
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        old_qty = order.requested_qty
        order.requested_qty = new_requested_qty
        order.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)

        await self._repository.save(order)
        logger.info(
            f"订单请求数量已更新：{order_id} "
            f"(旧数量：{old_qty}, 新数量：{new_requested_qty})"
        )
        return order

    async def update_order_from_exchange(
        self,
        order: Order
    ) -> Order:
        """
        根据交易所推送更新订单状态

        P0 修复：统一契约，直接接收 Order 对象
        ExchangeGateway._handle_order_update() 已经解析了 CCXT 原始数据为 Order 对象

        P0 修复（第二步）：使用 exchange_order_id 查询本地订单
        ExchangeGateway 推送的 Order.id 是交易所订单 ID，不是本地订单 ID

        Args:
            order: 交易所推送的订单对象（已解析）

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        exchange_order_id = order.exchange_order_id

        if not exchange_order_id:
            raise ValueError(f"交易所订单 ID 为空，无法查询本地订单")

        return await self._apply_exchange_update(order, buffer_if_missing=True)

    async def _apply_exchange_update(
        self,
        order: Order,
        *,
        buffer_if_missing: bool,
    ) -> Order:
        """Apply an exchange order update, optionally buffering early unknown updates."""
        exchange_order_id = order.exchange_order_id
        if not exchange_order_id:
            raise ValueError(f"交易所订单 ID 为空，无法查询本地订单")

        local_order = await self._repository.get_order_by_exchange_id(exchange_order_id)
        if not local_order:
            if buffer_if_missing:
                self._buffer_unknown_exchange_update(exchange_order_id, order)
                return order
            raise ValueError(f"订单不存在：exchange_order_id={exchange_order_id}")

        if self._should_ignore_stale_or_regressive_update(local_order, order):
            self._clear_pending_exchange_update(exchange_order_id)
            return local_order

        # 直接从 Order 对象读取字段（已经是 Decimal 类型）
        target_status = order.status
        filled_qty = order.filled_qty
        average_exec_price = order.average_exec_price

        # 获取状态机
        state_machine = self._get_or_create_state_machine(local_order)

        previous_status = local_order.status
        previous_filled_qty = local_order.filled_qty

        # 更新本地订单数据
        if order.exchange_order_id:
            local_order.exchange_order_id = order.exchange_order_id
        if filled_qty > 0:
            local_order.filled_qty = filled_qty
        if average_exec_price:
            local_order.average_exec_price = average_exec_price

        # 执行状态转换
        if target_status == OrderStatus.FILLED:
            # 完全成交
            if previous_status != OrderStatus.FILLED:
                await state_machine.mark_filled(
                    filled_qty=str(filled_qty),
                    average_exec_price=str(average_exec_price) if average_exec_price else "0"
                )
        elif target_status == OrderStatus.PARTIALLY_FILLED:
            # 部分成交
            # MVP-Protected-Position-Step2: 避免重复状态转换
            # 如果订单已经是 PARTIALLY_FILLED，只更新成交信息，不触发状态转换
            if local_order.status != OrderStatus.PARTIALLY_FILLED:
                await state_machine.mark_partially_filled(
                    filled_qty=str(filled_qty),
                    average_exec_price=str(average_exec_price) if average_exec_price else "0"
                )

            # MVP-Protected-Position-Step2: ENTRY 部分成交后挂载最小保护单
            # 仅对 ENTRY 订单且已成交数量 > 0 时触发
            # 注意：只在首次部分成交时触发（避免重复挂载）
            if local_order.order_role == OrderRole.ENTRY and filled_qty > 0:
                # 检查是否已有保护单（避免重复挂载）
                all_orders = await self._repository.get_orders_by_signal(local_order.signal_id)
                existing_protection = [
                    o for o in all_orders
                    if o.parent_order_id == local_order.id
                    and o.order_role in [OrderRole.SL, OrderRole.TP1, OrderRole.TP2]
                ]

                if not existing_protection:
                    logger.info(
                        f"[OrderLifecycleService] ENTRY 部分成交，触发保护单挂载: "
                        f"order_id={local_order.id}, filled_qty={filled_qty}, "
                        f"average_exec_price={average_exec_price}"
                    )

                    # 触发保护单挂载回调
                    if self._on_entry_partially_filled:
                        try:
                            await self._on_entry_partially_filled(local_order)
                        except Exception as e:
                            logger.error(
                                f"[OrderLifecycleService] 保护单挂载回调失败: "
                                f"order_id={local_order.id}, error={e}",
                                exc_info=True
                            )
        elif target_status == OrderStatus.CANCELED:
            # 取消订单
            await state_machine.mark_canceled(oco_triggered=False)
        elif target_status == OrderStatus.REJECTED:
            # 拒绝订单
            await state_machine.mark_rejected(reason="Exchange rejected")
        elif target_status == OrderStatus.OPEN:
            # 订单开放但有成交量 → 部分成交
            if filled_qty > 0 and filled_qty < local_order.requested_qty:
                await state_machine.mark_partially_filled(
                    filled_qty=str(filled_qty),
                    average_exec_price=str(average_exec_price) if average_exec_price else "0"
                )
            # 订单开放且无成交量 → 确认挂单
            elif local_order.status != OrderStatus.OPEN:
                await state_machine.confirm_open()

        await self._repository.save(local_order)

        if (
            local_order.order_role in {
                OrderRole.EXIT,
                OrderRole.SL,
                OrderRole.TP1,
                OrderRole.TP2,
                OrderRole.TP3,
                OrderRole.TP4,
                OrderRole.TP5,
            }
            and filled_qty > previous_filled_qty
            and self._on_exit_progressed is not None
        ):
            try:
                await self._on_exit_progressed(local_order)
            except Exception as e:
                logger.error(
                    f"[OrderLifecycleService] EXIT 成交推进回调失败: "
                    f"order_id={local_order.id}, error={e}",
                    exc_info=True
                )

        if (
            target_status == OrderStatus.FILLED
            and previous_status != OrderStatus.FILLED
            and local_order.order_role == OrderRole.ENTRY
            and filled_qty > 0
            and self._on_entry_filled is not None
        ):
            try:
                await self._on_entry_filled(local_order)
            except Exception as e:
                logger.error(
                    f"[OrderLifecycleService] ENTRY 完全成交回调失败: "
                    f"order_id={local_order.id}, error={e}",
                    exc_info=True
                )

        if (
            target_status == OrderStatus.FILLED
            and previous_status != OrderStatus.FILLED
            and local_order.order_role in {
                OrderRole.EXIT,
                OrderRole.SL,
                OrderRole.TP1,
                OrderRole.TP2,
                OrderRole.TP3,
                OrderRole.TP4,
                OrderRole.TP5,
            }
            and filled_qty > 0
            and self._on_exit_filled is not None
        ):
            try:
                await self._on_exit_filled(local_order)
            except Exception as e:
                logger.error(
                    f"[OrderLifecycleService] EXIT 完全成交回调失败: "
                    f"order_id={local_order.id}, error={e}",
                    exc_info=True
                )

        logger.info(f"订单根据交易所数据更新：{local_order.id} (exchange_id={exchange_order_id}) -> {target_status.value}")
        self._clear_pending_exchange_update(exchange_order_id)
        return local_order

    def _clear_pending_exchange_update(self, exchange_order_id: str) -> None:
        self._pending_exchange_updates.pop(exchange_order_id, None)
        completed_retry_task = self._pending_update_tasks.pop(exchange_order_id, None)
        current_task = asyncio.current_task()
        if completed_retry_task is not None and completed_retry_task is not current_task:
            completed_retry_task.cancel()

    def _should_ignore_stale_or_regressive_update(
        self,
        local_order: Order,
        exchange_update: Order,
    ) -> bool:
        local_status = local_order.status
        incoming_status = exchange_update.status
        incoming_filled = exchange_update.filled_qty or Decimal("0")
        local_filled = local_order.filled_qty or Decimal("0")
        incoming_updated_at = exchange_update.updated_at or 0
        local_updated_at = local_order.updated_at or 0

        if local_status in TERMINAL_ORDER_STATUSES:
            if incoming_status == local_status:
                logger.debug(
                    "Ignoring duplicate terminal exchange order update: "
                    "order_id=%s exchange_order_id=%s status=%s",
                    local_order.id,
                    exchange_update.exchange_order_id,
                    incoming_status.value,
                )
                return True
            if incoming_status not in TERMINAL_ORDER_STATUSES:
                logger.warning(
                    "Ignoring regressive exchange order update for terminal local order: "
                    "order_id=%s exchange_order_id=%s local_status=%s incoming_status=%s",
                    local_order.id,
                    exchange_update.exchange_order_id,
                    local_status.value,
                    incoming_status.value,
                )
                return True
            logger.warning(
                "Ignoring conflicting terminal exchange order update: "
                "order_id=%s exchange_order_id=%s local_status=%s incoming_status=%s",
                local_order.id,
                exchange_update.exchange_order_id,
                local_status.value,
                incoming_status.value,
            )
            return True

        if (
            incoming_updated_at
            and local_updated_at
            and incoming_updated_at < local_updated_at
            and ORDER_STATUS_RANK.get(incoming_status, 0) <= ORDER_STATUS_RANK.get(local_status, 0)
            and incoming_filled <= local_filled
        ):
            logger.warning(
                "Ignoring stale exchange order update: order_id=%s exchange_order_id=%s "
                "local_status=%s incoming_status=%s local_updated_at=%s incoming_updated_at=%s",
                local_order.id,
                exchange_update.exchange_order_id,
                local_status.value,
                incoming_status.value,
                local_updated_at,
                incoming_updated_at,
            )
            return True

        if (
            ORDER_STATUS_RANK.get(incoming_status, 0) < ORDER_STATUS_RANK.get(local_status, 0)
            and incoming_filled <= local_filled
        ):
            logger.warning(
                "Ignoring regressive exchange order update: order_id=%s exchange_order_id=%s "
                "local_status=%s incoming_status=%s local_filled=%s incoming_filled=%s",
                local_order.id,
                exchange_update.exchange_order_id,
                local_status.value,
                incoming_status.value,
                local_filled,
                incoming_filled,
            )
            return True

        return False

    def _buffer_unknown_exchange_update(
        self,
        exchange_order_id: str,
        order: Order,
    ) -> None:
        """Buffer a user-stream update that arrived before the local order row."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        existing = self._pending_exchange_updates.get(exchange_order_id)
        first_seen_at = existing.get("first_seen_at") if existing else now_ms
        retry_count = existing.get("retry_count", 0) if existing else 0
        self._pending_exchange_updates[exchange_order_id] = {
            "order": order,
            "first_seen_at": first_seen_at,
            "last_seen_at": now_ms,
            "retry_count": retry_count,
        }
        if exchange_order_id not in self._pending_update_tasks:
            self._pending_update_tasks[exchange_order_id] = asyncio.create_task(
                self._retry_pending_exchange_update(exchange_order_id),
                name=f"pending-exchange-update:{exchange_order_id}",
            )
        logger.warning(
            "Buffered unknown exchange order update: exchange_order_id=%s status=%s retry_count=%s",
            exchange_order_id,
            getattr(order.status, "value", order.status),
            retry_count,
        )

    async def _retry_pending_exchange_update(self, exchange_order_id: str) -> None:
        """Retry applying one buffered update for a short race window."""
        try:
            while True:
                await asyncio.sleep(self._pending_update_retry_interval_seconds)
                pending = self._pending_exchange_updates.get(exchange_order_id)
                if pending is None:
                    return
                retry_count = int(pending.get("retry_count", 0)) + 1
                pending["retry_count"] = retry_count
                try:
                    await self._apply_exchange_update(
                        pending["order"],
                        buffer_if_missing=False,
                    )
                    return
                except ValueError:
                    if retry_count >= self._pending_update_max_retries:
                        logger.warning(
                            "Dropping unresolved exchange order update after retries: "
                            "exchange_order_id=%s retry_count=%s first_seen_at=%s",
                            exchange_order_id,
                            retry_count,
                            pending.get("first_seen_at"),
                        )
                        self._pending_exchange_updates.pop(exchange_order_id, None)
                        return
                except Exception as exc:
                    logger.warning(
                        "Pending exchange order update replay failed: exchange_order_id=%s error=%s",
                        exchange_order_id,
                        exc,
                        exc_info=True,
                    )
                    if retry_count >= self._pending_update_max_retries:
                        self._pending_exchange_updates.pop(exchange_order_id, None)
                        return
        finally:
            current_task = asyncio.current_task()
            stored_task = self._pending_update_tasks.get(exchange_order_id)
            if stored_task is current_task:
                self._pending_update_tasks.pop(exchange_order_id, None)

    async def cancel_order(
        self,
        order_id: str,
        reason: Optional[str] = None,
        oco_triggered: bool = False
    ) -> Order:
        """
        取消订单

        Args:
            order_id: 订单 ID
            reason: 取消原因
            oco_triggered: 是否由 OCO 逻辑触发

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)

        await state_machine.mark_canceled(
            reason=reason,
            oco_triggered=oco_triggered
        )

        await self._repository.save(order)

        # 记录审计日志
        await self._log_audit(
            order=order,
            event_type=OrderAuditEventType.ORDER_CANCELED,
            triggered_by=OrderAuditTriggerSource.USER if not oco_triggered else OrderAuditTriggerSource.SYSTEM,
            old_status=order.status.value,
            new_status=OrderStatus.CANCELED.value,
            metadata={
                "cancel_reason": reason,
                "oco_triggered": oco_triggered,
            }
        )

        logger.info(f"订单已取消：{order_id} (原因：{reason or 'N/A'}, OCO: {oco_triggered})")
        return order

    async def mark_stale_protection_orders_after_external_close(
        self,
        signal_id: str,
        *,
        source: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Order]:
        """Terminalize active local protection orders after exchange-flat proof.

        This is a local hygiene transition only. It must not call the exchange.
        The external-close monitor invokes it after reconciliation proves the
        exchange position is already flat and position projection has marked the
        local position unresolved-closed.
        """
        orders = await self.get_orders_by_signal(signal_id)
        active_statuses = {
            OrderStatus.SUBMITTED,
            OrderStatus.OPEN,
            OrderStatus.PARTIALLY_FILLED,
        }
        protection_roles = {
            OrderRole.SL,
            OrderRole.TP1,
            OrderRole.TP2,
            OrderRole.TP3,
            OrderRole.TP4,
            OrderRole.TP5,
        }
        terminalized: List[Order] = []
        for order in orders:
            if order.order_role not in protection_roles or order.status not in active_statuses:
                continue

            old_status = order.status
            state_machine = self._get_or_create_state_machine(order)
            await state_machine.mark_canceled(
                reason=reason,
                oco_triggered=True,
            )
            order.exit_reason = "EXTERNAL_CLOSE_LOCAL_HYGIENE"
            await self._repository.save(order)
            await self._log_audit(
                order=order,
                event_type=OrderAuditEventType.ORDER_CANCELED,
                triggered_by=OrderAuditTriggerSource.SYSTEM,
                old_status=old_status.value,
                new_status=OrderStatus.CANCELED.value,
                metadata={
                    "operation": "external_close_local_hygiene",
                    "source": source,
                    "reason": reason,
                    **dict(metadata or {}),
                },
            )
            terminalized.append(order)

        if terminalized:
            logger.warning(
                "Stale local protection orders terminalized after external close: "
                "signal_id=%s source=%s order_ids=%s",
                signal_id,
                source,
                [order.id for order in terminalized],
            )
        return terminalized

    async def reject_order(
        self,
        order_id: str,
        reason: str
    ) -> Order:
        """
        标记订单为被拒绝

        Args:
            order_id: 订单 ID
            reason: 拒绝原因

        Returns:
            更新后的订单对象
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)
        await state_machine.mark_rejected(reason=reason)
        await self._repository.save(order)

        logger.warning(f"订单被拒绝：{order_id} (原因：{reason})")
        return order

    async def expire_order(self, order_id: str) -> Order:
        """
        标记订单为已过期

        Args:
            order_id: 订单 ID

        Returns:
            更新后的订单对象
        """
        order = await self._get_order(order_id)
        if not order:
            raise ValueError(f"订单不存在：{order_id}")

        state_machine = self._get_or_create_state_machine(order)
        await state_machine.mark_expired()
        await self._repository.save(order)

        logger.info(f"订单已过期：{order_id}")
        return order

    # ============================================================
    # 查询方法
    # ============================================================

    async def _get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return await self._repository.get_order(order_id)

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        获取订单

        Args:
            order_id: 订单 ID

        Returns:
            订单对象，不存在返回 None
        """
        return await self._get_order(order_id)

    async def get_orders_by_signal(self, signal_id: str) -> List[Order]:
        """
        根据信号 ID 获取订单列表

        Args:
            signal_id: 信号 ID

        Returns:
            订单列表
        """
        return await self._repository.get_orders_by_signal(signal_id)

    async def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """
        根据币种获取订单列表

        Args:
            symbol: 交易对

        Returns:
            订单列表
        """
        return await self._repository.get_orders_by_symbol(symbol)

    async def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """
        根据状态获取订单列表

        Args:
            status: 订单状态

        Returns:
            订单列表
        """
        return await self._repository.get_orders_by_status(status)

    async def get_open_orders(self) -> List[Order]:
        """
        获取所有未完成的订单

        Returns:
            未完成订单列表
        """
        return await self._repository.get_open_orders()

    def get_state_machine(self, order_id: str) -> Optional[OrderStateMachine]:
        """
        获取订单的状态机

        Args:
            order_id: 订单 ID

        Returns:
            状态机对象，不存在返回 None
        """
        return self._state_machines.get(order_id)
