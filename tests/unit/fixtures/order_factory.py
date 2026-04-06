"""订单工厂 - 快速创建测试订单"""
from decimal import Decimal
import uuid
import itertools
from datetime import datetime, timezone

from src.domain.models import (
    Order, OrderStatus, OrderType, OrderRole, Direction
)


class OrderFactory:
    """订单工厂

    注意：使用 itertools.count() 确保测试并发执行时计数器安全
    """

    _counter = itertools.count(1)  # 线程安全的递增计数器

    @classmethod
    def create(
        cls,
        role: OrderRole = OrderRole.ENTRY,
        status: OrderStatus = OrderStatus.OPEN,
        symbol: str = "BTC/USDT:USDT",
        direction: Direction = Direction.LONG,
        qty: Decimal = Decimal('1.0'),
        price: Decimal = Decimal('65000'),
        filled_qty: Decimal = Decimal('0'),
        **overrides
    ) -> Order:
        """
        创建订单，支持覆盖默认值

        Args:
            role: 订单角色
            status: 订单状态
            symbol: 交易对
            direction: 方向
            qty: 数量
            price: 价格
            filled_qty: 已成交数量
            **overrides: 其他覆盖字段

        Returns:
            Order 对象
        """
        counter_val = next(cls._counter)  # 线程安全获取下一个计数值
        current_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        return Order(
            id=f"ord_test_{counter_val}_{uuid.uuid4().hex[:8]}",
            signal_id=f"sig_test_{counter_val}",
            symbol=symbol,
            direction=direction,
            order_type=OrderType.LIMIT if price else OrderType.MARKET,
            order_role=role,
            price=price,
            requested_qty=qty,
            filled_qty=filled_qty,
            status=status,
            created_at=current_time,
            updated_at=current_time,
            reduce_only=role in [OrderRole.TP1, OrderRole.TP2, OrderRole.TP3, OrderRole.TP4, OrderRole.TP5, OrderRole.SL],
            **overrides
        )

    @classmethod
    def entry_order(cls, **kwargs) -> Order:
        """快速创建 ENTRY 订单"""
        return cls.create(role=OrderRole.ENTRY, status=OrderStatus.CREATED, **kwargs)

    @classmethod
    def long_entry(cls, **kwargs) -> Order:
        """快速创建 LONG ENTRY 订单"""
        return cls.create(role=OrderRole.ENTRY, direction=Direction.LONG, status=OrderStatus.CREATED, **kwargs)

    @classmethod
    def short_entry(cls, **kwargs) -> Order:
        """快速创建 SHORT ENTRY 订单"""
        return cls.create(role=OrderRole.ENTRY, direction=Direction.SHORT, status=OrderStatus.CREATED, **kwargs)

    @classmethod
    def tp_order(cls, level: int = 1, **kwargs) -> Order:
        """快速创建 TP 订单

        Args:
            level: TP 级别 (1-5)
        """
        role_map = {
            1: OrderRole.TP1,
            2: OrderRole.TP2,
            3: OrderRole.TP3,
            4: OrderRole.TP4,
            5: OrderRole.TP5
        }
        return cls.create(role=role_map.get(level, OrderRole.TP1), **kwargs)

    @classmethod
    def sl_order(cls, **kwargs) -> Order:
        """快速创建 SL 订单"""
        return cls.create(role=OrderRole.SL, **kwargs)
