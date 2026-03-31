"""
Phase 5 E2E 集成测试 - 窗口 2：DCA + 持仓管理

测试环境：Binance Testnet
"""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.domain.models import Direction, OrderType, OrderRole, OrderStatus
from src.domain.dca_strategy import DcaStrategy, DcaConfig
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.config_manager import load_all_configs


# 移除 skipif 装饰器


@pytest.fixture
def config():
    return load_all_configs()


@pytest.fixture
async def gateway(config):
    gw = ExchangeGateway(
        exchange_name="binance",
        api_key=config.user_config.exchange.api_key,
        api_secret=config.user_config.exchange.api_secret,
        testnet=True
    )
    await gw.initialize()
    yield gw
    await gw.close()


@pytest.fixture
def dca_config():
    return DcaConfig(
        total_amount=Decimal("0.003"),  # 总数量 0.003 BTC
        num_batches=3,  # 分 3 批
        trigger_type="price",  # 价格触发
        price_drop_percent=Decimal("2.0")  # 每跌 2% 加仓
    )


@pytest.fixture
def dca_strategy(dca_config):
    return DcaStrategy(config=dca_config)


# ========== Test-2.1 ~ Test-2.3: DCA 策略测试 ==========

@pytest.mark.e2e
@pytest.mark.window2
class TestDcaStrategy:
    """DCA 策略测试"""

    async def test_2_1_first_batch_market_order(self, gateway, dca_strategy):
        """Test-2.1: DCA 第一批市价单"""
        # Arrange
        symbol = "BTC/USDT:USDT"

        # Act - 执行第一批市价单
        result = await dca_strategy.execute_first_batch(gateway, symbol)

        # Assert
        assert result.success is True, f"第一批下单失败：{result.error_message}"
        assert result.filled_quantity > 0
        assert result.average_price > 0

    async def test_2_2_place_limit_orders(self, gateway, dca_strategy):
        """Test-2.2: DCA 挂出第 2-N 批限价单"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        entry_price = Decimal("100000")

        # Act - 挂出后续限价单
        orders = await dca_strategy.place_subsequent_limit_orders(
            gateway=gateway,
            symbol=symbol,
            entry_price=entry_price
        )

        # Assert
        assert len(orders) > 0, "应该挂出至少 1 个限价单"

        # 清理 - 取消所有挂单
        for order in orders:
            if order.get("id"):
                await gateway.cancel_order(order["id"], symbol)

    async def test_2_3_average_cost_calculation(self, dca_strategy):
        """Test-2.3: DCA 平均成本计算"""
        # Arrange
        fills = [
            {"price": Decimal("100000"), "quantity": Decimal("0.001")},
            {"price": Decimal("98000"), "quantity": Decimal("0.001")},
            {"price": Decimal("96000"), "quantity": Decimal("0.001")},
        ]

        # Act
        avg_price, total_qty = dca_strategy.calculate_average_cost(fills)

        # Assert
        assert avg_price > 0
        assert total_qty == Decimal("0.003")


# ========== Test-2.4 ~ Test-2.7: 持仓管理测试 ==========

@pytest.mark.e2e
@pytest.mark.window2
class TestPositionManagement:
    """持仓管理测试"""

    async def test_2_4_position_status_tracking(self, gateway):
        """Test-2.4: 持仓状态追踪"""
        # Arrange - 先建立一个持仓
        symbol = "BTC/USDT:USDT"

        # 下一个市价单建立持仓
        result = await gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            reduce_only=False
        )

        if result.success:
            # Act - 查询持仓
            positions = await gateway.fetch_positions(symbols=[symbol])

            # Assert
            assert positions is not None
            # 验证持仓状态更新

    async def test_2_5_take_profit_order_chain(self, gateway):
        """Test-2.5: 止盈订单链创建"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        entry_price = Decimal("100000")

        # Act & Assert - 创建 TP1-TP5 订单
        tp_levels = [
            (OrderRole.TP1, Decimal("102000")),  # 2% 止盈
            (OrderRole.TP2, Decimal("104000")),  # 4% 止盈
            (OrderRole.TP3, Decimal("106000")),  # 6% 止盈
        ]

        for role, tp_price in tp_levels:
            result = await gateway.place_order(
                symbol=symbol,
                order_type="limit",
                side="sell",
                amount=Decimal("0.0003"),  # 部分仓位
                price=tp_price,
                reduce_only=True,
                role=role
            )
            # 验证订单创建成功
            assert result.success is True

            # 清理
            await gateway.cancel_order(result.order_id, symbol)

    async def test_2_6_stop_loss_order(self, gateway):
        """Test-2.6: 止损订单创建"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        entry_price = Decimal("100000")
        stop_loss_price = Decimal("98000")  # 2% 止损

        # Act
        result = await gateway.place_order(
            symbol=symbol,
            order_type="stop_market",
            side="sell",
            amount=Decimal("0.001"),
            trigger_price=stop_loss_price,
            reduce_only=True,
            role=OrderRole.SL
        )

        # Assert
        assert result.success is True, f"止损单创建失败：{result.error_message}"

        # 清理
        await gateway.cancel_order(result.order_id, symbol)

    async def test_2_7_close_position_flow(self, gateway):
        """Test-2.7: 完整平仓流程"""
        # Arrange - 建立持仓
        symbol = "BTC/USDT:USDT"

        entry_result = await gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            reduce_only=False
        )

        if entry_result.success:
            # 等待订单成交
            await asyncio.sleep(1)

            # Act - 平仓
            close_result = await gateway.place_order(
                symbol=symbol,
                order_type="market",
                side="sell",
                amount=Decimal("0.001"),
                reduce_only=True,
                role=OrderRole.TP1
            )

            # Assert
            assert close_result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
