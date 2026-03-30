动态风控状态机 详细设计
1. 核心职责与触发时机
动态风控状态机主要在两个时刻被唤醒：

事件触发 (Event-Driven)：当 B 模块刚刚把一个 TP1 订单标记为 FILLED（成交）时。

时间触发 (Tick/Kline-Driven)：在每一根新 K 线进来时，评估是否需要上调（Trailing）现有的移动止损单。

2. 核心状态转移逻辑 (State Transitions)
场景：多头仓位 (LONG)，已开仓 1 BTC，开仓均价 65,000。

初始防守：Order_SL（止损单），数量 1 BTC，触发价 64,000。

初始目标：Order_TP1（止盈单），数量 0.5 BTC，挂单价 66,000。

动作 1：推保护损 (Breakeven) 与 订单缩容
当状态机监听到 Order_TP1.status == FILLED 时，必须极其果断地执行以下“三连击”：

缩减防守单体积：将 Order_SL 的 requested_qty 从 1 BTC 强制修改为 0.5 BTC（与 Position.current_qty 对齐）。

上移生命线：将 Order_SL 的 trigger_price 强制修改为 Position.entry_price (65,000)。这笔交易从这一秒起，彻底进入“零风险”的免费抽奖模式。

属性变异：将 Order_SL 的 order_type 标记为 TRAILING_STOP（移动止盈），赋予其追随高水位线的能力。

动作 2：高水位追踪 (Trailing) 与 阶梯阈值 (Step Threshold)
当防守单变成了 TRAILING_STOP 后，每一根新 K 线进来，状态机都会计算新的动态止损位：

更新极值：如果 kline.high > Position.highest_price_since_entry，刷新最高价。

计算理论止损价：理论触发价 = 最高价 * (1 - 移动止损比例)，例如回调 2%。

阶梯频控（核心红线）：不能每次算出新价格就去更新。只有当 理论触发价 - 当前 trigger_price > 最小阶梯阈值 时，才执行更新操作。这能完美避开实盘中被交易所封禁 API 的风险。

3. 核心代码骨架 (risk_state_machine.py)
这段代码负责接管 B 模块撮合完毕后的残局清理与新风控部署。

Python
from decimal import Decimal
from typing import List
# 假设导入了 domain 模型
# from src.domain.models import Position, Order, OrderStatus, OrderRole, OrderType, Direction, KlineData

class DynamicRiskManager:
    def __init__(self, trailing_percent: Decimal = Decimal('0.02'), step_threshold: Decimal = Decimal('0.005')):
        """
        :param trailing_percent: 移动止损回撤容忍度 (例如 2%)
        :param step_threshold: 阶梯阈值，新止损价必须比老止损价高出 0.5% 才更新，防 API 限流
        """
        self.trailing_percent = trailing_percent
        self.step_threshold = step_threshold

    def evaluate_and_mutate(self, kline: 'KlineData', position: 'Position', active_orders: List['Order']):
        """
        每根 K 线撮合完成后，调用此方法进行风控状态突变
        """
        if position.is_closed:
            return

        # 刷新仓位的高低水位线
        if position.direction == Direction.LONG and kline.high > position.highest_price_since_entry:
            position.highest_price_since_entry = kline.high
        elif position.direction == Direction.SHORT and kline.low < position.highest_price_since_entry: # 做空时 low 越低越好
            position.highest_price_since_entry = kline.low

        sl_order = self._find_order_by_role(active_orders, OrderRole.SL)
        tp1_order = self._find_order_by_role(active_orders, OrderRole.TP1)

        # 找不到止损单说明风控裸奔，属于异常状态
        if not sl_order:
            return 

        # ==========================================
        # 突变逻辑 1: TP1 刚刚成交 -> 推保护损 (Breakeven)
        # ==========================================
        # 如果 TP1 存在，且刚被 B 模块标记为 FILLED，而 SL 还没被改造成 TRAILING_STOP
        if tp1_order and tp1_order.status == OrderStatus.FILLED and sl_order.order_type != OrderType.TRAILING_STOP:
            
            # 1. 对齐剩余数量
            sl_order.requested_qty = position.current_qty
            
            # 2. 强制推保护损 (把止损价移到开仓均价)
            sl_order.trigger_price = position.entry_price
            
            # 3. 属性变异，激活移动追踪
            sl_order.order_type = OrderType.TRAILING_STOP
            
            # (实盘中，这里需要调用交易所 API 撤销原 SL 单，下达新的条件单)
            # return 因为这根 K 线已经做了重大调整，追踪逻辑等下一根再算
            return

        # ==========================================
        # 突变逻辑 2: 高水位追踪 (Trailing Stop)
        # ==========================================
        if sl_order.order_type == OrderType.TRAILING_STOP:
            self._apply_trailing_logic(position, sl_order)

    def _apply_trailing_logic(self, position: 'Position', sl_order: 'Order'):
        """执行带阶梯阈值的移动止盈计算"""
        current_trigger = sl_order.trigger_price
        new_trigger = current_trigger

        if position.direction == Direction.LONG:
            # 理论计算：最高价往下回撤百分比
            theoretical_trigger = position.highest_price_since_entry * (Decimal('1') - self.trailing_percent)
            
            # 阶梯判定：只有新算出止损价，比当前的止损价高出一个“阶梯阈值”，才允许更新
            min_required_price = current_trigger * (Decimal('1') + self.step_threshold)
            
            if theoretical_trigger >= min_required_price:
                new_trigger = theoretical_trigger

        elif position.direction == Direction.SHORT:
            # 空头逻辑反转：最低价往上反弹百分比
            theoretical_trigger = position.highest_price_since_entry * (Decimal('1') + self.trailing_percent)
            min_required_price = current_trigger * (Decimal('1') - self.step_threshold)
            
            if theoretical_trigger <= min_required_price:
                new_trigger = theoretical_trigger

        # 如果触发了阶梯更新
        if new_trigger != current_trigger:
            # 安全底线：无论怎么移动，多头止盈价不能低于开仓价，空头止盈价不能高于开仓价
            if position.direction == Direction.LONG:
                sl_order.trigger_price = max(position.entry_price, new_trigger)
            else:
                sl_order.trigger_price = min(position.entry_price, new_trigger)
                
            # (实盘中，这里调用 CCXT 修改远端订单的触发价)

    def _find_order_by_role(self, orders: List['Order'], role: OrderRole) -> 'Order':
        for o in orders:
            if o.order_role == role:
                return o
        return None
4. 回测系统总调度 (The Pipeline)
现在我们把 A（数据模型）、B（撮合引擎）、C（风控状态机）拼装到一起。在你的 backtester.py 中，处理单根 K 线的总调度流如下：

Python
for kline in klines:
    # 1. 策略引擎运算，看是否要生成新 Signal 和新 Orders
    # ... 你的原逻辑 ...

    # 2. 调用 B 模块：物理撮合
    mock_matching_engine.match_orders_for_kline(kline, all_active_orders, positions_map, account)

    # 3. 调用 C 模块：风控决策与状态突变
    for position in active_positions:
        dynamic_risk_manager.evaluate_and_mutate(kline, position, all_active_orders)
        
    # 4. 净值采样 (画资金曲线用)
    # ...