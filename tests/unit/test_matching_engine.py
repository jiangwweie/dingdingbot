"""
Unit tests for MockMatchingEngine (v3.0 Phase 2)

Tests cover:
- UT-001: Stop loss trigger (LONG)
- UT-002: Stop loss trigger (SHORT)
- UT-003: TP1 limit order trigger (LONG)
- UT-004: TP1 limit order trigger (SHORT)
- UT-005: Order priority sorting
- UT-006: _execute_fill ENTRY order
- UT-007: _execute_fill TP1/SL order
- UT-008: ENTRY order PnL calculation (fee only)
- UT-009: TP1/SL order PnL calculation
- UT-010: Anti-oversell protection
- UT-011: Cancel related orders after stop loss
- UT-012: Decimal precision
- UT-013: Boundary case (kline.low == trigger_price)
- UT-014: TP1 slippage calculation (LONG) - T2 fix
- UT-015: TP1 slippage calculation (SHORT) - T2 fix
- UT-016: TP1 not triggered (price not reached) - T2 fix
- UT-017: TP1 slippage default rate - T2 fix
"""
import pytest
from decimal import Decimal
import uuid

from src.domain.matching_engine import MockMatchingEngine
from src.domain.models import (
    KlineData,
    Order,
    Position,
    Account,
    OrderStatus,
    OrderType,
    OrderRole,
    Direction,
    Signal,
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
    """Helper to create KlineData"""
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
    """Helper to create Order"""
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
    """Helper to create Position"""
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
    """Helper to create Account"""
    return Account(
        account_id="test_wallet",
        total_balance=total_balance,
        frozen_margin=Decimal("0"),
    )


# ============================================================
# UT-001: Stop loss trigger (LONG)
# ============================================================
def test_ut_001_stop_loss_trigger_long():
    """
    UT-001: 止损单触发 (LONG)
    预期：按 low <= trigger 触发，执行价 = trigger * (1 - slippage)
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    # Create kline where low hits stop loss
    kline = create_kline(low=Decimal("69000"), high=Decimal("71000"))

    # Create LONG position
    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    # Create SL order
    sl_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("69500"),  # Above kline.low, should trigger
        requested_qty=Decimal("0.1"),
    )

    # Create account
    account = create_account()

    # Run matching engine
    positions_map = {signal_id: position}
    executed = engine.match_orders_for_kline(kline, [sl_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    assert executed[0].average_exec_price == Decimal("69500") * (Decimal("1") - Decimal("0.001"))
    assert executed[0].average_exec_price == Decimal("69430.5")


# ============================================================
# UT-002: Stop loss trigger (SHORT)
# ============================================================
def test_ut_002_stop_loss_trigger_short():
    """
    UT-002: 止损单触发 (SHORT)
    预期：按 high >= trigger 触发，执行价 = trigger * (1 + slippage)
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    # Create kline where high hits stop loss
    kline = create_kline(low=Decimal("69000"), high=Decimal("71000"))

    # Create SHORT position
    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.SHORT, entry_price=Decimal("70000"))

    # Create SL order
    sl_order = create_order(
        signal_id=signal_id,
        direction=Direction.SHORT,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("70500"),  # Below kline.high, should trigger
        requested_qty=Decimal("0.1"),
    )

    account = create_account()
    positions_map = {signal_id: position}
    executed = engine.match_orders_for_kline(kline, [sl_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    assert executed[0].average_exec_price == Decimal("70500") * (Decimal("1") + Decimal("0.001"))
    assert executed[0].average_exec_price == Decimal("70570.5")


# ============================================================
# UT-003: TP1 limit order trigger (LONG) - Updated with slippage
# ============================================================
def test_ut_003_tp1_limit_trigger_long():
    """
    UT-003: TP1 限价单触发 (LONG)
    预期：按 high >= price 触发，执行价 = price * (1 - tp_slippage)

    T2 修复：止盈单添加滑点计算
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005")  # 0.05% TP slippage
    )

    kline = create_kline(low=Decimal("69000"), high=Decimal("71000"))

    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    # Create TP1 order
    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("70500"),  # Below kline.high, should trigger
        requested_qty=Decimal("0.1"),
    )

    account = create_account()
    positions_map = {signal_id: position}
    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    # T2 fix: Apply slippage to limit TP orders
    # LONG TP: slippage downward (less money received)
    # Expected price = 70500 * (1 - 0.0005) = 70464.75
    expected_price = Decimal("70500") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("70464.75")


# ============================================================
# UT-004: TP1 limit order trigger (SHORT) - Updated with slippage
# ============================================================
def test_ut_004_tp1_limit_trigger_short():
    """
    UT-004: TP1 限价单触发 (SHORT)
    预期：按 low <= price 触发，执行价 = price * (1 + tp_slippage)

    T2 修复：止盈单添加滑点计算
    """
    engine = MockMatchingEngine(
        slippage_rate=Decimal("0.001"),
        fee_rate=Decimal("0.0004"),
        tp_slippage_rate=Decimal("0.0005")  # 0.05% TP slippage
    )

    kline = create_kline(low=Decimal("69000"), high=Decimal("71000"))

    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.SHORT, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("69500"),  # Above kline.low, should trigger
        requested_qty=Decimal("0.1"),
    )

    account = create_account()
    positions_map = {signal_id: position}
    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    # T2 fix: Apply slippage to limit TP orders
    # SHORT TP: slippage upward (pay more)
    # Expected price = 69500 * (1 + 0.0005) = 69534.75
    expected_price = Decimal("69500") * (Decimal("1") + Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("69534.75")


# ============================================================
# UT-005: Order priority sorting
# ============================================================
def test_ut_005_order_priority_sorting():
    """
    UT-005: 订单优先级排序
    预期：SL 订单排在 TP 和 ENTRY 之前
    """
    engine = MockMatchingEngine()

    signal_id = "sig_test"

    # Create orders with different priorities
    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY)
    sl_order = create_order(signal_id, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL)
    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1)

    # Shuffle orders
    orders = [entry_order, tp1_order, sl_order]

    # Sort by priority
    sorted_orders = engine._sort_orders_by_priority(orders)

    # Assertions
    assert len(sorted_orders) == 3
    assert sorted_orders[0].order_type == OrderType.STOP_MARKET  # SL first
    assert sorted_orders[1].order_role == OrderRole.TP1  # TP second
    assert sorted_orders[2].order_role == OrderRole.ENTRY  # ENTRY last


# ============================================================
# UT-006: _execute_fill ENTRY order
# ============================================================
def test_ut_006_execute_fill_entry_order():
    """
    UT-006: _execute_fill 入场单 (ENTRY)
    预期：current_qty 增加，entry_price 设置为 exec_price
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("0"), current_qty=Decimal("0"))

    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY, requested_qty=Decimal("0.1"))

    account = create_account(total_balance=Decimal("10000"))

    exec_price = Decimal("70000")
    positions_map = {signal_id: position}
    engine._execute_fill(entry_order, exec_price, position, account, positions_map, 1711785600000)

    # Assertions
    assert entry_order.status == OrderStatus.FILLED
    assert entry_order.filled_qty == Decimal("0.1")
    assert entry_order.average_exec_price == Decimal("70000")
    assert position.current_qty == Decimal("0.1")
    assert position.entry_price == Decimal("70000")


# ============================================================
# UT-007: _execute_fill TP1/SL order
# ============================================================
def test_ut_007_execute_fill_exit_order():
    """
    UT-007: _execute_fill 平仓单 (TP1/SL)
    预期：current_qty 减少，realized_pnl 正确计算
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"), current_qty=Decimal("0.1"))

    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1, requested_qty=Decimal("0.1"))

    account = create_account(total_balance=Decimal("10000"))

    exec_price = Decimal("71000")  # Profit of 1000 per BTC
    positions_map = {signal_id: position}
    engine._execute_fill(tp1_order, exec_price, position, account, positions_map, 1711785600000)

    # Assertions
    assert tp1_order.status == OrderStatus.FILLED
    assert position.current_qty == Decimal("0")
    assert position.is_closed == True
    # Gross PnL = (71000 - 70000) * 0.1 = 100 USDT
    # Fee = 71000 * 0.1 * 0.0004 = 2.84 USDT
    # Net PnL = 100 - 2.84 = 97.16 USDT
    assert position.realized_pnl > Decimal("97")  # Approximately 97.16


# ============================================================
# UT-008: ENTRY order PnL calculation (fee only)
# ============================================================
def test_ut_008_entry_order_pnl():
    """
    UT-008: _execute_fill 开仓 PnL 计算
    预期：ENTRY 单 net_pnl = -fee_paid (只扣手续费)
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "sig_test"
    position = create_position(signal_id, current_qty=Decimal("0"))

    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY, requested_qty=Decimal("0.1"))

    initial_balance = Decimal("10000")
    account = create_account(total_balance=initial_balance)

    exec_price = Decimal("70000")
    positions_map = {signal_id: position}
    engine._execute_fill(entry_order, exec_price, position, account, positions_map, 1711785600000)

    # Fee = 70000 * 0.1 * 0.0004 = 2.8 USDT
    expected_fee = Decimal("70000") * Decimal("0.1") * Decimal("0.0004")

    # Account balance should only decrease by fee
    assert account.total_balance == initial_balance - expected_fee


# ============================================================
# UT-009: TP1/SL order PnL calculation
# ============================================================
def test_ut_009_exit_order_pnl():
    """
    UT-009: _execute_fill 平仓 PnL 计算
    预期：TP/SL 单 net_pnl = gross_pnl - fee_paid
    """
    engine = MockMatchingEngine(fee_rate=Decimal("0.0004"))

    signal_id = "sig_test"
    entry_price = Decimal("70000")
    position = create_position(signal_id, direction=Direction.LONG, entry_price=entry_price, current_qty=Decimal("0.1"))

    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1, requested_qty=Decimal("0.1"))

    initial_balance = Decimal("10000")
    account = create_account(total_balance=initial_balance)

    exec_price = Decimal("71000")  # 1000 profit per BTC
    positions_map = {signal_id: position}
    engine._execute_fill(tp1_order, exec_price, position, account, positions_map, 1711785600000)

    # Gross PnL = (71000 - 70000) * 0.1 = 100 USDT
    gross_pnl = (exec_price - entry_price) * Decimal("0.1")

    # Fee = 71000 * 0.1 * 0.0004 = 2.84 USDT
    fee = exec_price * Decimal("0.1") * Decimal("0.0004")

    # Net PnL = 100 - 2.84 = 97.16 USDT
    expected_net_pnl = gross_pnl - fee

    # Account balance should increase by net PnL
    assert account.total_balance == initial_balance + expected_net_pnl


# ============================================================
# UT-010: Anti-oversell protection
# ============================================================
def test_ut_010_anti_oversell():
    """
    UT-010: 防超卖保护 (requested_qty > current_qty)
    预期：filled_qty 被截断为 current_qty，防止仓位变负
    """
    engine = MockMatchingEngine()

    signal_id = "sig_test"
    # Position has only 0.05 BTC
    position = create_position(signal_id, current_qty=Decimal("0.05"))

    # But order requests 0.1 BTC
    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1, requested_qty=Decimal("0.1"))

    account = create_account()

    exec_price = Decimal("71000")
    positions_map = {signal_id: position}
    engine._execute_fill(tp1_order, exec_price, position, account, positions_map, 1711785600000)

    # Assertions
    assert position.current_qty == Decimal("0")  # Should not go negative
    assert position.is_closed == True


# ============================================================
# UT-011: Cancel related orders after stop loss
# ============================================================
def test_ut_011_cancel_related_orders():
    """
    UT-011: 止损后撤销关联订单
    预期：TP1 挂单被撤销
    """
    engine = MockMatchingEngine()

    signal_id = "sig_test"

    # Create active orders
    sl_order = create_order(signal_id, order_type=OrderType.STOP_MARKET, order_role=OrderRole.SL)
    tp1_order = create_order(signal_id, order_type=OrderType.LIMIT, order_role=OrderRole.TP1)

    orders = [sl_order, tp1_order]

    # Cancel related orders
    cancelled = engine._cancel_related_orders(signal_id, orders)

    # Assertions
    assert len(cancelled) == 2  # Both orders should be cancelled
    assert sl_order.status == OrderStatus.CANCELED
    assert tp1_order.status == OrderStatus.CANCELED


# ============================================================
# UT-012: Decimal precision
# ============================================================
def test_ut_012_decimal_precision():
    """
    UT-012: Decimal 精度保护
    预期：所有金额计算无 float 污染
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    signal_id = "sig_test"
    position = create_position(signal_id, current_qty=Decimal("0"))

    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY, requested_qty=Decimal("0.1"))

    account = create_account()

    exec_price = Decimal("70000.123456789")  # High precision price
    positions_map = {signal_id: position}
    engine._execute_fill(entry_order, exec_price, position, account, positions_map, 1711785600000)

    # All calculations should use Decimal
    assert isinstance(position.entry_price, Decimal)
    assert isinstance(account.total_balance, Decimal)
    assert isinstance(position.total_fees_paid, Decimal)


# ============================================================
# UT-013: Boundary case (kline.low == trigger_price)
# ============================================================
def test_ut_013_boundary_trigger_price():
    """
    UT-013: 边界 case: kline.low == trigger_price
    预期：触发止损
    """
    engine = MockMatchingEngine()

    # Create kline where low exactly equals trigger price
    kline = create_kline(low=Decimal("69500"), high=Decimal("71000"))

    signal_id = "sig_test"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    sl_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("69500"),  # Exactly equals kline.low
        requested_qty=Decimal("0.1"),
    )

    account = create_account()
    positions_map = {signal_id: position}
    executed = engine.match_orders_for_kline(kline, [sl_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED


# ============================================================
# UT-014: TP1 slippage calculation (LONG) - T2 fix
# ============================================================
def test_ut_014_tp1_slippage_long():
    """
    UT-014: TP1 止盈滑点计算 (LONG) - T2 修复验证
    预期：多头止盈，滑点向下（少收钱）
    公式：exec_price = price * (1 - tp_slippage_rate)
    """
    engine = MockMatchingEngine(tp_slippage_rate=Decimal("0.0005"))

    signal_id = "sig_test_tp_slippage"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("1000"),
        requested_qty=Decimal("1"),
    )

    kline = create_kline(high=Decimal("1010"), low=Decimal("990"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    # Expected: 1000 * (1 - 0.0005) = 999.5
    expected_price = Decimal("1000") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("999.5")


# ============================================================
# UT-015: TP1 slippage calculation (SHORT) - T2 fix
# ============================================================
def test_ut_015_tp1_slippage_short():
    """
    UT-015: TP1 止盈滑点计算 (SHORT) - T2 修复验证
    预期：空头止盈，滑点向上（多付钱）
    公式：exec_price = price * (1 + tp_slippage_rate)
    """
    engine = MockMatchingEngine(tp_slippage_rate=Decimal("0.0005"))

    signal_id = "sig_test_tp_slippage"
    position = create_position(signal_id, direction=Direction.SHORT, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.SHORT,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("1000"),
        requested_qty=Decimal("1"),
    )

    kline = create_kline(high=Decimal("1010"), low=Decimal("990"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    assert executed[0].status == OrderStatus.FILLED
    # Expected: 1000 * (1 + 0.0005) = 1000.5
    expected_price = Decimal("1000") * (Decimal("1") + Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price
    assert executed[0].average_exec_price == Decimal("1000.5")


# ============================================================
# UT-016: TP1 not triggered (price not reached) - T2 fix
# ============================================================
def test_ut_016_tp1_not_triggered():
    """
    UT-016: TP1 止盈未触发场景 - T2 修复验证
    预期：价格未触及止盈价，订单保持 OPEN
    """
    engine = MockMatchingEngine(tp_slippage_rate=Decimal("0.0005"))

    signal_id = "sig_test_tp_slippage"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("1000"),
        requested_qty=Decimal("1"),
    )

    # K-line high is below TP price - should NOT trigger
    kline = create_kline(high=Decimal("999"), low=Decimal("990"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 0  # No execution
    assert tp1_order.status == OrderStatus.OPEN  # Order still pending


# ============================================================
# UT-017: TP1 slippage default rate - T2 fix
# ============================================================
def test_ut_017_tp1_slippage_default_rate():
    """
    UT-017: TP1 止盈滑点默认值 - T2 修复验证
    预期：未指定 tp_slippage_rate 时，使用默认值 0.05%
    """
    # Default constructor should use 0.05% for TP slippage
    engine = MockMatchingEngine()

    signal_id = "sig_test_tp_slippage"
    position = create_position(signal_id, direction=Direction.LONG, entry_price=Decimal("70000"))

    tp1_order = create_order(
        signal_id=signal_id,
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("1000"),
        requested_qty=Decimal("1"),
    )

    kline = create_kline(high=Decimal("1010"), low=Decimal("990"))
    account = create_account()
    positions_map = {signal_id: position}

    executed = engine.match_orders_for_kline(kline, [tp1_order], positions_map, account)

    # Assertions
    assert len(executed) == 1
    # Default TP slippage is 0.05% = 0.0005
    # Expected: 1000 * (1 - 0.0005) = 999.5
    expected_price = Decimal("1000") * (Decimal("1") - Decimal("0.0005"))
    assert executed[0].average_exec_price == expected_price


# ============================================================
# Integration Test: Complete trade cycle
# ============================================================
def test_it_001_complete_trade_cycle():
    """
    IT-001: 完整交易周期测试
    预期：ENTRY -> TP1 完整流程
    """
    engine = MockMatchingEngine(slippage_rate=Decimal("0.001"), fee_rate=Decimal("0.0004"))

    # Day 1: Entry
    kline_entry = create_kline(
        timestamp=1711785600000,
        open=Decimal("70000"),
        high=Decimal("71000"),
        low=Decimal("69500"),
        close=Decimal("70500"),
    )

    signal_id = "sig_test"
    account = create_account(total_balance=Decimal("10000"))
    positions_map: dict = {}
    active_orders = []

    # Create ENTRY order
    entry_order = create_order(signal_id, order_type=OrderType.MARKET, order_role=OrderRole.ENTRY, requested_qty=Decimal("0.1"))
    active_orders.append(entry_order)

    # Execute entry
    executed = engine.match_orders_for_kline(kline_entry, active_orders, positions_map, account)
    assert len(executed) == 1
    assert entry_order.status == OrderStatus.FILLED

    # Get position
    position = positions_map.get(signal_id)
    assert position is not None
    assert position.current_qty == Decimal("0.1")

    # Create TP1 and SL orders
    tp1_order = create_order(
        signal_id=signal_id,
        order_type=OrderType.LIMIT,
        order_role=OrderRole.TP1,
        price=Decimal("72000"),  # Take profit level
        requested_qty=Decimal("0.1"),
    )
    sl_order = create_order(
        signal_id=signal_id,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        trigger_price=Decimal("69000"),  # Stop loss level
        requested_qty=Decimal("0.1"),
    )
    active_orders = [tp1_order, sl_order]

    # Day 2: TP1 hit
    kline_tp1 = create_kline(
        timestamp=1711872000000,
        open=Decimal("71000"),
        high=Decimal("72500"),  # Above TP1
        low=Decimal("70500"),
        close=Decimal("72000"),
    )

    executed = engine.match_orders_for_kline(kline_tp1, active_orders, positions_map, account)

    # TP1 should be executed
    assert tp1_order.status == OrderStatus.FILLED
    assert position.is_closed == True
    assert position.realized_pnl > 0  # Profit trade


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
