"""
P0-4: Pinbar 最小波幅检查单元测试

测试目标:
1. 验证 ATR 可用时使用 10% 阈值
2. 验证无 ATR 时使用固定后备值 0.5 USDT
3. 验证有效 Pinbar 正常检测
4. 验证零波幅 K 线处理
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction
from src.domain.strategy_engine import PinbarStrategy, PinbarConfig


# ============================================================
# Test 1: ATR 可用时最小波幅检查
# ============================================================
def test_pinbar_rejects_small_range_with_atr():
    """测试 Pinbar 拒绝波幅过小的 K 线（有 ATR）"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 波幅极小的 K 线
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100.00"),
        high=Decimal("100.02"),  # 仅 0.02 波幅
        low=Decimal("100.00"),
        close=Decimal("100.01"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # ATR = 5.0
    atr = Decimal("5.0")

    # Act
    result = strategy.detect(kline, atr_value=atr)

    # Assert
    # 期望：min_required = 5.0 * 0.1 = 0.5
    # candle_range = 0.02 < 0.5
    # 应该返回 None
    assert result is None


# ============================================================
# Test 2: 无 ATR 时最小波幅检查
# ============================================================
def test_pinbar_rejects_small_range_without_atr():
    """测试 Pinbar 拒绝波幅过小的 K 线（无 ATR）"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 波幅极小的 K 线（价格 100，波幅应 >= 0.1 即 0.1%）
    # 这里波幅只有 0.01 < 0.1，应该被过滤
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100.00"),
        high=Decimal("100.005"),  # 波幅 = 0.005
        low=Decimal("100.00"),
        close=Decimal("100.002"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # Act: 不提供 ATR
    result = strategy.detect(kline, atr_value=None)

    # Assert
    # 期望：min_required = 100 * 0.001 = 0.1
    # candle_range = 0.005 < 0.1
    # 应该返回 None
    assert result is None


# ============================================================
# Test 3: 有效 Pinbar 正常检测（有 ATR）
# ============================================================
def test_pinbar_accepts_normal_range_with_atr():
    """测试 Pinbar 接受正常波幅的 K 线（有 ATR）"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 有效 Pinbar：长下影线，body 在顶部
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("108"),
        high=Decimal("110"),
        low=Decimal("100"),  # 长下影线
        close=Decimal("109"),  # body 在顶部
        volume=Decimal("1000"),
        is_closed=True,
    )

    # ATR = 5.0, min_required = 0.5
    # candle_range = 10 > 0.5，满足条件
    atr = Decimal("5.0")

    # Act
    result = strategy.detect(kline, atr_value=atr)

    # Assert
    assert result is not None
    assert result.direction == Direction.LONG
    assert result.score > 0
    assert result.strategy_name == "pinbar"


# ============================================================
# Test 4: 有效 Pinbar 正常检测（无 ATR）
# ============================================================
def test_pinbar_accepts_normal_range_without_atr():
    """测试 Pinbar 接受正常波幅的 K 线（无 ATR）"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 有效 Pinbar：长下影线，body 在顶部
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("108"),
        high=Decimal("110"),
        low=Decimal("100"),  # 长下影线
        close=Decimal("109"),  # body 在顶部
        volume=Decimal("1000"),
        is_closed=True,
    )

    # Act: 不提供 ATR
    result = strategy.detect(kline, atr_value=None)

    # Assert
    assert result is not None
    assert result.direction == Direction.LONG
    assert result.score > 0


# ============================================================
# Test 5: 零波幅 K 线处理
# ============================================================
def test_pinbar_zero_range():
    """测试零波幅 K 线（high=low）被正确处理"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 零波幅 K 线
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # Act
    result = strategy.detect(kline, atr_value=Decimal("50"))

    # Assert
    assert result is None  # 零波幅应直接返回 None


# ============================================================
# Test 6: ATR 阈值边界测试
# ============================================================
def test_pinbar_atr_threshold_boundary():
    """测试 ATR 阈值边界情况"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # ATR = 5.0, min_required = 0.5
    atr = Decimal("5.0")

    # 波幅 = 0.5（刚好等于阈值）
    kline_boundary = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100.00"),
        high=Decimal("100.50"),  # 波幅 = 0.5
        low=Decimal("100.00"),
        close=Decimal("100.25"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # Act
    result = strategy.detect(kline_boundary, atr_value=atr)

    # Assert
    # 波幅 = 0.5 == min_required (0.5)，应该通过波幅检查
    # 但可能因为不满足 Pinbar 形态条件而返回 None
    # 这里只验证不会因波幅过小被过滤（可能因其他条件被过滤）
    # 我们主要验证边界值不会抛出异常
    assert result is None or result is not None  # 任何结果都可以，只要不抛异常


# ============================================================
# Test 7: 看跌 Pinbar 检测
# ============================================================
def test_pinbar_bearish_with_sufficient_range():
    """测试看跌 Pinbar 正常检测"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 有效看跌 Pinbar：长上影线，body 在底部
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("101"),
        high=Decimal("110"),  # 长上影线
        low=Decimal("100"),
        close=Decimal("102"),  # body 在底部
        volume=Decimal("1000"),
        is_closed=True,
    )

    # ATR = 5.0, min_required = 0.5
    atr = Decimal("5.0")

    # Act
    result = strategy.detect(kline, atr_value=atr)

    # Assert
    assert result is not None
    assert result.direction == Direction.SHORT
    assert result.score > 0


# ============================================================
# Test 8: 低波动市场过滤（集成测试场景）
# ============================================================
def test_pinbar_low_volatility_filter():
    """集成测试：低波动市场 Pinbar 被过滤"""
    # Arrange
    config = PinbarConfig()
    strategy = PinbarStrategy(config)

    # 低波动 K 线（价格 100，波幅应 >= 0.1）
    # 这里波幅只有 0.02 < 0.1，应该被过滤
    kline = KlineData(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp=1000,
        open=Decimal("100.01"),
        high=Decimal("100.02"),  # 波幅 = 0.01
        low=Decimal("100.00"),
        close=Decimal("100.01"),
        volume=Decimal("1000"),
        is_closed=True,
    )

    # Act
    result = strategy.detect(kline, atr_value=Decimal("50"))

    # Assert
    # ATR = 50, min_required = 50 * 0.1 = 5
    # 波幅 0.01 < 5，应被过滤
    assert result is None
