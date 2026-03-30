"""
Unit tests for CapitalProtectionManager

Phase 5: 实盘集成 - 资金保护管理器单元测试
覆盖所有检查项和 G-002 市价单价格获取逻辑

Reference: docs/designs/phase5-detailed-design.md Section 3.4
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.application.capital_protection import CapitalProtectionManager, AccountService
from src.domain.models import (
    OrderType,
    OrderCheckResult,
    DailyTradeStats,
    CapitalProtectionConfig,
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


@pytest.mark.asyncio
async def test_single_trade_loss_check_pass(capital_protection, mock_gateway):
    """测试单笔损失检查通过场景"""
    # 场景：损失 1% < 限制 2%
    # 仓位：0.01 BTC * 50000 = 500 USDT
    # 损失：0.01 * (50000 - 49500) = 5 USDT
    # 限制：10000 * 2% = 200 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,  # 市价单
        trigger_price=None,
        stop_loss=Decimal("49500"),
    )

    assert result.allowed is True
    assert result.single_trade_check is True
    assert result.estimated_loss == Decimal("5")
    assert result.max_allowed_loss == Decimal("200")


@pytest.mark.asyncio
async def test_single_trade_loss_check_fail(capital_protection, mock_notifier, mock_gateway):
    """测试单笔损失检查失败场景"""
    # 场景：损失 3% > 限制 2%
    # 仓位：0.1 BTC * 50000 = 5000 USDT
    # 损失：0.1 * (50000 - 47000) = 300 USDT
    # 限制：10000 * 2% = 200 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("47000"),
    )

    assert result.allowed is False
    assert result.reason == "SINGLE_TRADE_LOSS_LIMIT"
    assert result.single_trade_check is False
    assert result.estimated_loss == Decimal("300")
    assert result.max_allowed_loss == Decimal("200")

    # 验证告警已发送
    mock_notifier.send_alert.assert_called_once()


@pytest.mark.asyncio
async def test_position_limit_check_pass(capital_protection, mock_gateway):
    """测试仓位限制检查通过场景"""
    # 场景：仓位 10% < 限制 20%
    # 仓位：0.02 BTC * 50000 = 1000 USDT
    # 限制：10000 * 20% = 2000 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.02"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is True
    assert result.position_limit_check is True
    assert result.position_value == Decimal("1000")
    assert result.max_allowed_position == Decimal("2000")


@pytest.mark.asyncio
async def test_position_limit_check_fail(capital_protection, mock_gateway):
    """测试仓位限制检查失败场景"""
    # 场景：仓位 30% > 限制 20%
    # 仓位：0.1 BTC * 50000 = 5000 USDT
    # 限制：10000 * 20% = 2000 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.1"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49500"),
    )

    assert result.allowed is False
    assert result.reason == "POSITION_LIMIT"
    assert result.position_limit_check is False
    assert result.position_value == Decimal("5000")
    assert result.max_allowed_position == Decimal("2000")


@pytest.mark.asyncio
async def test_daily_loss_limit_check_pass(capital_protection, mock_gateway):
    """测试每日亏损检查通过场景"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 先记录一些亏损（但未超限）
    # 限制：10000 * 5% = 500 USDT
    capital_protection.record_trade(Decimal("-300"))  # 亏损 300 USDT

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is True
    assert result.daily_loss_check is True
    assert result.daily_pnl == Decimal("-300")


@pytest.mark.asyncio
async def test_daily_loss_limit_check_fail(capital_protection, mock_gateway):
    """测试每日亏损检查失败场景"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 记录亏损超限
    # 限制：10000 * 5% = 500 USDT
    capital_protection.record_trade(Decimal("-600"))  # 亏损 600 USDT > 500 USDT

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is False
    assert result.reason == "DAILY_LOSS_LIMIT"
    assert result.daily_loss_check is False
    assert result.daily_pnl == Decimal("-600")


@pytest.mark.asyncio
async def test_daily_trade_count_limit_check_pass(capital_protection, mock_gateway):
    """测试每日交易次数检查通过场景"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 记录 49 次交易（未超限）
    for _ in range(49):
        capital_protection.record_trade(Decimal("10"))

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is True
    assert result.daily_count_check is True
    assert result.daily_trade_count == 49


@pytest.mark.asyncio
async def test_daily_trade_count_limit_check_fail(capital_protection, mock_gateway):
    """测试每日交易次数检查失败场景"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 记录 50 次交易（超限）
    for _ in range(50):
        capital_protection.record_trade(Decimal("10"))

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is False
    assert result.reason == "DAILY_TRADE_COUNT_LIMIT"
    assert result.daily_count_check is False
    assert result.daily_trade_count == 50


@pytest.mark.asyncio
async def test_min_balance_check_pass(capital_protection, mock_account_service, mock_gateway):
    """测试最低余额检查通过场景"""
    mock_account_service.get_balance.return_value = Decimal("500")  # 500 USDT > 100 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.001"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is True
    assert result.balance_check is True
    assert result.available_balance == Decimal("500")
    assert result.min_required_balance == Decimal("100")


@pytest.mark.asyncio
async def test_min_balance_check_fail(capital_protection, mock_account_service, mock_gateway):
    """测试最低余额检查失败场景"""
    mock_account_service.get_balance.return_value = Decimal("50")  # 50 USDT < 100 USDT
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 使用极小仓位，避免先触发仓位限制
    # 0.0001 BTC * 50000 = 5 USDT < 50 * 20% = 10 USDT
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.0001"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),  # 损失：0.0001 * 1000 = 0.1 USDT < 50 * 2% = 1 USDT
    )

    assert result.allowed is False
    assert result.reason == "INSUFFICIENT_BALANCE"
    assert result.balance_check is False
    assert result.available_balance == Decimal("50")
    assert result.min_required_balance == Decimal("100")


# ============================================================
# G-002 修复：市价单价格获取逻辑测试
# ============================================================

@pytest.mark.asyncio
async def test_g002_market_order_price_fetch_success(capital_protection, mock_gateway):
    """G-002 测试：市价单成功获取盘口价格"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50123.45")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,  # 市价单无价格
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    # 验证调用了 fetch_ticker_price
    mock_gateway.fetch_ticker_price.assert_called_once_with("BTC/USDT:USDT")
    assert result.allowed is True
    # 验证使用了获取的价格计算仓位价值
    assert result.position_value == Decimal("501.2345")


@pytest.mark.asyncio
async def test_g002_market_order_price_fetch_failure(capital_protection, mock_gateway):
    """G-002 测试：市价单无法获取盘口价格"""
    mock_gateway.fetch_ticker_price.return_value = None

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,  # 市价单无价格
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is False
    assert result.reason == "CANNOT_ESTIMATE_MARKET_PRICE"


@pytest.mark.asyncio
async def test_g002_stop_market_order_uses_trigger_price(capital_protection, mock_gateway):
    """G-002 测试：条件市价单使用触发价作为预估"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")  # 不应该被调用

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.STOP_MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=Decimal("51000"),  # 触发价
        stop_loss=Decimal("50500"),
    )

    # 验证没有调用 fetch_ticker_price（因为使用了 trigger_price）
    mock_gateway.fetch_ticker_price.assert_not_called()
    assert result.allowed is True
    # 验证使用触发价计算
    assert result.position_value == Decimal("510")


@pytest.mark.asyncio
async def test_g002_stop_market_order_missing_trigger_price(capital_protection):
    """G-002 测试：条件市价单缺少触发价"""
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.STOP_MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,  # 缺少触发价
        stop_loss=Decimal("50500"),
    )

    assert result.allowed is False
    assert result.reason == "MISSING_TRIGGER_PRICE"


@pytest.mark.asyncio
async def test_g002_limit_order_missing_price(capital_protection):
    """G-002 测试：限价单缺少价格"""
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.LIMIT,
        amount=Decimal("0.01"),
        price=None,  # 限价单必须有价格
        trigger_price=None,
        stop_loss=Decimal("50500"),
    )

    assert result.allowed is False
    assert result.reason == "MISSING_PRICE"


@pytest.mark.asyncio
async def test_g002_limit_order_with_price(capital_protection, mock_gateway):
    """G-002 测试：限价单有价格"""
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.LIMIT,
        amount=Decimal("0.01"),
        price=Decimal("50000"),  # 限价单价格
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    # 限价单不应该调用 fetch_ticker_price
    mock_gateway.fetch_ticker_price.assert_not_called()
    assert result.allowed is True
    assert result.position_value == Decimal("500")


# ============================================================
# 每日统计重置测试
# ============================================================

@pytest.mark.asyncio
async def test_reset_if_new_day(capital_protection):
    """测试每日统计重置"""
    # 先记录一些交易
    capital_protection.record_trade(Decimal("100"))
    stats_before = capital_protection.get_daily_stats()
    assert stats_before.trade_count == 1
    assert stats_before.realized_pnl == Decimal("100")

    # 模拟跨天（修改 last_reset_date 为昨天）
    from datetime import timedelta
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    capital_protection._daily_stats.last_reset_date = yesterday

    # 触发重置
    capital_protection.reset_if_new_day()

    # 验证已重置
    stats_after = capital_protection.get_daily_stats()
    assert stats_after.trade_count == 0
    assert stats_after.realized_pnl == Decimal("0")
    assert stats_after.last_reset_date == datetime.now(timezone.utc).date().isoformat()


@pytest.mark.asyncio
async def test_no_reset_if_same_day(capital_protection):
    """测试同一天内不重置"""
    # 先记录一些交易
    capital_protection.record_trade(Decimal("100"))
    stats_before = capital_protection.get_daily_stats()

    # 触发重置（但还在同一天）
    capital_protection.reset_if_new_day()

    # 验证没有变化
    stats_after = capital_protection.get_daily_stats()
    assert stats_after.trade_count == stats_before.trade_count
    assert stats_after.realized_pnl == stats_before.realized_pnl


# ============================================================
# 综合场景测试
# ============================================================

@pytest.mark.asyncio
async def test_all_checks_comprehensive_pass(capital_protection, mock_gateway):
    """综合测试：所有检查都通过"""
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 小仓位，止损合理
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),  # 0.01 BTC = 500 USDT (5% of balance)
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49500"),  # 1% loss
    )

    assert result.allowed is True
    assert result.single_trade_check is True
    assert result.position_limit_check is True
    assert result.daily_loss_check is True
    assert result.daily_count_check is True
    assert result.balance_check is True


@pytest.mark.asyncio
async def test_all_checks_comprehensive_failure(capital_protection, mock_account_service, mock_gateway):
    """综合测试：多项检查失败"""
    mock_account_service.get_balance.return_value = Decimal("50")  # 低于最低余额
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    # 大额仓位，止损宽松
    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("1"),  # 1 BTC = 50000 USDT (远超 20% 限制)
        price=None,
        trigger_price=None,
        stop_loss=Decimal("40000"),  # 20% loss (远超 2% 限制)
    )

    # 应该首先失败于单笔损失检查
    assert result.allowed is False
    assert result.single_trade_check is False


@pytest.mark.asyncio
async def test_get_balance_error(capital_protection, mock_account_service, mock_gateway):
    """测试获取余额失败场景"""
    mock_account_service.get_balance.side_effect = Exception("Connection error")
    mock_gateway.fetch_ticker_price.return_value = Decimal("50000")

    result = await capital_protection.pre_order_check(
        symbol="BTC/USDT:USDT",
        order_type=OrderType.MARKET,
        amount=Decimal("0.01"),
        price=None,
        trigger_price=None,
        stop_loss=Decimal("49000"),
    )

    assert result.allowed is False
    assert result.reason == "CANNOT_GET_BALANCE"
