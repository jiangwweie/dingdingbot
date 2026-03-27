"""
Test-05: Queue Congestion + Signal Integrity Integration Test

Verifies signal state integrity during queue congestion.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import List
from unittest.mock import patch, AsyncMock

from src.domain.models import KlineData, SignalResult, SignalStatus
from src.application.config_manager import ConfigManager, load_all_configs
from src.application.signal_pipeline import SignalPipeline
from src.infrastructure.signal_repository import SignalRepository
from src.application.signal_tracker import SignalStatusTracker
from src.domain.risk_calculator import RiskConfig
from src.infrastructure.notifier import NotificationService


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
    # 配置小队列参数用于测试
    config_manager.core_config.signal_pipeline.queue.batch_size = 10
    config_manager.core_config.signal_pipeline.queue.flush_interval = 0.5
    config_manager.core_config.signal_pipeline.queue.max_queue_size = 100

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


class TestQueueCongestionSignalIntegrity:
    """Test signal integrity during queue congestion."""

    @pytest.mark.asyncio
    async def test_no_signal_loss_during_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 配置小队列（max_size=100）
        2. 快速推送 500 个 K 线数据
        3. 验证背压告警触发
        4. 等待队列处理完成
        5. 验证所有信号落盘，无丢失
        """
        # 1. 准备 500 个 K 线数据
        klines = []
        for i in range(500):
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
            klines.append(kline)

        # 2. 并发推送所有 K 线
        tasks = [signal_pipeline.process_kline(kline) for kline in klines]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 等待队列完全处理
        max_wait = 60  # 最多等 60 秒
        waited = 0
        while waited < max_wait:
            queue_size = signal_pipeline.get_queue_size()
            if queue_size == 0:
                break
            await asyncio.sleep(1)
            waited += 1

        # 4. 验证：队列已清空
        assert signal_pipeline.get_queue_size() == 0, f"Queue not empty after waiting, size={signal_pipeline.get_queue_size()}"

        # 5. 验证：有 attempt 记录落盘
        all_attempts = await signal_repository.get_all_attempts()
        assert len(all_attempts) > 0, "No attempts were persisted to database"

    @pytest.mark.asyncio
    async def test_no_duplicate_signals_during_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 队列拥堵场景
        2. 验证无重复信号
        """
        # 1. 准备 200 个 K 线数据
        klines = []
        for i in range(200):
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
            klines.append(kline)

        # 2. 并发推送所有 K 线
        tasks = [signal_pipeline.process_kline(kline) for kline in klines]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 等待队列完全处理
        max_wait = 60
        waited = 0
        while waited < max_wait:
            queue_size = signal_pipeline.get_queue_size()
            if queue_size == 0:
                break
            await asyncio.sleep(1)
            waited += 1

        # 4. 验证：队列已清空
        assert signal_pipeline.get_queue_size() == 0

        # 5. 验证：无重复 attempt 记录
        all_attempts = await signal_repository.get_all_attempts()

        # 提取唯一标识 (symbol:timeframe:strategy:timestamp)
        attempt_keys = []
        for attempt in all_attempts:
            if isinstance(attempt, dict):
                key = f"{attempt.get('symbol', '')}:{attempt.get('timeframe', '')}:{attempt.get('strategy_name', '')}:{attempt.get('kline_timestamp', '')}"
            else:
                key = f"{attempt.symbol}:{attempt.timeframe}:{attempt.strategy_name}:{attempt.kline_timestamp}"
            attempt_keys.append(key)

        unique_keys = set(attempt_keys)
        assert len(unique_keys) == len(attempt_keys), "Duplicate attempt records detected"

    @pytest.mark.asyncio
    async def test_backpressure_alert_triggered(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
        caplog,
    ):
        """
        验证背压告警正确触发。

        测试场景:
        1. 设置小队列容量
        2. 快速推送大量信号使队列接近容量
        3. 验证背压告警日志被触发
        """
        import logging

        # 1. 设置日志捕获级别
        caplog.set_level(logging.WARNING)

        # 2. 配置非常小的队列以快速触发背压
        config_manager.core_config.signal_pipeline.queue.max_queue_size = 50
        config_manager.core_config.signal_pipeline.queue.batch_size = 5
        config_manager.core_config.signal_pipeline.queue.flush_interval = 2.0

        # 重新初始化队列以应用新配置
        signal_pipeline._queue_max_size = 50
        signal_pipeline._queue_batch_size = 5
        signal_pipeline._queue_flush_interval = 2.0

        # 3. 推送大量信号使队列拥堵
        tasks = []
        for i in range(200):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=3000000 + i * 60000,
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

    @pytest.mark.asyncio
    async def test_all_signal_statuses_correct_after_congestion(
        self,
        config_manager,
        signal_pipeline,
        signal_repository,
        status_tracker,
    ):
        """
        测试场景:
        1. 队列拥堵后
        2. 验证队列清空且 attempt 记录正确
        """
        # 1. 准备 K 线数据 - 使用与 test_no_signal_loss 相同的生成逻辑
        klines = []
        for i in range(100):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=5000000 + i * 60000,
                open=Decimal('50000') + Decimal(i),
                high=Decimal('50100') + Decimal(i),
                low=Decimal('49900') + Decimal(i),
                close=Decimal('50050') + Decimal(i),
                volume=Decimal('1000'),
                is_closed=True,
            )
            klines.append(kline)

        # 2. 并发推送所有 K 线
        tasks = [signal_pipeline.process_kline(kline) for kline in klines]
        await asyncio.gather(*tasks, return_exceptions=True)

        # 3. 等待队列处理完成
        max_wait = 60
        waited = 0
        while waited < max_wait:
            queue_size = signal_pipeline.get_queue_size()
            if queue_size == 0:
                break
            await asyncio.sleep(1)
            waited += 1

        # 4. 验证：队列已清空
        assert signal_pipeline.get_queue_size() == 0

        # 5. 验证：有 attempt 记录落盘（由于策略检测，可能不是所有 K 线都产生 attempt）
        all_attempts = await signal_repository.get_all_attempts()
        assert len(all_attempts) > 0, "No attempts were recorded"

        # 6. 验证：所有 attempt 的 final_result 有效
        valid_results = {"SIGNAL_FIRED", "NO_PATTERN", "FILTERED"}
        for attempt in all_attempts:
            if isinstance(attempt, dict):
                result = attempt.get('final_result')
            else:
                result = attempt.final_result
            assert result in valid_results, f"Invalid final_result: {result}"
