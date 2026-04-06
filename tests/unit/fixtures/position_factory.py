"""仓位工厂"""
from decimal import Decimal
import uuid
import itertools

from src.domain.models import Position, Direction


class PositionFactory:
    """仓位工厂

    注意：使用 itertools.count() 确保测试并发执行时计数器安全
    """

    _counter = itertools.count(1)  # 线程安全的递增计数器

    @classmethod
    def create(
        cls,
        direction: Direction = Direction.LONG,
        entry_price: Decimal = Decimal('65000'),
        current_qty: Decimal = Decimal('1.0'),
        symbol: str = "BTC/USDT:USDT",
        signal_id: str = None,
        **overrides
    ) -> Position:
        """
        创建仓位，支持覆盖默认值

        Args:
            direction: 方向
            entry_price: 开仓均价
            current_qty: 当前持仓数量
            symbol: 交易对
            signal_id: 关联信号 ID
            **overrides: 其他覆盖字段

        Returns:
            Position 对象
        """
        counter_val = next(cls._counter)

        return Position(
            id=f"pos_test_{counter_val}_{uuid.uuid4().hex[:8]}",
            signal_id=signal_id or f"sig_test_{counter_val}",
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            current_qty=current_qty,
            watermark_price=None,
            realized_pnl=Decimal('0'),
            total_fees_paid=Decimal('0'),
            is_closed=False,
            **overrides
        )

    @classmethod
    def long_position(cls, **kwargs) -> Position:
        """快速创建 LONG 仓位"""
        return cls.create(direction=Direction.LONG, **kwargs)

    @classmethod
    def short_position(cls, **kwargs) -> Position:
        """快速创建 SHORT 仓位"""
        return cls.create(direction=Direction.SHORT, **kwargs)
