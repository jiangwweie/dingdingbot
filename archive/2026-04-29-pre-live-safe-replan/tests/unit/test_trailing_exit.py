"""
Trailing Exit (追踪退出) 单元测试

验证 ADR-2026-04-20: 追踪退出机制
核心逻辑: watermark 达到激活阈值后，追踪水位并触发市价平仓
"""
from decimal import Decimal
import pytest

from src.domain.models import (
    KlineData, Position, Order, OrderStatus, OrderType, OrderRole,
    Direction, RiskManagerConfig, PositionCloseEvent,
)
from src.domain.risk_manager import DynamicRiskManager


# ============================================================
# Helpers
# ============================================================

def create_kline(
    high: Decimal = Decimal('50200'),
    low: Decimal = Decimal('49900'),
    close: Decimal = Decimal('50100'),
    timestamp: int = 1000000,
) -> KlineData:
    return KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        timestamp=timestamp,
        open=Decimal('50000'),
        high=high,
        low=low,
        close=close,
        volume=Decimal('1000'),
        is_closed=True,
    )


def create_position(
    signal_id: str = "sig-1",
    direction: Direction = Direction.LONG,
    entry_price: Decimal = Decimal('50000'),
    current_qty: Decimal = Decimal('0.1'),
    watermark_price: Decimal = None,
    is_closed: bool = False,
) -> Position:
    return Position(
        id="pos-1",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=direction,
        entry_price=entry_price,
        current_qty=current_qty,
        watermark_price=watermark_price,
        is_closed=is_closed,
    )


def create_sl_order(
    signal_id: str = "sig-1",
    direction: Direction = Direction.LONG,
    trigger_price: Decimal = Decimal('49500'),
    requested_qty: Decimal = Decimal('0.1'),
) -> Order:
    return Order(
        id="sl-1",
        signal_id=signal_id,
        symbol="BTC/USDT:USDT",
        direction=direction,
        order_type=OrderType.STOP_MARKET,
        order_role=OrderRole.SL,
        requested_qty=requested_qty,
        trigger_price=trigger_price,
        price=None,
        status=OrderStatus.OPEN,
        filled_qty=Decimal('0'),
        created_at=1000000,
        updated_at=1000000,
    )


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def trailing_exit_config() -> RiskManagerConfig:
    return RiskManagerConfig(
        trailing_exit_enabled=True,
        trailing_exit_percent=Decimal('0.015'),
        trailing_exit_activation_rr=Decimal('0.3'),
        trailing_exit_slippage_rate=Decimal('0.001'),
    )


@pytest.fixture
def manager(trailing_exit_config) -> DynamicRiskManager:
    return DynamicRiskManager(config=trailing_exit_config)


# ============================================================
# 测试: 激活条件
# ============================================================

class TestTrailingActivation:

    def test_long_activates_at_threshold(self, manager):
        """LONG: watermark 达到 entry + 0.3R 时激活
        entry=50000, sl=49500, sl_distance=500
        activation_threshold = 50000 + 0.3*500 = 50150
        """
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        kline = create_kline(high=Decimal('50150'), low=Decimal('50000'), close=Decimal('50100'))
        events = manager.evaluate_and_mutate(kline, position, [sl_order])

        assert position.trailing_exit_activated is True
        assert any(e.event_category == 'trailing_activated' for e in events)

    def test_long_not_activated_below_threshold(self, manager):
        """LONG: watermark < 阈值时不激活"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        kline = create_kline(high=Decimal('50100'), low=Decimal('50000'), close=Decimal('50050'))
        events = manager.evaluate_and_mutate(kline, position, [sl_order])

        assert position.trailing_exit_activated is False

    def test_short_activates_at_threshold(self, manager):
        """SHORT: watermark 跌破 entry - 0.3R 时激活
        entry=50000, sl=50500, sl_distance=500
        activation_threshold = 50000 - 0.3*500 = 49850
        """
        position = create_position(direction=Direction.SHORT, entry_price=Decimal('50000'))
        sl_order = create_sl_order(
            direction=Direction.SHORT,
            trigger_price=Decimal('50500'),
        )

        kline = create_kline(high=Decimal('50000'), low=Decimal('49850'), close=Decimal('49900'))
        events = manager.evaluate_and_mutate(kline, position, [sl_order])

        assert position.trailing_exit_activated is True
        assert any(e.event_category == 'trailing_activated' for e in events)

    def test_disabled_never_activates(self):
        """配置关闭时不激活"""
        config = RiskManagerConfig(trailing_exit_enabled=False)
        mgr = DynamicRiskManager(config=config)
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        kline = create_kline(high=Decimal('51000'), low=Decimal('50000'))
        events = mgr.evaluate_and_mutate(kline, position, [sl_order])

        assert position.trailing_exit_activated is False
        trailing_events = [e for e in events if e.event_category in ('trailing_activated', 'trailing_exit')]
        assert len(trailing_events) == 0


# ============================================================
# 测试: 追踪退出价更新
# ============================================================

class TestTrailingExitPriceUpdate:

    def test_long_exit_price_follows_watermark_up(self, manager):
        """LONG: 追踪退出价随 watermark 上涨而上升"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        # 激活 (high=50200 > 50150)
        kline1 = create_kline(high=Decimal('50200'), low=Decimal('50000'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])
        assert position.trailing_exit_activated is True
        first_exit_price = position.trailing_exit_price

        # watermark 继续上涨 (high=50500)
        kline2 = create_kline(high=Decimal('50500'), low=Decimal('50300'), timestamp=2000)
        manager.evaluate_and_mutate(kline2, position, [sl_order])
        assert position.trailing_exit_price > first_exit_price

    def test_long_exit_price_does_not_go_down(self, manager):
        """LONG: 追踪退出价只升不降"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        # 激活
        kline1 = create_kline(high=Decimal('50500'), low=Decimal('50300'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])
        high_exit_price = position.trailing_exit_price

        # watermark 下跌 - 追踪退出价不变
        kline2 = create_kline(high=Decimal('50300'), low=Decimal('50100'), timestamp=2000)
        manager.evaluate_and_mutate(kline2, position, [sl_order])
        assert position.trailing_exit_price == high_exit_price

    def test_short_exit_price_follows_watermark_down(self, manager):
        """SHORT: 追踪退出价随 watermark 下跌而下降"""
        position = create_position(direction=Direction.SHORT, entry_price=Decimal('50000'))
        sl_order = create_sl_order(direction=Direction.SHORT, trigger_price=Decimal('50500'))

        # 激活 (low=49800 < 49850)
        kline1 = create_kline(high=Decimal('50000'), low=Decimal('49800'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])
        assert position.trailing_exit_activated is True
        first_exit_price = position.trailing_exit_price

        # watermark 继续下跌
        kline2 = create_kline(high=Decimal('49700'), low=Decimal('49500'), timestamp=2000)
        manager.evaluate_and_mutate(kline2, position, [sl_order])
        assert position.trailing_exit_price < first_exit_price


# ============================================================
# 测试: 平仓触发
# ============================================================

class TestTrailingExitTrigger:

    def test_long_exit_triggered_when_low_breaks_trailing_price(self, manager):
        """LONG: K 线最低价跌破追踪退出价时触发平仓"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        # 激活 (high=51000)
        kline1 = create_kline(high=Decimal('51000'), low=Decimal('50500'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])
        trailing_price = position.trailing_exit_price
        assert trailing_price is not None

        # 价格回落跌破追踪退出价 (trailing ≈ 51000 * 0.985 = 50235)
        kline2 = create_kline(high=Decimal('50500'), low=Decimal('50200'), timestamp=2000)
        events = manager.evaluate_and_mutate(kline2, position, [sl_order])

        exit_events = [e for e in events if e.event_category == 'trailing_exit']
        assert len(exit_events) == 1
        assert exit_events[0].close_price == trailing_price

    def test_long_no_exit_when_low_above_trailing_price(self, manager):
        """LONG: K 线最低价在追踪退出价之上时不触发"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        # 激活
        kline1 = create_kline(high=Decimal('51000'), low=Decimal('50500'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])

        # 价格仍在追踪退出价之上
        kline2 = create_kline(high=Decimal('51000'), low=Decimal('50500'), timestamp=2000)
        events = manager.evaluate_and_mutate(kline2, position, [sl_order])

        exit_events = [e for e in events if e.event_category == 'trailing_exit']
        assert len(exit_events) == 0

    def test_short_exit_triggered_when_high_breaks_trailing_price(self, manager):
        """SHORT: K 线最高价涨破追踪退出价时触发平仓"""
        position = create_position(direction=Direction.SHORT, entry_price=Decimal('50000'))
        sl_order = create_sl_order(direction=Direction.SHORT, trigger_price=Decimal('50500'))

        # 激活 (low=49000)
        kline1 = create_kline(high=Decimal('49500'), low=Decimal('49000'), timestamp=1000)
        manager.evaluate_and_mutate(kline1, position, [sl_order])
        trailing_price = position.trailing_exit_price
        assert trailing_price is not None

        # 价格反弹涨破追踪退出价 (trailing ≈ 49000 * 1.015 = 49735)
        kline2 = create_kline(high=Decimal('49800'), low=Decimal('49500'), timestamp=2000)
        events = manager.evaluate_and_mutate(kline2, position, [sl_order])

        exit_events = [e for e in events if e.event_category == 'trailing_exit']
        assert len(exit_events) == 1
        assert exit_events[0].close_price == trailing_price


# ============================================================
# 测试: 边界条件
# ============================================================

class TestTrailingExitEdgeCases:

    def test_closed_position_not_processed(self, manager):
        """已平仓仓位不处理追踪退出"""
        position = create_position(direction=Direction.LONG, is_closed=True)
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        kline = create_kline()
        events = manager.evaluate_and_mutate(kline, position, [sl_order])

        trailing_events = [e for e in events if e.event_category in ('trailing_activated', 'trailing_exit')]
        assert len(trailing_events) == 0

    def test_no_sl_order_no_activation(self, manager):
        """无 SL 订单时不激活追踪退出"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))

        kline = create_kline(high=Decimal('51000'), low=Decimal('50000'))
        events = manager.evaluate_and_mutate(kline, position, [])

        assert position.trailing_exit_activated is False

    def test_already_activated_skips_activation_check(self, manager):
        """已激活的仓位跳过激活检查"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        position.trailing_exit_activated = True
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        kline = create_kline(high=Decimal('51000'), low=Decimal('50500'), timestamp=1000)
        events = manager.evaluate_and_mutate(kline, position, [sl_order])

        # 不应产生 activated 事件（已激活）
        activated_events = [e for e in events if e.event_category == 'trailing_activated']
        assert len(activated_events) == 0
        # 但应更新追踪退出价
        assert position.trailing_exit_price is not None

    def test_activation_time_recorded(self, manager):
        """激活时间戳正确记录"""
        position = create_position(direction=Direction.LONG, entry_price=Decimal('50000'))
        sl_order = create_sl_order(trigger_price=Decimal('49500'))

        ts = 1700000000000
        kline = create_kline(high=Decimal('50200'), low=Decimal('50000'), timestamp=ts)
        manager.evaluate_and_mutate(kline, position, [sl_order])

        assert position.trailing_activation_time == ts
