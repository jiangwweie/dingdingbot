"""
Order State Machine - 订单状态机

v3.0 Phase 4: 订单编排核心组件

职责：管理订单状态流转，确保状态转换符合交易所规范

状态转移图:
┌─────────────────────────────────────────────────────────────┐
│                    订单状态转移图                              │
│                                                             │
│   ┌─────────┐                                               │
│   │ CREATED │───→ CANCELED (终态)                            │
│   └────┬────┘                                               │
│        │                                                     │
│        ↓                                                     │
│   ┌───────────┐                                             │
│   │ SUBMITTED │───→ REJECTED (终态)                          │
│   └────┬──────┘    │                                         │
│        │           └──→ CANCELED (终态)                      │
│        │                                                     │
│        ↓                                                     │
│   ┌─────────┐                                               │
│   │ PENDING │───→ REJECTED (终态)                            │
│   └────┬────┘                                               │
│        │                                                     │
│        ├───→ CANCELED (终态)                                 │
│        │                                                     │
│        ↓                                                     │
│   ┌─────────┐                                               │
│   │   OPEN  │───→ CANCELED (终态)                            │
│   └────┬────┤    │                                           │
│        │    └───→ REJECTED (终态)                            │
│        │                                                     │
│        ↓                                                     │
│   ┌──────────────────┐                                       │
│   │ PARTIALLY_FILLED │───→ CANCELED (终态)                   │
│   └────────┬─────────┘                                       │
│            │                                                  │
│            ↓                                                  │
│       ┌─────────┐                                             │
│       │ FILLED  │ (终态)                                       │
│       └─────────┘                                             │
│                                                               │
│   EXPIRED (终态) - 由交易所返回                                │
└─────────────────────────────────────────────────────────────┘

终态 (Terminal States): FILLED, CANCELED, REJECTED, EXPIRED
非终态 (Non-Terminal): CREATED, SUBMITTED, PENDING, OPEN, PARTIALLY_FILLED
"""

from typing import Set, Optional, Callable, Awaitable, Dict, Any
from datetime import datetime, timezone

from src.domain.models import Order, OrderStatus
from src.domain.exceptions import InvalidOrderStateTransition


class OrderTransitionError(Exception):
    """订单状态转换错误"""
    pass


class OrderStateMachine:
    """
    订单状态机 - 管理订单状态流转

    核心职责:
    1. 定义订单的 8 种状态
    2. 管理合法的状态转换规则
    3. 验证状态流转的合法性
    4. 提供终态判定

    状态说明:
    - PENDING: 订单已创建但尚未发送到交易所
    - OPEN: 订单已发送到交易所，正在挂单中
    - PARTIALLY_FILLED: 订单部分成交
    - FILLED: 订单完全成交 (终态)
    - CANCELED: 订单已撤销 (终态)
    - REJECTED: 订单被交易所拒绝 (终态)
    - EXPIRED: 订单已过期 (终态)
    """

    # ============================================================
    # 状态定义 (9 种)
    # ============================================================
    STATES = frozenset({
        "CREATED",              # 订单已创建（本地）
        "SUBMITTED",            # 订单已提交到交易所
        "PENDING",              # 尚未发送到交易所
        "OPEN",                 # 挂单中
        "PARTIALLY_FILLED",     # 部分成交
        "FILLED",               # 完全成交
        "CANCELED",             # 已撤销
        "REJECTED",             # 交易所拒单
        "EXPIRED",              # 已过期
    })

    # ============================================================
    # 合法流转矩阵
    # ============================================================
    # key: 当前状态
    # value: 可以转换到的目标状态集合
    TRANSITIONS = {
        "CREATED": {"SUBMITTED", "CANCELED"},
        "SUBMITTED": {"OPEN", "REJECTED", "CANCELED", "EXPIRED"},
        "PENDING": {"OPEN", "REJECTED", "CANCELED", "SUBMITTED"},
        "OPEN": {"PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED"},
        "PARTIALLY_FILLED": {"FILLED", "CANCELED"},
        "FILLED": frozenset(),       # 终态，不可转换
        "CANCELED": frozenset(),     # 终态，不可转换
        "REJECTED": frozenset(),     # 终态，不可转换
        "EXPIRED": frozenset(),      # 终态，不可转换
    }

    # ============================================================
    # 终态定义
    # ============================================================
    TERMINAL_STATES = frozenset({"FILLED", "CANCELED", "REJECTED", "EXPIRED"})

    # ============================================================
    # 实例方法 - 支持状态机实例化
    # ============================================================

    def __init__(self, order: Order):
        """
        初始化状态机实例

        Args:
            order: 订单对象
        """
        self._order = order
        self._initial_status = order.status
        self._transition_count = 0
        self._on_transition: Optional[Callable[[Order, OrderStatus, OrderStatus], Awaitable[None]]] = None

    @property
    def order(self) -> Order:
        """获取关联的订单"""
        return self._order

    @property
    def current_status(self) -> OrderStatus:
        """获取当前状态"""
        return self._order.status

    @property
    def initial_status(self) -> OrderStatus:
        """获取初始状态"""
        return self._initial_status

    @property
    def transition_count(self) -> int:
        """获取状态转换次数"""
        return self._transition_count

    @property
    def is_terminal(self) -> bool:
        """是否为终态（不可再转换）"""
        return self._order.status.value in self.TERMINAL_STATES

    def set_transition_callback(
        self,
        callback: Callable[[Order, OrderStatus, OrderStatus], Awaitable[None]]
    ) -> None:
        """
        设置状态转换回调

        Args:
            callback: 异步回调函数，接收 (order, old_status, new_status)
        """
        self._on_transition = callback

    def can_transition_to(self, new_status: OrderStatus) -> bool:
        """
        检查是否可以转换到目标状态

        Args:
            new_status: 目标状态

        Returns:
            是否可转换
        """
        current = self._order.status.value
        valid_targets = self.TRANSITIONS.get(current, set())
        return new_status.value in valid_targets

    def get_valid_transitions(self) -> Set[OrderStatus]:
        """
        获取所有合法的下一个状态

        Returns:
            合法状态集合
        """
        current = self._order.status.value
        valid_targets = self.TRANSITIONS.get(current, set())
        return {OrderStatus(s) for s in valid_targets}

    async def transition_to(
        self,
        new_status: OrderStatus,
        trigger_source: str = "SYSTEM",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行状态转换

        Args:
            new_status: 目标状态
            trigger_source: 触发来源 (USER/SYSTEM/EXCHANGE)
            metadata: 元数据

        Returns:
            是否转换成功

        Raises:
            InvalidOrderStateTransition: 当转换不合法时
        """
        old_status = self._order.status

        # 检查是否为终态
        if self.is_terminal:
            raise InvalidOrderStateTransition(
                order_id=self._order.id,
                from_status=old_status.value,
                to_status=new_status.value,
                valid_transitions=set()
            )

        # 检查转换是否合法
        if not self.can_transition_to(new_status):
            valid_targets = self.get_valid_transitions()
            raise InvalidOrderStateTransition(
                order_id=self._order.id,
                from_status=old_status.value,
                to_status=new_status.value,
                valid_transitions={s.value for s in valid_targets}
            )

        # 执行转换
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        self._order.status = new_status
        self._order.updated_at = current_time
        self._transition_count += 1

        # 触发回调
        if self._on_transition:
            try:
                await self._on_transition(self._order, old_status, new_status)
            except Exception:
                # 回调失败不影响主流程
                pass

        return True

    async def submit_to_exchange(
        self,
        exchange_order_id: Optional[str] = None
    ) -> bool:
        """便捷方法：提交到交易所"""
        if exchange_order_id:
            self._order.exchange_order_id = exchange_order_id
        return await self.transition_to(
            OrderStatus.SUBMITTED,
            trigger_source="SYSTEM",
            metadata={"action": "submit_to_exchange"}
        )

    async def confirm_open(
        self,
        exchange_order_id: Optional[str] = None
    ) -> bool:
        """便捷方法：确认挂单"""
        if exchange_order_id:
            self._order.exchange_order_id = exchange_order_id
        return await self.transition_to(
            OrderStatus.OPEN,
            trigger_source="EXCHANGE",
            metadata={"action": "confirm_open"}
        )

    async def mark_partially_filled(
        self,
        filled_qty: str,
        average_exec_price: str
    ) -> bool:
        """便捷方法：标记部分成交"""
        from decimal import Decimal
        self._order.filled_qty = Decimal(filled_qty)
        self._order.average_exec_price = Decimal(average_exec_price)
        return await self.transition_to(
            OrderStatus.PARTIALLY_FILLED,
            trigger_source="EXCHANGE",
            metadata={
                "action": "partially_filled",
                "filled_qty": filled_qty,
                "average_exec_price": average_exec_price
            }
        )

    async def mark_filled(
        self,
        filled_qty: str,
        average_exec_price: str
    ) -> bool:
        """便捷方法：标记完全成交"""
        from decimal import Decimal
        self._order.filled_qty = Decimal(filled_qty)
        self._order.average_exec_price = Decimal(average_exec_price)
        return await self.transition_to(
            OrderStatus.FILLED,
            trigger_source="EXCHANGE",
            metadata={
                "action": "filled",
                "filled_qty": filled_qty,
                "average_exec_price": average_exec_price
            }
        )

    async def mark_canceled(
        self,
        reason: Optional[str] = None,
        oco_triggered: bool = False
    ) -> bool:
        """便捷方法：标记已取消"""
        metadata = {"action": "canceled"}
        if reason:
            metadata["cancel_reason"] = reason
        if oco_triggered:
            metadata["oco_triggered"] = True

        return await self.transition_to(
            OrderStatus.CANCELED,
            trigger_source="SYSTEM" if oco_triggered else "USER",
            metadata=metadata
        )

    async def mark_rejected(
        self,
        reason: str
    ) -> bool:
        """便捷方法：标记被拒单"""
        return await self.transition_to(
            OrderStatus.REJECTED,
            trigger_source="EXCHANGE",
            metadata={
                "action": "rejected",
                "reject_reason": reason
            }
        )

    async def mark_expired(self) -> bool:
        """便捷方法：标记已过期"""
        return await self.transition_to(
            OrderStatus.EXPIRED,
            trigger_source="SYSTEM",
            metadata={"action": "expired"}
        )

    # ============================================================
    # 类方法 - 保持向后兼容
    # ============================================================

    @classmethod
    def can_transition(cls, from_status: str, to_status: str) -> bool:
        """
        检查状态流转是否合法

        Args:
            from_status: 当前状态
            to_status: 目标状态

        Returns:
            True 表示流转合法，False 表示非法

        Examples:
            >>> OrderStateMachine.can_transition("PENDING", "OPEN")
            True
            >>> OrderStateMachine.can_transition("PENDING", "FILLED")
            False
            >>> OrderStateMachine.can_transition("FILLED", "CANCELED")
            False  # 终态不可转换
        """
        if from_status not in cls.STATES:
            return False
        if to_status not in cls.STATES:
            return False
        return to_status in cls.TRANSITIONS.get(from_status, frozenset())

    @classmethod
    def can_transition_with_exception(
        cls,
        order_id: str,
        from_status: str,
        to_status: str,
    ) -> bool:
        """
        检查状态流转是否合法，非法时抛出异常

        Args:
            order_id: 订单 ID
            from_status: 当前状态
            to_status: 目标状态

        Returns:
            True 表示流转合法

        Raises:
            InvalidOrderStateTransition: 当流转非法时

        Examples:
            >>> OrderStateMachine.can_transition_with_exception("ord_123", "PENDING", "OPEN")
            True
            >>> OrderStateMachine.can_transition_with_exception("ord_123", "FILLED", "OPEN")
            InvalidOrderStateTransition: Cannot transition order 'ord_123' from FILLED to OPEN...
        """
        if not cls.can_transition(from_status, to_status):
            valid = cls.get_valid_transitions_from(from_status)
            raise InvalidOrderStateTransition(
                order_id=order_id,
                from_status=from_status,
                to_status=to_status,
                valid_transitions=valid,
            )
        return True

    @classmethod
    def get_valid_transitions_from(cls, from_status: str) -> Set[str]:
        """
        获取从当前状态可以转换到的所有目标状态

        Args:
            from_status: 当前状态

        Returns:
            合法目标状态的集合

        Examples:
            >>> OrderStateMachine.get_valid_transitions_from("PENDING")
            {'OPEN', 'REJECTED', 'CANCELED'}
            >>> OrderStateMachine.get_valid_transitions_from("FILLED")
            set()  # 终态无合法转换
        """
        return set(cls.TRANSITIONS.get(from_status, frozenset()))

    @classmethod
    def is_terminal_state(cls, status: str) -> bool:
        """
        判断是否为终态

        Args:
            status: 状态名称

        Returns:
            True 表示终态，False 表示非终态

        Examples:
            >>> OrderStateMachine.is_terminal_state("FILLED")
            True
            >>> OrderStateMachine.is_terminal_state("OPEN")
            False
        """
        return status in cls.TERMINAL_STATES

    @classmethod
    def is_valid_state(cls, status: str) -> bool:
        """
        检查状态是否有效

        Args:
            status: 状态名称

        Returns:
            True 表示状态有效
        """
        return status in cls.STATES

    @classmethod
    def get_all_states(cls) -> Set[str]:
        """
        获取所有状态集合

        Returns:
            所有状态的集合
        """
        return set(cls.STATES)

    @classmethod
    def get_terminal_states(cls) -> Set[str]:
        """
        获取所有终态集合

        Returns:
            所有终态的集合
        """
        return set(cls.TERMINAL_STATES)

    @classmethod
    def get_non_terminal_states(cls) -> Set[str]:
        """
        获取所有非终态集合

        Returns:
            所有非终态的集合
        """
        return cls.STATES - cls.TERMINAL_STATES

    @classmethod
    def describe_transition(cls, from_status: str, to_status: str) -> str:
        """
        获取状态流转的描述

        Args:
            from_status: 当前状态
            to_status: 目标状态

        Returns:
            流转描述字符串

        Examples:
            >>> OrderStateMachine.describe_transition("CREATED", "SUBMITTED")
            'CREATED → SUBMITTED: Order submitted to exchange'
            >>> OrderStateMachine.describe_transition("PENDING", "OPEN")
            'PENDING → OPEN: Order sent to exchange'
        """
        descriptions = {
            ("CREATED", "SUBMITTED"): "Order submitted to exchange",
            ("CREATED", "CANCELED"): "Order canceled before submission",
            ("SUBMITTED", "OPEN"): "Order confirmed by exchange",
            ("SUBMITTED", "REJECTED"): "Order rejected by exchange",
            ("SUBMITTED", "CANCELED"): "Order canceled after submission",
            ("SUBMITTED", "EXPIRED"): "Order expired",
            ("PENDING", "OPEN"): "Order sent to exchange",
            ("PENDING", "REJECTED"): "Order rejected by exchange",
            ("PENDING", "CANCELED"): "Order canceled before submission",
            ("PENDING", "SUBMITTED"): "Order moved to submitted",
            ("OPEN", "PARTIALLY_FILLED"): "Order partially filled",
            ("OPEN", "FILLED"): "Order fully filled",
            ("OPEN", "CANCELED"): "Order canceled",
            ("OPEN", "REJECTED"): "Order rejected during execution",
            ("OPEN", "EXPIRED"): "Order expired",
            ("PARTIALLY_FILLED", "FILLED"): "Remaining quantity filled",
            ("PARTIALLY_FILLED", "CANCELED"): "Remaining quantity canceled",
        }
        key = (from_status, to_status)
        if key in descriptions:
            return f"{from_status} → {to_status}: {descriptions[key]}"
        return f"{from_status} → {to_status}: Invalid transition"
