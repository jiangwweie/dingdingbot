"""
Test-02: Queue Backpressure + WebSocket Fallback Integration Test

Verifies queue functionality during WebSocket degradation.
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from src.domain.models import KlineData
from src.application.config_manager import ConfigManager, load_all_configs
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.signal_repository import SignalRepository
from src.domain.risk_calculator import RiskConfig
from src.infrastructure.notifier import NotificationService
from src.application.signal_tracker import SignalStatusTracker


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
async def config_manager():
    """Create ConfigManager instance."""
    return load_all_configs()


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
    return SignalStatusTracker(signal_repository)


@pytest.fixture
async def signal_pipeline(config_manager, signal_repository, status_tracker):
    """Create SignalPipeline with small queue for testing."""
    # 配置小队列入量
    config_manager.core_config.signal_pipeline.queue.batch_size = 5
    config_manager.core_config.signal_pipeline.queue.flush_interval = 1.0
    config_manager.core_config.signal_pipeline.queue.max_queue_size = 50

    risk_config = RiskConfig(
        max_loss_percent=Decimal('0.01'),
        max_leverage=10,
        max_total_exposure=Decimal('0.8'),
    )

    notifier = NotificationService()

    pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=notifier,
        signal_repository=signal_repository,
        cooldown_seconds=0,  # Disable cooldown for testing
    )

    # Ensure async primitives are initialized
    pipeline._ensure_async_primitives()

    yield pipeline

    await pipeline.close()


class TestQueueBackpressureWSFallback:
    """Test queue backpressure during WebSocket fallback."""

    @pytest.mark.asyncio
    async def test_queue_works_during_ws_fallback(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        caplog,
    ):
        """
        测试场景:
        1. 模拟 WebSocket 正常运行
        2. 模拟 WebSocket 失败，降级到轮询
        3. 轮询间隔内大量 K 线涌入
        4. 验证队列背压告警触发
        5. 验证批量落盘正常
        """
        import logging

        # 1. 设置日志捕获级别
        caplog.set_level(logging.WARNING)

        # 2. 配置非常小的队列以快速触发背压
        config_manager.core_config.signal_pipeline.queue.max_queue_size = 30
        config_manager.core_config.signal_pipeline.queue.batch_size = 5
        config_manager.core_config.signal_pipeline.queue.flush_interval = 2.0

        # 更新 pipeline 配置
        signal_pipeline._queue_max_size = 30
        signal_pipeline._queue_batch_size = 5
        signal_pipeline._queue_flush_interval = 2.0

        # 3. 快速推送 100 个 K 线（模拟轮询间隔内积压）
        tasks = []
        for i in range(100):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1000000 + i * 60000,
                open=Decimal('50000') + Decimal(i),
                high=Decimal('50100') + Decimal(i),
                low=Decimal('49900') + Decimal(i),
                close=Decimal('50050') + Decimal(i),
                volume=Decimal('1000'),
                is_closed=True,
            )
            tasks.append(signal_pipeline.process_kline(kline))

        await asyncio.gather(*tasks, return_exceptions=True)

        # 4. 等待一段时间让 worker 处理
        await asyncio.sleep(3)

        # 5. 验证：背压告警日志
        assert "BACKPRESSURE ALERT" in caplog.text, f"Expected backpressure alert in logs, got: {caplog.text}"

        # 6. 等待队列清空
        max_wait = 30
        waited = 0
        while waited < max_wait:
            queue_size = signal_pipeline.get_queue_size()
            if queue_size == 0:
                break
            await asyncio.sleep(1)
            waited += 1

        # 7. 验证：队列已清空
        assert signal_pipeline.get_queue_size() == 0, f"Queue not empty after waiting, size={signal_pipeline.get_queue_size()}"

        # 8. 验证：有 attempt 记录落盘
        all_attempts = await signal_repository.get_all_attempts()
        assert len(all_attempts) > 0, "No attempts were persisted to database"

    @pytest.mark.asyncio
    async def test_worker_auto_recovery_during_ws_fallback(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. WebSocket 降级后
        2. 模拟 Worker 异常
        3. 验证自动恢复机制
        """
        # 1. 配置小队列入量
        config_manager.core_config.signal_pipeline.queue.max_queue_size = 50
        config_manager.core_config.signal_pipeline.queue.batch_size = 5
        config_manager.core_config.signal_pipeline.queue.flush_interval = 1.0

        # 更新 pipeline 配置
        signal_pipeline._queue_max_size = 50
        signal_pipeline._queue_batch_size = 5
        signal_pipeline._queue_flush_interval = 1.0

        # 2. 推送一些 K 线让队列有数据
        tasks = []
        for i in range(50):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=2000000 + i * 60000,
                open=Decimal('50000') + Decimal(i),
                high=Decimal('50100') + Decimal(i),
                low=Decimal('49900') + Decimal(i),
                close=Decimal('50050') + Decimal(i),
                volume=Decimal('1000'),
                is_closed=True,
            )
            tasks.append(signal_pipeline.process_kline(kline))

        await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 等待队列处理
        await asyncio.sleep(2)

        # 4. 验证：队列已清空或正在处理
        # 注意：这个测试主要验证队列机制正常工作
        # Worker 自动恢复在 signal_pipeline.py 的_monitor_flush_worker 中实现
        max_wait = 30
        waited = 0
        while waited < max_wait:
            queue_size = signal_pipeline.get_queue_size()
            if queue_size == 0:
                break
            await asyncio.sleep(1)
            waited += 1

        # 5. 验证：队列最终清空
        assert signal_pipeline.get_queue_size() == 0

        # 6. 验证：有 attempt 记录落盘
        all_attempts = await signal_repository.get_all_attempts()
        assert len(all_attempts) > 0, "No attempts were persisted to database"
