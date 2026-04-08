"""
Test P0-2: process_kline() 防御性检查

验证 SignalPipeline 的 process_kline() 方法正确处理未收盘 K 线
"""
import pytest
from decimal import Decimal
from src.domain.models import KlineData
from src.application.signal_pipeline import SignalPipeline


class TestP02_ProcessKlineDefense:
    """测试 process_kline() 防御性检查"""

    @pytest.fixture
    def pipeline(self):
        """创建 SignalPipeline 实例"""
        # 创建最小配置的 pipeline
        from src.application.config_manager import load_all_configs
        from src.domain.models import RiskConfig

        config_manager = load_all_configs()
        risk_config = RiskConfig(
            max_loss_percent=Decimal('0.01'),
            max_leverage=10,
            max_total_exposure=Decimal('0.8')
        )

        pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            notification_service=None,
            signal_repository=None,
            cooldown_seconds=300
        )
        return pipeline

    @pytest.mark.asyncio
    async def test_skips_unclosed_kline_with_warning(self, pipeline, caplog):
        """测试未收盘 K 线被跳过并记录警告"""
        # 构造未收盘 K 线
        unclosed_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1712500000000,
            open=Decimal('50000'),
            high=Decimal('50100'),
            low=Decimal('49900'),
            close=Decimal('50050'),
            volume=Decimal('100'),
            is_closed=False  # 🔴 未收盘
        )

        # 调用 process_kline
        await pipeline.process_kline(unclosed_kline)

        # 验证：记录了 WARNING 日志
        assert "[DEFENSE] Received unclosed K-line" in caplog.text
        assert "BTC/USDT:USDT" in caplog.text
        assert "15m" in caplog.text

        # 验证：K 线未被存储（早期返回）
        # 由于没有 repository，无法验证存储，但可以通过日志确认早期返回

    @pytest.mark.asyncio
    async def test_processes_closed_kline_normally(self, pipeline, caplog):
        """测试已收盘 K 线正常处理"""
        # 构造已收盘 K 线
        closed_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1712500000000,
            open=Decimal('50000'),
            high=Decimal('50100'),
            low=Decimal('49900'),
            close=Decimal('50050'),
            volume=Decimal('100'),
            is_closed=True  # ✅ 已收盘
        )

        # 调用 process_kline（不应触发 WARNING 日志）
        await pipeline.process_kline(closed_kline)

        # 验证：未记录 WARNING 日志
        assert "[DEFENSE]" not in caplog.text

    @pytest.mark.asyncio
    async def test_multiple_unclosed_klines_all_skipped(self, pipeline, caplog):
        """测试多次未收盘 K 线全部被跳过"""
        # 构造多个未收盘 K 线（模拟实时推送）
        for i in range(3):
            unclosed_kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1712500000000 + i * 1000,
                open=Decimal('50000'),
                high=Decimal(f'5010{i}'),
                low=Decimal('49900'),
                close=Decimal(f'5005{i}'),
                volume=Decimal('100'),
                is_closed=False
            )
            await pipeline.process_kline(unclosed_kline)

        # 验证：记录了 3 次 WARNING 日志
        warning_count = caplog.text.count("[DEFENSE] Received unclosed K-line")
        assert warning_count == 3

    @pytest.mark.asyncio
    async def test_mixed_klines_only_closed_processed(self, pipeline, caplog):
        """测试混合 K 线（未收盘 + 已收盘）只处理已收盘"""
        # 未收盘 K 线
        unclosed_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1712500000000,
            open=Decimal('50000'),
            high=Decimal('50100'),
            low=Decimal('49900'),
            close=Decimal('50050'),
            volume=Decimal('100'),
            is_closed=False
        )

        # 已收盘 K 线
        closed_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1712500900000,  # 15 分钟后（一个周期）
            open=Decimal('50050'),
            high=Decimal('50200'),
            low=Decimal('50000'),
            close=Decimal('50150'),
            volume=Decimal('120'),
            is_closed=True
        )

        # 先推送未收盘，后推送已收盘
        await pipeline.process_kline(unclosed_kline)
        await pipeline.process_kline(closed_kline)

        # 验证：只有 1 次 WARNING 日志（未收盘）
        warning_count = caplog.text.count("[DEFENSE]")
        assert warning_count == 1  # 只有未收盘触发 WARNING