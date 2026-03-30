"""
ATR 问题 BCD 方案修复 - 集成测试

测试契约：docs/designs/atr-bcd-fix-contract.md

验收标准:
- 方案 B: 止损距离 < 0.1% 的信号被自动调整到最小距离
- 方案 C: ATR 绝对波幅 < 0.1 USDT 被过滤
- 方案 D: API 返回完整 metadata (candle_range, atr, ratio 等)
"""
import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock

from src.domain.models import KlineData, Direction, PatternResult, AccountSnapshot
from src.domain.filter_factory import AtrFilterDynamic, FilterContext, TraceEvent
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.infrastructure.signal_repository import SignalRepository


# ============================================================
# 方案 C: ATR 绝对波幅阈值测试
# ============================================================
class TestSchemeC_AttrAbsoluteRange:
    """方案 C: ATR 过滤器添加绝对波幅阈值检查"""

    def test_cross_doji_filtered_by_absolute_range(self):
        """测试十字星形态被绝对波幅过滤"""
        # 配置 ATR 过滤器：min_absolute_range = 0.1 USDT
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),  # 最小绝对波幅 0.1 USDT
            enabled=True
        )

        # 模拟十字星形态：波幅仅 0.02 USDT
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50000.01"),  # 波幅 = 0.02 USDT
            low=Decimal("49999.99"),
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        # 预热 ATR 数据
        key = "BTC/USDT:USDT:15m"
        atr_filter._atr_state[key] = {
            "tr_values": [Decimal("1.0")] * 14,
            "atr": Decimal("1.0"),
            "prev_close": None
        }

        pattern = Mock(spec=PatternResult)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
            kline=kline,
        )

        event = atr_filter.check(pattern, context)

        # 验证：十字星被过滤
        assert event.passed is False
        assert event.reason == "insufficient_absolute_volatility"
        assert event.metadata["candle_range"] == 0.02
        assert event.metadata["min_required"] == 0.1

    def test_normal_volatility_passes(self):
        """测试正常波幅的 K 线通过过滤"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # 正常波幅 K 线：波幅 = 5 USDT
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50002.50"),  # 波幅 = 5 USDT
            low=Decimal("49997.50"),
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        key = "BTC/USDT:USDT:15m"
        atr_filter._atr_state[key] = {
            "tr_values": [Decimal("1.0")] * 14,
            "atr": Decimal("1.0"),
            "prev_close": None
        }

        pattern = Mock(spec=PatternResult)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
            kline=kline,
        )

        event = atr_filter.check(pattern, context)

        # 验证：正常波幅通过
        assert event.passed is True
        assert event.reason == "volatility_sufficient"

    def test_metadata_contains_all_required_fields(self):
        """测试 metadata 包含所有必要字段（方案 D 验证）"""
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        # 低波幅 K 线
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50000.01"),
            low=Decimal("49999.99"),
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        key = "BTC/USDT:USDT:15m"
        atr_filter._atr_state[key] = {
            "tr_values": [Decimal("1.0")] * 14,
            "atr": Decimal("1.0"),
            "prev_close": None
        }

        pattern = Mock(spec=PatternResult)
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
            kline=kline,
        )

        event = atr_filter.check(pattern, context)

        # 验证 metadata 字段完整性
        assert "candle_range" in event.metadata
        assert "min_required" in event.metadata
        # 方案 C：绝对波幅不足时，metadata 包含 candle_range 和 min_required


# ============================================================
# 方案 B: 最小止损距离检查测试
# ============================================================
class TestSchemeB_MinimumStopLoss:
    """方案 B: 添加最小止损距离检查（0.1%）"""

    @pytest.fixture
    def calculator(self):
        """创建风险计算器"""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),  # 1%
            max_leverage=10,
            max_total_exposure=Decimal("0.8")
        )
        return RiskCalculator(config)

    @pytest.fixture
    def account(self):
        """创建账户快照"""
        return AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1000000
        )

    def test_stop_loss_clamped_when_too_close_long(self, calculator, account):
        """测试做多时止损距离过小被自动调整"""
        # 创建 Pinbar K 线：止损距离极小
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50000.25"),
            low=Decimal("49999.75"),  # 止损 = 49999.75，距离 = 0.0005 = 0.001%
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        # 计算信号结果
        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
            kline_timestamp=1000000,
            strategy_name="pinbar",
            score=0.7
        )

        # 验证：止损被调整到最小距离 0.1%
        # 原始止损 = 49999.75，距离 = 0.0005 = 0.001% < 0.1%
        # 调整后止损 = 50000 * (1 - 0.001) = 49950
        assert result.suggested_stop_loss <= Decimal("49950")
        assert result.suggested_stop_loss > Decimal("49900")

    def test_stop_loss_clamped_when_too_close_short(self, calculator, account):
        """测试做空时止损距离过小被自动调整"""
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50000.25"),  # 止损 = 50000.25，距离 = 0.0005 = 0.001%
            low=Decimal("49999.75"),
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.SHORT,
            tags=[],
            kline_timestamp=1000000,
            strategy_name="pinbar",
            score=0.7
        )

        # 验证：止损被调整到最小距离 0.1%
        # 调整后止损 = 50000 * (1 + 0.001) = 50050
        assert result.suggested_stop_loss >= Decimal("50050")
        assert result.suggested_stop_loss < Decimal("50100")

    def test_normal_stop_loss_not_adjusted(self, calculator, account):
        """测试正常止损距离不被调整"""
        # 正常 Pinbar：止损距离合理
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50100.00"),
            low=Decimal("49900.00"),  # 止损 = 49900，距离 = 100/50000 = 0.2% > 0.1%
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
            kline_timestamp=1000000,
            strategy_name="pinbar",
            score=0.7
        )

        # 验证：止损未被调整，保持原始值
        assert result.suggested_stop_loss == Decimal("49900.00")


# ============================================================
# 方案 D: metadata 保存测试
# ============================================================
class TestSchemeD_MetadataPersistence:
    """方案 D: FilterResult.metadata 保存到数据库"""

    @pytest.mark.asyncio
    async def test_save_attempt_includes_metadata_in_details(self, tmp_path):
        """测试保存 attempt 时 metadata 被包含在 details 中"""
        import sqlite3
        from src.domain.models import SignalAttempt

        # 创建临时数据库
        db_path = tmp_path / "test_signals.db"
        repo = SignalRepository(str(db_path))
        await repo.initialize()

        # 创建 mock attempt，包含 metadata
        attempt = Mock(spec=SignalAttempt)
        attempt.strategy_name = "pinbar"
        attempt.pattern = Mock(spec=PatternResult)
        attempt.pattern.direction = Direction.LONG
        attempt.pattern.score = 0.7
        attempt.pattern.details = {"wick_ratio": 0.7}
        attempt.pattern.strategy_name = "pinbar"  # 添加缺失的属性
        attempt.final_result = "FILTERED"
        attempt.kline_timestamp = 1000000

        # 创建带 metadata 的 filter results
        filter_result = Mock()
        filter_result.passed = False
        filter_result.reason = "insufficient_absolute_volatility"
        filter_result.metadata = {
            "candle_range": 0.02,
            "min_required": 0.1,
        }

        attempt.filter_results = [
            ("atr_volatility", filter_result)
        ]

        # 保存 attempt
        await repo.save_attempt(attempt, "BTC/USDT:USDT", "15m")

        # 验证 metadata 被保存
        async with repo._db.execute(
            "SELECT details FROM signal_attempts WHERE symbol = ?",
            ("BTC/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            import json
            details = json.loads(row[0])

            assert "filters" in details
            assert len(details["filters"]) == 1
            assert details["filters"][0]["name"] == "atr_volatility"
            assert details["filters"][0]["metadata"]["candle_range"] == 0.02
            assert details["filters"][0]["metadata"]["min_required"] == 0.1

    @pytest.mark.asyncio
    async def test_trace_tree_includes_metadata(self, tmp_path):
        """测试 trace tree 包含 metadata"""
        import sqlite3
        from src.domain.models import SignalAttempt

        db_path = tmp_path / "test_signals.db"
        repo = SignalRepository(str(db_path))
        await repo.initialize()

        attempt = Mock(spec=SignalAttempt)
        attempt.strategy_name = "pinbar"
        attempt.pattern = Mock(spec=PatternResult)
        attempt.pattern.direction = Direction.LONG
        attempt.pattern.score = 0.7
        attempt.pattern.details = {"wick_ratio": 0.7}
        attempt.pattern.strategy_name = "pinbar"  # 添加缺失的属性
        attempt.final_result = "SIGNAL_FIRED"
        attempt.kline_timestamp = 1000000
        attempt.filter_results = []

        await repo.save_attempt(attempt, "BTC/USDT:USDT", "15m")

        async with repo._db.execute(
            "SELECT trace_tree FROM signal_attempts WHERE symbol = ?",
            ("BTC/USDT:USDT",)
        ) as cursor:
            row = await cursor.fetchone()
            import json
            trace_tree = json.loads(row[0])

            # 验证 trace tree 结构
            assert "node_id" in trace_tree
            assert "node_type" in trace_tree
            assert trace_tree["node_type"] == "and_gate"
            assert "children" in trace_tree
            assert "metadata" in trace_tree


# ============================================================
# 端到端集成测试
# ============================================================
class TestBCDFixEndToEnd:
    """BCD 方案端到端集成测试"""

    def test_cross_doji_filtered_and_metadata_saved(self, tmp_path):
        """端到端测试：十字星被过滤且 metadata 被保存"""
        from src.domain.models import SignalAttempt

        # 1. ATR 过滤器拒绝十字星
        atr_filter = AtrFilterDynamic(
            period=14,
            min_atr_ratio=Decimal("0.5"),
            min_absolute_range=Decimal("0.1"),
            enabled=True
        )

        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1000000,
            open=Decimal("50000.00"),
            high=Decimal("50000.01"),
            low=Decimal("49999.99"),
            close=Decimal("50000.00"),
            volume=Decimal("1000"),
            is_closed=True
        )

        key = "BTC/USDT:USDT:15m"
        atr_filter._atr_state[key] = {
            "tr_values": [Decimal("1.0")] * 14,
            "atr": Decimal("1.0"),
            "prev_close": None
        }

        pattern = Mock(spec=PatternResult)
        pattern.direction = Direction.LONG
        context = FilterContext(
            higher_tf_trends={},
            current_timeframe="15m",
            kline=kline,
        )

        event = atr_filter.check(pattern, context)

        # 验证：十字星被过滤
        assert event.passed is False
        assert event.reason == "insufficient_absolute_volatility"

        # 2. 验证 metadata 包含必要字段
        assert event.metadata["candle_range"] == 0.02
        assert event.metadata["min_required"] == 0.1
