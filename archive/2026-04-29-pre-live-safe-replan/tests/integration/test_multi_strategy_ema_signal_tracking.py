"""
Test-06: Multi-Strategy + EMA Cache + Signal Tracking Integration Test

Verifies independent signal tracking when multiple strategies share EMA cache.
"""
import pytest
import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.domain.models import KlineData, SignalStatus
from src.domain.indicators import EMACache
from src.application.config_manager import ConfigManager, load_all_configs
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.signal_repository import SignalRepository
from src.application.signal_tracker import SignalStatusTracker


@pytest.fixture
def config_manager():
    """Load real config for integration testing."""
    return load_all_configs()


@pytest.fixture
async def ema_cache():
    """Create EMACache instance."""
    cache = EMACache(ttl_seconds=3600, max_size=1000)
    yield cache
    await cache.clear()


@pytest.fixture
async def signal_repository():
    """Create in-memory SignalRepository."""
    repository = SignalRepository(":memory:")
    await repository.initialize()
    yield repository
    await repository.close()


@pytest.fixture
async def status_tracker(signal_repository):
    """Create SignalStatusTracker."""
    # Note: We use a separate repository instance for the tracker
    # to avoid conflicts with the pipeline's repository
    repo = SignalRepository(":memory:")
    await repo.initialize()
    tracker = SignalStatusTracker(repo)
    yield tracker
    await repo.close()


@pytest.fixture
async def signal_pipeline(config_manager, signal_repository):
    """Create SignalPipeline instance."""
    from src.domain.risk_calculator import RiskConfig
    from src.infrastructure.notifier import NotificationService

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_leverage=10,
    )

    # Create mock notifier
    mock_notifier = AsyncMock()
    mock_notifier.send_signal = AsyncMock()

    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=mock_notifier,
        signal_repository=signal_repository,
        cooldown_seconds=300,
    )

    yield pipeline

    await pipeline.close()


def create_test_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1000000,
    price_offset: Decimal = Decimal('0'),
) -> KlineData:
    """Helper to create test kline data."""
    base_price = Decimal('50000') + price_offset
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=base_price,
        high=base_price + Decimal('100'),
        low=base_price - Decimal('100'),
        close=base_price + Decimal('50'),
        volume=Decimal('1000'),
        is_closed=True,
    )


def create_test_signal(
    signal_id: str,
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1000000,
    strategy_name: str = "test",
) -> 'SignalResult':
    """Helper to create test SignalResult."""
    from src.domain.models import SignalResult, Direction
    return SignalResult(
        symbol=symbol,
        timeframe=timeframe,
        direction=Direction.LONG,
        entry_price=Decimal('50000'),
        suggested_stop_loss=Decimal('49000'),
        suggested_position_size=Decimal('0.1'),
        current_leverage=10,
        tags=[],
        risk_reward_info="1:2",
        strategy_name=strategy_name,
        score=0.8,
        kline_timestamp=timestamp,
    )


class TestMultiStrategyEMASignalTracking:
    """Test multi-strategy with shared EMA cache and signal tracking."""

    @pytest.mark.asyncio
    async def test_ema_cache_shared_across_strategies(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 配置多个策略，都使用 EMA60 过滤器
        2. 推送足够 K 线数据让 EMA 就绪
        3. 验证 EMA 缓存正常工作
        4. 验证每个策略可以共享同一个 EMA 实例
        """
        # 1. 清空缓存
        await ema_cache.clear()

        # 2. 获取 EMA 计算器（模拟多策略共享）
        ema_60 = await ema_cache.get_or_create("BTC/USDT:USDT", "15m", 60)

        # 3. 推送足够的 K 线数据让 EMA 就绪（需要至少 60 个数据点）
        for i in range(60):
            kline = create_test_kline(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1000000 + i * 60000,
                price_offset=Decimal(str(i * 10)),
            )
            ema_60.update(kline.close)

        # 4. 验证：EMA 已就绪
        assert ema_60.is_ready is True

        # 5. 验证：缓存统计正确
        stats = await ema_cache.get_stats()
        assert stats['size'] >= 1

        # 6. 验证：访问计数正确
        for key, entry in stats['entries'].items():
            assert entry['period'] == 60
            assert entry['is_ready'] is True
            assert entry['access_count'] >= 1

    @pytest.mark.asyncio
    async def test_signals_tracked_independently(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 多个策略生成多个信号
        2. 验证每个信号独立跟踪
        3. 更新一个信号状态，其他不受影响
        """
        # 1. 生成多个信号
        tracked_ids = []
        for i in range(5):
            # 创建模拟 SignalResult
            signal = create_test_signal(
                signal_id=f"signal-{i}",
                timestamp=1000000 + i * 60000,
                strategy_name=f"strategy-{i}"
            )

            # 开始跟踪（track_signal 会生成自己的 ID）
            tracked_id = await status_tracker.track_signal(signal)
            tracked_ids.append(tracked_id)

        # 2. 验证：所有信号初始状态为 GENERATED
        for tracked_id in tracked_ids:
            track = await status_tracker.get_signal_status(tracked_id)
            assert track is not None
            assert track.status == SignalStatus.GENERATED

        # 3. 更新信号 1 为 FILLED
        await status_tracker.update_status(
            tracked_ids[0],
            SignalStatus.FILLED,
            filled_price=Decimal('51000'),
        )

        # 4. 更新信号 2 为 CANCELLED
        await status_tracker.update_status(
            tracked_ids[1],
            SignalStatus.CANCELLED,
            reason="测试取消",
        )

        # 5. 验证：信号 1 状态为 FILLED
        track1 = await status_tracker.get_signal_status(tracked_ids[0])
        assert track1.status == SignalStatus.FILLED
        assert track1.filled_price == Decimal('51000')

        # 6. 验证：信号 2 状态为 CANCELLED
        track2 = await status_tracker.get_signal_status(tracked_ids[1])
        assert track2.status == SignalStatus.CANCELLED
        assert track2.cancel_reason == "测试取消"

        # 7. 验证：其他信号状态不变
        for i in range(2, len(tracked_ids)):
            track = await status_tracker.get_signal_status(tracked_ids[i])
            assert track.status == SignalStatus.GENERATED

    @pytest.mark.asyncio
    async def test_ema_cache_stats_correct(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 多策略共享缓存
        2. 验证缓存统计正确
        3. 访问计数符合预期
        """
        # 1. 清空缓存
        await ema_cache.clear()

        # 2. 获取 EMA 并推送数据
        ema_60 = await ema_cache.get_or_create("BTC/USDT:USDT", "15m", 60)
        kline = create_test_kline()

        # 推送足够数据让 EMA 就绪
        for _ in range(60):
            ema_60.update(kline.close)

        # 3. 验证缓存统计
        stats = await ema_cache.get_stats()

        assert stats['size'] >= 1
        assert stats['max_size'] == 1000
        assert stats['ttl_seconds'] == 3600

        # 4. 验证条目信息
        for key, entry in stats['entries'].items():
            assert 'period' in entry
            assert 'is_ready' in entry
            assert 'access_count' in entry
            assert 'age_seconds' in entry
            assert entry['access_count'] >= 1

    @pytest.mark.asyncio
    async def test_multiple_ema_periods_cached(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 多个不同周期的 EMA 同时缓存
        2. 验证每个周期独立缓存
        3. 验证缓存隔离正确
        """
        # 1. 清空缓存
        await ema_cache.clear()

        # 2. 创建多个不同周期的 EMA
        ema_20 = await ema_cache.get_or_create("BTC/USDT:USDT", "15m", 20)
        ema_60 = await ema_cache.get_or_create("BTC/USDT:USDT", "15m", 60)
        ema_200 = await ema_cache.get_or_create("BTC/USDT:USDT", "15m", 200)

        # 3. 更新数据 - 推送足够数据让所有 EMA 就绪
        kline = create_test_kline()
        for _ in range(200):  # 需要最多 200 个数据点
            ema_20.update(kline.close)
            ema_60.update(kline.close)
            ema_200.update(kline.close)

        # 4. 验证：所有 EMA 都已就绪
        assert ema_20.is_ready
        assert ema_60.is_ready
        assert ema_200.is_ready

        # 5. 验证：缓存统计正确
        stats = await ema_cache.get_stats()
        assert stats['size'] == 3

        # 6. 验证：每个周期的 EMA 独立
        periods = set()
        for key, entry in stats['entries'].items():
            periods.add(entry['period'])

        assert periods == {20, 60, 200}

    @pytest.mark.asyncio
    async def test_signal_status_list_filter(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        ema_cache,
    ):
        """
        测试场景:
        1. 创建多个不同状态的信号
        2. 验证按状态过滤正确
        """
        # 1. 创建多个信号
        generated_ids = []
        filled_ids = []

        # 创建 GENERATED 信号
        for i in range(3):
            signal = create_test_signal(
                signal_id=f"gen-signal-{i}",
                timestamp=1000000 + i * 60000,
                strategy_name="test"
            )
            tracked_id = await status_tracker.track_signal(signal)
            generated_ids.append(tracked_id)

        # 创建 FILLED 信号
        for i in range(2):
            signal = create_test_signal(
                signal_id=f"filled-signal-{i}",
                timestamp=1000000 + i * 60000,
                strategy_name="test"
            )
            tracked_id = await status_tracker.track_signal(signal)
            await status_tracker.update_status(tracked_id, SignalStatus.FILLED, filled_price=Decimal('51000'))
            filled_ids.append(tracked_id)

        # 2. 验证：列出所有信号
        all_tracks = await status_tracker.list_statuses(limit=50)
        assert len(all_tracks) == 5

        # 3. 验证：按状态过滤 - GENERATED
        generated_tracks = await status_tracker.list_statuses(status_filter=SignalStatus.GENERATED, limit=50)
        assert len(generated_tracks) == 3
        generated_track_ids = [t.signal_id for t in generated_tracks]
        for signal_id in generated_ids:
            assert signal_id in generated_track_ids

        # 4. 验证：按状态过滤 - FILLED
        filled_tracks = await status_tracker.list_statuses(status_filter=SignalStatus.FILLED, limit=50)
        assert len(filled_tracks) == 2
        filled_track_ids = [t.signal_id for t in filled_tracks]
        for signal_id in filled_ids:
            assert signal_id in filled_track_ids
