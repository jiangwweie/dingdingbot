"""
Engulfing Pattern Strategy - 吞没形态检测策略。

Engulfing Pattern (吞没形态) 是一种经典的双 K 线反转形态：
- 看涨吞没 (Bullish Engulfing): 前一根为阴线，当前根为阳线，且阳线实体完全包覆阴线实体
- 看跌吞没 (Bearish Engulfing): 前一根为阳线，当前根为阴线，且阴线实体完全包覆阳线实体
"""
from decimal import Decimal
from typing import Optional, List

from ..models import KlineData, Direction, PatternResult
from ..strategy_engine import PatternStrategy


class EngulfingStrategy(PatternStrategy):
    """
    Engulfing Pattern (吞没形态) 策略实现。

    策略逻辑：
    - 看涨吞没：前一根阴线，当前根阳线，且 current.open < prev.low 且 current.close > prev.high
    - 看跌吞没：前一根阳线，当前根阴线，且 current.open > prev.high 且 current.close < prev.low

    打分逻辑：
    - score = engulfing_ratio / (engulfing_ratio + 1)
    - engulfing_ratio = current_body_size / prev_body_size
    - 分数范围 (0.5, 1.0]，当 engulfing_ratio >= 1 时至少为 0.5
    """

    def __init__(self, max_wick_ratio: Decimal = Decimal("0.6")):
        """
        初始化吞没形态策略。

        Args:
            max_wick_ratio: 最大影线比例，用于过滤十字星等极端情况 (默认 0.3)
        """
        self._max_wick_ratio = max_wick_ratio

    @property
    def name(self) -> str:
        """返回策略名称"""
        return "engulfing"

    def detect(self, kline: KlineData, prev_kline: Optional[KlineData] = None, atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
        """
        检测吞没形态。

        注意：此策略需要两根 K 线才能判断，prev_kline 不能为 None。

        Args:
            kline: 当前 K 线数据
            prev_kline: 前一根 K 线数据 (必需)

        Returns:
            PatternResult 如果检测到吞没形态，None  otherwise
        """
        if prev_kline is None:
            return None

        # 提取价格数据
        curr_open = kline.open
        curr_close = kline.close
        curr_high = kline.high
        curr_low = kline.low

        prev_open = prev_kline.open
        prev_close = prev_kline.close
        prev_high = prev_kline.high
        prev_low = prev_kline.low

        # 计算 K 线实体
        curr_body = abs(curr_close - curr_open)
        prev_body = abs(prev_close - prev_open)

        # 过滤零实体 (十字星)
        if curr_body == Decimal(0) or prev_body == Decimal(0):
            return None

        # 判断 K 线阴阳
        curr_is_bullish = curr_close > curr_open  # 阳线
        prev_is_bullish = prev_close > prev_open  # 阳线

        # 检测看涨吞没 (Bullish Engulfing)
        # 条件：前一根阴线，当前根阳线，且阳线实体包覆阴线实体
        is_bullish_engulfing = (
            not prev_is_bullish and  # 前一根阴线
            curr_is_bullish and      # 当前根阳线
            curr_open <= prev_close and  # 阳线开盘 <= 阴线收盘 (开盘价)
            curr_close >= prev_open      # 阳线收盘 >= 阴线开盘 (最高价)
        )

        # 检测看跌吞没 (Bearish Engulfing)
        # 条件：前一根阳线，当前根阴线，且阴线实体包覆阳线实体
        is_bearish_engulfing = (
            prev_is_bullish and      # 前一根阳线
            not curr_is_bullish and  # 当前根阴线
            curr_open >= prev_close and  # 阴线开盘 >= 阳线收盘 (开盘价)
            curr_close <= prev_open      # 阴线收盘 <= 阳线开盘 (最低价)
        )

        if not is_bullish_engulfing and not is_bearish_engulfing:
            return None

        # 计算吞没比率：当前实体 / 前一根实体
        engulfing_ratio = curr_body / prev_body

        # S6-2-2: 使用统一的评分公式（基类 PatternStrategy 提供）
        # 基础分 = engulfing_ratio 归一化到 0~1
        # 如果有 ATR 值，则使用 ATR 调整评分
        pattern_ratio = Decimal("1.0") - Decimal("1.0") / (engulfing_ratio + Decimal("1.0"))
        # pattern_ratio 范围：当 engulfing_ratio=1 时为 0.5，engulfing_ratio 越大越接近 1

        if atr_value and atr_value > 0:
            candle_range = curr_high - curr_low
            atr_ratio = candle_range / atr_value
            score = self.calculate_score(pattern_ratio, atr_ratio)
        else:
            # Fallback to legacy scoring when ATR not available
            score = float(pattern_ratio)

        score = max(0.5, min(1.0, score))  # 确保在 [0.5, 1.0] 范围内

        # 确定方向
        direction = Direction.LONG if is_bullish_engulfing else Direction.SHORT

        # 计算影线比例用于诊断
        curr_range = curr_high - curr_low
        curr_wick_ratio = (curr_range - curr_body) / curr_range if curr_range > Decimal(0) else Decimal(0)

        # 如果实体太小（影线比例过大），则拒绝这个由于实体差距形成的伪吞没
        if curr_wick_ratio > self._max_wick_ratio:
            return None

        return PatternResult(
            strategy_name="engulfing",
            direction=direction,
            score=score,
            details={
                "engulfing_ratio": float(engulfing_ratio),
                "curr_body": float(curr_body),
                "prev_body": float(prev_body),
                "prev_is_bullish": prev_is_bullish,
                "curr_is_bullish": curr_is_bullish,
                "wick_ratio": float(curr_wick_ratio),
            },
        )

    def detect_with_history(self, kline: KlineData, history: List[KlineData], atr_value: Optional[Decimal] = None) -> Optional[PatternResult]:
        """
        从历史 K 线中自动获取前一根 K 线并检测吞没形态。

        Args:
            kline: 当前 K 线数据
            history: K 线历史列表 (按时间顺序排列，最后一根是最新的)
            atr_value: 可选的 ATR 值（用于评分调整）

        Returns:
            PatternResult 如果检测到吞没形态，None otherwise
        """
        if not history:
            return None

        prev_kline = history[-1]
        return self.detect(kline, prev_kline, atr_value)
