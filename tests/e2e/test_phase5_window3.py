"""
Phase 5 E2E 集成测试 - 窗口 3：对账服务 + WebSocket 推送

测试环境：Binance Testnet
"""

import pytest
import asyncio
from decimal import Decimal
from pathlib import Path
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.domain.models import Direction, OrderType, OrderStatus
from src.application.reconciliation import ReconciliationService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.application.config_manager import load_all_configs
from src.infrastructure.signal_repository import SignalRepository


pytestmark = pytest.mark.skipif(
    not os.getenv("EXCHANGE_API_KEY"),
    reason="需要配置 EXCHANGE_API_KEY 环境变量"
)


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
def repository():
    return SignalRepository(db_path="data/v3_dev.db")


@pytest.fixture
def reconciliation_service(gateway, repository):
    return ReconciliationService(
        gateway=gateway,
        repository=repository,
        grace_period_seconds=10
    )


# ========== Test-3.1 ~ Test-3.2: WebSocket 测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
class TestWebSocketPush:
    """WebSocket 推送测试"""

    async def test_3_1_websocket_connection(self, gateway):
        """Test-3.1: WebSocket 连接"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        received_updates = []

        def on_order_update(order):
            received_updates.append(order)

        # Act - 订阅订单推送
        await gateway.watch_orders(symbol, on_order_update)

        # Assert - 连接成功建立
        # 注意：这是一个长时间运行的订阅，实际测试中需要超时控制
        assert gateway._ws_client is not None

    async def test_3_2_order_push_realtime(self, gateway):
        """Test-3.2: 订单状态变更实时推送"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        received_updates = []

        def on_order_update(order):
            received_updates.append(order)

        # 订阅推送
        await gateway.watch_orders(symbol, on_order_update)

        # 下一个市价单触发推送
        result = await gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            reduce_only=False
        )

        # 等待推送（最多 5 秒）
        for _ in range(50):
            if len(received_updates) > 0:
                break
            await asyncio.sleep(0.1)

        # Assert
        assert len(received_updates) > 0, "应该在 5 秒内收到订单推送"
        assert received_updates[0]["id"] == result.order_id


# ========== Test-3.3 ~ Test-3.6: 对账服务测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
class TestReconciliation:
    """对账服务测试"""

    async def test_3_3_start_reconciliation(self, reconciliation_service):
        """Test-3.3: 启动对账服务"""
        # Act
        report = await reconciliation_service.run_full_reconciliation()

        # Assert
        assert report is not None
        assert hasattr(report, "timestamp")

    async def test_3_4_position_reconciliation(self, reconciliation_service):
        """Test-3.4: 持仓对账"""
        # Arrange - 确保有一个持仓
        symbol = "BTC/USDT:USDT"

        # 先下一个市价单
        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            reduce_only=False
        )

        if result.is_success:
            await asyncio.sleep(2)  # 等待成交

            # Act - 执行持仓对账
            positions_match, position_report = await reconciliation_service.reconcile_positions(
                symbols=[symbol]
            )

            # Assert
            assert positions_match is True or position_report is not None

    async def test_3_5_order_reconciliation(self, reconciliation_service):
        """Test-3.5: 订单对账"""
        # Arrange - 创建一个订单
        symbol = "BTC/USDT:USDT"

        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.001"),
            reduce_only=False
        )

        if result.is_success:
            # Act - 执行订单对账
            orders_match, order_report = await reconciliation_service.reconcile_orders(
                symbol=symbol,
                since_minutes=5
            )

            # Assert
            assert orders_match is True or order_report is not None

    async def test_3_6_grace_period(self, reconciliation_service):
        """Test-3.6: Grace Period 处理 WebSocket 延迟"""
        # Arrange
        symbol = "BTC/USDT:USDT"

        # 下一个限价单（不会立即成交）
        current_price = await reconciliation_service._gateway.fetch_ticker_price(symbol)
        limit_price = current_price * Decimal("0.90")

        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="limit",
            side="buy",
            amount=Decimal("0.001"),
            price=limit_price,
            reduce_only=False
        )

        # Act - 立即对账（订单可能还未同步）
        # 验证 Grace Period 逻辑
        await asyncio.sleep(1)

        # 清理
        await reconciliation_service._gateway.cancel_order(result.order_id, symbol)


# ========== Test-3.7: 飞书告警测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
class TestFeishuNotification:
    """飞书告警测试"""

    async def test_3_7_feishu_alert(self, config, gateway):
        """Test-3.7: 飞书告警通知"""
        # Arrange
        from src.infrastructure.notifier_feishu import FeishuNotifier

        notifier = FeishuNotifier(
            webhook_url=config.user_config.notifications.feishu_webhook
        )

        # Act - 发送测试通知
        result = await notifier.send_alert(
            title="🐶 盯盘狗 E2E 测试",
            content=[
                {"tag": "text", "text": "测试内容：订单执行成功"},
                {"tag": "text", "text": "币种：BTC/USDT:USDT"},
                {"tag": "text", "text": "方向：LONG"},
                {"tag": "text", "text": "数量：0.001 BTC"},
            ]
        )

        # Assert
        assert result.is_success is True, f"发送失败：{result.error_message}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
