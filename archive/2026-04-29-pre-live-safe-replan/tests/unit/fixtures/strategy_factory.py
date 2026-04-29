"""策略工厂"""
from decimal import Decimal
from typing import List, Optional

from src.domain.models import OrderStrategy


class StrategyFactory:
    """策略工厂"""

    @classmethod
    def single_tp(
        cls,
        strategy_id: str = "std-single-tp",
        name: str = "标准单 TP",
        tp_ratio: Decimal = Decimal('1.0'),
        tp_target: Decimal = Decimal('1.5'),
        sl_rr: Decimal = Decimal('-1.0'),
        **overrides
    ) -> OrderStrategy:
        """
        创建单 TP 策略

        Args:
            strategy_id: 策略 ID
            name: 策略名称
            tp_ratio: TP 比例 (默认 1.0 = 100%)
            tp_target: TP 目标 RR 倍数 (默认 1.5R)
            sl_rr: 初始止损 RR 倍数 (默认 -1.0R)
            **overrides: 其他覆盖字段

        Returns:
            OrderStrategy 对象
        """
        return OrderStrategy(
            id=strategy_id,
            name=name,
            tp_levels=1,
            tp_ratios=[tp_ratio],
            tp_targets=[tp_target],
            initial_stop_loss_rr=sl_rr,
            trailing_stop_enabled=True,
            oco_enabled=True,
            **overrides
        )

    @classmethod
    def multi_tp(
        cls,
        strategy_id: str = "std-multi-tp",
        name: str = "多级别止盈",
        tp_levels: int = 3,
        tp_ratios: Optional[List[Decimal]] = None,
        tp_targets: Optional[List[Decimal]] = None,
        sl_rr: Decimal = Decimal('-1.0'),
        **overrides
    ) -> OrderStrategy:
        """
        创建多 TP 策略

        Args:
            strategy_id: 策略 ID
            name: 策略名称
            tp_levels: TP 级别数量
            tp_ratios: 各级 TP 比例列表 (总和必须为 1.0)
            tp_targets: 各级 TP 目标 RR 倍数列表
            sl_rr: 初始止损 RR 倍数
            **overrides: 其他覆盖字段

        Returns:
            OrderStrategy 对象
        """
        if tp_ratios is None:
            tp_ratios = [Decimal('0.5'), Decimal('0.3'), Decimal('0.2')]
        if tp_targets is None:
            tp_targets = [Decimal('1.5'), Decimal('2.0'), Decimal('3.0')]

        return OrderStrategy(
            id=strategy_id,
            name=name,
            tp_levels=tp_levels,
            tp_ratios=tp_ratios,
            tp_targets=tp_targets,
            initial_stop_loss_rr=sl_rr,
            trailing_stop_enabled=True,
            oco_enabled=True,
            **overrides
        )

    @classmethod
    def two_tp(
        cls,
        strategy_id: str = "std-two-tp",
        name: str = "双 TP 策略",
        tp1_ratio: Decimal = Decimal('0.5'),
        tp1_target: Decimal = Decimal('1.5'),
        tp2_ratio: Decimal = Decimal('0.5'),
        tp2_target: Decimal = Decimal('2.5'),
        sl_rr: Decimal = Decimal('-1.0'),
        **overrides
    ) -> OrderStrategy:
        """
        创建双 TP 策略

        Args:
            strategy_id: 策略 ID
            name: 策略名称
            tp1_ratio: TP1 比例
            tp1_target: TP1 目标 RR 倍数
            tp2_ratio: TP2 比例
            tp2_target: TP2 目标 RR 倍数
            sl_rr: 初始止损 RR 倍数
            **overrides: 其他覆盖字段

        Returns:
            OrderStrategy 对象
        """
        return OrderStrategy(
            id=strategy_id,
            name=name,
            tp_levels=2,
            tp_ratios=[tp1_ratio, tp2_ratio],
            tp_targets=[tp1_target, tp2_target],
            initial_stop_loss_rr=sl_rr,
            trailing_stop_enabled=True,
            oco_enabled=True,
            **overrides
        )
