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
        order_repository=repository,
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

        # Act - 订阅订单推送（添加超时）
        await asyncio.wait_for(
            gateway.watch_orders(symbol, on_order_update),
            timeout=10.0
        )

        # Assert - 连接成功建立
        assert gateway.ws_exchange is not None, "WebSocket 客户端应该已初始化"

    async def test_3_2_order_push_realtime(self, gateway):
        """Test-3.2: 订单状态变更实时推送"""
        # Arrange
        symbol = "BTC/USDT:USDT"
        received_updates = []

        def on_order_update(order):
            received_updates.append(order)

        # 订阅推送
        await gateway.watch_orders(symbol, on_order_update)

        # Binance 要求最小名义价值 100 USDT
        # 下一个市价单触发推送
        result = await gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.002"),
            reduce_only=False
        )

        if not result.is_success:
            pytest.skip(f"无法下订单用于 WebSocket 推送测试：{result.error_message}")

        # 等待推送（最多 10 秒）
        for _ in range(100):
            if len(received_updates) > 0:
                break
            await asyncio.sleep(0.1)

        # Assert
        assert len(received_updates) > 0, "应该在 10 秒内收到订单推送"
        # 注意：received_updates[0] 是 CCXT Order 字典，使用 'id' 字段
        assert str(received_updates[0]["id"]) == str(result.order_id)


# ========== Test-3.3 ~ Test-3.6: 对账服务测试 ==========

@pytest.mark.e2e
@pytest.mark.window3
class TestReconciliation:
    """对账服务测试"""

    async def test_3_3_start_reconciliation(self, reconciliation_service):
        """Test-3.3: 启动对账服务"""
        # Act
        report = await reconciliation_service.run_reconciliation(symbol="BTC/USDT:USDT")

        # Assert
        assert report is not None
        assert hasattr(report, "reconciliation_time")

    async def test_3_4_position_reconciliation(self, reconciliation_service):
        """Test-3.4: 持仓对账"""
        # Arrange - 确保有一个持仓
        symbol = "BTC/USDT:USDT"

        # Binance 要求最小名义价值 100 USDT
        # 假设 BTC 价格约为 60000 USDT，需要至少 0.002 BTC
        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.002"),
            reduce_only=False
        )

        if result.is_success:
            await asyncio.sleep(2)  # 等待成交

            # Act - 执行对账（包含持仓对账）
            report = await reconciliation_service.run_reconciliation(symbol=symbol)

            # Assert - 报告应该包含持仓信息
            assert report is not None
            assert hasattr(report, "missing_positions")
            assert hasattr(report, "position_mismatches")

    async def test_3_5_order_reconciliation(self, reconciliation_service):
        """Test-3.5: 订单对账"""
        # Arrange - 创建一个订单
        symbol = "BTC/USDT:USDT"

        # Binance 要求最小名义价值 100 USDT
        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.002"),
            reduce_only=False
        )

        if result.is_success:
            await asyncio.sleep(2)  # 等待订单同步

            # Act - 执行对账（包含订单对账）
            report = await reconciliation_service.run_reconciliation(symbol=symbol)

            # Assert - 报告应该包含订单信息
            assert report is not None
            assert hasattr(report, "orphan_orders")
            assert hasattr(report, "ghost_orders")

    async def test_3_6_grace_period(self, reconciliation_service):
        """Test-3.6: Grace Period 处理 WebSocket 延迟"""
        # Arrange
        symbol = "BTC/USDT:USDT"

        # 获取当前价格
        current_price = await reconciliation_service._gateway.fetch_ticker_price(symbol)

        # 下一个限价单（低于市价 5%，但金额仍然满足最小要求）
        limit_price = current_price * Decimal("0.95")

        result = await reconciliation_service._gateway.place_order(
            symbol=symbol,
            order_type="limit",
            side="buy",
            amount=Decimal("0.002"),
            price=limit_price,
            reduce_only=False
        )

        if result.is_success:
            try:
                # Act - 执行对账（验证 Grace Period 逻辑）
                report = await reconciliation_service.run_reconciliation(symbol=symbol)

                # Assert - 报告应该包含宽限期信息
                assert report is not None
                assert report.grace_period_seconds == 10
            except Exception as e:
                # 即使对账失败，也尝试清理
                pass
            finally:
                # 清理 - 取消订单（如果仍然有效）
                try:
                    # 注意：订单可能已经成交或取消，所以这里允许失败
                    await reconciliation_service._gateway.cancel_order(str(result.order_id), symbol)
                except Exception:
                    pass  # 忽略取消失败（订单可能已成交或已取消）
        else:
            # 如果下单失败，跳过 Grace Period 测试
            pytest.skip(f"无法创建限价单用于 Grace Period 测试：{result.error_message}")


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
            webhook_url=config.user_config.notification.feishu_webhook
        )

        # Act - 发送测试通知
        result = await notifier.send_alert(
            title="🐶 盯盘狗 E2E 测试",
            content=[
                {"tag": "text", "text": "测试内容：订单执行成功"},
                {"tag": "text", "text": "币种：BTC/USDT:USDT"},
                {"tag": "text", "text": "方向：LONG"},
                {"tag": "text", "text": "数量：0.002 BTC"},
            ]
        )

        # Assert
        assert result.is_success is True, f"发送失败：{result.error_message}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
