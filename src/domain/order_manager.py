"""
Order Manager - 订单编排管理器

v3.0 Phase 4: 订单编排核心组件

核心职责:
1. 管理订单链的生命周期
2. 执行 OCO 逻辑
3. 订单状态同步
4. 订单生成与撤销

职责边界声明:
- OrderManager: 负责 SL 订单的 requested_qty 更新 (数量同步)
- DynamicRiskManager: 负责 SL 订单的 trigger_price 调整 (Breakeven/Trailing)
"""
from decimal import Decimal
from typing import List, Dict, Optional
import uuid
from datetime import datetime, timezone

from src.domain.models import (
    Order,
    OrderStrategy,
    OrderType,
    OrderRole,
    OrderStatus,
    Position,
    Direction,
)


class OrderManager:
    """
    订单编排管理器

    核心职责:
    1. 管理订单链的生命周期
    2. 执行 OCO 逻辑
    3. 订单状态同步
    4. 订单生成与撤销

    职责边界声明:
    - OrderManager: 负责 SL 订单的 requested_qty 更新 (数量同步)
    - DynamicRiskManager: 负责 SL 订单的 trigger_price 调整 (Breakeven/Trailing)
    """

    def __init__(self):
        """
        初始化订单管理器
        """
        pass

    def create_order_chain(
        self,
        strategy: OrderStrategy,
        signal_id: str,
        symbol: str,
        direction: Direction,
        total_qty: Decimal,
        initial_sl_rr: Decimal,
        tp_targets: List[Decimal],
    ) -> List[Order]:
        """
        创建订单链 - 仅生成 ENTRY 订单

        注意：TP/SL 订单将在 ENTRY 成交后，由 handle_order_filled() 动态生成
        理由：实盘场景中，ENTRY 订单由于滑点会导致实际开仓价 (average_exec_price) 偏离预期
             必须在 ENTRY 成交后，以实际开仓价为锚点计算 TP/SL 价格

        Args:
            strategy: 订单策略
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

        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 仅生成 ENTRY 订单
        entry_order = Order(
            id=f"ord_{uuid.uuid4().hex[:8]}",
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=total_qty,
            status=OrderStatus.OPEN,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=False,
        )

        return [entry_order]

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

    def handle_order_filled(
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
                self._apply_oco_logic_for_tp(filled_order, active_orders, position)

        elif filled_order.order_role == OrderRole.SL:
            # SL 成交：撤销所有 TP 订单
            self._cancel_all_tp_orders(filled_order.signal_id, active_orders)

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

        # 计算止损价格 (基于实际开仓价，默认使用 -1.0 RR)
        stop_loss_price = self._calculate_stop_loss_price(
            actual_entry_price,
            filled_entry.direction,
            Decimal('-1.0'),
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
        total_ratio = sum(tp_ratios)
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

        注意：rr_multiple 参数的绝对值表示止损距离占入场价的百分比
        例如：rr_multiple = -0.02 表示止损距离为入场价的 2%

        LONG: sl_price = entry × (1 - |rr_multiple|)
        SHORT: sl_price = entry × (1 + |rr_multiple|)

        Args:
            entry_price: 入场价格
            direction: 方向
            rr_multiple: RR 倍数 (负值表示止损，绝对值表示百分比)

        Returns:
            止损价格
        """
        # 使用 |rr_multiple| 作为止损百分比
        # 如果 rr_multiple 的绝对值 > 1，则视为比例因子，否则视为百分比
        sl_percent = abs(rr_multiple)

        # 如果 sl_percent > 1，说明是倍数而非百分比，转换为百分比 (例如 1.0 -> 0.02 表示 2%)
        # 这是为了向后兼容旧的使用方式
        if sl_percent >= Decimal('1'):
            sl_percent = Decimal('0.02')  # 默认 2% 止损

        if direction == Direction.LONG:
            # LONG: 止损在入场价下方
            return entry_price * (Decimal('1') - sl_percent)
        else:
            # SHORT: 止损在入场价上方
            return entry_price * (Decimal('1') + sl_percent)

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

    def _apply_oco_logic_for_tp(
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
                    order.status = OrderStatus.CANCELED
                    order.updated_at = current_time
        else:
            # 部分平仓：更新 SL 数量与剩余仓位对齐
            sl_order = self._find_order_by_role(active_orders, OrderRole.SL, signal_id)
            if sl_order:
                sl_order.requested_qty = position.current_qty
                sl_order.updated_at = current_time

    def _cancel_all_tp_orders(
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
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        tp_roles = [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]
        for order in active_orders:
            if (
                order.signal_id == signal_id
                and order.status == OrderStatus.OPEN
                and order.order_role in tp_roles
            ):
                order.status = OrderStatus.CANCELED
                order.updated_at = current_time

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

    def apply_oco_logic(
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
        from datetime import datetime, timezone

        canceled_orders = []
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        signal_id = filled_order.signal_id

        # 核心判定：基于仓位剩余数量
        if position.current_qty <= Decimal('0'):
            # 完全平仓：撤销所有剩余挂单
            for order in active_orders:
                if (
                    order.signal_id == signal_id
                    and order.status == OrderStatus.OPEN
                ):
                    order.status = OrderStatus.CANCELED
                    order.updated_at = current_time
                    canceled_orders.append(order)
        else:
            # 部分平仓：更新 SL 数量与剩余仓位对齐
            sl_order = self._find_order_by_role(active_orders, OrderRole.SL, signal_id)
            if sl_order:
                sl_order.requested_qty = position.current_qty
                sl_order.updated_at = current_time

        return canceled_orders
