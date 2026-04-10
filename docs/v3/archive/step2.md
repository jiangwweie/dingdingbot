极端悲观撮合引擎 详细设计
1. 核心撮合优先级法则 (The Priority Queue)
在没有 Tick 级数据的单根 K 线内，引擎必须人为规定判定顺序，以阻断“日内路径欺骗”。
针对同一个 Position 关联的活跃订单，判定顺序必须严格遵循以下排列：

Top 1: 止损类订单 (SL / TRAILING_STOP)

逻辑：防守至上。只要 K 线最低点/最高点碰到了止损线，无论该 K 线最终收盘涨得多高，这笔交易直接按止损结算出局。

Top 2: 止盈类订单 (TP1)

逻辑：在确认没有被打损的前提下，才允许判断是否触及了限价止盈位。

Top 3: 入场类订单 (ENTRY)

逻辑：如果是开仓市价单/突破单，放在最后判定。

2. 触发条件与滑点计算公式 (Decimal 计算)
结合你之前确认的“无需跳空惩罚，直接加滑点”原则，具体计算如下：

止损单 (SL/TRAILING_STOP) - 假设触发条件满足：

多头 (LONG)：kline.low <= trigger_price。实际成交价 = trigger_price * (1 - slippage_rate)

空头 (SHORT)：kline.high >= trigger_price。实际成交价 = trigger_price * (1 + slippage_rate)

限价止盈单 (TP1 - LIMIT) - 假设触发条件满足：

多头 (LONG)：kline.high >= price。实际成交价 = price (限价单被动成交，通常无负滑点)

空头 (SHORT)：kline.low <= price。实际成交价 = price

3. 核心代码骨架 (mock_match_orders.py)
这段代码完全遵循你使用 decimal.Decimal 保证金融精度的规范，并直接承接上一步定义的 Pydantic 数据模型。

Python
from decimal import Decimal
from typing import List
# 假设从你的 domain 导入了相关模型
# from src.domain.models import KlineData, Order, Position, Account, OrderStatus, OrderType, Direction, OrderRole

class MockMatchingEngine:
    def __init__(self, slippage_rate: Decimal = Decimal('0.001'), fee_rate: Decimal = Decimal('0.0004')):
        self.slippage = slippage_rate
        self.fee_rate = fee_rate

    def match_orders_for_kline(self, kline: 'KlineData', active_orders: List['Order'], positions_map: dict, account: 'Account'):
        """
        K 线级悲观撮合入口
        positions_map: {signal_id: Position} 用于快速查找订单归属的仓位
        """
        # 提取当前 K 线的极值
        k_high, k_low = kline.high, kline.low
        
        # 必须先按规则排序：SL 优先，TP 其次，ENTRY 最后
        sorted_orders = self._sort_orders_by_priority(active_orders)

        for order in sorted_orders:
            if order.status != OrderStatus.OPEN:
                continue
                
            position = positions_map.get(order.signal_id)

            # ==========================================
            # 1. 处理止损单 (STOP_MARKET / TRAILING_STOP)
            # ==========================================
            if order.order_type in [OrderType.STOP_MARKET, OrderType.TRAILING_STOP]:
                is_triggered = False
                exec_price = Decimal('0')

                if order.direction == Direction.LONG and k_low <= order.trigger_price:
                    is_triggered = True
                    # 多头止损：滑点向下
                    exec_price = order.trigger_price * (1 - self.slippage)
                elif order.direction == Direction.SHORT and k_high >= order.trigger_price:
                    is_triggered = True
                    # 空头止损：滑点向上
                    exec_price = order.trigger_price * (1 + self.slippage)

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account)
                    # 关键动作：打损后，将该仓位关联的其他挂单（如 TP1）全部撤销
                    self._cancel_related_orders(order.signal_id, active_orders)
                    continue # 该仓位在这根 K 线已死，跳过后续判定

            # ==========================================
            # 2. 处理止盈单 (LIMIT)
            # ==========================================
            elif order.order_type == OrderType.LIMIT and order.order_role == OrderRole.TP1:
                is_triggered = False
                exec_price = order.price # 限价单按挂单价成交

                if order.direction == Direction.LONG and k_high >= order.price:
                    is_triggered = True
                elif order.direction == Direction.SHORT and k_low <= order.price:
                    is_triggered = True

                if is_triggered:
                    self._execute_fill(order, exec_price, position, account)
                    # 注意：TP1 成交不代表仓位死亡，不需要撤销关联单。
                    # 但需要触发上层状态机去修改防守单（这部分逻辑在 C 模块）

            # ==========================================
            # 3. 处理入场单 (MARKET) - 略，取决于具体开仓逻辑
            # ==========================================


    def _execute_fill(self, order: 'Order', exec_price: Decimal, position: 'Position', account: 'Account'):
        """执行订单结算与仓位/资金账本同步"""
        # 1. 翻转订单状态
        order.status = OrderStatus.FILLED
        order.filled_qty = order.requested_qty
        order.average_exec_price = exec_price
        
        # 计算交易手续费
        trade_value = exec_price * order.filled_qty
        fee_paid = trade_value * self.fee_rate
        
        # 2. 若是平仓单 (TP1/SL)，计算并固化真实盈亏 (Realized PnL)
        if order.order_role in [OrderRole.TP1, OrderRole.SL]:
            if position.direction == Direction.LONG:
                gross_pnl = (exec_price - position.entry_price) * order.filled_qty
            else:
                gross_pnl = (position.entry_price - exec_price) * order.filled_qty
            
            net_pnl = gross_pnl - fee_paid
            
            # 3. 更新 Position (缩减体积，均价绝对不动)
            position.current_qty -= order.filled_qty
            position.realized_pnl += net_pnl
            position.total_fees_paid += fee_paid
            
            if position.current_qty <= Decimal('0'):
                position.is_closed = True
                
            # 4. 结算至钱包余额
            account.total_balance += net_pnl
        
        # 若是入场单，逻辑另算（通常是新建 Position，扣除冻结保证金等）
4. 架构解耦带来的红利
仔细看 _execute_fill() 这个方法，你会发现，它完美实现了我们之前讨论的**“PMS 资产池视角”**：

无论是固定止盈 TP1 还是移动止损打穿，订单的最终归宿都是调用 _execute_fill。

在这里，系统通过纯数学公式 (退出价 - 开仓均价) * 退出体积 精准算出了纯利，并把它塞进了钱包 account.total_balance 中。

底层的 Position.entry_price 一行代码都没有去碰它。这就保证了在执行你 S6-3 的多级别止盈时，剩下的 30% 尾仓永远能算对它的盈亏平衡点。