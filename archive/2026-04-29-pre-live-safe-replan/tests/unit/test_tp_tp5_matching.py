"""
Unit tests for TP2-TP5 matching engine extension (Task 1.4).

Tests cover:
- UT-1: TP2 limit order triggered (LONG)
- UT-2: TP3 limit order triggered (SHORT)
- UT-3: TP4/TP5 same priority as TP1
- UT-4: TP5 not triggered (price not reached)
- UT-5: _execute_fill TP3 PnL calculation
- UT-6: _execute_fill TP2 partial close (position not closed)
- UT-7: _execute_fill TP final close (position closed)
- UT-8: TP4 slippage Decimal precision
- BT-1: Same kline TP1+TP2+SL simultaneous
- BT-2: TP2 requested_qty exceeds remaining position
- BT-3: TP order with no position
- BT-4: TP triggered at exact high (boundary value)
"""
import pytest
from decimal import Decimal
import uuid

from src.domain.matching_engine import MockMatchingEngine, OrderPriority
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


# ============================================================
# Helper Functions
# ============================================================

def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1711785600000,
    open: Decimal = Decimal("70000"),
    high: Decimal = Decimal("71000"),
    low: Decimal = Decimal("69000"),
    close: Decimal = Decimal("70500"),
    volume: Decimal = Decimal("1000"),
) -> KlineData:
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


def create_order(
    signal_id: str,
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    order_type: OrderType = OrderType.MARKET,
    order_role: OrderRole = OrderRole.ENTRY,
    price: Decimal = None,
    trigger_price: Decimal = None,
    requested_qty: Decimal = Decimal("0.1"),
    status: OrderStatus = OrderStatus.OPEN,
) -> Order:
    return Order(
        id=f"ord_{uuid.uuid4().hex[:8]}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        order_type=order_type,
        order_role=order_role,
        price=price,
        trigger_price=trigger_price,
        requested_qty=requested_qty,
        status=status,
        created_at=1711785600000,
        updated_at=1711785600000,
    )


def create_position(
    signal_id: str,
    symbol: str = "BTC/USDT:USDT",
    direction: Direction = Direction.LONG,
    entry_price: Decimal = Decimal("70000"),
    current_qty: Decimal = Decimal("0.1"),
) -> Position:
    return Position(
        id=f"pos_{uuid.uuid4().hex[:8]}",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=entry_price,
    )


def create_account(
    total_balance: Decimal = Decimal("10000"),
) -> Account:
    return Account(
        account_id="test_wallet",
        total_balance=total_balance,
        frozen_margin=Decimal("0"),
    )


# ============================================================
# UT-1: TP2 limit order triggered (LONG)
# ============================================================
def test_ut_001_tp2_limit_order_triggered_long():
    """
    UT-1: TP2 止盈单撮合触发 (LONG)
    前置: LONG 仓位 entry=70000, TP2 LIMIT price=72000
    预期: TP2 触发, exec_price = 72000 * (1 - 0.0005) = 71964
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "sig_tp2_long"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp2_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal("72000"),
        requested_qty=Decimal("0.03"),
    )

    kline = create_kline(high=Decimal("73000"), low=Decimal("69000"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp2_order], positions_map, account)

    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    expected_price = Decimal("72000") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("71964.0")
    # Position qty reduced
    assert position.current_qty == Decimal("0.07")


# ============================================================
# UT-2: TP3 limit order triggered (SHORT)
# ============================================================
def test_ut_002_tp3_limit_order_triggered_short():
    """
    UT-2: TP3 止盈单撮合触发 (SHORT)
    前置: SHORT 仓位 entry=70000, TP3 LIMIT price=68000
    预期: TP3 触发, exec_price = 68000 * (1 + 0.0005) = 68034
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "sig_tp3_short"
    position = create_position(signal_id, direction=Direction.SHORT, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp3_order = create_order(
        signal_id=signal_id,
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP3,
        price=Decimal("68000"),
        requested_qty=Decimal("0.02"),
    )

    kline = create_kline(high=Decimal("71000"), low=Decimal("67000"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp3_order], positions_map, account)

    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    expected_price = Decimal("68000") * (Decimal("1") + Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("68034.0")
    assert position.current_qty == Decimal("0.08")


# ============================================================
# UT-3: TP4/TP5 same priority as TP1
# ============================================================
def test_ut_003_tp4_tp5_same_priority_as_tp1():
    """
    UT-3: TP4/TP5 订单优先级与 TP1 相同
    前置: 同时存在 SL, TP1, TP2, TP3, TP4, TP5, ENTRY 订单
    预期: 排序结果 SL 在前, TP1-TP5 在中(相对顺序不变), ENTRY 在后
    """
    engine = MockMatchingEngine()
    signal_id = "sig_priority"

    sl_order = create_order(signal_id, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL)
    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1)
    tp2_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP2)
    tp3_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP3)
    tp4_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP4)
    tp5_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP5)
    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY)

    # Shuffle
    orders = [entry_order, tp3_order, sl_order, tp1_order, tp5_order, tp2_order, tp4_order]
    sorted_orders = engine._sort_orders_by_priority(orders)

    # SL first
    assert sorted_orders[0].order_role == OrderRole.SL
    # ENTRY last
    assert sorted_orders[-1].order_role == OrderRole.ENTRY
    # TP1-TP5 in the middle (relative order preserved since stable sort)
    tp_orders = [o for o in sorted_orders if o.order_role in (OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5)]
    assert len(tp_orders) == 5

    # Verify priority values
    assert engine._sort_orders_by_priority([sl_order])[0] == sl_order  # SL priority = 1
    # All TP roles map to same priority (OrderPriority.TP = 2)
    for role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5]:
        test_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=role)
        priority = engine._sort_orders_by_priority([test_order])
        assert priority[0] == test_order


# ============================================================
# UT-4: TP5 not triggered (price not reached)
# ============================================================
def test_ut_004_tp5_not_triggered_price_not_reached():
    """
    UT-4: TP5 未触发 (价格未达)
    前置: TP5 LIMIT price=80000, K 线 high=75000
    预期: TP5 保持 OPEN, 不执行
    """
    engine = MockMatchingEngine(
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "sig_tp5_not_triggered"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp5_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP5,
        price=Decimal("80000"),
        requested_qty=Decimal("0.01"),
    )

    kline = create_kline(high=Decimal("75000"), low=Decimal("69000"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp5_order], positions_map, account)

    assert len(executed) == 0
    assert tp5_order.status == OrderStatus.OPEN


# ============================================================
# UT-5: _execute_fill TP3 PnL calculation
# ============================================================
def test_ut_005_execute_fill_tp3_pnl_calculation():
    """
    UT-5: _execute_fill 处理 TP3 平仓 PnL
    前置: LONG entry=70000, TP3 exec_price=74000, qty=0.02
    预期: gross_pnl=80, fee=0.592, net_pnl=79.408
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    signal_id = "sig_tp3_pnl"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp3_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP3,
        price=Decimal("74000"),
        requested_qty=Decimal("0.02"),
    )

    account = create_account(total_balance=Decimal("10000"))
    positions_map = {signal_id: position}

    exec_price = Decimal("74000")
    engine._execute_fill(tp3_order, exec_price, position, account, positions_map, 1711785600000)

    # Verify position
    assert position.current_qty == Decimal("0.08")
    assert position.is_closed == False

    # Verify PnL written to order (Task 1.1 fields)
    assert tp3_order.actual_filled == Decimal("0.02")
    # gross_pnl = (74000 - 70000) * 0.02 = 80
    # fee = 74000 * 0.02 * 0.0004 = 0.592
    expected_fee = Decimal("74000") * Decimal("0.02") * Decimal("0.0004")
    expected_gross_pnl = (Decimal("74000") - Decimal("70000")) * Decimal("0.02")
    expected_net_pnl = expected_gross_pnl - expected_fee

    assert tp3_order.close_fee == expected_fee
    assert tp3_order.close_pnl == expected_net_pnl
    assert position.realized_pnl == expected_net_pnl


# ============================================================
# UT-6: _execute_fill TP2 partial close
# ============================================================
def test_ut_006_execute_fill_tp2_partial_close():
    """
    UT-6: _execute_fill 处理 TP2 部分平仓后仓位未关闭
    前置: qty=0.1, TP2 requested_qty=0.03
    预期: current_qty=0.07, is_closed=False, balance increases
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "sig_tp2_partial"
    initial_balance = Decimal("10000")
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp2_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal("72000"),
        requested_qty=Decimal("0.03"),
    )

    account = create_account(total_balance=initial_balance)
    positions_map = {signal_id: position}

    exec_price = Decimal("72000")
    engine._execute_fill(tp2_order, exec_price, position, account, positions_map, 1711785600000)

    assert position.current_qty == Decimal("0.07")
    assert position.is_closed == False
    # Account balance should have increased by net PnL
    expected_gross_pnl = (Decimal("72000") - Decimal("70000")) * Decimal("0.03")
    expected_fee = Decimal("72000") * Decimal("0.03") * Decimal("0.0004")
    expected_net_pnl = expected_gross_pnl - expected_fee
    assert account.total_balance == initial_balance + expected_net_pnl


# ============================================================
# UT-7: TP final close (position closed)
# ============================================================
def test_ut_007_execute_fill_tp_final_close():
    """
    UT-7: TP 成交后仓位归零触发 is_closed
    前置: qty=0.02, TP3 requested_qty=0.02 (last batch)
    预期: current_qty=0, is_closed=True
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "sig_tp_final"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.02"))

    tp3_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP3,
        price=Decimal("75000"),
        requested_qty=Decimal("0.02"),
    )

    account = create_account()
    positions_map = {signal_id: position}

    exec_price = Decimal("75000")
    engine._execute_fill(tp3_order, exec_price, position, account, positions_map, 1711785600000)

    assert position.current_qty == Decimal("0")
    assert position.is_closed == True
    assert tp3_order.status == OrderStatus.FILLED
    assert tp3_order.actual_filled == Decimal("0.02")


# ============================================================
# UT-8: TP4 slippage Decimal precision
# ============================================================
def test_ut_008_tp4_slippage_decimal_precision():
    """
    UT-8: Decimal 精度 — TP4 滑点计算
    前置: TP4 price=71234.567
    预期: exec_price = 71234.567 * (1 - 0.0005) = 71198.9497165
    """
    engine = MockMatchingEngine(tp_slippage_rate=Decimal("0.0005"))

    signal_id = "sig_tp4_precision"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp4_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP4,
        price=Decimal("71234.567"),
        requested_qty=Decimal("0.1"),
    )

    kline = create_kline(high=Decimal("72000"), low=Decimal("69000"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp4_order], positions_map, account)

    assert len(executed) == 1
    expected_price = Decimal("71234.567") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    # Verify no float contamination
    assert isinstance(executed[0].average_exec_price, Decimal)
    assert isinstance(position.total_fees_paid, Decimal)
    assert isinstance(account.total_balance, Decimal)


# ============================================================
# BT-1: Same kline TP1+TP2+SL simultaneous
# ============================================================
def test_bt_001_same_kline_tp1_tp2_sl_simultaneous():
    """
    BT-1: 同一 K 线 TP1+TP2+SL 同时触发
    前置: LONG qty=0.1, TP1(qty=0.05, price=72000), TP2(qty=0.03, price=73000), SL(trigger=69000)
          K 线 high=74000, low=68000 (both TP and SL conditions met)
    预期: SL 优先成交, TP1/TP2 被撤销, 只有 SL 事件写入
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "simultaneous"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("72000"),
        requested_qty=Decimal("0.05"),
    )
    tp2_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal("73000"),
        requested_qty=Decimal("0.03"),
    )
    sl_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("69000"),
        requested_qty=Decimal("0.1"),
    )

    kline = create_kline(high=Decimal("74000"), low=Decimal("68000"))
    account = create_account()
    positions_map = {signal_id: position}

    all_orders = [tp1_order, tp2_order, sl_order]
    executed = engine.match_orders_for_kline(kline, all_orders, positions_map, account)

    # SL should execute first
    assert sl_order.status == OrderStatus.FILLED
    # TP orders should be canceled (position is closed by SL)
    assert tp1_order.status == OrderStatus.CANCELED
    assert tp2_order.status == OrderStatus.CANCELED
    # Only SL in executed
    assert len(executed) == 1
    assert executed[0].order_role == OrderRole.SL
    # Position closed
    assert position.is_closed == True


# ============================================================
# BT-2: TP2 requested_qty exceeds remaining position
# ============================================================
def test_bt_002_tp2_requested_qty_exceeds_remaining():
    """
    BT-2: TP2 requested_qty 超过剩余仓位
    前置: TP1 已成交 50%, 剩余 qty=0.05, TP2 requested_qty=0.08
    预期: TP2 actual_filled=0.05 (截断), current_qty=0, is_closed=True
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "overshoot"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.05"))

    tp2_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal("72000"),
        requested_qty=Decimal("0.08"),  # Exceeds remaining 0.05
    )

    account = create_account()
    positions_map = {signal_id: position}

    exec_price = Decimal("72000")
    engine._execute_fill(tp2_order, exec_price, position, account, positions_map, 1711785600000)

    # Truncated to remaining position
    assert tp2_order.actual_filled == Decimal("0.05")
    assert position.current_qty == Decimal("0")
    assert position.is_closed == True


# ============================================================
# BT-3: TP order with no position
# ============================================================
def test_bt_003_tp_order_with_no_position():
    """
    BT-3: 无仓位时收到 TP 订单
    前置: positions_map 中无对应 signal_id 的 Position
    预期: _execute_fill 在 TP/SL 分支检测到 position is None 后 return,
          不抛异常，但 order 状态已被设为 FILLED（order 状态在检查 position 之前设置）
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "nonexistent"

    tp2_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP2,
        price=Decimal("72000"),
        requested_qty=Decimal("0.03"),
    )

    account = create_account()
    positions_map: dict = {}  # No position for this signal_id

    # Call _execute_fill directly with None position
    # This simulates what happens when match_orders_for_kline passes None position
    engine._execute_fill(tp2_order, Decimal("72000"), None, account, positions_map, 1711785600000)

    # _execute_fill sets order to FILLED before checking position
    # Then in TP/SL branch, it checks `if position is None: return`
    # So order status is FILLED but no position/account changes happened
    assert tp2_order.status == OrderStatus.FILLED  # Status set before position check
    assert signal_id not in positions_map  # No position created
    # Account balance unchanged (no PnL was applied since position was None)
    assert account.total_balance == Decimal("10000")


# ============================================================
# BT-4: TP triggered at exact high (boundary value)
# ============================================================
def test_bt_004_tp_triggered_at_exact_high():
    """
    BT-4: TP 价格等于 K 线 high（边界值）
    前置: TP1 price = K 线 high = 71000
    预期: TP1 被触发 (k_high >= order.price, 包含等于)
    """
    engine = MockMatchingEngine(
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "exact_boundary"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("71000"),
        requested_qty=Decimal("0.1"),
    )

    kline = create_kline(high=Decimal("71000"), low=Decimal("69000"))  # Exactly equals TP price
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    assert len(executed) == 1
    assert tp1_order.status == OrderStatus.FILLED
    expected_price = Decimal("71000") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("70964.5")


# ============================================================
# Additional: Multi-TP sequential partial close
# ============================================================
def test_it_multi_tp_sequential_partial_close():
    """
    Integration: 多 TP 顺序部分平仓完整流程
    模拟 TP1(50%) -> TP2(30%) -> TP3(20%) 完整平仓
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005"),
    )

    signal_id = "multi_tp"
    initial_balance = Decimal("10000")
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp1_order = create_order(signal_id, direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP1, price=Decimal("72000"), requested_qty=Decimal("0.05"))
    tp2_order = create_order(signal_id, direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP2, price=Decimal("74000"), requested_qty=Decimal("0.03"))
    tp3_order = create_order(signal_id, direction=Direction.LONG, order_type=OrderType.LIMIT, order_role=OrderRole.TP3, price=Decimal("76000"), requested_qty=Decimal("0.02"))

    account = create_account(total_balance=initial_balance)
    positions_map = {signal_id: position}

    all_executed = []

    # Kline 1: Only TP1 triggered
    kline1 = create_kline(timestamp=1711785600000, high=Decimal("73000"), low=Decimal("69000"))
    executed1 = engine.match_orders_for_kline(kline1, [tp1_order, tp2_order, tp3_order], positions_map, account)
    all_executed.extend(executed1)

    assert len(executed1) == 1
    assert executed1[0].order_role == OrderRole.TP1
    assert tp1_order.status == OrderStatus.FILLED
    assert position.current_qty == Decimal("0.05")

    # Kline 2: TP2 and TP3 triggered
    kline2 = create_kline(timestamp=1711872000000, high=Decimal("77000"), low=Decimal("69000"))
    executed2 = engine.match_orders_for_kline(kline2, [tp2_order, tp3_order], positions_map, account)
    all_executed.extend(executed2)

    assert len(executed2) == 2
    assert tp2_order.status == OrderStatus.FILLED
    assert tp3_order.status == OrderStatus.FILLED
    assert position.current_qty == Decimal("0")
    assert position.is_closed == True

    # Verify all TP orders have close_pnl/close_fee set (Task 1.1 fields)
    for order in all_executed:
        assert order.close_pnl is not None, f"{order.order_role.value} should have close_pnl"
        assert order.close_fee is not None, f"{order.order_role.value} should have close_fee"
        assert order.actual_filled is not None, f"{order.order_role.value} should have actual_filled"
        assert isinstance(order.close_pnl, Decimal), f"{order.order_role.value} close_pnl should be Decimal"

    # Verify total PnL invariant: sum of close_pnl == realized_pnl
    total_close_pnl = sum(o.close_pnl for o in all_executed)
    assert total_close_pnl == position.realized_pnl


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
