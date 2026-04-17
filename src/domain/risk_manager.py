"""
Dynamic Risk Manager - 动态风控状态机

核心职责:
1. 监听 TP1 成交事件，执行 Breakeven 推保护损
2. 每根 K 线追踪高水位线，执行 Trailing Stop
3. 阶梯频控，防止频繁更新止损单
4. Trailing Take Profit - 追踪止盈调价

设计原则:
1. 领域层纯净：严禁导入 ccxt/aiohttp/fastapi 等 I/O 框架
2. Decimal 精度：所有金额计算使用 Decimal，禁止 float
3. T+1 时序：TP1 引发的 SL 修改在下一根 K 线生效
"""
from decimal import Decimal
from typing import List, Optional

from src.domain.models import (
    KlineData, Position, Order, OrderStatus, OrderType, OrderRole,
    Direction, RiskManagerConfig, PositionCloseEvent
)


class DynamicRiskManager:
    """
    动态风控状态机

    核心职责:
    1. 监听 TP1 成交事件，执行 Breakeven 推保护损
    2. 每根 K 线追踪高水位线，执行 Trailing Stop
    3. 阶梯频控，防止频繁更新止损单
    4. Trailing Take Profit - 追踪止盈调价
    """

    def __init__(
        self,
        config: Optional[RiskManagerConfig] = None,
        trailing_percent: Optional[Decimal] = None,  # 向后兼容：如果提供，覆盖 config
        step_threshold: Optional[Decimal] = None,     # 向后兼容：如果提供，覆盖 config
    ):
        """
        初始化动态风控管理器

        Args:
            config: 风控管理器配置（提供默认值）
            trailing_percent: 移动止损回撤容忍度 (向后兼容参数)
            step_threshold: 阶梯阈值 (向后兼容参数)
        """
        self._config = config or RiskManagerConfig()

        # 向后兼容：如果提供旧参数，覆盖 config 中的值
        if trailing_percent is not None:
            self._config.trailing_percent = trailing_percent
        if step_threshold is not None:
            self._config.step_threshold = step_threshold

    def evaluate_and_mutate(
        self,
        kline: KlineData,
        position: Position,
        active_orders: List[Order],
    ) -> List[PositionCloseEvent]:
        """
        每根 K 线撮合完成后调用此方法进行风控状态突变

        参数:
            kline: 当前 K 线数据
            position: 关联的仓位
            active_orders: 活跃订单列表

        返回:
            List[PositionCloseEvent]: TP 调价事件列表 (event_category='tp_modified')

        副作用:
            - 刷新 position.watermark_price (水位线价格)
            - TP1 成交时：修改 SL 单的 requested_qty/trigger_price/order_type
            - Trailing 时：更新 SL 单的 trigger_price
            - Trailing TP 时：更新 TP 单的 price

        T+1 时序声明:
            TP1 成交引发的 SL 修改，仅在下一根 K 线 (T+1) 开始生效参与撮合
            TP 调价在本 K 线撮合之后、下一根 K 线开始之前执行
            matching_engine 在下一根 K 线使用修改后的 TP 价格进行撮合判定
        """
        # 防御性检查：已平仓仓位不处理
        if position.is_closed or position.current_qty <= 0:
            return []

        # 查找 SL 订单
        sl_order = self._find_order_by_role(active_orders, OrderRole.SL)
        if sl_order is None:
            # 无 SL 订单，风控裸奔，直接返回
            return []

        # 查找 TP1 订单
        tp1_order = self._find_order_by_role(active_orders, OrderRole.TP1)

        # Step 1: 检查 TP1 是否成交，执行 Breakeven 逻辑
        if tp1_order and tp1_order.status == OrderStatus.FILLED:
            self._apply_breakeven(position, sl_order)

        # Step 2: 更新水位线
        self._update_watermark(kline, position)

        # Step 3: 执行 Trailing Stop 逻辑 (如果已激活)
        if sl_order.order_type == OrderType.TRAILING_STOP:
            self._apply_trailing_logic(position, sl_order)

        # Step 4: 执行 Trailing Take Profit 逻辑 (如果已启用)
        if self._config.tp_trailing_enabled:
            return self._apply_trailing_tp(kline, position, active_orders)

        return []

    def _apply_breakeven(
        self,
        position: Position,
        sl_order: Order,
    ) -> None:
        """
        执行 Breakeven 逻辑 (TP1 成交后推保护损)

        触发条件: TP1 订单成交 AND SL 订单尚未变为 TRAILING_STOP

        执行动作:
            - sl_order.requested_qty = position.current_qty (数量对齐)
            - sl_order.trigger_price = position.entry_price (移至开仓价)
            - sl_order.order_type = OrderType.TRAILING_STOP (激活追踪)

        Args:
            position: 关联的仓位
            sl_order: 止损订单
        """
        # 数量对齐：与剩余仓位对齐 (每次都执行，确保多笔 TP1 成交时同步更新)
        sl_order.requested_qty = position.current_qty

        # 仅在 SL 尚未变为 TRAILING_STOP 时执行价格和类型变更
        if sl_order.order_type != OrderType.TRAILING_STOP:

            # 上移止损至开仓价 (Breakeven)
            sl_order.trigger_price = position.entry_price

            # 属性变异：激活移动追踪
            sl_order.order_type = OrderType.TRAILING_STOP

            # 设置退出原因标记
            sl_order.exit_reason = "BREAKEVEN_STOP"

    def _update_watermark(
        self,
        kline: KlineData,
        position: Position,
    ) -> None:
        """
        更新水位线价格

        LONG 仓位：追踪入场后的最高价 (High Watermark)
        SHORT 仓位：追踪入场后的最低价 (Low Watermark)

        Args:
            kline: 当前 K 线数据
            position: 关联的仓位
        """
        if position.direction == Direction.LONG:
            # LONG: 更新最高价
            if position.watermark_price is None or kline.high > position.watermark_price:
                position.watermark_price = kline.high
        else:
            # SHORT: 更新最低价
            if position.watermark_price is None or kline.low < position.watermark_price:
                position.watermark_price = kline.low

    def _apply_trailing_logic(
        self,
        position: Position,
        sl_order: Order,
    ) -> None:
        """
        执行带阶梯阈值的移动止盈计算

        阶梯频控原则:
            新止损价必须比当前价高出阈值才更新，防止 API 限流

        保护损底线:
            LONG: 止损价 ≥ entry_price
            SHORT: 止损价 ≤ entry_price

        Args:
            position: 关联的仓位
            sl_order: 止损订单

        副作用:
            - 更新 sl_order.trigger_price (满足阶梯条件时)
        """
        if position.watermark_price is None:
            return

        # P1-1 修复：使用 is not None 判断，避免 trigger_price=0 时错误使用 entry_price
        current_trigger = sl_order.trigger_price if sl_order.trigger_price is not None else position.entry_price

        if position.direction == Direction.LONG:
            # LONG 仓位 Trailing Stop 计算
            # 理论止损价 = 水位线 * (1 - trailing_percent)
            theoretical_trigger = position.watermark_price * (Decimal('1') - self._config.trailing_percent)

            # 阶梯判定：新止损价必须比当前价高出 step_threshold
            min_required_price = current_trigger * (Decimal('1') + self._config.step_threshold)

            if theoretical_trigger >= min_required_price:
                # 更新止损价，但不低于 entry_price (保护损底线)
                sl_order.trigger_price = max(position.entry_price, theoretical_trigger)
                sl_order.exit_reason = "TRAILING_PROFIT"

        else:
            # SHORT 仓位 Trailing Stop 计算
            # 理论止损价 = 水位线 * (1 + trailing_percent)
            theoretical_trigger = position.watermark_price * (Decimal('1') + self._config.trailing_percent)

            # 阶梯判定：新止损价必须比当前价低于 step_threshold
            min_required_price = current_trigger * (Decimal('1') - self._config.step_threshold)

            if theoretical_trigger <= min_required_price:
                # 更新止损价，但不高于 entry_price (保护损底线)
                sl_order.trigger_price = min(position.entry_price, theoretical_trigger)
                sl_order.exit_reason = "TRAILING_PROFIT"

    def _find_order_by_role(
        self,
        orders: List[Order],
        role: OrderRole,
    ) -> Optional[Order]:
        """
        查找指定角色的订单

        Args:
            orders: 订单列表
            role: 订单角色

        Returns:
            匹配的订单，未找到返回 None
        """
        for order in orders:
            if order.order_role == role:
                return order
        return None

    # ============================================================
    # Trailing Take Profit 方法
    # ============================================================

    def _apply_trailing_tp(
        self,
        kline: KlineData,
        position: Position,
        active_orders: List[Order],
    ) -> List[PositionCloseEvent]:
        """
        对所有启用了 trailing 的活跃 TP 订单执行追踪调价

        激活条件 (必须同时满足):
            1. tp_trailing_enabled = True (全局配置)
            2. 该 TP 级别在 tp_trailing_enabled_levels 中
            3. 该 TP 订单状态为 OPEN
            4. position.watermark_price 已达到激活阈值
               (LONG: watermark >= entry + activation_rr * (tp_price - entry))
               (SHORT: watermark <= entry - activation_rr * (entry - tp_price))

        调价逻辑 (LONG 示例):
            theoretical_tp = watermark * (1 - tp_trailing_percent)
            min_required   = current_tp * (1 + tp_step_threshold)
            if theoretical_tp >= min_required:
                new_tp = max(original_tp_price, theoretical_tp)   # 保护底线
                tp_order.price = new_tp

        Args:
            kline: 当前 K 线数据
            position: 关联的仓位
            active_orders: 活跃订单列表

        Returns:
            List[PositionCloseEvent]: TP 调价事件列表 (event_category='tp_modified')

        副作用:
            - 更新 tp_order.price (满足条件时)
            - 设置 position.tp_trailing_activated = True (首次激活时)
            - 写入 position.original_tp_prices (首次遇到该 TP 时)
        """
        events = []

        if position.watermark_price is None:
            return events

        enabled_levels = set(self._config.tp_trailing_enabled_levels)

        for order in active_orders:
            # 仅处理活跃的 TP 订单
            if order.status != OrderStatus.OPEN:
                continue
            if order.signal_id != position.signal_id:
                continue
            if order.order_role.value not in enabled_levels:
                continue
            if order.price is None:
                continue

            # 记录原始 TP 价格 (仅首次)
            tp_level_key = order.order_role.value  # "TP1", "TP2", etc.
            if tp_level_key not in position.original_tp_prices:
                position.original_tp_prices[tp_level_key] = order.price

            original_tp = position.original_tp_prices[tp_level_key]

            # 检查激活条件
            if not self._check_tp_trailing_activation(position, original_tp):
                continue

            # 标记激活 (单向状态)
            if not position.tp_trailing_activated:
                position.tp_trailing_activated = True

            # 执行调价计算
            event = self._calculate_and_apply_tp_trailing(
                position, order, original_tp, kline.timestamp
            )
            if event:
                events.append(event)

        return events

    def _check_tp_trailing_activation(
        self,
        position: Position,
        original_tp_price: Decimal,
    ) -> bool:
        """
        检查 Trailing TP 激活条件

        激活阈值 = entry + activation_rr × (tp_price - entry)

        示例 (LONG, entry=60000, tp=66000, activation_rr=0.5):
            activation_price = 60000 + 0.5 × (66000 - 60000) = 63000
            当 watermark >= 63000 时激活

        Args:
            position: 仓位对象 (需要 watermark_price, entry_price, direction)
            original_tp_price: 原始 TP 价格

        Returns:
            True: 满足激活条件
        """
        if position.tp_trailing_activated:
            return True  # 已激活，无需再检查

        if position.watermark_price is None:
            return False

        activation_rr = self._config.tp_trailing_activation_rr

        if position.direction == Direction.LONG:
            price_range = original_tp_price - position.entry_price
            activation_price = position.entry_price + activation_rr * price_range
            return position.watermark_price >= activation_price
        else:
            price_range = position.entry_price - original_tp_price
            activation_price = position.entry_price - activation_rr * price_range
            return position.watermark_price <= activation_price

    def _calculate_and_apply_tp_trailing(
        self,
        position: Position,
        tp_order: Order,
        original_tp_price: Decimal,
        timestamp: int,
    ) -> Optional[PositionCloseEvent]:
        """
        对单个 TP 订单执行 trailing 调价

        LONG 方向:
            theoretical_tp = watermark × (1 - tp_trailing_percent)
            上移方向：theoretical_tp > current_tp_price
            阶梯判定：theoretical_tp >= current_tp × (1 + tp_step_threshold)
            底线保护：new_tp >= original_tp_price (不可低于原始 TP)

        SHORT 方向:
            theoretical_tp = watermark × (1 + tp_trailing_percent)
            下移方向：theoretical_tp < current_tp_price
            阶梯判定：theoretical_tp <= current_tp × (1 - tp_step_threshold)
            底线保护：new_tp <= original_tp_price (不可高于原始 TP)

        Args:
            position: 仓位对象
            tp_order: TP 订单
            original_tp_price: 原始 TP 价格（底线）
            timestamp: K 线时间戳 (用于事件记录)

        Returns:
            PositionCloseEvent: 调价事件 (event_category='tp_modified')
            None: 未满足调价条件
        """
        current_tp = tp_order.price
        watermark = position.watermark_price

        if position.direction == Direction.LONG:
            # LONG: TP 价格随水位线上移
            theoretical_tp = watermark * (Decimal('1') - self._config.tp_trailing_percent)

            # 阶梯判定：新价格必须高出当前价一定比例
            min_required = current_tp * (Decimal('1') + self._config.tp_step_threshold)

            if theoretical_tp >= min_required:
                # 底线保护：不低于原始 TP 价格
                new_tp = max(original_tp_price, theoretical_tp)
                old_tp = tp_order.price
                tp_order.price = new_tp

                # 生成调价事件
                return PositionCloseEvent(
                    position_id=position.id,
                    order_id=tp_order.id,
                    event_type=tp_order.order_role.value,
                    event_category='tp_modified',
                    close_price=None,
                    close_qty=None,
                    close_pnl=None,
                    close_fee=None,
                    close_time=timestamp,
                    exit_reason=f"TRAILING_TP: {old_tp}→{new_tp} (watermark={watermark})",
                )

        else:
            # SHORT: TP 价格随水位线下移
            theoretical_tp = watermark * (Decimal('1') + self._config.tp_trailing_percent)

            # 阶梯判定：新价格必须低于当前价一定比例
            min_required = current_tp * (Decimal('1') - self._config.tp_step_threshold)

            if theoretical_tp <= min_required:
                # 底线保护：不高于原始 TP 价格
                new_tp = min(original_tp_price, theoretical_tp)
                old_tp = tp_order.price
                tp_order.price = new_tp

                return PositionCloseEvent(
                    position_id=position.id,
                    order_id=tp_order.id,
                    event_type=tp_order.order_role.value,
                    event_category='tp_modified',
                    close_price=None,
                    close_qty=None,
                    close_pnl=None,
                    close_fee=None,
                    close_time=timestamp,
                    exit_reason=f"TRAILING_TP: {old_tp}→{new_tp} (watermark={watermark})",
                )

        return None
