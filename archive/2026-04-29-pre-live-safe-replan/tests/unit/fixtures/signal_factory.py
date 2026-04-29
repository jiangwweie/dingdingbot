"""信号工厂"""
from decimal import Decimal
import uuid
import itertools

from src.domain.models import Signal, Direction


class SignalFactory:
    """信号工厂

    注意：使用 itertools.count() 确保测试并发执行时计数器安全
    """

    _counter = itertools.count(1)  # 线程安全的递增计数器

    @classmethod
    def create(
        cls,
        signal_id: str = None,
        strategy_id: str = "pinbar",
        symbol: str = "BTC/USDT:USDT",
        direction: Direction = Direction.LONG,
        timestamp: int = 1711785600000,
        expected_entry: Decimal = Decimal('65000'),
        expected_sl: Decimal = Decimal('64000'),
        pattern_score: float = 0.85,
        **overrides
    ) -> Signal:
        """
        创建测试信号，支持覆盖默认值

        Args:
            signal_id: 信号 ID
            strategy_id: 策略 ID
            symbol: 交易对
            direction: 方向
            timestamp: 时间戳
            expected_entry: 预期入场价
            expected_sl: 预期止损价
            pattern_score: 形态评分
            **overrides: 其他覆盖字段

        Returns:
            Signal 对象
        """
        counter_val = next(cls._counter)

        return Signal(
            id=signal_id or f"sig_test_{counter_val}_{uuid.uuid4().hex[:8]}",
            strategy_id=strategy_id,
            symbol=symbol,
            direction=direction,
            timestamp=timestamp,
            expected_entry=expected_entry,
            expected_sl=expected_sl,
            pattern_score=pattern_score,
            is_active=True,
            **overrides
        )

    @classmethod
    def long_signal(cls, **kwargs) -> Signal:
        """快速创建 LONG 信号"""
        return cls.create(direction=Direction.LONG, **kwargs)

    @classmethod
    def short_signal(cls, **kwargs) -> Signal:
        """快速创建 SHORT 信号"""
        return cls.create(direction=Direction.SHORT, **kwargs)
