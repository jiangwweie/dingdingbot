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
from src.infrastructure.order_repository import OrderRepository
from src.application.order_audit_logger import OrderAuditLogger, OrderAuditEventType, OrderAuditTriggerSource

logger = logging.getLogger(__name__)


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
        repository: OrderRepository,
        audit_logger: Optional[OrderAuditLogger] = None,
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

    async def start(self) -> None:
        """启动服务"""
        await self._repository.initialize()
        if self._audit_logger:
            await self._audit_logger.start(queue_size=1000)  # 显式传入队列容量参数，增强可读性
        logger.info("OrderLifecycleService 已启动")

    async def stop(self) -> None:
        """停止服务"""
        if self._audit_logger:
            await self._audit_logger.stop()
        self._state_machines.clear()
        logger.info("OrderLifecycleService 已停止")

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

    async def update_order_from_exchange(
        self,
        order: Order
    ) -> Order:
        """
        根据交易所推送更新订单状态

        P0 修复：统一契约，直接接收 Order 对象
        ExchangeGateway._handle_order_update() 已经解析了 CCXT 原始数据为 Order 对象

        Args:
            order: 交易所推送的订单对象（已解析）

        Returns:
            更新后的订单对象

        Raises:
            OrderTransitionError: 状态转换失败
            ValueError: 订单不存在
        """
        # P0 修复：ExchangeGateway 传入的是已解析的 Order 对象
        order_id = order.id

        # 从数据库获取本地订单
        local_order = await self._get_order(order_id)
        if not local_order:
            raise ValueError(f"订单不存在：{order_id}")

        # 直接从 Order 对象读取字段（已经是 Decimal 类型）
        target_status = order.status
        filled_qty = order.filled_qty
        average_exec_price = order.average_exec_price

        # 获取状态机
        state_machine = self._get_or_create_state_machine(local_order)

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
            await state_machine.mark_filled(
                filled_qty=str(filled_qty),
                average_exec_price=str(average_exec_price) if average_exec_price else "0"
            )
        elif target_status == OrderStatus.PARTIALLY_FILLED:
            # 部分成交
            await state_machine.mark_partially_filled(
                filled_qty=str(filled_qty),
                average_exec_price=str(average_exec_price) if average_exec_price else "0"
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
        logger.info(f"订单根据交易所数据更新：{order_id} -> {target_status.value}")
        return local_order

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
        return await self._repository.get_by_signal_id(signal_id)

    async def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """
        根据币种获取订单列表

        Args:
            symbol: 交易对

        Returns:
            订单列表
        """
        return await self._repository.get_by_symbol(symbol)

    async def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """
        根据状态获取订单列表

        Args:
            status: 订单状态

        Returns:
            订单列表
        """
        return await self._repository.get_by_status(status.value)

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
