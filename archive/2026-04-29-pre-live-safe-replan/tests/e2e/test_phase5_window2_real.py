"""
Phase 5 E2E 集成测试 - 窗口 2：DCA + 持仓管理

测试环境：Binance Testnet
"""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.domain.models import Direction, OrderType, OrderRole, OrderStatus
from src.infrastructure.exchange_gateway import ExchangeGateway


# API Key 配置（与 Window 1 一致）
API_KEY = "rmy4DPO0uydnQLRCKxql5oeqURfBlC36W7ijW0QwBjR9HxAXMEahc0KutHlHA8hI"
API_SECRET = "mP7Hk5r3D8TeryzZKxipJ6aTfOJ6qbjqO3fzeG6VJtJB9DVxE4NXgMJZYXpqMFtR"

# Binance 测试网最小名义价值：100 USDT
MIN_AMOUNT = Decimal("0.002")  # 约 132 USDT


@pytest.fixture
async def gateway():
    """创建交易所网关实例"""
    gw = ExchangeGateway(
        exchange_name="binance",
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=True
    )
    await gw.initialize()
    yield gw
    await gw.close()


# ========== Test-2.1: DCA 第一批市价单 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_1_dca_first_batch(gateway):
    """Test-2.1: DCA 第一批市价单执行"""
    symbol = "BTC/USDT:USDT"
    amount = MIN_AMOUNT

    # 执行市价单
    result = await gateway.place_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=amount,
        reduce_only=False
    )

    # 验证
    assert result.is_success is True, f"第一批下单失败：{result.error_message}"
    print(f"✅ DCA 第一批成交：exchange_id={result.exchange_order_id}")


# ========== Test-2.2: DCA 限价单挂单 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_2_dca_limit_orders(gateway):
    """Test-2.2: DCA 挂出限价单"""
    symbol = "BTC/USDT:USDT"
    amount = MIN_AMOUNT

    # 获取当前价格
    ticker = await gateway.rest_exchange.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))

    # 挂出低于市价 2% 的限价单
    limit_price = current_price * Decimal("0.98")

    result = await gateway.place_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=amount,
        price=limit_price,
        reduce_only=False
    )

    # 验证
    assert result.is_success is True, f"限价单失败：{result.error_message}"
    order_id = result.exchange_order_id
    print(f"✅ DCA 限价单已挂出：order_id={order_id}, price={limit_price}")

    # 清理：取消订单
    cancel_result = await gateway.cancel_order(order_id, symbol)
    assert cancel_result.is_success is True
    print(f"✅ 限价单已取消")


# ========== Test-2.3: 持仓状态追踪 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_3_position_tracking(gateway):
    """Test-2.3: 持仓状态追踪"""
    symbol = "BTC/USDT:USDT"

    # 建立一个多头持仓
    result = await gateway.place_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=MIN_AMOUNT,
        reduce_only=False
    )
    assert result.is_success is True

    # 等待成交
    await asyncio.sleep(0.5)

    # 查询持仓 (直接使用 CCXT)
    positions = await gateway.rest_exchange.fetch_positions(symbols=[symbol])

    # 验证
    assert positions is not None
    print(f"✅ 持仓追踪：{len(positions)} 个持仓")


# ========== Test-2.4: 止盈订单链 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_4_take_profit_orders(gateway):
    """Test-2.4: 止盈订单链创建"""
    symbol = "BTC/USDT:USDT"

    # 获取当前价格
    ticker = await gateway.rest_exchange.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))

    # 创建 TP1-TP3 止盈单
    tp_levels = [
        (OrderRole.TP1, current_price * Decimal("1.02")),  # 2% 止盈
        (OrderRole.TP2, current_price * Decimal("1.04")),  # 4% 止盈
    ]

    for role, tp_price in tp_levels:
        result = await gateway.place_order(
            symbol=symbol,
            order_type="limit",
            side="sell",
            amount=Decimal("0.0003"),
            price=tp_price,
            reduce_only=True,
        )
        # 验证订单创建成功
        assert result.is_success is True, f"{role.value}订单失败：{result.error_message}"
        print(f"✅ {role.value}订单已挂出：price={tp_price}")

        # 清理：取消订单
        await gateway.cancel_order(result.exchange_order_id, symbol)


# ========== Test-2.5: 止损订单 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_5_stop_loss_order(gateway):
    """Test-2.5: 止损订单创建"""
    symbol = "BTC/USDT:USDT"

    # 获取当前价格
    ticker = await gateway.rest_exchange.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))

    stop_loss_price = current_price * Decimal("0.98")  # 2% 止损

    result = await gateway.place_order(
        symbol=symbol,
        order_type="stop_market",
        side="sell",
        amount=MIN_AMOUNT,
        trigger_price=stop_loss_price,
        reduce_only=True,
    )

    # 验证
    assert result.is_success is True, f"止损单失败：{result.error_message}"
    print(f"✅ 止损单已挂出：trigger_price={stop_loss_price}")

    # 清理
    try:
        await gateway.cancel_order(result.exchange_order_id, symbol)
        print(f"✅ 止损单已取消")
    except Exception as e:
        print(f"⚠️  取消失败（可能已触发）：{e}")


# ========== Test-2.6: 完整平仓流程 ==========

@pytest.mark.e2e
@pytest.mark.window2
async def test_2_6_close_position_flow(gateway):
    """Test-2.6: 完整平仓流程"""
    symbol = "BTC/USDT:USDT"
    amount = MIN_AMOUNT

    # 1. 开仓
    entry_result = await gateway.place_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=amount,
        reduce_only=False
    )
    assert entry_result.is_success is True
    print(f"✅ 开仓成功")

    # 等待成交
    await asyncio.sleep(0.5)

    # 2. 平仓 (sell reduce_only)
    close_result = await gateway.place_order(
        symbol=symbol,
        order_type="market",
        side="sell",
        amount=amount,
        reduce_only=True
    )

    # 验证平仓成功
    assert close_result.is_success is True, f"平仓失败：{close_result.error_message}"
    print(f"✅ 平仓成功")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
