"""
Unit tests for v3.0 core models.

Tests cover:
1. Enum types (Direction, OrderStatus, OrderType, OrderRole)
2. Account model validation
3. Order model validation
4. Position model validation
5. Decimal precision for financial fields

Note: Direction enum uses uppercase ('LONG'/'SHORT') since v3 migration.
"""
import pytest
from decimal import Decimal
from src.domain.models import (
    Direction,
    OrderStatus,
    OrderType,
    OrderRole,
    Account,
    Order,
    Position,
)


# ===== Enum Tests =====

class TestDirectionEnum:
    """Direction 枚举测试"""

    def test_direction_long_value(self):
        """测试 LONG 方向值（v3 迁移后统一为大写）"""
        assert Direction.LONG == "LONG"

    def test_direction_short_value(self):
        """测试 SHORT 方向值（v3 迁移后统一为大写）"""
        assert Direction.SHORT == "SHORT"

    def test_direction_comparison(self):
        """测试方向比较"""
        assert Direction.LONG != Direction.SHORT


class TestOrderStatusEnum:
    """OrderStatus 枚举测试"""

    def test_status_values(self):
        """测试所有订单状态值"""
        assert OrderStatus.PENDING == "PENDING"
        assert OrderStatus.OPEN == "OPEN"
        assert OrderStatus.PARTIALLY_FILLED == "PARTIALLY_FILLED"
        assert OrderStatus.FILLED == "FILLED"
        assert OrderStatus.CANCELED == "CANCELED"
        assert OrderStatus.REJECTED == "REJECTED"


class TestOrderTypeEnum:
    """OrderType 枚举测试"""

    def test_type_values(self):
        """测试所有订单类型值"""
        assert OrderType.MARKET == "MARKET"
        assert OrderType.LIMIT == "LIMIT"
        assert OrderType.STOP_MARKET == "STOP_MARKET"
        assert OrderType.TRAILING_STOP == "TRAILING_STOP"


class TestOrderRoleEnum:
    """OrderRole 枚举测试"""

    def test_role_values(self):
        """测试所有订单角色值"""
        assert OrderRole.ENTRY == "ENTRY"
        assert OrderRole.TP1 == "TP1"
        assert OrderRole.SL == "SL"


# ===== Account Model Tests =====

class TestAccountModel:
    """Account 模型测试"""

    def test_account_default_values(self):
        """测试账户默认值"""
        account = Account()
        assert account.account_id == "default_wallet"
        assert account.total_balance == Decimal("0")
        assert account.frozen_margin == Decimal("0")

    def test_account_custom_values(self):
        """测试账户自定义值"""
        account = Account(
            account_id="test_wallet",
            total_balance=Decimal("100000"),
            frozen_margin=Decimal("20000"),
        )
        assert account.account_id == "test_wallet"
        assert account.total_balance == Decimal("100000")
        assert account.frozen_margin == Decimal("20000")

    def test_available_balance_calculation(self):
        """测试可用余额计算"""
        account = Account(
            total_balance=Decimal("100000"),
            frozen_margin=Decimal("20000"),
        )
        assert account.available_balance == Decimal("80000")

    def test_available_balance_zero_frozen(self):
        """测试可用余额计算 - 无冻结"""
        account = Account(total_balance=Decimal("100000"))
        assert account.available_balance == Decimal("100000")


# ===== Order Model Tests =====

class TestOrderModel:
    """Order 模型测试"""

    def test_order_required_fields(self):
        """测试订单必填字段"""
        order = Order(
            id="order_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            requested_qty=Decimal("0.5"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        assert order.id == "order_001"
        assert order.signal_id == "signal_001"
        assert order.direction == Direction.LONG
        assert order.order_type == OrderType.LIMIT
        assert order.order_role == OrderRole.TP1
        assert order.requested_qty == Decimal("0.5")

    def test_order_default_values(self):
        """测试订单默认值"""
        order = Order(
            id="order_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("1"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        assert order.filled_qty == Decimal("0")
        assert order.status == OrderStatus.PENDING
        assert order.price is None
        assert order.trigger_price is None
        assert order.exchange_order_id is None

    def test_order_with_price(self):
        """测试限价单价格"""
        order = Order(
            id="order_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal("70000"),
            requested_qty=Decimal("0.5"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        assert order.price == Decimal("70000")

    def test_order_with_trigger_price(self):
        """测试条件单触发价"""
        order = Order(
            id="order_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,
            order_type=OrderType.STOP_MARKET,
            order_role=OrderRole.SL,
            trigger_price=Decimal("64000"),
            requested_qty=Decimal("1"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        assert order.trigger_price == Decimal("64000")

    def test_order_decimal_precision(self):
        """测试订单 Decimal 精度"""
        order = Order(
            id="order_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            order_type=OrderType.MARKET,
            order_role=OrderRole.ENTRY,
            requested_qty=Decimal("0.123456789"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )
        assert order.requested_qty == Decimal("0.123456789")


# ===== Position Model Tests =====

class TestPositionModel:
    """Position 模型测试"""

    def test_position_required_fields(self):
        """测试仓位必填字段"""
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1"),
            watermark_price=Decimal("65000"),
        )
        assert position.id == "position_001"
        assert position.direction == Direction.LONG
        assert position.entry_price == Decimal("65000")
        assert position.current_qty == Decimal("1")

    def test_position_default_values(self):
        """测试仓位默认值"""
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1"),
            watermark_price=Decimal("65000"),
        )
        assert position.realized_pnl == Decimal("0")
        assert position.total_fees_paid == Decimal("0")
        assert position.is_closed is False

    def test_position_with_pnl(self):
        """测试仓位有已实现盈亏"""
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0.5"),  # TP1 后缩减
            watermark_price=Decimal("68000"),
            realized_pnl=Decimal("500"),
            total_fees_paid=Decimal("10"),
        )
        assert position.realized_pnl == Decimal("500")
        assert position.total_fees_paid == Decimal("10")

    def test_position_closed(self):
        """测试平仓状态"""
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("0"),
            watermark_price=Decimal("68000"),
            realized_pnl=Decimal("1000"),
            is_closed=True,
        )
        assert position.current_qty == Decimal("0")
        assert position.is_closed is True

    def test_position_decimal_precision(self):
        """测试仓位 Decimal 精度"""
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000.123456789"),
            current_qty=Decimal("0.123456789"),
            watermark_price=Decimal("68000.987654321"),
            realized_pnl=Decimal("500.111222333"),
        )
        assert position.entry_price == Decimal("65000.123456789")
        assert position.current_qty == Decimal("0.123456789")
        assert position.watermark_price == Decimal("68000.987654321")
        assert position.realized_pnl == Decimal("500.111222333")


# ===== Integration Tests =====

class TestV3ModelsIntegration:
    """v3 模型集成测试"""

    def test_order_position_relationship(self):
        """测试订单与仓位关系"""
        # 创建仓位
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1"),
            watermark_price=Decimal("65000"),
        )

        # 创建 TP1 订单
        tp1_order = Order(
            id="order_tp1_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.SHORT,  # 平仓方向
            order_type=OrderType.LIMIT,
            order_role=OrderRole.TP1,
            price=Decimal("70000"),
            requested_qty=Decimal("0.5"),
            created_at=1234567890000,
            updated_at=1234567890000,
        )

        # 验证关联
        assert position.signal_id == tp1_order.signal_id
        assert position.symbol == tp1_order.symbol

    def test_account_order_position_flow(self):
        """测试账户 - 订单 - 仓位流程"""
        # 1. 初始账户
        account = Account(
            account_id="test_wallet",
            total_balance=Decimal("100000"),
            frozen_margin=Decimal("0"),
        )

        # 2. 创建仓位
        position = Position(
            id="position_001",
            signal_id="signal_001",
            symbol="BTC/USDT:USDT",
            direction=Direction.LONG,
            entry_price=Decimal("65000"),
            current_qty=Decimal("1"),
            watermark_price=Decimal("65000"),
        )

        # 3. TP1 成交后
        position.current_qty = Decimal("0.5")
        position.realized_pnl = Decimal("2500")  # (70000 - 65000) * 0.5

        # 4. 更新账户
        account.total_balance += position.realized_pnl

        # 验证
        assert account.total_balance == Decimal("102500")
        assert position.current_qty == Decimal("0.5")
        assert position.realized_pnl == Decimal("2500")
