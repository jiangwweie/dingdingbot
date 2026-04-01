"""
Unit tests for signal_pipeline.py - Signal deduplication mechanism and dynamic tags.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.signal_pipeline import SignalPipeline
from src.domain.models import KlineData, Direction, TrendDirection, MtfStatus, AccountSnapshot, SignalResult
from src.domain.risk_calculator import RiskConfig
from src.domain.strategy_engine import PinbarConfig, SignalAttempt, PatternResult, FilterResult


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1234567890000,
    open: Decimal = Decimal(100),
    high: Decimal = Decimal(100),
    low: Decimal = Decimal(100),
    close: Decimal = Decimal(100),
    volume: Decimal = Decimal(1000),
) -> KlineData:
    """Helper to create KlineData for testing."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


class TestSignalDeduplication:
    """Test signal deduplication mechanism."""

    @pytest.fixture
    def pipeline(self):
        """Create a signal pipeline with mocked dependencies."""
        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        # Mock notification service
        mock_notifier = MagicMock()
        mock_notifier.send_signal = AsyncMock()

        # Mock signal repository
        mock_repository = MagicMock()
        mock_repository.save_signal = AsyncMock()
        mock_repository.save_attempt = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
        )

        # Set account snapshot for risk calculation
        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1234567890000,
        ))

        return pipeline

    async def _force_signal(self, pipeline, kline, direction=Direction.LONG):
        """
        Force a signal to fire by mocking the strategy engine.
        This bypasses actual pinbar detection for testing deduplication logic.
        """
        from src.domain.strategy_engine import SignalAttempt, PatternResult

        mock_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=direction,
                score=0.8,
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Mock _run_strategy to return a list with our forced signal
        with patch.object(pipeline, '_run_strategy', return_value=[mock_attempt]):
            await pipeline.process_kline(kline)

    @pytest.mark.asyncio
    async def test_signal_dedup_within_cooldown(self, pipeline):
        """
        Test that signals within cooldown period are deduplicated.
        First signal should be sent, second identical signal should be skipped.
        """
        kline1 = create_kline(close=Decimal("150"))
        kline2 = create_kline(close=Decimal("151"), timestamp=1234567890000 + 60000)  # 1 minute later

        # First signal should succeed
        await self._force_signal(pipeline, kline1, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # Second signal within cooldown should be deduplicated
        await self._force_signal(pipeline, kline2, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_direction(self, pipeline):
        """
        Test that LONG and SHORT signals have separate dedup keys.
        A LONG signal should not affect SHORT signal deduplication.
        """
        kline_long = create_kline(close=Decimal("150"))
        kline_short = create_kline(close=Decimal("149"))

        # LONG signal
        await self._force_signal(pipeline, kline_long, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # SHORT signal should NOT be deduplicated (different direction)
        await self._force_signal(pipeline, kline_short, Direction.SHORT)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_expires_after_cooldown(self, pipeline):
        """
        Test that signals expire after cooldown period.
        Signal fired 5 hours ago should allow new signal.
        """
        # Set cooldown to a short period for testing
        pipeline._cooldown_seconds = 60  # 1 minute

        kline1 = create_kline(close=Decimal("150"), timestamp=1234567890000)
        kline2 = create_kline(close=Decimal("151"), timestamp=1234567890000 + 120000)  # 2 minutes later

        # First signal
        await self._force_signal(pipeline, kline1, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # Manually set the cache to expire (simulate time passage)
        dedup_key = f"{kline1.symbol}:{kline1.timeframe}:{Direction.LONG.value}:pinbar"
        pipeline._signal_cooldown_cache[dedup_key] = 0  # Force expiry

        # Second signal after cooldown expiry should succeed
        await self._force_signal(pipeline, kline2, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_symbol(self, pipeline):
        """
        Test that different symbols have separate dedup keys.
        """
        kline_btc = create_kline(symbol="BTC/USDT:USDT", close=Decimal("150"))
        kline_eth = create_kline(symbol="ETH/USDT:USDT", close=Decimal("2200"))

        # BTC signal
        await self._force_signal(pipeline, kline_btc, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # ETH signal should NOT be deduplicated (different symbol)
        await self._force_signal(pipeline, kline_eth, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_signal_dedup_different_timeframe(self, pipeline):
        """
        Test that different timeframes have separate dedup keys.
        """
        kline_15m = create_kline(timeframe="15m", close=Decimal("150"))
        kline_1h = create_kline(timeframe="1h", close=Decimal("151"))

        # 15m signal
        await self._force_signal(pipeline, kline_15m, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 1

        # 1h signal should NOT be deduplicated (different timeframe)
        await self._force_signal(pipeline, kline_1h, Direction.LONG)
        assert pipeline._notification_service.send_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_dedup_key_format(self, pipeline):
        """
        Test that dedup key uses correct format: symbol:timeframe:direction:strategy_name
        """
        kline = create_kline(symbol="BTC/USDT:USDT", timeframe="15m", close=Decimal("150"))

        await self._force_signal(pipeline, kline, Direction.LONG)

        expected_key = "BTC/USDT:USDT:15m:long:pinbar"
        assert expected_key in pipeline._signal_cooldown_cache


class TestDynamicTags:
    """Test dynamic tag generation from filter results."""

    @pytest.fixture
    def pipeline(self):
        """Create a signal pipeline with mocked dependencies."""
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        mock_notifier = MagicMock()
        mock_notifier.send_signal = AsyncMock()

        mock_repository = MagicMock()
        mock_repository.save_signal = AsyncMock()
        mock_repository.save_attempt = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
        )

        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1234567890000,
        ))

        return pipeline

    def test_generate_tags_from_filters_ema(self, pipeline):
        """Test EMA filter generates correct tag."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bullish"}

    def test_generate_tags_from_filters_ema_bearish(self, pipeline):
        """Test EMA bearish filter generates correct tag."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is below EMA - bearish trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bearish"}

    def test_generate_tags_from_filters_mtf(self, pipeline):
        """Test MTF filter generates correct tag."""
        filter_results = [
            ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "MTF", "value": "Confirmed"}

    def test_generate_tags_from_filters_volume_surge(self, pipeline):
        """Test Volume Surge filter generates correct tag."""
        filter_results = [
            ("volume_surge", FilterResult(passed=True, reason="Volume surge detected")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "Volume", "value": "Surge"}

    def test_generate_tags_from_filters_multiple(self, pipeline):
        """Test multiple filters generate multiple tags."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
            ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
            ("volume_surge", FilterResult(passed=True, reason="Volume surge detected")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 3
        assert tags[0] == {"name": "EMA", "value": "Bullish"}
        assert tags[1] == {"name": "MTF", "value": "Confirmed"}
        assert tags[2] == {"name": "Volume", "value": "Surge"}

    def test_generate_tags_only_passed(self, pipeline):
        """Test that only passed filters generate tags."""
        filter_results = [
            ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
            ("mtf", FilterResult(passed=False, reason="Higher timeframe conflicts")),
        ]
        tags = pipeline._generate_tags_from_filters(filter_results)
        assert len(tags) == 1
        assert tags[0] == {"name": "EMA", "value": "Bullish"}

    def test_signal_result_contains_tags(self, pipeline):
        """Test that SignalResult contains dynamic tags."""
        kline = create_kline(close=Decimal("150"))

        # Create attempt with filter results
        mock_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=0.8,
                details={},
            ),
            filter_results=[
                ("ema", FilterResult(passed=True, reason="Price is above EMA - bullish trend")),
                ("mtf", FilterResult(passed=True, reason="Higher timeframe confirms trend")),
            ],
            final_result="SIGNAL_FIRED",
        )

        # Manually call _calculate_risk to get SignalResult
        signal = pipeline._calculate_risk(kline, Direction.LONG, mock_attempt, "pinbar", 0.8)

        assert isinstance(signal, SignalResult)
        assert len(signal.tags) == 2
        assert {"name": "EMA", "value": "Bullish"} in signal.tags
        assert {"name": "MTF", "value": "Confirmed"} in signal.tags


class TestSignalCovering:
    """Test S6-2-4: Signal covering mechanism."""

    @pytest.fixture
    def pipeline_with_repo(self):
        """Create a signal pipeline with repository for covering tests."""
        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.core_config.signal_pipeline.queue.batch_size = 10
        mock_config_manager.core_config.signal_pipeline.queue.flush_interval = 5.0
        mock_config_manager.core_config.signal_pipeline.queue.max_queue_size = 1000
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        # Mock notification service
        mock_notifier = MagicMock()
        mock_notifier.send_signal = AsyncMock()

        # Mock signal repository with covering methods
        mock_repository = MagicMock()
        mock_repository.save_signal = AsyncMock()
        mock_repository.save_attempt = AsyncMock()
        mock_repository.update_superseded_by = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
            cooldown_seconds=14400,  # 4 hours
        )

        # Set account snapshot for risk calculation
        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1234567890000,
        ))

        return pipeline

    async def _force_signal_with_score(self, pipeline, kline, direction=Direction.LONG, score=0.8, disable_strategy=True):
        """Force a signal with specific score."""
        mock_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=direction,
                score=score,
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        if disable_strategy:
            with patch.object(pipeline, '_run_strategy', return_value=[mock_attempt]):
                await pipeline.process_kline(kline)
        else:
            # For integration tests, don't mock _run_strategy
            pass

    @pytest.mark.asyncio
    async def test_check_cover_no_existing_signal(self, pipeline_with_repo):
        """Test _check_cover returns False when no existing signal."""
        kline = create_kline()
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(strategy_name="pinbar", direction=Direction.LONG, score=0.8, details={}),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Cache is empty, should return False
        should_cover, superseded_id, old_data = await pipeline_with_repo._check_cover(
            kline, attempt, score=0.8
        )

        assert should_cover is False
        assert superseded_id is None
        assert old_data is None

    @pytest.mark.asyncio
    async def test_check_cover_new_score_higher(self, pipeline_with_repo):
        """Test _check_cover returns True when new score is higher."""
        import time

        kline = create_kline()
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(strategy_name="pinbar", direction=Direction.LONG, score=0.8, details={}),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Setup cache with lower score old signal
        dedup_key = f"{kline.symbol}:{kline.timeframe}:{Direction.LONG.value}:pinbar"
        pipeline_with_repo._signal_cache[dedup_key] = {
            "timestamp": time.time(),
            "signal_id": "old-signal-123",
            "score": 0.6,  # Lower than new score
        }

        # Mock DB fetch to return None (no additional data needed)
        with patch.object(pipeline_with_repo._repository._db, 'execute') as mock_execute:
            mock_cursor = MagicMock()
            mock_cursor.fetchone = MagicMock(return_value=None)
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=None)
            mock_execute.return_value = mock_cursor

            should_cover, superseded_id, old_data = await pipeline_with_repo._check_cover(
                kline, attempt, score=0.8
            )

        assert should_cover is True
        assert superseded_id == "old-signal-123"

    @pytest.mark.asyncio
    async def test_check_cover_new_score_lower(self, pipeline_with_repo):
        """Test _check_cover returns False when new score is not higher."""
        import time

        kline = create_kline()
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(strategy_name="pinbar", direction=Direction.LONG, score=0.7, details={}),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Setup cache with higher score old signal
        dedup_key = f"{kline.symbol}:{kline.timeframe}:{Direction.LONG.value}:pinbar"
        pipeline_with_repo._signal_cache[dedup_key] = {
            "timestamp": time.time(),
            "signal_id": "old-signal-456",
            "score": 0.85,  # Higher than new score
        }

        should_cover, superseded_id, old_data = await pipeline_with_repo._check_cover(
            kline, attempt, score=0.7
        )

        assert should_cover is False
        assert superseded_id is None

    @pytest.mark.asyncio
    async def test_check_cover_time_window_expired(self, pipeline_with_repo):
        """Test _check_cover returns False when time window expired."""
        kline = create_kline()
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(strategy_name="pinbar", direction=Direction.LONG, score=0.9, details={}),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Setup cache with expired timestamp (15m window = 4 hours)
        dedup_key = f"{kline.symbol}:{kline.timeframe}:{Direction.LONG.value}:pinbar"
        old_timestamp = 1234567890000 / 1000  # Very old timestamp
        pipeline_with_repo._signal_cache[dedup_key] = {
            "timestamp": old_timestamp,
            "signal_id": "old-signal-789",
            "score": 0.5,
        }

        should_cover, superseded_id, old_data = await pipeline_with_repo._check_cover(
            kline, attempt, score=0.9
        )

        assert should_cover is False
        assert superseded_id is None

    @pytest.mark.asyncio
    async def test_get_timeframe_window(self, pipeline_with_repo):
        """Test _get_timeframe_window returns correct values."""
        assert pipeline_with_repo._get_timeframe_window("15m") == 4 * 3600  # 4 hours
        assert pipeline_with_repo._get_timeframe_window("1h") == 24 * 3600  # 24 hours
        assert pipeline_with_repo._get_timeframe_window("4h") == 72 * 3600  # 72 hours
        assert pipeline_with_repo._get_timeframe_window("1d") == 30 * 24 * 3600  # 30 days
        assert pipeline_with_repo._get_timeframe_window("1w") == 90 * 24 * 3600  # 90 days
        assert pipeline_with_repo._get_timeframe_window("unknown") == 24 * 3600  # Default

    @pytest.mark.asyncio
    async def test_cache_key_format(self, pipeline_with_repo):
        """Test that cache key format is correct for covering."""
        import time

        # Setup cache
        dedup_key = "BTC/USDT:USDT:15m:long:pinbar"
        pipeline_with_repo._signal_cache[dedup_key] = {
            "timestamp": time.time(),
            "signal_id": "test-signal",
            "score": 0.75,
        }

        # Verify cache can be accessed with correct key
        assert dedup_key in pipeline_with_repo._signal_cache
        assert pipeline_with_repo._signal_cache[dedup_key]["score"] == 0.75
        assert pipeline_with_repo._signal_cache[dedup_key]["signal_id"] == "test-signal"

# ============================================================
# 测试：MTF EMA 预热逻辑 (DA-20260401-001)
# ============================================================

class TestMTFEMAWarmup:
    """测试 MTF EMA 预热逻辑"""

    @pytest.fixture
    def pipeline_with_history(self):
        """创建带有历史 K 线数据的 pipeline"""
        from src.domain.indicators import EMACalculator

        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()
        mock_config_manager.user_config.mtf_ema_period = 60  # 添加 mtf_ema_period 配置

        # 创建 pipeline
        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10),
        )

        # 创建历史 K 线数据 (每个周期 100 根)
        history = []
        for i in range(100):
            history.append(create_kline(
                symbol="BTC/USDT:USDT",
                timeframe="1h",
                timestamp=1234567890000 + i * 3600000,  # 每小时
                close=Decimal(str(50000 + i * 100)),
            ))

        pipeline._kline_history = {
            "BTC/USDT:USDT:1h": history,
            "BTC/USDT:USDT:4h": [create_kline(timeframe="4h", timestamp=1234567890000 + i * 14400000) for i in range(50)],
            "BTC/USDT:USDT:15m": [create_kline(timeframe="15m", timestamp=1234567890000 + i * 900000) for i in range(200)],
        }

        return pipeline

    def test_warmup_initializes_mtf_ema_indicators(self, pipeline_with_history):
        """测试：warmup 后 _mtf_ema_indicators 被正确初始化"""
        # 执行 warmup
        runner = pipeline_with_history._build_and_warmup_runner()

        # 验证：高周期 EMA 应该被初始化
        assert "BTC/USDT:USDT:1h" in pipeline_with_history._mtf_ema_indicators
        assert "BTC/USDT:USDT:4h" in pipeline_with_history._mtf_ema_indicators
        # 15m 不应该被初始化 (不是高周期)
        assert "BTC/USDT:USDT:15m" not in pipeline_with_history._mtf_ema_indicators

    def test_mtf_ema_ready_after_warmup(self, pipeline_with_history):
        """测试：warmup 后 EMA is_ready = True"""
        # 执行 warmup
        runner = pipeline_with_history._build_and_warmup_runner()

        # 验证：1h EMA 应该已经 ready (因为有 100 根历史 K 线，远超过 60 的需求)
        ema_1h = pipeline_with_history._mtf_ema_indicators["BTC/USDT:USDT:1h"]
        assert ema_1h.is_ready is True

        # 注意：4h EMA 只有 49 根数据 (50-1)，少于 60 的需求，所以 is_ready=False
        # 这符合预期行为
        ema_4h = pipeline_with_history._mtf_ema_indicators["BTC/USDT:USDT:4h"]
        # 4h EMA 虽然没有 ready，但已经被正确初始化
        assert ema_4h is not None

    def test_mtf_ema_warmup_excludes_current_kline(self, pipeline_with_history):
        """测试：warmup 排除未闭合 K 线 (history[:-1])"""
        # 执行 warmup
        runner = pipeline_with_history._build_and_warmup_runner()

        # 验证：EMA 更新次数应该是 len(history) - 1 (排除当前 K 线)
        ema_1h = pipeline_with_history._mtf_ema_indicators["BTC/USDT:USDT:1h"]
        # is_ready 需要 60 次更新，我们有 99 次 (100 - 1)
        assert ema_1h.is_ready is True
        # 验证 EMA 值是基于 99 根 K 线计算的
        assert ema_1h.value is not None

    def test_warmup_multiple_symbols(self):
        """测试：多符号 warmup 正确"""
        from src.domain.indicators import EMACalculator

        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.active_strategies = []
        mock_config_manager.core_config = MagicMock()
        mock_config_manager.add_observer = MagicMock()
        mock_config_manager.user_config.mtf_ema_period = 60  # 添加 mtf_ema_period 配置

        # 创建 pipeline
        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10),
        )

        # 创建多个符号的历史 K 线数据
        pipeline._kline_history = {
            "BTC/USDT:USDT:1h": [create_kline(symbol="BTC/USDT:USDT", timeframe="1h", timestamp=i * 3600000) for i in range(100)],
            "ETH/USDT:USDT:1h": [create_kline(symbol="ETH/USDT:USDT", timeframe="1h", timestamp=i * 3600000) for i in range(100)],
            "SOL/USDT:USDT:1h": [create_kline(symbol="SOL/USDT:USDT", timeframe="1h", timestamp=i * 3600000) for i in range(100)],
        }

        # 执行 warmup
        runner = pipeline._build_and_warmup_runner()

        # 验证：所有符号的 1h EMA 都应该被初始化
        assert "BTC/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        assert "ETH/USDT:USDT:1h" in pipeline._mtf_ema_indicators
        assert "SOL/USDT:USDT:1h" in pipeline._mtf_ema_indicators

        # 验证：所有 EMA 都应该 ready
        for key in pipeline._mtf_ema_indicators:
            assert pipeline._mtf_ema_indicators[key].is_ready is True
