"""
MockMatchingEngine - 可配置撮合引擎

实现 v3.0 Phase 2 撮合引擎核心逻辑：
1. 按优先级排序订单 (SL > TP > ENTRY)
2. 检查订单触发条件
3. 计算滑点后的执行价格
4. 执行仓位和账户同步

设计文档：docs/designs/phase2-matching-engine-contract.md (v1.1)
"""
import uuid
import random
from decimal import Decimal
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.domain.models import (
    KlineData,
    Order,
    Position,
    Account,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
)
from src.infrastructure.logger import logger


# ============================================================
# TP 订单角色集合（支持 TP1-TP5）
# ============================================================
TP_ROLES = {OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5}


# ============================================================
# 订单优先级枚举 (内部使用)
# ============================================================
@dataclass
class OrderPriority:
    """订单优先级映射"""
    SL = 1       # 止损类订单 - 最高优先级
    TP = 2       # 止盈类订单 - 中等优先级
    ENTRY = 3    # 入场类订单 - 最低优先级


# ============================================================
# MockMatchingEngine 核心类
# ============================================================

class MockMatchingEngine:
    """
    可配置撮合引擎 - K 线级撮合

    核心职责:
    1. 按优先级排序订单 (SL > TP > ENTRY)
    2. 检查订单触发条件
    3. 计算滑点后的执行价格
    4. 执行仓位和账户同步

    设计原则:
    - 防守至上：止损单优先判定（默认）
    - 可配置：同 bar TP/SL 冲突时可选择悲观/随机策略
    - Decimal 精度：所有金额计算使用 Decimal

    使用示例:
        >>> engine = MockMatchingEngine(
        ...     slippage_rate=Decimal('0.001'),
        ...     fee_rate=Decimal('0.0004'),
        ...     same_bar_policy='pessimistic'
        ... )
        >>> executed_orders = engine.match_orders_for_kline(
        ...     kline, active_orders, positions_map, account
        ... )
    """

    def __init__(
        self,
        slippage_rate: Decimal = Decimal('0.001'),
        fee_rate: Decimal = Decimal('0.0004'),
        tp_slippage_rate: Optional[Decimal] = None,
        same_bar_policy: str = "pessimistic",
        same_bar_tp_first_prob: Decimal = Decimal("0.5"),
        random_seed: Optional[int] = None,
    ):
        """
        初始化撮合引擎

        Args:
            slippage_rate: 滑点率 (默认 0.1%)
            fee_rate: 手续费率 (默认 0.04%)
            tp_slippage_rate: 止盈滑点率 (默认 0.05%)
            same_bar_policy: 同 bar TP/SL 冲突策略
                - "pessimistic": SL 优先（默认，与旧行为一致）
                - "random": 随机决定 TP/SL 优先级
            same_bar_tp_first_prob: random 策略下 TP 优先概率（默认 0.5）
            random_seed: 随机种子（用于 random 策略可复现）
        """
        self.slippage_rate = slippage_rate
        self.fee_rate = fee_rate
        # 止盈滑点率，默认 0.05%
        self.tp_slippage_rate = tp_slippage_rate if tp_slippage_rate is not None else Decimal('0.0005')

        # 撮合配置
        self.same_bar_policy = same_bar_policy
        self.same_bar_tp_first_prob = same_bar_tp_first_prob

        # 初始化随机数生成器
        if random_seed is not None:
            self.rng = random.Random(random_seed)
        else:
            self.rng = random.Random()

    def match_orders_for_kline(
        self,
        kline: KlineData,
        active_orders: List[Order],
        positions_map: Dict[str, Position],
        account: Account,
    ) -> List[Order]:
        """
        K 线级悲观撮合入口

        参数:
            kline: 当前 K 线数据 (包含 high/low/close/volume)
            active_orders: 活跃订单列表 (状态为 OPEN)
            positions_map: {signal_id: Position} 仓位映射表
            account: 账户快照对象

        返回:
            已执行的订单列表 (status=FILLED)

        副作用:
            - 修改订单状态 (OPEN → FILLED)
            - 修改 Position (current_qty, realized_pnl)
            - 修改 Account (total_balance)
        """
        executed_orders = []
        k_high, k_low = kline.high, kline.low

        # 按优先级排序订单（考虑 same-bar 冲突策略）
        sorted_orders = self._sort_orders_by_priority(active_orders, kline)

        # 跟踪已处理的 signal_id，用于止损后撤销关联订单
        processed_signals = set()

        for order in sorted_orders:
            # 跳过非 OPEN 状态的订单
            if order.status != OrderStatus.OPEN:
                continue

            # 跳过已处理过的 signal_id (止损后撤销的订单)
            if order.signal_id in processed_signals:
                continue

            position = positions_map.get(order.signal_id)

            # =====================================================
            # 1. 处理止损单 (STOP_MARKET / TRAILING_STOP)
            # =====================================================
            if order.order_type in [OrderType.STOP_MARKET, OrderType.TRAILING_STOP]:
                is_triggered = False
                exec_price = Decimal('0')

                if order.direction == Direction.LONG and k_low <= order.trigger_price:
                    is_triggered = True
                    # 多头止损：滑点向下
                    exec_price = order.trigger_price * (Decimal('1') - self.slippage_rate)
                elif order.direction == Direction.SHORT and k_high >= order.trigger_price:
                    is_triggered = True
                    # 空头止损：滑点向上
                    exec_price = order.trigger_price * (Decimal('1') + self.slippage_rate)

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
                    executed_orders.append(order)
                    # 止损触发后，标记该 signal_id，后续关联订单会被跳过
                    processed_signals.add(order.signal_id)
                    # 撤销该仓位关联的其他挂单 (如 TP1)
                    self._cancel_related_orders(order.signal_id, active_orders)
                    continue  # 该仓位在这根 K 线已死，跳过后续判定

            # =====================================================
            # 2. 处理止盈单 (LIMIT + OrderRole.TP1-TP5) - T2 修复 + TTP 扩展
            # =====================================================
            elif order.order_type == OrderType.LIMIT and order.order_role in TP_ROLES:
                is_triggered = False
                exec_price = Decimal('0')

                if order.direction == Direction.LONG and k_high >= order.price:
                    is_triggered = True
                    # 多头止盈：滑点向下 (少收钱)
                    exec_price = order.price * (Decimal('1') - self.tp_slippage_rate)
                elif order.direction == Direction.SHORT and k_low <= order.price:
                    is_triggered = True
                    # 空头止盈：滑点向上 (多付钱)
                    exec_price = order.price * (Decimal('1') + self.tp_slippage_rate)

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
                    executed_orders.append(order)
                    # 注意：TP1 成交不代表仓位死亡，不需要撤销关联单

            # =====================================================
            # 3. 处理入场单 (MARKET + OrderRole.ENTRY)
            # =====================================================
            elif order.order_type == OrderType.MARKET and order.order_role == OrderRole.ENTRY:
                # MARKET 入场单：无条件按 kline.open 成交
                is_triggered = True

                if order.direction == Direction.LONG:
                    # 买入：向上滑点 (多付钱)
                    exec_price = kline.open * (Decimal('1') + self.slippage_rate)
                else:
                    # 卖出：向下滑点 (少收钱)
                    exec_price = kline.open * (Decimal('1') - self.slippage_rate)

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account, positions_map, kline.timestamp)
                    executed_orders.append(order)

        return executed_orders

    def _sort_orders_by_priority(
        self,
        orders: List[Order],
        kline: KlineData,
    ) -> List[Order]:
        """
        按优先级排序订单（支持 same-bar 冲突可配置）

        排序规则:
        1. 默认（pessimistic）: SL > TP > ENTRY
        2. random: 检测 same-bar 冲突，为每个冲突 signal 抽签一次决定 TP/SL 优先级

        Args:
            orders: 待排序订单列表
            kline: 当前 K 线数据（用于检测 same-bar 冲突）

        Returns:
            按优先级排序后的订单列表
        """
        # 检测 same-bar 冲突：同一 signal_id 的 TP 和 SL 都会被触发
        signal_conflicts = self._detect_same_bar_conflicts(orders, kline)

        # 为每个冲突 signal 预先抽签一次（仅 random 策略）
        # signal_id -> True(TP优先) / False(SL优先)
        signal_tp_first = {}
        if self.same_bar_policy == "random" and signal_conflicts:
            for signal_id in signal_conflicts:
                # 每个 signal 只抽签一次
                tp_first = self.rng.random() < float(self.same_bar_tp_first_prob)
                signal_tp_first[signal_id] = tp_first

        def get_priority(order: Order) -> int:
            # 止损类订单
            if order.order_type in [OrderType.STOP_MARKET, OrderType.TRAILING_STOP]:
                # 如果该 signal_id 存在冲突且使用 random 策略
                if order.signal_id in signal_tp_first:
                    # 使用预先抽签的结果
                    if signal_tp_first[order.signal_id]:
                        return OrderPriority.TP  # TP 优先，SL 降级
                    else:
                        return OrderPriority.SL  # SL 优先
                else:
                    # 默认：SL 最高优先级
                    return OrderPriority.SL

            # 止盈类订单
            elif order.order_type == OrderType.LIMIT and order.order_role in TP_ROLES:
                # 如果该 signal_id 存在冲突且使用 random 策略
                if order.signal_id in signal_tp_first:
                    # 使用预先抽签的结果（与 SL 相反）
                    if signal_tp_first[order.signal_id]:
                        return OrderPriority.SL  # TP 优先，TP 提升到最高
                    else:
                        return OrderPriority.TP  # SL 优先，TP 保持中等
                else:
                    # 默认：TP 中等优先级
                    return OrderPriority.TP

            # 入场类订单 - 最低优先级
            elif order.order_type == OrderType.MARKET and order.order_role == OrderRole.ENTRY:
                return OrderPriority.ENTRY

            # 其他订单 - 最低优先级
            return 999

        return sorted(orders, key=get_priority)

    def _detect_same_bar_conflicts(
        self,
        orders: List[Order],
        kline: KlineData,
    ) -> set:
        """
        检测 same-bar TP/SL 冲突

        当同一根 K 线的 high/low 同时覆盖 TP 和 SL 价格时，判定为冲突。

        Args:
            orders: 订单列表
            kline: 当前 K 线数据

        Returns:
            存在冲突的 signal_id 集合
        """
        conflict_signals = set()

        # 按 signal_id 分组订单
        signal_orders = {}
        for order in orders:
            if order.signal_id not in signal_orders:
                signal_orders[order.signal_id] = []
            signal_orders[order.signal_id].append(order)

        # 检测每个 signal_id 的 TP/SL 冲突
        for signal_id, signal_order_list in signal_orders.items():
            has_sl = False
            has_tp = False
            sl_triggered = False
            tp_triggered = False

            for order in signal_order_list:
                # 检查止损单
                if order.order_type in [OrderType.STOP_MARKET, OrderType.TRAILING_STOP]:
                    has_sl = True
                    if order.direction == Direction.LONG and kline.low <= order.trigger_price:
                        sl_triggered = True
                    elif order.direction == Direction.SHORT and kline.high >= order.trigger_price:
                        sl_triggered = True

                # 检查止盈单
                elif order.order_type == OrderType.LIMIT and order.order_role in TP_ROLES:
                    has_tp = True
                    if order.direction == Direction.LONG and kline.high >= order.price:
                        tp_triggered = True
                    elif order.direction == Direction.SHORT and kline.low <= order.price:
                        tp_triggered = True

            # 如果 TP 和 SL 都会被触发，标记为冲突
            if has_sl and has_tp and sl_triggered and tp_triggered:
                conflict_signals.add(signal_id)

        return conflict_signals

    def _execute_fill(
        self,
        order: Order,
        exec_price: Decimal,
        position: Optional[Position],
        account: Account,
        positions_map: Dict[str, Position],
        timestamp: int,
    ) -> None:
        """
        执行订单结算与仓位/账户同步

        参数:
            order: 待执行的订单
            exec_price: 执行价格 (已包含滑点)
            position: 关联的仓位 (ENTRY 单时可为 None)
            account: 账户快照
            positions_map: {signal_id: Position} 仓位映射表 (用于 ENTRY 单创建新仓位)
            timestamp: 当前 K 线时间戳 (用于创建新仓位)

        副作用:
            - order.status = FILLED
            - order.filled_qty = requested_qty
            - order.average_exec_price = exec_price

        核心逻辑:
            # 入场单 (ENTRY): 开仓逻辑
            if order.order_role == OrderRole.ENTRY:
                # 创建新仓位
                position = Position(...)
                positions_map[signal_id] = position
                position.current_qty += filled_qty
                position.entry_price = exec_price
                account.total_balance -= fee_paid  # 只扣除手续费

            # 平仓单 (TP1-TP5/SL): 平仓逻辑
            elif order.order_role in TP_ROLES or order.order_role == OrderRole.SL:
                actual_filled = min(filled_qty, position.current_qty)  # 防超卖保护
                position.current_qty -= actual_filled

                # 计算盈亏
                if position.direction == Direction.LONG:
                    gross_pnl = (exec_price - position.entry_price) * actual_filled
                else:
                    gross_pnl = (position.entry_price - exec_price) * actual_filled

                net_pnl = gross_pnl - fee_paid
                position.realized_pnl += net_pnl
                position.total_fees_paid += fee_paid

                if position.current_qty <= Decimal('0'):
                    position.is_closed = True

                account.total_balance += net_pnl  # 盈亏计入账户
        """
        # 1. 翻转订单状态
        order.status = OrderStatus.FILLED
        order.filled_qty = order.requested_qty
        order.average_exec_price = exec_price
        order.filled_at = timestamp  # 任务 3: 设置成交时间戳
        order.updated_at = timestamp  # 任务 3: 同步更新时间戳

        # 计算交易手续费
        trade_value = exec_price * order.requested_qty
        fee_paid = trade_value * self.fee_rate

        # 2. 区分入场单 vs 平仓单
        if order.order_role == OrderRole.ENTRY:
            # ===== 入场单：开仓逻辑 =====
            if position is None:
                # 创建新仓位
                position = Position(
                    id=f"pos_{uuid.uuid4().hex[:8]}",
                    signal_id=order.signal_id,
                    symbol=order.symbol,
                    direction=order.direction,
                    entry_price=exec_price,
                    current_qty=order.requested_qty,
                    watermark_price=exec_price,
                    realized_pnl=Decimal('0'),
                    total_fees_paid=fee_paid,
                    is_closed=False,
                )
                positions_map[order.signal_id] = position
            else:
                # 已有仓位（加仓场景）
                position.current_qty += order.requested_qty
                # 简单平均：实际场景中可能需要更复杂的均价计算
                position.entry_price = exec_price
                position.total_fees_paid += fee_paid

            # 只扣除手续费
            account.total_balance -= fee_paid

        elif order.order_role in TP_ROLES or order.order_role == OrderRole.SL:
            # ===== 平仓单：平仓逻辑 =====
            if position is None:
                # 理论上不应该发生，但做防御性处理
                return

            # 防超卖保护：截断成交数量
            actual_filled = min(order.requested_qty, position.current_qty)

            # 计算盈亏
            if position.direction == Direction.LONG:
                gross_pnl = (exec_price - position.entry_price) * actual_filled
            else:
                gross_pnl = (position.entry_price - exec_price) * actual_filled

            net_pnl = gross_pnl - fee_paid

            # 设置订单成交明细（用于 close_events 收集）
            order.actual_filled = actual_filled
            order.close_pnl = net_pnl
            order.close_fee = fee_paid

            # 更新仓位数量
            position.current_qty -= actual_filled

            # 更新 Position
            position.realized_pnl += net_pnl
            position.total_fees_paid += fee_paid

            # 检查是否完全平仓
            if position.current_qty <= Decimal('0'):
                position.is_closed = True

            # 盈亏计入账户
            account.total_balance += net_pnl

    def _cancel_related_orders(
        self,
        signal_id: str,
        active_orders: List[Order],
    ) -> List[Order]:
        """
        止损触发后，撤销该仓位关联的其他挂单

        参数:
            signal_id: 信号 ID
            active_orders: 活跃订单列表

        返回:
            被撤销的订单列表
        """
        cancelled_orders = []

        for order in active_orders:
            if order.signal_id == signal_id and order.status == OrderStatus.OPEN:
                order.status = OrderStatus.CANCELED
                cancelled_orders.append(order)

        return cancelled_orders
