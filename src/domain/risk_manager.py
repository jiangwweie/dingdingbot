"""
Dynamic Risk Manager - 动态风控状态机

核心职责:
1. 监听 TP1 成交事件，执行 Breakeven 推保护损
2. 每根 K 线追踪高水位线，执行 Trailing Stop
3. 阶梯频控，防止频繁更新止损单

设计原则:
1. 领域层纯净：严禁导入 ccxt/aiohttp/fastapi 等 I/O 框架
2. Decimal 精度：所有金额计算使用 Decimal，禁止 float
3. T+1 时序：TP1 引发的 SL 修改在下一根 K 线生效
"""
from decimal import Decimal
from typing import List, Optional

from src.domain.models import KlineData, Position, Order, OrderStatus, OrderType, OrderRole, Direction, RiskManagerConfig


class DynamicRiskManager:
    """
    动态风控状态机

    核心职责:
    1. 监听 TP1 成交事件，执行 Breakeven 推保护损
    2. 每根 K 线追踪高水位线，执行 Trailing Stop
    3. 阶梯频控，防止频繁更新止损单
    """

    def __init__(
        self,
        config: Optional[RiskManagerConfig] = None,
    ):
        """
        初始化动态风控管理器

        Args:
            config: 风控管理器配置（提供默认值）
        """
        self._config = config or RiskManagerConfig()

    def evaluate_and_mutate(
        self,
        kline: KlineData,
        position: Position,
        active_orders: List[Order],
    ) -> None:
        """
        每根 K 线撮合完成后调用此方法进行风控状态突变

        参数:
            kline: 当前 K 线数据
            position: 关联的仓位
            active_orders: 活跃订单列表

        副作用:
            - 刷新 position.watermark_price (水位线价格)
            - TP1 成交时：修改 SL 单的 requested_qty/trigger_price/order_type
            - Trailing 时：更新 SL 单的 trigger_price

        T+1 时序声明:
            TP1 成交引发的 SL 修改，仅在下一根 K 线 (T+1) 开始生效参与撮合
        """
        # 防御性检查：已平仓仓位不处理
        if position.is_closed or position.current_qty <= 0:
            return

        # 查找 SL 订单
        sl_order = self._find_order_by_role(active_orders, OrderRole.SL)
        if sl_order is None:
            # 无 SL 订单，风控裸奔，直接返回
            return

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
