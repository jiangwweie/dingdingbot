"""
Order Manager - 订单编排管理器

v3.0 Phase 4: 订单编排核心组件

核心职责:
1. 管理订单链的生命周期
2. 执行 OCO 逻辑
3. 订单状态同步
4. 订单生成与撤销

职责边界声明:
- OrderManager: 负责订单编排逻辑（订单链生成、OCO 逻辑）
- OrderLifecycleService: 负责订单状态管理（所有状态转换）
- DynamicRiskManager: 负责 SL 订单的 trigger_price 调整 (Breakeven/Trailing)
"""
from decimal import Decimal
from typing import List, Dict, Optional, Callable, Awaitable, Any
import uuid
from datetime import datetime, timezone
import logging

from src.domain.models import (
    Order,
    OrderStrategy,
    OrderType,
    OrderRole,
    OrderStatus,
    Position,
    Direction,
)

logger = logging.getLogger(__name__)


class OrderManager:
    """
    订单编排管理器

    核心职责:
    1. 管理订单链的生命周期
    2. 执行 OCO 逻辑
    3. 订单状态同步
    4. 订单生成与撤销

    职责边界声明:
    - OrderManager: 负责订单编排逻辑（订单链生成、OCO 逻辑）
    - OrderLifecycleService: 负责订单状态管理（所有状态转换）
    - DynamicRiskManager: 负责 SL 订单的 trigger_price 调整 (Breakeven/Trailing)
    """

    def __init__(
        self,
        order_repository: Optional[Any] = None,
        order_lifecycle_service: Optional[Any] = None,
    ):
        """
        初始化订单管理器

        Args:
            order_repository: OrderRepository 实例（可选，用于订单持久化）
            order_lifecycle_service: OrderLifecycleService 实例（可选，用于状态管理）
        """
        self._order_repository = order_repository
        self._order_lifecycle_service = order_lifecycle_service
        self._on_order_changed: Optional[Callable[[Order], Awaitable[None]]] = None

    def set_order_repository(self, order_repository: Any) -> None:
        """设置订单仓库"""
        self._order_repository = order_repository

    def set_order_lifecycle_service(self, service: Any) -> None:
        """设置订单生命周期服务"""
        self._order_lifecycle_service = service

    def set_order_changed_callback(self, callback: Callable[[Order], Awaitable[None]]) -> None:
        """
        设置订单变更回调（用于 WebSocket 推送）

        Args:
            callback: 异步回调函数，接收 Order 对象作为参数
        """
        self._on_order_changed = callback

    async def _notify_order_changed(self, order: Order) -> None:
        """通知订单已变更"""
        if self._on_order_changed:
            try:
                await self._on_order_changed(order)
            except Exception as e:
                # 回调失败不影响主逻辑
                pass

    async def _save_order(self, order: Order) -> None:
        """保存订单到仓库"""
        if self._order_repository:
            try:
                await self._order_repository.save(order)
            except Exception as e:
                # 保存失败不影响主逻辑，记录日志即可
                pass
        # 触发变更通知
        await self._notify_order_changed(order)

    async def _cancel_order_via_service(
        self,
        order: Order,
        reason: Optional[str] = None,
        oco_triggered: bool = False
    ) -> None:
        """
        通过 OrderLifecycleService 取消订单

        Args:
            order: 订单对象
            reason: 取消原因
            oco_triggered: 是否由 OCO 逻辑触发
        """
        if self._order_lifecycle_service:
            try:
                await self._order_lifecycle_service.cancel_order(
                    order_id=order.id,
                    reason=reason,
                    oco_triggered=oco_triggered
                )
            except Exception as e:
                logger.error(f"通过 Service 取消订单失败：{order.id}, error={e}")
                # 降级处理：直接保存订单状态
                order.status = OrderStatus.CANCELED
                order.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
                await self._save_order(order)
        else:
            # 降级处理：直接保存订单状态（用于单元测试或无服务场景）
            order.status = OrderStatus.CANCELED
            order.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
            await self._save_order(order)

    def create_order_chain(
        self,
        strategy: Optional[OrderStrategy] = None,
        signal_id: str = "",
        symbol: str = "",
        direction: Optional[Direction] = None,
        total_qty: Optional[Decimal] = None,
        initial_sl_rr: Optional[Decimal] = None,
        tp_targets: Optional[List[Decimal]] = None,
    ) -> List[Order]:
        """
        创建订单链 - 仅生成 ENTRY 订单

        注意：TP/SL 订单将在 ENTRY 成交后，由 handle_order_filled() 动态生成
        理由：实盘场景中，ENTRY 订单由于滑点会导致实际开仓价 (average_exec_price) 偏离预期
             必须在 ENTRY 成交后，以实际开仓价为锚点计算 TP/SL 价格

        Args:
            strategy: 订单策略 (可选，为 None 时使用默认单 TP 配置)
            signal_id: 信号 ID
            symbol: 交易对
            direction: 方向
            total_qty: 总数量
            initial_sl_rr: 初始止损 RR 倍数 (如 -1.0 表示亏损 1R)
            tp_targets: TP 目标价格列表 (RR 倍数，如 [1.0, 2.0, 3.0])

        Returns:
            仅包含 ENTRY 订单的列表
        """
        from src.domain.models import OrderType, OrderRole, OrderStatus
        import uuid
        from datetime import datetime, timezone

        # Bug #3 防护：total_qty <= 0 时返回空订单列表
        if total_qty is None or total_qty <= Decimal('0'):
            return []

        # strategy 为 None 时使用默认单 TP 配置
        if strategy is None:
            # 默认策略：单 TP 级别，100% 比例
            tp_levels = 1
            tp_ratios = [Decimal('1.0')]
        else:
            tp_levels = strategy.tp_levels
            tp_ratios = strategy.tp_ratios

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 仅生成 ENTRY 订单（状态为 CREATED，由 OrderLifecycleService 管理）
        entry_order = Order(
            id=f"ord_{uuid.uuid4().hex[:8]}",
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=total_qty,
            status=OrderStatus.CREATED,  # 初始状态为 CREATED
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )

        return [entry_order]

    async def save_order_chain(self, orders: List[Order]) -> None:
        """
        保存订单链到仓库

        P5-011: 订单清理机制 - 所有订单都要有迹可循

        Args:
            orders: 订单列表
        """
        for order in orders:
            await self._save_order(order)
        logger.info(f"订单链已保存：{len(orders)} 个订单")

    def _get_tp_role(self, level: int) -> OrderRole:
        """
        根据 TP 级别获取对应的 OrderRole

        Args:
            level: TP 级别 (1-based)

        Returns:
            OrderRole 枚举值

        Raises:
            ValueError: 当级别超出支持范围时
        """
        role_map = {
            1: OrderRole.TP1,
            2: OrderRole.TP2,
            3: OrderRole.TP3,
            4: OrderRole.TP4,
            5: OrderRole.TP5,
        }
        if level not in role_map:
            raise ValueError(f"TP 级别 {level} 超出支持范围 (1-5)")
        return role_map[level]

    async def handle_order_filled(
        self,
        filled_order: Order,
        active_orders: List[Order],
        positions_map: Dict[str, Position],
        strategy: Optional[OrderStrategy] = None,
        tp_targets: Optional[List[Decimal]] = None,
    ) -> List[Order]:
        """
        处理订单成交事件

        Args:
            filled_order: 已成交的订单
            active_orders: 活跃订单列表
            positions_map: 仓位映射表
            strategy: 订单策略 (可选，用于生成多 TP 订单)
            tp_targets: TP 目标 RR 倍数列表 (可选，如 [1.0, 2.0, 3.0])

        Returns:
            新生成或撤销的订单列表

        副作用:
            - ENTRY 成交：动态生成 TP 和 SL 订单 (基于 actual_exec_price)
            - TP 成交：更新 SL 数量 (OrderManager 职责)，执行 OCO 逻辑
            - SL 成交：撤销所有 TP 订单
        """
        new_orders = []

        if filled_order.order_role == OrderRole.ENTRY:
            # ENTRY 成交：动态生成 TP 和 SL 订单
            new_orders = self._generate_tp_sl_orders(
                filled_order, positions_map, strategy, tp_targets
            )
            # P5-011: 保存新生成的 TP/SL 订单
            for order in new_orders:
                await self._save_order(order)

        elif filled_order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]:
            # TP 成交：更新 SL 数量，执行 OCO 逻辑
            # 支持两种 key: signal_id 或 position.id
            position = positions_map.get(filled_order.signal_id)
            if not position:
                for p in positions_map.values():
                    if p.signal_id == filled_order.signal_id:
                        position = p
                        break
            if position:
                await self._apply_oco_logic_for_tp(filled_order, active_orders, position)
            # P5-011: 保存已成交的 TP 订单
            await self._save_order(filled_order)

        elif filled_order.order_role == OrderRole.SL:
            # SL 成交：撤销所有 TP 订单
            await self._cancel_all_tp_orders(filled_order.signal_id, active_orders)
            # P5-011: 保存已成交的 SL 订单
            await self._save_order(filled_order)

        return new_orders

    def _generate_tp_sl_orders(
        self,
        filled_entry: Order,
        positions_map: Dict[str, Position],
        strategy: Optional[OrderStrategy] = None,
        tp_targets: Optional[List[Decimal]] = None,
    ) -> List[Order]:
        """
        基于 ENTRY 成交结果，动态生成 TP 和 SL 订单

        Args:
            filled_entry: 已成交的 ENTRY 订单
            positions_map: 仓位映射表 (key: signal_id 或 position.id)
            strategy: 订单策略 (可选，用于生成多 TP 订单)
            tp_targets: TP 目标 RR 倍数列表 (可选，如 [1.0, 2.0, 3.0])

        Returns:
            新生成的 TP 和 SL 订单列表
        """
        # 获取仓位信息 (支持两种 key: signal_id 或 position.id)
        position = positions_map.get(filled_entry.signal_id)
        if not position:
            for p in positions_map.values():
                if p.signal_id == filled_entry.signal_id:
                    position = p
                    break

        if not position:
            return []

        # 使用实际成交价作为锚点
        actual_entry_price = filled_entry.average_exec_price or filled_entry.price
        if not actual_entry_price:
            return []

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # P1-2 修复：从策略获取止损比例，支持动态配置
        stop_loss_rr = (
            strategy.initial_stop_loss_rr
            if strategy and strategy.initial_stop_loss_rr is not None
            else Decimal('-1.0')  # 默认值：1R 止损
        )

        stop_loss_price = self._calculate_stop_loss_price(
            actual_entry_price,
            filled_entry.direction,
            stop_loss_rr,
        )

        new_orders = []

        # 确定 TP 配置：优先使用传入的 strategy，否则使用默认单 TP 策略
        if strategy and strategy.tp_ratios:
            tp_levels = strategy.tp_levels
            tp_ratios = strategy.tp_ratios
        else:
            tp_levels = 1
            tp_ratios = [Decimal('1.0')]

        # 如果 tp_targets 未提供，使用默认值
        if tp_targets is None:
            tp_targets = [Decimal('1.5')] * tp_levels

        # 验证 tp_ratios 总和
        # ✅ IMP-002 修复：使用 Decimal 累加器确保精度
        total_ratio = Decimal('0')
        for ratio in tp_ratios:
            total_ratio += ratio
        if total_ratio != Decimal('1.0'):
            # 自动归一化
            if total_ratio > 0:
                tp_ratios = [r / total_ratio for r in tp_ratios]

        # 生成多级别 TP 订单
        for level in range(1, tp_levels + 1):
            tp_ratio = tp_ratios[level - 1] if level <= len(tp_ratios) else Decimal('0')

            # 计算 TP 价格
            tp_rr = tp_targets[level - 1] if level <= len(tp_targets) else Decimal('1.5')
            tp_price = self._calculate_tp_price(
                actual_entry_price=actual_entry_price,
                stop_loss_price=stop_loss_price,
                rr_multiple=tp_rr,
                direction=filled_entry.direction,
            )

            # 计算 TP 数量：最后一个级别使用剩余数量 (防止精度误差)
            if level == tp_levels:
                tp_qty = filled_entry.requested_qty - sum(
                    o.requested_qty for o in new_orders if 'TP' in str(o.order_role)
                )
            else:
                tp_qty = filled_entry.requested_qty * tp_ratio

            if tp_qty <= 0:
                tp_qty = filled_entry.requested_qty * tp_ratio

            tp_role = self._get_tp_role(level)
            tp_order = Order(
                id=f"ord_{tp_role.value}_{uuid.uuid4().hex[:8]}",
                signal_id=filled_entry.signal_id,
                symbol=filled_entry.symbol,
                direction=filled_entry.direction,
                order_type=OrderType.LIMIT,
                order_role=tp_role,
                price=tp_price,
                requested_qty=tp_qty,
                status=OrderStatus.OPEN,
                created_at=current_time,
                updated_at=current_time,
                reduce_only=True,
                parent_order_id=filled_entry.id,
                oco_group_id=f"oco_{filled_entry.signal_id}",
            )
            new_orders.append(tp_order)

        # 生成 SL 订单 (数量为总开仓数量)
        sl_order = Order(
            id=f"ord_sl_{uuid.uuid4().hex[:8]}",
            signal_id=filled_entry.signal_id,
            symbol=filled_entry.symbol,
            direction=filled_entry.direction,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            trigger_price=stop_loss_price,
            requested_qty=filled_entry.requested_qty,
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=True,
            parent_order_id=filled_entry.id,
            oco_group_id=f"oco_{filled_entry.signal_id}",
        )
        new_orders.append(sl_order)

        return new_orders

    def _calculate_stop_loss_price(
        self,
        entry_price: Decimal,
        direction: Direction,
        rr_multiple: Decimal,
    ) -> Decimal:
        """
        计算止损价格

        语义说明:
        - rr_multiple < 0: 表示止损 RR 倍数（如 -1.0 表示亏损 1R）
        - rr_multiple > 0: 表示止损百分比（如 0.02 表示 2% 止损）

        计算公式:
        - LONG: sl_price = entry × (1 + rr_multiple)  if rr_multiple < 0
        - LONG: sl_price = entry × (1 - rr_multiple)  if rr_multiple > 0
        - SHORT: sl_price = entry × (1 - rr_multiple) if rr_multiple < 0
        - SHORT: sl_price = entry × (1 + rr_multiple) if rr_multiple > 0

        Args:
            entry_price: 入场价格
            direction: 方向 (LONG/SHORT)
            rr_multiple:
                - 负值表示 RR 倍数（如 -1.0 表示 1R 止损）
                - 正值表示百分比（如 0.02 表示 2% 止损）

        Returns:
            止损价格

        Examples:
            >>> _calculate_stop_loss_price(50000, Direction.LONG, Decimal('-1.0'))
            Decimal('49500')  # LONG 1R 止损 = 50000 * (1 - 0.01)

            >>> _calculate_stop_loss_price(50000, Direction.LONG, Decimal('0.02'))
            Decimal('49000')  # LONG 2% 止损 = 50000 * (1 - 0.02)
        """
        # P2-4 修复：明确区分 RR 倍数模式和百分比模式
        if rr_multiple < 0:
            # RR 倍数模式：基于入场价和止损距离计算
            # 对于 LONG: sl_price = entry - entry × |rr_multiple| × 0.01
            # 对于 SHORT: sl_price = entry + entry × |rr_multiple| × 0.01
            sl_ratio = abs(rr_multiple) * Decimal('0.01')  # 转换为百分比
            if direction == Direction.LONG:
                return entry_price * (Decimal('1') - sl_ratio)
            else:
                return entry_price * (Decimal('1') + sl_ratio)
        else:
            # 百分比模式：直接按百分比计算
            # 对于 LONG: sl_price = entry × (1 - percent)
            # 对于 SHORT: sl_price = entry × (1 + percent)
            if direction == Direction.LONG:
                return entry_price * (Decimal('1') - rr_multiple)
            else:
                return entry_price * (Decimal('1') + rr_multiple)

    def _calculate_tp_price(
        self,
        actual_entry_price: Decimal,
        stop_loss_price: Decimal,
        rr_multiple: Decimal,
        direction: Direction,
    ) -> Decimal:
        """
        计算 TP 目标价格 (基于实际开仓价)

        LONG: tp_price = actual_entry + RR × (actual_entry - sl)
        SHORT: tp_price = actual_entry - RR × (sl - actual_entry)

        Args:
            actual_entry_price: 实际开仓价格
            stop_loss_price: 止损价格
            rr_multiple: RR 倍数 (如 1.0, 2.0, 3.0)
            direction: 方向

        Returns:
            TP 目标价格
        """
        if direction == Direction.LONG:
            # LONG: tp_price = actual_entry + RR × (actual_entry - sl)
            price_diff = actual_entry_price - stop_loss_price
            return actual_entry_price + rr_multiple * price_diff
        else:
            # SHORT: tp_price = actual_entry - RR × (sl - actual_entry)
            price_diff = stop_loss_price - actual_entry_price
            return actual_entry_price - rr_multiple * price_diff

    async def _apply_oco_logic_for_tp(
        self,
        filled_tp: Order,
        active_orders: List[Order],
        position: Position,
    ) -> None:
        """
        TP 成交后执行 OCO 逻辑

        规则:
        1. 如果 position.current_qty == 0: 撤销所有剩余挂单
        2. 如果 position.current_qty > 0: 更新 SL 数量 = current_qty

        Args:
            filled_tp: 已成交的 TP 订单
            active_orders: 活跃订单列表
            position: 关联的仓位
        """
        signal_id = filled_tp.signal_id
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 核心判定：基于仓位剩余数量
        if position.current_qty <= Decimal('0'):
            # 完全平仓：撤销所有剩余挂单
            for order in active_orders:
                if (
                    order.signal_id == signal_id
                    and order.status == OrderStatus.OPEN
                    and order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL]
                ):
                    # 使用 OrderLifecycleService 取消订单
                    await self._cancel_order_via_service(
                        order=order,
                        reason="OCO 逻辑触发（完全平仓）",
                        oco_triggered=True
                    )
        else:
            # 部分平仓：更新 SL 数量与剩余仓位对齐
            sl_order = self._find_order_by_role(active_orders, OrderRole.SL, signal_id)
            if sl_order:
                sl_order.requested_qty = position.current_qty
                sl_order.updated_at = current_time
                # P5-011: 保存更新后的 SL 订单
                await self._save_order(sl_order)

    async def _cancel_all_tp_orders(
        self,
        signal_id: str,
        active_orders: List[Order],
    ) -> None:
        """
        SL 成交后撤销所有 TP 订单

        Args:
            signal_id: 信号 ID
            active_orders: 活跃订单列表
        """
        tp_roles = [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]
        for order in active_orders:
            if (
                order.signal_id == signal_id
                and order.status == OrderStatus.OPEN
                and order.order_role in tp_roles
            ):
                # 使用 OrderLifecycleService 取消订单
                await self._cancel_order_via_service(
                    order=order,
                    reason="SL 成交，取消剩余 TP 订单",
                    oco_triggered=True
                )

    def _find_order_by_role(
        self,
        orders: List[Order],
        role: OrderRole,
        signal_id: Optional[str] = None,
    ) -> Optional[Order]:
        """
        根据角色查找订单

        Args:
            orders: 订单列表
            role: 订单角色
            signal_id: 信号 ID (可选)

        Returns:
            找到的订单，未找到返回 None
        """
        for order in orders:
            if order.order_role == role:
                if signal_id is None or order.signal_id == signal_id:
                    return order
        return None

    def get_active_order_count(
        self,
        orders: List[Order],
        signal_id: str,
        role: Optional[OrderRole] = None,
    ) -> int:
        """
        统计活跃订单数量

        Args:
            orders: 订单列表
            signal_id: 信号 ID
            role: 订单角色 (可选)

        Returns:
            活跃订单数量
        """
        count = 0
        for order in orders:
            if order.signal_id == signal_id and order.status in [
                OrderStatus.OPEN,
                OrderStatus.PENDING,
            ]:
                if role is None or order.order_role == role:
                    count += 1
        return count

    def get_order_chain_status(
        self,
        orders: List[Order],
        signal_id: str,
    ) -> Dict[str, any]:
        """
        获取订单链状态

        Args:
            orders: 订单列表
            signal_id: 信号 ID

        Returns:
            状态字典 {
                "entry_filled": bool,
                "tp_filled_count": int,
                "sl_status": str,
                "remaining_qty": Decimal,
                "closed_percent": Decimal
            }
        """
        status = {
            "entry_filled": False,
            "tp_filled_count": 0,
            "sl_status": "PENDING",
            "remaining_qty": Decimal('0'),
            "closed_percent": Decimal('0'),
        }

        entry_qty = Decimal('0')
        tp_filled_qty = Decimal('0')
        sl_filled_qty = Decimal('0')

        for order in orders:
            if order.signal_id != signal_id:
                continue

            if order.order_role == OrderRole.ENTRY:
                if order.status == OrderStatus.FILLED:
                    status["entry_filled"] = True
                    entry_qty = order.filled_qty

            elif order.order_role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]:
                if order.status == OrderStatus.FILLED:
                    status["tp_filled_count"] += 1
                    tp_filled_qty += order.filled_qty

            elif order.order_role == OrderRole.SL:
                if order.status == OrderStatus.FILLED:
                    status["sl_status"] = "FILLED"
                    sl_filled_qty = order.filled_qty
                elif order.status == OrderStatus.OPEN:
                    status["sl_status"] = "OPEN"
                elif order.status == OrderStatus.CANCELED:
                    status["sl_status"] = "CANCELED"

        # 计算剩余数量
        status["remaining_qty"] = entry_qty - tp_filled_qty - sl_filled_qty

        # 计算已平仓比例
        if entry_qty > 0:
            status["closed_percent"] = (tp_filled_qty + sl_filled_qty) / entry_qty * Decimal('100')

        return status

    async def apply_oco_logic(
        self,
        filled_order: Order,
        active_orders: List[Order],
        position: Position,
    ) -> List[Order]:
        """
        执行 OCO 逻辑 - 基于仓位剩余数量判定

        规则:
        1. 如果 position.current_qty == 0: 撤销所有剩余挂单
        2. 如果 position.current_qty > 0: 更新 SL 数量 = current_qty

        Args:
            filled_order: 已成交的订单
            active_orders: 活跃订单列表
            position: 关联的仓位

        Returns:
            被撤销的订单列表
        """
        canceled_orders = []
        signal_id = filled_order.signal_id

        # 核心判定：基于仓位剩余数量
        if position.current_qty <= Decimal('0'):
            # 完全平仓：撤销所有剩余挂单
            for order in active_orders:
                if (
                    order.signal_id == signal_id
                    and order.status == OrderStatus.OPEN
                ):
                    canceled_orders.append(order)
                    # 使用 OrderLifecycleService 取消订单
                    await self._cancel_order_via_service(
                        order=order,
                        reason="OCO 逻辑触发（完全平仓）",
                        oco_triggered=True
                    )
        else:
            # 部分平仓：更新 SL 数量与剩余仓位对齐
            sl_order = self._find_order_by_role(active_orders, OrderRole.SL, signal_id)
            if sl_order:
                sl_order.requested_qty = position.current_qty
                sl_order.updated_at = int(datetime.now(timezone.utc).timestamp() * 1000)
                # P5-011: 保存更新后的 SL 订单
                await self._save_order(sl_order)

        return canceled_orders
