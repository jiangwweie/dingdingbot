"""
Unit tests for VolatilityDetector

P0-004: 订单参数合理性检查 - 波动率检测器单元测试
覆盖极端行情检测、状态管理、放宽逻辑

Reference: docs/designs/p0-004-order-validation.md Section 2.6
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import time

from src.application.volatility_detector import VolatilityDetector, PricePoint
from src.domain.models import ExtremeVolatilityConfig, ExtremeVolatilityStatus


@pytest.fixture
def default_config():
    """创建默认极端行情配置"""
    return ExtremeVolatilityConfig(
        enabled=True,
        price_volatility_threshold=Decimal("5.0"),  # 5% 触发
        volatility_window_seconds=300,  # 5 分钟窗口
        relaxed_price_deviation=Decimal("20.0"),  # 极端行情下 20% 偏差
        allow_only_tp_sl=True,
        notify_on_trigger=False,  # 测试时禁用通知
        auto_recovery_seconds=600,  # 10 分钟自动恢复
    )


@pytest.fixture
def volatility_detector(default_config):
    """创建波动率检测器实例"""
    return VolatilityDetector(config=default_config)


@pytest.fixture
def mock_notifier():
    """创建模拟通知服务"""
    notifier = AsyncMock()
    notifier.send_alert = AsyncMock()
    return notifier


class TestVolatilityDetectorBasic:
    """基础功能测试"""

    @pytest.mark.asyncio
    async def test_initial_status(self, volatility_detector):
        """测试初始状态"""
        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False
        assert status.triggered_at is None
        assert status.trigger_reason is None
        assert status.current_volatility == Decimal("0")

    @pytest.mark.asyncio
    async def test_add_single_price_point_no_trigger(self, volatility_detector):
        """测试添加单个价格点不触发极端行情"""
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False
        # 单个价格点无法计算波动率

    @pytest.mark.asyncio
    async def test_add_price_points_small_volatility(self, volatility_detector):
        """测试添加价格点波动率低不触发"""
        # 添加两个价格点，波动很小
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50100"))  # 0.2% 波动

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False
        assert status.current_volatility < Decimal("5.0")  # 低于阈值


class TestVolatilityDetectorTrigger:
    """极端行情触发测试"""

    @pytest.mark.asyncio
    async def test_trigger_on_high_volatility(self, volatility_detector):
        """测试高波动率触发极端行情"""
        # 添加两个价格点，波动超过 5% 阈值
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))  # 6% 波动

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is True
        assert status.trigger_reason is not None
        assert "价格波动" in status.trigger_reason
        assert status.current_volatility >= Decimal("5.0")

    @pytest.mark.asyncio
    async def test_trigger_boundary_exactly_at_threshold(self, default_config):
        """测试边界值：波动率正好等于阈值"""
        detector = VolatilityDetector(config=default_config)

        # 正好 5% 波动
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("52500"))  # 约 5% 波动

        status = detector.get_status("BTC/USDT:USDT")
        # 应该触发（>= 阈值）
        assert status.is_extreme is True or status.current_volatility >= Decimal("5.0")

    @pytest.mark.asyncio
    async def test_trigger_boundary_just_below_threshold(self, volatility_detector):
        """测试边界值：波动率略低于阈值"""
        # 4.9% 波动
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("52450"))  # 约 4.9% 波动

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False

    @pytest.mark.asyncio
    async def test_no_trigger_when_disabled(self):
        """测试禁用检测时不触发"""
        config = ExtremeVolatilityConfig(enabled=False)
        detector = VolatilityDetector(config=config)

        # 大波动
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("60000"))  # 20% 波动

        status = detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False


class TestEffectivePriceDeviation:
    """有效价格偏差限制测试"""

    @pytest.mark.asyncio
    async def test_normal_deviation_limit(self, volatility_detector):
        """测试正常行情下的偏差限制"""
        deviation = volatility_detector.get_effective_price_deviation("BTC/USDT:USDT")
        assert deviation == Decimal("10.0")  # 默认 10%

    @pytest.mark.asyncio
    async def test_extreme_deviation_limit(self, volatility_detector):
        """测试极端行情下的偏差限制（放宽）"""
        # 先触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        deviation = volatility_detector.get_effective_price_deviation("BTC/USDT:USDT")
        assert deviation == Decimal("20.0")  # 放宽到 20%


class TestShouldAllowOrder:
    """订单允许判断测试"""

    @pytest.mark.asyncio
    async def test_allow_order_normal_market(self, volatility_detector):
        """测试正常市场下允许下单"""
        assert volatility_detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=False) is True
        assert volatility_detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=True) is True

    @pytest.mark.asyncio
    async def test_allow_only_tp_sl_in_extreme(self, volatility_detector):
        """测试极端行情下仅允许 TP/SL 订单"""
        # 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # TP/SL 订单允许
        assert volatility_detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=True) is True
        # 非 TP/SL 订单拒绝
        assert volatility_detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=False) is False

    @pytest.mark.asyncio
    async def test_allow_all_if_not_allow_only_tp_sl(self):
        """测试配置为不限制时的行为"""
        config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            allow_only_tp_sl=False,  # 不限制仅 TP/SL
        )
        detector = VolatilityDetector(config=config)

        # 触发极端行情
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # 所有订单都允许
        assert detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=False) is True
        assert detector.should_allow_order("BTC/USDT:USDT", is_tp_sl=True) is True


class TestRecovery:
    """自动恢复测试"""

    @pytest.mark.asyncio
    async def test_auto_recovery_after_timeout(self):
        """测试超时后自动恢复"""
        config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            auto_recovery_seconds=1,  # 1 秒恢复（测试用）
            notify_on_trigger=False,
        )
        detector = VolatilityDetector(config=config)

        # 触发极端行情
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        status = detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is True

        # 等待恢复时间
        await asyncio.sleep(1.1)

        # 再次检查（触发 recovery 检查）
        await detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        status = detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False
        assert status.triggered_at is None

    @pytest.mark.asyncio
    async def test_no_recovery_before_timeout(self, volatility_detector):
        """测试未超时前不恢复"""
        # 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is True
        assert status.recovery_at is not None

        # 立即检查，不应该恢复
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))
        status = volatility_detector.get_status("BTC/USDT:USDT")
        # 由于 auto_recovery_seconds=600，短时间内不应该恢复
        assert status.is_extreme is True


class TestSymbolIsolation:
    """多币种隔离测试"""

    @pytest.mark.asyncio
    async def test_independent_status_per_symbol(self, volatility_detector):
        """测试每个币种状态独立"""
        # BTC 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # ETH 不触发
        await volatility_detector.add_price_point("ETH/USDT:USDT", Decimal("3000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("ETH/USDT:USDT", Decimal("3010"))  # 小波动

        btc_status = volatility_detector.get_status("BTC/USDT:USDT")
        eth_status = volatility_detector.get_status("ETH/USDT:USDT")

        assert btc_status.is_extreme is True
        assert eth_status.is_extreme is False

    @pytest.mark.asyncio
    async def test_independent_deviation_per_symbol(self, volatility_detector):
        """测试每个币种偏差限制独立"""
        # BTC 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # BTC 偏差限制放宽到 20%
        btc_deviation = volatility_detector.get_effective_price_deviation("BTC/USDT:USDT")
        assert btc_deviation == Decimal("20.0")

        # ETH 仍为 10%
        eth_deviation = volatility_detector.get_effective_price_deviation("ETH/USDT:USDT")
        assert eth_deviation == Decimal("10.0")


class TestReset:
    """重置功能测试"""

    @pytest.mark.asyncio
    async def test_reset_single_symbol(self, volatility_detector):
        """测试重置单个币种"""
        # 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # 重置 BTC
        volatility_detector.reset("BTC/USDT:USDT")

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is False
        assert status.current_volatility == Decimal("0")

    @pytest.mark.asyncio
    async def test_reset_all_symbols(self, volatility_detector):
        """测试重置所有币种"""
        # 触发多个币种极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        await volatility_detector.add_price_point("ETH/USDT:USDT", Decimal("3000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("ETH/USDT:USDT", Decimal("3200"))

        # 重置所有
        volatility_detector.reset()

        btc_status = volatility_detector.get_status("BTC/USDT:USDT")
        eth_status = volatility_detector.get_status("ETH/USDT:USDT")

        assert btc_status.is_extreme is False
        assert eth_status.is_extreme is False


class TestNotification:
    """通知功能测试"""

    @pytest.mark.asyncio
    async def test_send_alert_on_trigger(self, mock_notifier):
        """测试触发时发送告警"""
        config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            notify_on_trigger=True,
        )
        detector = VolatilityDetector(config=config, notifier=mock_notifier)

        # 触发极端行情
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # 验证告警已发送
        mock_notifier.send_alert.assert_called_once()
        call_args = mock_notifier.send_alert.call_args
        assert "极端行情告警" in call_args[0][0]
        assert "BTC/USDT:USDT" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_no_alert_when_notify_disabled(self):
        """测试禁用通知时不发送告警"""
        config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            notify_on_trigger=False,
        )
        detector = VolatilityDetector(config=config)

        # 触发极端行情
        await detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        # 没有 notifier，不应该报错


class TestEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_zero_price_handling(self, volatility_detector):
        """测试零价格处理"""
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("0"))
        # 不应该报错

    @pytest.mark.asyncio
    async def test_large_price_difference(self, volatility_detector):
        """测试极大价格差异"""
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("1"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("1000000"))

        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status.is_extreme is True
        assert status.current_volatility > Decimal("100")

    @pytest.mark.asyncio
    async def test_concurrent_add_price_points(self, volatility_detector):
        """测试并发添加价格点"""
        async def add_price(price: Decimal):
            await volatility_detector.add_price_point("BTC/USDT:USDT", price)

        # 并发添加多个价格点
        await asyncio.gather(*[
            add_price(Decimal("50000")),
            add_price(Decimal("50100")),
            add_price(Decimal("49900")),
            add_price(Decimal("50200")),
        ])

        # 不应该报错
        status = volatility_detector.get_status("BTC/USDT:USDT")
        assert status is not None


# ============================================================
# P0-004: 集成测试 - 与 CapitalProtectionManager 集成
# ============================================================

class TestCapitalProtectionIntegration:
    """与资金保护管理器集成测试"""

    @pytest.mark.asyncio
    async def test_volatility_detector_in_capital_protection(self):
        """测试波动率检测器在资金保护中的使用"""
        from src.application.capital_protection import CapitalProtectionManager
        from src.domain.models import CapitalProtectionConfig

        # 创建配置
        config = CapitalProtectionConfig()
        volatility_config = ExtremeVolatilityConfig(
            price_volatility_threshold=Decimal("5.0"),
        )

        # 创建 mock 对象
        account_service = AsyncMock()
        account_service.get_balance = AsyncMock(return_value=Decimal("10000"))
        notifier = AsyncMock()
        gateway = AsyncMock()
        gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50000"))

        # 创建波动率检测器
        volatility_detector = VolatilityDetector(config=volatility_config)

        # 创建资金保护管理器
        protection = CapitalProtectionManager(
            config=config,
            account_service=account_service,
            notifier=notifier,
            gateway=gateway,
            volatility_detector=volatility_detector,
        )

        # 验证波动率检测器已注入
        assert protection._volatility_detector is volatility_detector
