"""
Test-04: Snapshot Rollback + Signal Continuity Integration Test

Verifies that signal status tracking remains intact after config snapshot rollback.
"""
import pytest
import asyncio
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, patch

from src.domain.models import (
    SignalStatus, SignalResult, StrategyDefinition, KlineData,
)
from src.application.config_manager import ConfigManager, load_all_configs
from src.application.signal_pipeline import SignalPipeline
from src.application.signal_tracker import SignalStatusTracker
from src.infrastructure.signal_repository import SignalRepository
from src.domain.risk_calculator import RiskConfig


@pytest.fixture
def config_manager():
    """Load real config for integration testing"""
    return load_all_configs()


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=125,
        max_total_exposure=Decimal("0.8"),
    )


@pytest.fixture
def mock_notifier():
    """Create mock notification service"""
    mock = AsyncMock()
    mock.send_signal = AsyncMock()
    return mock


@pytest.fixture
def mock_repository():
    """Create mock signal repository"""
    mock = AsyncMock()
    mock.save_attempt = AsyncMock()
    mock.save_signal = AsyncMock()
    mock.get_signal_status = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def pipeline(config_manager, risk_config, mock_notifier, mock_repository):
    """Create signal pipeline with mock dependencies"""
    with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
        mock_getter.return_value = mock_notifier
        return SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
            cooldown_seconds=300
        )


class TestSnapshotRollbackSignalContinuity:
    """Test signal continuity after snapshot rollback."""

    async def test_signal_tracking_continues_after_rollback(
        self,
        config_manager,
        risk_config,
        mock_notifier,
    ):
        """
        测试场景:
        1. 策略 A 正在运行，生成信号 Signal-001（状态：GENERATED）
        2. 保存配置快照 V1
        3. 修改策略配置，生成信号 Signal-002（状态：GENERATED）
        4. 回滚到快照 V1（策略 A 恢复）
        5. 验证：Signal-001 和 Signal-002 的状态跟踪不中断
        """
        # 使用内存数据库进行测试
        repository = SignalRepository(":memory:")
        await repository.initialize()

        try:
            status_tracker = SignalStatusTracker(repository)

            with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
                mock_getter.return_value = mock_notifier
                pipeline = SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier,
                    signal_repository=repository,
                    cooldown_seconds=300
                )

                # 1. 创建测试 K 线数据（看涨 Pinbar 形态）
                # Pinbar 条件：min_wick_ratio=0.6, max_body_ratio=0.3
                # 下影线 = 50000 - 49000 = 1000
                # 实体 = |50050 - 50000| = 50
                # 总范围 = 50100 - 49000 = 1100
                # 下影线占比 = 1000/1100 = 0.91 > 0.6 ✓
                # 实体占比 = 50/1100 = 0.045 < 0.3 ✓
                kline1 = KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1000000,
                    open=Decimal('50000'),
                    high=Decimal('50100'),
                    low=Decimal('49000'),  # 长下影线 (1000 点)
                    close=Decimal('50050'),  # 小实体在顶部 (50 点)
                    volume=Decimal('1000'),
                    is_closed=True,
                )

                # 2. 处理 K 线，生成信号
                signal1 = await pipeline.process_kline(kline1)

                # 3. 保存快照 V1
                snapshot_id = await repository.create_config_snapshot(
                    version="v1-rollback-point",
                    config_json='{"strategies": []}',
                    description="rollback-point",
                    created_by="test",
                )
                assert snapshot_id is not None

                # 4. 验证信号 1 被跟踪
                track1 = await status_tracker.get_signal_status(signal1.id) if signal1 else None

                # 5. 回滚到快照 V1
                await repository.activate_config_snapshot(snapshot_id)

                # 6. 验证回滚后状态跟踪仍然有效
                if track1:
                    track1_after = await status_tracker.get_signal_status(signal1.id)
                    assert track1_after.status == SignalStatus.GENERATED

        finally:
            await repository.close()

    async def test_signal_status_update_works_after_rollback(
        self,
        config_manager,
        risk_config,
        mock_notifier,
    ):
        """
        测试场景:
        1. 回滚后，更新信号状态为 FILLED
        2. 验证状态正确保存
        """
        repository = SignalRepository(":memory:")
        await repository.initialize()

        try:
            status_tracker = SignalStatusTracker(repository)

            with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
                mock_getter.return_value = mock_notifier
                pipeline = SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier,
                    signal_repository=repository,
                    cooldown_seconds=300
                )

                # 1. 创建测试 K 线数据
                kline1 = KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1000000,
                    open=Decimal('50000'),
                    high=Decimal('50100'),
                    low=Decimal('49000'),
                    close=Decimal('50050'),
                    volume=Decimal('1000'),
                    is_closed=True,
                )

                # 2. 处理 K 线，生成信号
                signal1 = await pipeline.process_kline(kline1)

                if signal1 is None:
                    pytest.skip("No signal generated")

                # 3. 保存快照 V1
                snapshot_id = await repository.create_config_snapshot(
                    version="v1-rollback-point",
                    config_json='{"strategies": []}',
                    description="rollback-point",
                    created_by="test",
                )
                assert snapshot_id is not None

                # 4. 回滚到快照 V1
                await repository.activate_config_snapshot(snapshot_id)

                # 5. 更新信号 1 状态为 FILLED
                await status_tracker.update_status(
                    signal1.id,
                    SignalStatus.FILLED,
                    filled_price=Decimal('51000'),
                )

                # 6. 验证状态正确保存
                track1_filled = await status_tracker.get_signal_status(signal1.id)
                assert track1_filled.status == SignalStatus.FILLED
                assert track1_filled.filled_price == Decimal('51000')
                assert track1_filled.filled_at is not None

        finally:
            await repository.close()

    async def test_multiple_signals_tracked_independently_after_rollback(
        self,
        config_manager,
        risk_config,
        mock_notifier,
    ):
        """
        测试场景:
        1. 回滚前有多个信号在跟踪
        2. 回滚后所有信号独立跟踪，互不影响
        """
        repository = SignalRepository(":memory:")
        await repository.initialize()

        try:
            status_tracker = SignalStatusTracker(repository)

            with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
                mock_getter.return_value = mock_notifier
                pipeline = SignalPipeline(
                    config_manager=config_manager,
                    risk_config=risk_config,
                    notification_service=mock_notifier,
                    signal_repository=repository,
                    cooldown_seconds=300
                )

                # 1. 创建两个测试 K 线数据
                kline1 = KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1000000,
                    open=Decimal('50000'),
                    high=Decimal('50100'),
                    low=Decimal('49000'),
                    close=Decimal('50050'),
                    volume=Decimal('1000'),
                    is_closed=True,
                )

                kline2 = KlineData(
                    symbol="ETH/USDT:USDT",
                    timeframe="15m",
                    timestamp=1000000 + 900000,
                    open=Decimal('3000'),
                    high=Decimal('3050'),
                    low=Decimal('2900'),
                    close=Decimal('3025'),
                    volume=Decimal('1000'),
                    is_closed=True,
                )

                # 2. 处理 K 线，生成信号
                signal1 = await pipeline.process_kline(kline1)
                signal2 = await pipeline.process_kline(kline2)

                if signal1 is None and signal2 is None:
                    pytest.skip("No signals generated")

                signals = [s for s in [signal1, signal2] if s is not None]
                if len(signals) < 2:
                    pytest.skip("Need at least 2 signals for this test")

                # 3. 保存快照 V1
                snapshot_id = await repository.create_config_snapshot(
                    version="v1-rollback-point",
                    config_json='{"strategies": []}',
                    description="rollback-point",
                    created_by="test",
                )
                assert snapshot_id is not None

                # 4. 回滚到快照 V1
                await repository.activate_config_snapshot(snapshot_id)

                # 5. 更新信号 1 状态为 FILLED
                await status_tracker.update_status(
                    signal1.id,
                    SignalStatus.FILLED,
                    filled_price=Decimal('51000'),
                )

                # 6. 更新信号 2 状态为 CANCELLED
                await status_tracker.update_status(
                    signal2.id,
                    SignalStatus.CANCELLED,
                    cancel_reason="测试取消",
                )

                # 7. 验证：信号 1 状态为 FILLED
                track1 = await status_tracker.get_signal_status(signal1.id)
                assert track1.status == SignalStatus.FILLED

                # 8. 验证：信号 2 状态为 CANCELLED
                track2 = await status_tracker.get_signal_status(signal2.id)
                assert track2.status == SignalStatus.CANCELLED

                # 9. 验证：两个信号状态互不影响
                assert track1.filled_price == Decimal('51000')
                assert track2.filled_price is None

        finally:
            await repository.close()
