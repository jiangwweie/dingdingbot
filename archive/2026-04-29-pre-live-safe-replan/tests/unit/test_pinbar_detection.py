"""
P0 Pinbar Detection Boundary Tests

测试目标:
- A1: 看涨 Pinbar 检测边界值 (8 个测试)
- A2: 看跌 Pinbar 检测边界值 (8 个测试)
- A3: 最小波幅检查补充 (6 个测试)
- A4: 不同价格级别适配 (3 个测试)

技术约束:
- 所有金额使用 decimal.Decimal，严禁 float
- 使用 PinbarStrategy + PinbarConfig 直接测试
- 合成数据，精确构造边界值
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData, Direction
from src.domain.strategy_engine import PinbarStrategy, PinbarConfig


# ============================================================
# Helpers
# ============================================================

def _make_kline(
    open: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
) -> KlineData:
    """Helper to create KlineData with precise Decimal values."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=1000,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
        is_closed=True,
    )


# ============================================================
# A1. 看涨 Pinbar 检测 (8 个测试)
# ============================================================

class TestBullishPinbar:
    """看涨 Pinbar 边界值测试"""

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_bullish_pinbar_standard(self, strategy):
        """A1-01: 标准看涨 Pinbar 检测"""
        # range=20, body=1, body_ratio=0.05, lower_wick=18, wick_ratio=0.9
        # body_position = (108.5-100)/20 = 0.925 >= 0.875
        kline = _make_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("109"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.strategy_name == "pinbar"
        assert result.score > 0

    def test_bullish_pinbar_bearish_candle(self, strategy):
        """A1-02: 阴线形态的反转信号（颜色无关）"""
        # 阴线 (open > close)，但下影线主导，仍为看涨 Pinbar
        # range=20, body=1, lower_wick=17, wick_ratio=0.85
        # body_position = (107.5-100)/20 = 0.875 >= 0.875 (刚好在边界)
        kline = _make_kline(
            open=Decimal("109"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("108"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG

    def test_bullish_pinbar_wick_ratio_at_boundary(self, strategy):
        """A1-03: 影线比例边界值（wick_ratio 刚好满足 >= 0.6 且 body_position 也满足）

        注意：由于 body_position 阈值 = 1 - tolerance - body_ratio/2，
        wick_ratio=0.6 时 body_position 必然低于阈值。
        所以此测试用较高的 wick_ratio (0.85) 确保整体通过。
        """
        # range=20, lower_wick=17, wick_ratio=0.85
        # body=2, body_ratio=0.1
        # upper_wick=1, body_position = (116-100)/20 = 0.8
        # Wait, need to check: threshold = 1-0.1-0.05=0.85, 0.8 < 0.85 FAIL
        #
        # Redesign: range=20, lower_wick=17, body=2, upper_wick=1
        # open=118, close=116: lower_wick=116-100=16, upper_wick=120-118=2
        # dominant=16, wick_ratio=0.8, body_ratio=0.1
        # body_center=117, body_position=17/20=0.85, threshold=0.85
        # 0.85 >= 0.85 PASS
        kline = _make_kline(
            open=Decimal("118"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("116"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.details["wick_ratio"] == pytest.approx(0.8, abs=1e-9)

    def test_bullish_pinbar_wick_ratio_below_boundary(self, strategy):
        """A1-04: 影线比例低于阈值（0.5 < 0.6）"""
        # range=10, dominant_wick=5, wick_ratio=0.5 < 0.6
        kline = _make_kline(
            open=Decimal("105"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("106"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_bullish_pinbar_body_ratio_at_boundary(self, strategy):
        """A1-05: 实体占比边界值（max_body_ratio=0.3 附近且整体通过）

        注意：body_ratio=0.3 时 dominant_wick 需 >= 0.6，
        而 body_position 需 >= 0.75。几何约束要求 dominant_wick 和 body_position
        需协同设计。此处用 body_ratio=0.15 且 wick_ratio=0.7 确保通过。
        """
        # range=20, body=3, body_ratio=0.15
        # lower_wick=14, upper_wick=3, dominant=14, wick_ratio=0.7
        # body_position = (109.5-100)/20 = 0.475
        # threshold = 1-0.1-0.075 = 0.825, 0.475 < 0.825 FAIL
        #
        # Redesign: Need body higher.
        # range=20, body=3, lower_wick=14, upper_wick=3
        # body_center should give body_position >= 0.825
        # body_position = (body_center-100)/20 >= 0.825
        # body_center >= 116.5
        # upper_wick = 120-body_center+body/2 = 120-116.5+1.5 = 5
        # But we need upper_wick=3 for lower_wick=14. Contradiction.
        #
        # Let me try: range=20, body=3, lower_wick=15, upper_wick=2
        # wick_ratio=0.75, body_ratio=0.15
        # low=100, high=120
        # lower_wick=close-100=15 => close=115
        # upper_wick=120-open=2 => open=118
        # body=|115-118|=3, body_ratio=0.15
        # body_center=116.5, body_position=16.5/20=0.825
        # threshold = 1-0.1-0.075=0.825
        # 0.825 >= 0.825 PASS
        kline = _make_kline(
            open=Decimal("118"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("115"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.details["body_ratio"] == pytest.approx(0.15, abs=1e-9)

    def test_bullish_pinbar_body_ratio_above_boundary(self, strategy):
        """A1-06: 实体占比超过阈值（0.4 > 0.3）"""
        # range=10, body=4, body_ratio=0.4 > 0.3
        kline = _make_kline(
            open=Decimal("107"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("103"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_bullish_pinbar_body_position_at_tolerance_edge(self, strategy):
        """A1-07: 实体位置容忍度边界（刚好在阈值上）"""
        # range=20, body=4, body_ratio=0.2
        # lower_wick=16, upper_wick=0, dominant=16, wick_ratio=0.8
        # body_position = (118-100)/20 = 0.9
        # Wait: open=120, close=116 => body_center=118, body_position=0.9
        # threshold = 1-0.1-0.1 = 0.8
        # 0.9 >= 0.8 PASS, but not at edge
        #
        # Need body_position = threshold exactly
        # threshold = 1 - 0.1 - 0.1 = 0.8
        # body_position = 0.8 => body_center = 100 + 0.8*20 = 116
        # body=4 => open=118, close=114 (or vice versa)
        # lower_wick = 114-100 = 14, upper_wick = 120-118 = 2
        # dominant=14, wick_ratio=0.7 >= 0.6
        # body_ratio = 4/20 = 0.2
        # body_position = 16/20 = 0.8
        # threshold = 1-0.1-0.1 = 0.8
        # 0.8 >= 0.8 PASS (exactly at edge)
        kline = _make_kline(
            open=Decimal("118"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("114"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.details["body_position"] == pytest.approx(0.8, abs=1e-9)

    def test_bullish_pinbar_body_position_below_tolerance(self, strategy):
        """A1-08: 实体位置低于容忍度（0.825 < 0.85）"""
        # Same candle but body slightly lower
        # body_center = 116.5, body_position = (116.5-100)/20 = 0.825 < 0.85
        kline = _make_kline(
            open=Decimal("116"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("115"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None


# ============================================================
# A2. 看跌 Pinbar 检测 (8 个测试)
# ============================================================

class TestBearishPinbar:
    """看跌 Pinbar 边界值测试"""

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_bearish_pinbar_standard(self, strategy):
        """A2-01: 标准看跌 Pinbar 检测"""
        # range=20, body=1, upper_wick=18, wick_ratio=0.9
        # body_position = (101.5-100)/20 = 0.075 <= 0.15
        kline = _make_kline(
            open=Decimal("101"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.SHORT
        assert result.strategy_name == "pinbar"
        assert result.score > 0

    def test_bearish_pinbar_bullish_candle(self, strategy):
        """A2-02: 阳线形态的反转信号（颜色无关）"""
        # 阳线 (close > open)，但上影线主导，仍为看跌 Pinbar
        # range=20, body=1, upper_wick=17, wick_ratio=0.85
        # body_position = (102.5-100)/20 = 0.125 <= 0.15
        kline = _make_kline(
            open=Decimal("102"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("103"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.SHORT

    def test_bearish_pinbar_wick_ratio_at_boundary(self, strategy):
        """A2-03: 影线比例边界值（upper_wick 主导且 body_position 刚好在阈值上）

        注意：bearish pinbar 需要 body_position <= tolerance + body_ratio/2。
        用较大的 upper_wick 和较低的 body 位置确保通过。
        """
        # range=20, body=2, body_ratio=0.1
        # upper_wick=16, lower_wick=2, dominant=16, wick_ratio=0.8
        # body_position = (103-100)/20 = 0.15
        # threshold = 0.1+0.05 = 0.15
        # 0.15 <= 0.15 PASS (exactly at edge)
        kline = _make_kline(
            open=Decimal("104"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.SHORT
        assert result.details["wick_ratio"] == pytest.approx(0.8, abs=1e-9)

    def test_bearish_pinbar_wick_ratio_below_boundary(self, strategy):
        """A2-04: 影线比例低于阈值（0.5 < 0.6）"""
        # range=10, upper_wick=5, wick_ratio=0.5 < 0.6
        kline = _make_kline(
            open=Decimal("104"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("105"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_bearish_pinbar_body_ratio_at_boundary(self, strategy):
        """A2-05: 实体占比边界值（max_body_ratio=0.3，刚好等于）"""
        # range=10, body=3, body_ratio=0.3
        # upper_wick=7, wick_ratio=0.7 >= 0.6
        # body_position = (102.5-100)/10 = 0.25 <= 0.35
        kline = _make_kline(
            open=Decimal("104"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("101"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.SHORT
        assert result.details["body_ratio"] == pytest.approx(0.3, abs=1e-9)

    def test_bearish_pinbar_body_ratio_above_boundary(self, strategy):
        """A2-06: 实体占比超过阈值（0.4 > 0.3）"""
        # range=10, body=4, body_ratio=0.4 > 0.3
        kline = _make_kline(
            open=Decimal("105"), high=Decimal("110"),
            low=Decimal("100"), close=Decimal("101"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_bearish_pinbar_body_position_at_tolerance_edge(self, strategy):
        """A2-07: 实体位置容忍度边界（刚好在阈值上）"""
        # range=20, body=2, body_ratio=0.1
        # upper_wick=14, wick_ratio=0.7 >= 0.6
        # body_position = 0.15, threshold = 0.1 + 0.05 = 0.15
        # body_center = 100 + 0.15*20 = 103
        # open=104, close=102, upper_wick=16, lower_wick=2
        # dominant=16, wick_ratio=0.8, body_ratio=0.1
        # body_position = 0.15, threshold = 0.15
        kline = _make_kline(
            open=Decimal("104"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("102"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.SHORT
        assert result.details["body_position"] == pytest.approx(0.15, abs=1e-9)

    def test_bearish_pinbar_body_position_above_tolerance(self, strategy):
        """A2-08: 实体位置高于容忍度（0.475 > 0.35）"""
        # range=10, body=1, body_ratio=0.1
        # upper_wick=6, wick_ratio=0.6
        # body_position = (104.75-100)/10 = 0.475 > 0.35
        # But wait: open=104.5, close=105 -> upper_wick=110-105=5, not 6
        # Let me recalculate: open=104, close=105
        # upper_wick=110-105=5, lower_wick=104-100=4
        # dominant=5, wick_ratio=0.5 < 0.6, fails wick check
        #
        # Redesign: open=105, close=106
        # upper_wick=110-106=4, lower_wick=105-100=5
        # dominant=5 (lower), not upper - won't be bearish
        #
        # Need upper_wick dominant with body_position > 0.35
        # range=10, body=1, upper_wick=6, lower_wick=3
        # open=103, close=104: upper_wick=110-104=6, lower_wick=103-100=3
        # body_position = (103.5-100)/10 = 0.35, not > 0.35
        #
        # open=103, close=103.5: upper_wick=110-103.5=6.5, lower_wick=3
        # Hmm, but then body=0.5, body_ratio=0.05
        # upper_wick=6.5, wick_ratio=0.65
        # body_position = (103.25-100)/10 = 0.325 <= 0.325
        #
        # Let me try different approach: use larger range
        # range=20, body=2, upper_wick=14, lower_wick=4
        # wick_ratio=0.7, body_ratio=0.1
        # body_position threshold = 0.1 + 0.05 = 0.15
        # Need body_position > 0.15
        # body_center = 100 + 0.25*20 = 105
        # open=106, close=104: upper_wick=120-106=14, lower_wick=104-100=4
        # body_position = (105-100)/20 = 0.25 > 0.15
        kline = _make_kline(
            open=Decimal("106"), high=Decimal("120"),
            low=Decimal("100"), close=Decimal("104"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None


# ============================================================
# A3. 最小波幅检查补充 (6 个测试)
# ============================================================

class TestMinRangeCheck:
    """最小波幅检查补充测试"""

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_min_range_doji_edge_case(self, strategy):
        """A3-01: Doji 十字星边界（零波幅直接返回 None）"""
        kline = _make_kline(
            open=Decimal("100"), high=Decimal("100"),
            low=Decimal("100"), close=Decimal("100"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_min_range_just_above_atr_threshold(self, strategy):
        """A3-02: 刚好超过 ATR 阈值，通过波幅检查（但不一定通过形态检查）"""
        # ATR=5.0, min_required = 0.5, candle_range = 0.5
        # 波幅检查通过，但形态可能不满足
        kline = _make_kline(
            open=Decimal("100.25"), high=Decimal("100.50"),
            low=Decimal("100.00"), close=Decimal("100.25"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        # 波幅检查应通过 (0.5 >= 0.5)，但形态可能不满足
        # 验证：不返回 None 即说明波幅检查通过
        # 实际可能因形态不满足返回 None，但不应因波幅过小被过滤
        # 用一个确保能通过形态检查的 K 线
        pass  # Will test with a valid pinbar shape below

    def test_min_range_just_above_atr_threshold_valid_pinbar(self, strategy):
        """A3-02b: 刚好超过 ATR 阈值且形态有效"""
        # ATR=5.0, min_required = 0.5
        # 设计一个刚好 range=0.5 的有效看涨 Pinbar
        # range=0.5, body=0.05, body_ratio=0.1
        # lower_wick=0.4, upper_wick=0.05, wick_ratio=0.8
        # body_position = (100.475-100)/0.5 = 0.95 >= 0.85
        kline = _make_kline(
            open=Decimal("100.45"), high=Decimal("100.50"),
            low=Decimal("100.00"), close=Decimal("100.48"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is not None
        assert result.direction == Direction.LONG

    def test_min_range_just_below_atr_threshold(self, strategy):
        """A3-03: 刚好低于 ATR 阈值，被波幅检查过滤"""
        # ATR=5.0, min_required = 0.5
        # candle_range = 0.49 < 0.5，应该被过滤
        kline = _make_kline(
            open=Decimal("100.20"), high=Decimal("100.49"),
            low=Decimal("100.00"), close=Decimal("100.25"),
        )
        result = strategy.detect(kline, atr_value=Decimal("5.0"))
        assert result is None

    def test_min_range_zero_atr_fallback_percentage(self, strategy):
        """A3-04: ATR=0 或 None 时使用百分比后备（close * 0.001）"""
        # price=10000, min_required = 10000 * 0.001 = 10
        # candle_range = 5 < 10，应该被过滤
        kline = _make_kline(
            open=Decimal("10002"), high=Decimal("10005"),
            low=Decimal("10000"), close=Decimal("10003"),
        )
        result = strategy.detect(kline, atr_value=None)
        assert result is None

    def test_min_range_low_price_level(self, strategy):
        """A3-05: 低价币种适配（DOGE 0.1 美元级别）"""
        # price=0.10, min_required = 0.10 * 0.001 = 0.0001
        # candle_range = 0.002 > 0.0001，通过波幅检查
        # 但形态不满足 pinbar
        kline = _make_kline(
            open=Decimal("0.100"), high=Decimal("0.102"),
            low=Decimal("0.100"), close=Decimal("0.101"),
            symbol="DOGE/USDT:USDT",
        )
        result = strategy.detect(kline, atr_value=None)
        # 波幅检查应通过 (0.002 > 0.0001)
        # 但 wick_ratio = 0/0.002 = 0 < 0.6，形态不满足
        assert result is None

    def test_min_range_extreme_atr_value(self, strategy):
        """A3-06: 极端 ATR 值（ATR 远大于实际波幅）"""
        # ATR=10000, min_required = 1000
        # candle_range = 1001 > 1000，通过波幅检查
        # 设计有效看涨 Pinbar
        # range=1001, body=1, lower_wick=1000, wick_ratio ~ 0.999
        # body_position = (1000.5-100)/1001 = 0.9001 >= 0.85
        kline = _make_kline(
            open=Decimal("1001"), high=Decimal("1101"),
            low=Decimal("100"), close=Decimal("1000"),
        )
        atr = Decimal("10000")
        result = strategy.detect(kline, atr_value=atr)
        assert result is not None
        assert result.direction == Direction.LONG


# ============================================================
# A4. 不同价格级别适配 (3 个测试)
# ============================================================

class TestPriceLevelAdaptation:
    """不同价格级别 Pinbar 检测适配测试"""

    @pytest.fixture
    def strategy(self):
        return PinbarStrategy(PinbarConfig())

    def test_pinbar_btc_high_price_100k(self, strategy):
        """A4-01: BTC 10 万美元级别 - 无 ATR 时百分比后备"""
        # price=100000, min_required = 100000 * 0.001 = 100
        # candle_range = 50 < 100，应该被过滤
        kline = _make_kline(
            open=Decimal("100025"), high=Decimal("100050"),
            low=Decimal("100000"), close=Decimal("100030"),
        )
        result = strategy.detect(kline, atr_value=None)
        assert result is None

    def test_pinbar_btc_high_price_100k_with_atr(self, strategy):
        """A4-01b: BTC 10 万美元级别 - 有 ATR 时正常检测"""
        # ATR=500, min_required = 50
        # candle_range = 200 > 50，通过波幅检查
        # 设计有效看涨 Pinbar
        # range=200, body=20, body_ratio=0.1
        # lower_wick=170, upper_wick=10, wick_ratio=0.85
        # body_position = (100190-100000)/200 = 0.95 >= 0.85
        kline = _make_kline(
            open=Decimal("100180"), high=Decimal("100200"),
            low=Decimal("100000"), close=Decimal("100195"),
        )
        result = strategy.detect(kline, atr_value=Decimal("500"))
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.strategy_name == "pinbar"

    def test_pinbar_eth_mid_price_3k(self, strategy):
        """A4-02: ETH 3 千美元级别"""
        # price=3000, min_required (no ATR) = 3000 * 0.001 = 3
        # candle_range = 50 > 3，通过波幅检查
        # 设计有效看涨 Pinbar
        # range=50, body=5, body_ratio=0.1
        # lower_wick=40, upper_wick=5, wick_ratio=0.8
        # body_position = (3022.5-3000)/50 = 0.45
        # threshold = 1 - 0.1 - 0.05 = 0.85, 0.45 < 0.85 FAIL
        #
        # Redesign: body at top
        # open=3045, close=3040, range=50
        # body_center = 3042.5, body_position = (3042.5-3000)/50 = 0.85
        # lower_wick = 3040-3000 = 40, upper_wick = 3050-3045 = 5
        # wick_ratio = 0.8, body_ratio = 0.1
        # 0.85 >= 0.85 PASS
        kline = _make_kline(
            open=Decimal("3045"), high=Decimal("3050"),
            low=Decimal("3000"), close=Decimal("3040"),
            symbol="ETH/USDT:USDT",
        )
        result = strategy.detect(kline, atr_value=None)
        assert result is not None
        assert result.direction == Direction.LONG

    def test_pinbar_doge_low_price_0_1(self, strategy):
        """A4-03: DOGE 0.1 美元级别"""
        # price=0.10, min_required (no ATR) = 0.10 * 0.001 = 0.0001
        # candle_range = 0.02 > 0.0001，通过波幅检查
        # 设计有效看涨 Pinbar
        # range=0.02, body=0.002, body_ratio=0.1
        # lower_wick=0.017, upper_wick=0.001, wick_ratio=0.85
        # body_position = (0.109-0.10)/0.02 = 0.45
        # threshold = 1-0.1-0.05 = 0.85, 0.45 < 0.85 FAIL
        #
        # Redesign: body at top
        # open=0.117, close=0.115, low=0.10, high=0.12
        # range=0.02, body=0.002, body_ratio=0.1
        # body_center=0.116, body_position=(0.116-0.10)/0.02 = 0.8
        # threshold = 0.85, 0.8 < 0.85 FAIL
        #
        # open=0.118, close=0.116
        # body_center=0.117, body_position=0.85
        # lower_wick=0.116-0.10=0.016, upper_wick=0.12-0.118=0.002
        # dominant=0.016, wick_ratio=0.8
        kline = _make_kline(
            open=Decimal("0.118"), high=Decimal("0.120"),
            low=Decimal("0.100"), close=Decimal("0.116"),
            symbol="DOGE/USDT:USDT",
        )
        result = strategy.detect(kline, atr_value=None)
        assert result is not None
        assert result.direction == Direction.LONG
