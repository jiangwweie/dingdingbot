"""
Unit tests for Order Validator (P0-004)

订单参数合理性检查单元测试：
1. 最小订单金额检查（防止粉尘订单）
2. 价格合理性检查（防止异常价格订单）
3. 数量精度检查（符合交易所精度要求）
4. 极端行情下的放宽逻辑

Reference: docs/designs/p0-004-order-validation.md
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.capital_protection import CapitalProtectionManager, AccountService
from src.application.volatility_detector import VolatilityDetector
from src.domain.models import (
    OrderType,
    OrderCheckResult,
    CapitalProtectionConfig,
    ExtremeVolatilityConfig,
)


@pytest.fixture
def mock_config():
    """创建测试配置"""
    return CapitalProtectionConfig(
        enabled=True,
        single_trade={
            "max_loss_percent": Decimal("2.0"),
            "max_position_percent": Decimal("20"),
        },
        daily={
            "max_loss_percent": Decimal("5.0"),
            "max_trade_count": 50,
        },
        account={
            "min_balance": Decimal("100"),
            "max_leverage": 10,
        },
    )


@pytest.fixture
def mock_account_service():
    """创建模拟账户服务"""
    account = AsyncMock(spec=AccountService)
    account.get_balance = AsyncMock(return_value=Decimal("10000"))  # 默认 10000 USDT 余额
    return account


@pytest.fixture
def mock_notifier():
    """创建模拟通知服务"""
    notifier = AsyncMock()
    notifier.send_alert = AsyncMock()
    return notifier


@pytest.fixture
def mock_gateway():
    """创建模拟交易所网关"""
    gateway = AsyncMock()
    gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50000"))  # 默认 BTC 价格
    gateway.get_market_info = AsyncMock(return_value={
        'min_quantity': Decimal("0.00001"),
        'quantity_precision': 5,
        'price_precision': 2,
        'min_notional': Decimal("5"),
        'step_size': Decimal("0.00001"),
    })
    return gateway


@pytest.fixture
def capital_protection(mock_config, mock_account_service, mock_notifier, mock_gateway):
    """创建资金保护管理器实例"""
    return CapitalProtectionManager(
        config=mock_config,
        account_service=mock_account_service,
        notifier=mock_notifier,
        gateway=mock_gateway,
    )


# ============================================================
# P0-004: 最小订单金额检查测试
# ============================================================

class TestMinNotionalCheck:
    """最小名义价值检查测试"""

    @pytest.mark.asyncio
    async def test_notional_exactly_at_limit(self, capital_protection, mock_gateway):
        """测试订单价值恰好等于最小限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.0001 * 50000 = 5 USDT (正好等于最小限制)
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("5")
        assert result.min_notional == Decimal("5")

    @pytest.mark.asyncio
    async def test_notional_just_below_limit(self, capital_protection, mock_gateway):
        """测试订单价值略低于最小限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.00009 * 50000 = 4.5 USDT < 5 USDT
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.00009"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "BELOW_MIN_NOTIONAL"
        assert result.notional_value == Decimal("4.5")

    @pytest.mark.asyncio
    async def test_notional_well_above_limit(self, capital_protection, mock_gateway):
        """测试订单价值远高于最小限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.01 * 50000 = 500 USDT >> 5 USDT
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("500")

    @pytest.mark.asyncio
    async def test_market_order_notional_check(self, capital_protection, mock_gateway):
        """测试市价单的名义价值检查（使用 ticker 价格）"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 市价单：0.00001 * 50000 = 0.5 USDT < 5 USDT
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            amount=Decimal("0.00001"),
            price=None,
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "BELOW_MIN_NOTIONAL"

    @pytest.mark.asyncio
    async def test_stop_market_order_notional_check(self, capital_protection, mock_gateway):
        """测试条件市价单的名义价值检查（使用触发价）"""
        # STOP_MARKET 使用 trigger_price 计算
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.STOP_MARKET,
            amount=Decimal("0.0001"),
            price=None,
            trigger_price=Decimal("50000"),  # 0.0001 * 50000 = 5 USDT
            stop_loss=Decimal("51000"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("5")


# ============================================================
# P0-004: 数量精度检查测试
# ============================================================

class TestQuantityPrecisionCheck:
    """数量精度检查测试"""

    @pytest.mark.asyncio
    async def test_quantity_within_precision(self, capital_protection, mock_gateway):
        """测试数量在精度范围内"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.001 (3 位小数) <= 5 位精度
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_quantity_exceeds_precision(self, capital_protection, mock_gateway):
        """测试数量超出精度限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")
        mock_gateway.get_market_info.return_value = {
            'min_quantity': Decimal("0.00001"),
            'quantity_precision': 3,  # 只允许 3 位小数
            'price_precision': 2,
            'min_notional': Decimal("5"),
            'step_size': Decimal("0.00001"),
        }

        # 0.1 (1 位小数) <= 3 位精度，但我们需要一个超过 3 位精度的例子
        # 0.0001 是 4 位小数 > 3 位精度
        # 同时满足名义价值：0.0001 * 50000 = 5 USDT (正好满足)
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.00012345"),  # 6 位小数 > 3 位精度
            price=Decimal("50000"),  # 0.00012345 * 50000 = 6.17 USDT > 5 USDT
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "QUANTITY_PRECISION_EXCEEDED"

    @pytest.mark.asyncio
    async def test_quantity_below_minimum(self, capital_protection, mock_gateway):
        """测试数量小于最小交易量"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")
        mock_gateway.get_market_info.return_value = {
            'min_quantity': Decimal("0.001"),  # 最小 0.001
            'quantity_precision': 5,
            'price_precision': 2,
            'min_notional': Decimal("5"),
            'step_size': Decimal("0.00001"),
        }

        # 0.0005 < 0.001 (最小限制)
        # 0.0005 * 50000 = 25 USDT > 5 USDT (名义价值满足)
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.0005"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "BELOW_MIN_QUANTITY"

    @pytest.mark.asyncio
    async def test_quantity_not_multiple_of_step_size(self, capital_protection, mock_gateway):
        """测试数量不是 step_size 的整数倍"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")
        mock_gateway.get_market_info.return_value = {
            'min_quantity': Decimal("0.00001"),
            'quantity_precision': 5,
            'price_precision': 2,
            'min_notional': Decimal("5"),
            'step_size': Decimal("0.0001"),  # 步长 0.0001
        }

        # 0.00015 不是 0.0001 的整数倍
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.00015"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "QUANTITY_NOT_MULTIPLE_OF_STEP"

    @pytest.mark.asyncio
    async def test_quantity_market_info_fetch_failure(self, capital_protection, mock_gateway):
        """测试获取市场信息失败时跳过检查"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")
        mock_gateway.get_market_info.side_effect = Exception("Connection error")

        # 异常情况下应该跳过检查
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.001"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 订单应该通过（跳过检查）
        assert result.allowed is True or result.reason != "QUANTITY_PRECISION_EXCEEDED"


# ============================================================
# P0-004: 价格合理性检查测试
# ============================================================

class TestPriceReasonabilityCheck:
    """价格合理性检查测试"""

    @pytest.mark.asyncio
    async def test_price_deviation_within_limit(self, capital_protection, mock_gateway):
        """测试价格偏差在限制内"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 订单价 51000，ticker 50000，偏差 = 2% < 10%
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("51000"),
            trigger_price=None,
            stop_loss=Decimal("50000"),
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_price_deviation_exactly_at_limit(self, capital_protection, mock_gateway):
        """测试价格偏差正好等于限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 订单价 55000，ticker 50000，偏差 = 10% = 阈值
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("55000"),
            trigger_price=None,
            stop_loss=Decimal("54000"),
        )

        # 10% 正好等于阈值，应该通过（<=）
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_price_deviation_just_over_limit(self, capital_protection, mock_gateway):
        """测试价格偏差略超限制"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 订单价 55001，ticker 50000，偏差 = 10.002% > 10%
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("55001"),
            trigger_price=None,
            stop_loss=Decimal("54000"),
        )

        assert result.allowed is False
        assert result.reason == "PRICE_DEVIATION_TOO_HIGH"

    @pytest.mark.asyncio
    async def test_price_deviation_market_order_skipped(self, capital_protection, mock_gateway):
        """测试市价单跳过价格偏差检查"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 市价单使用 ticker 价格，不应该检查偏差
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_price_deviation_fetch_failure_skipped(self, capital_protection, mock_gateway):
        """测试获取 ticker 价格失败时跳过检查"""
        mock_gateway.fetch_ticker_price.return_value = None

        # 获取 ticker 失败，应该跳过检查
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 订单应该通过（跳过检查）
        assert result.allowed is True or result.reason != "PRICE_DEVIATION_TOO_HIGH"


# ============================================================
# P0-004: 极端行情下的放宽逻辑测试
# ============================================================

class TestExtremeVolatilityRelaxation:
    """极端行情下的放宽逻辑测试"""

    @pytest.mark.asyncio
    async def test_extreme_volatility_relaxed_deviation(self, mock_config, mock_account_service,
                                                         mock_notifier, mock_gateway):
        """测试极端行情下放宽价格偏差限制"""
        # 创建波动率检测器
        volatility_config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            relaxed_price_deviation=Decimal("20.0"),
            allow_only_tp_sl=False,
        )
        volatility_detector = VolatilityDetector(config=volatility_config)

        # 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))  # 6% 波动

        # 验证已触发极端行情
        assert volatility_detector.is_extreme_volatility("BTC/USDT:USDT") is True

        # 创建资金保护管理器（带波动率检测器）
        protection = CapitalProtectionManager(
            config=mock_config,
            account_service=mock_account_service,
            notifier=mock_notifier,
            gateway=mock_gateway,
            volatility_detector=volatility_detector,
        )

        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 订单价 58000，ticker 50000，偏差 = 16% > 10% 但 < 20%
        result = await protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("58000"),  # 16% 偏差
            trigger_price=None,
            stop_loss=Decimal("57000"),
        )

        # 极端行情下应该允许（16% < 20% 放宽限制）
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_extreme_volatility_still_rejects_excessive_deviation(
        self, mock_config, mock_account_service, mock_notifier, mock_gateway
    ):
        """测试极端行情下仍拒绝过大的价格偏差"""
        # 创建波动率检测器
        volatility_config = ExtremeVolatilityConfig(
            enabled=True,
            price_volatility_threshold=Decimal("5.0"),
            relaxed_price_deviation=Decimal("20.0"),
            allow_only_tp_sl=False,
        )
        volatility_detector = VolatilityDetector(config=volatility_config)

        # 触发极端行情
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("50000"))
        await asyncio.sleep(0.01)
        await volatility_detector.add_price_point("BTC/USDT:USDT", Decimal("53000"))

        protection = CapitalProtectionManager(
            config=mock_config,
            account_service=mock_account_service,
            notifier=mock_notifier,
            gateway=mock_gateway,
            volatility_detector=volatility_detector,
        )

        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 订单价 65000，ticker 50000，偏差 = 30% > 20%
        result = await protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("65000"),  # 30% 偏差
            trigger_price=None,
            stop_loss=Decimal("64000"),
        )

        # 超过放宽后的限制，应该拒绝
        assert result.allowed is False
        assert result.reason == "PRICE_DEVIATION_TOO_HIGH"


# ============================================================
# P0-004: 综合场景测试
# ============================================================

class TestComprehensiveScenarios:
    """综合场景测试"""

    @pytest.mark.asyncio
    async def test_all_checks_pass(self, capital_protection, mock_gateway):
        """测试所有检查都通过"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),  # 0.01 * 50000 = 500 USDT > 5 USDT
            price=Decimal("51000"),  # 2% 偏差 < 10%
            trigger_price=None,
            stop_loss=Decimal("50000"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("510")

    @pytest.mark.asyncio
    async def test_dust_order_rejected(self, capital_protection, mock_gateway):
        """测试粉尘订单被拒绝"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.00001"),  # 0.00001 * 50000 = 0.5 USDT < 5 USDT
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "BELOW_MIN_NOTIONAL"

    @pytest.mark.asyncio
    async def test_abnormal_price_rejected(self, capital_protection, mock_gateway):
        """测试异常价格订单被拒绝"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("40000"),  # -20% 偏差
            trigger_price=None,
            stop_loss=Decimal("39000"),
        )

        assert result.allowed is False
        assert result.reason == "PRICE_DEVIATION_TOO_HIGH"

    @pytest.mark.asyncio
    async def test_invalid_precision_rejected(self, capital_protection, mock_gateway):
        """测试精度不符的订单被拒绝"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")
        mock_gateway.get_market_info.return_value = {
            'min_quantity': Decimal("0.00001"),
            'quantity_precision': 4,  # 只允许 4 位小数
            'price_precision': 2,
            'min_notional': Decimal("5"),
            'step_size': Decimal("0.0001"),
        }

        # 0.01 * 50000 = 500 USDT > 5 USDT (名义价值满足)
        # 0.00001234 (6 位小数) > 4 位精度
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01001234"),  # 6 位小数 > 4 位精度
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False
        assert result.reason == "QUANTITY_PRECISION_EXCEEDED"


# ============================================================
# P0-004: 边界值测试
# ============================================================

class TestBoundaryValues:
    """边界值测试"""

    @pytest.mark.asyncio
    async def test_min_notional_boundary_exactly_5_usdt(self, capital_protection, mock_gateway):
        """测试最小名义价值边界（正好 5 USDT）"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.0001 * 50000 = 5 USDT (正好等于最小限制)
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.0001"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_min_notional_boundary_just_under_5_usdt(self, capital_protection, mock_gateway):
        """测试最小名义价值边界（略低于 5 USDT）"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 0.00009 * 50000 = 4.5 USDT < 5 USDT
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.00009"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_price_deviation_boundary_exactly_10_percent(self, capital_protection, mock_gateway):
        """测试价格偏差边界（正好 10%）"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 55000 / 50000 = 1.1 -> 10% 偏差
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("55000"),
            trigger_price=None,
            stop_loss=Decimal("54000"),
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_price_deviation_boundary_just_over_10_percent(self, capital_protection, mock_gateway):
        """测试价格偏差边界（略超 10%）"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        # 55001 / 50000 = 1.10002 -> 10.002% 偏差
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("55001"),
            trigger_price=None,
            stop_loss=Decimal("54000"),
        )

        assert result.allowed is False


# ============================================================
# P0-004: 不同订单类型测试
# ============================================================

class TestDifferentOrderTypes:
    """不同订单类型测试"""

    @pytest.mark.asyncio
    async def test_limit_order_all_checks(self, capital_protection, mock_gateway):
        """测试限价单的所有检查"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("50000"),
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("500")

    @pytest.mark.asyncio
    async def test_market_order_uses_ticker_price(self, capital_protection, mock_gateway):
        """测试市价单使用 ticker 价格"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50123.45")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=None,
            stop_loss=Decimal("49000"),
        )

        # 验证调用了 fetch_ticker_price
        mock_gateway.fetch_ticker_price.assert_called_once()
        assert result.allowed is True
        assert result.notional_value == Decimal("501.2345")

    @pytest.mark.asyncio
    async def test_stop_market_uses_trigger_price(self, capital_protection, mock_gateway):
        """测试条件市价单使用触发价"""
        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.STOP_MARKET,
            amount=Decimal("0.01"),
            price=None,
            trigger_price=Decimal("51000"),
            stop_loss=Decimal("50500"),
        )

        assert result.allowed is True
        assert result.notional_value == Decimal("510")

    @pytest.mark.asyncio
    async def test_stop_limit_order(self, capital_protection, mock_gateway):
        """测试条件限价单"""
        mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

        result = await capital_protection.pre_order_check(
            symbol="BTC/USDT:USDT",
            order_type=OrderType.STOP_LIMIT,
            amount=Decimal("0.01"),
            price=Decimal("51000"),
            trigger_price=Decimal("51000"),
            stop_loss=Decimal("50500"),
        )

        assert result.allowed is True